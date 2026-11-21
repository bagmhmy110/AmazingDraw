#!/usr/bin/env python3
"""图片放大 API：用 SeedVR2 工作流把已完成卡片转高清。

链路：
  1. 取卡片的 render_image（归档盘里的 PNG）
  2. 复制到 ComfyUI 的 output/ —— LoadImageOutput 只能读 output 目录
  3. 用 SeedVR2 工作流提交到 ComfyUI（/prompt）
  4. 轮询 /history 拿结果
  5. 把放大后的图复制回归档盘，命名 <原名>-高清.png
  6. 回写卡片 render_image（保留原图路径到 upscale_from）

工作流：J:/work buddy/workflows/▶▷SeedVR2放大工作流API.json
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["upscale"])

# 默认放大工作流（含特殊字符 ▶▷，用常量避免转义问题）
DEFAULT_WORKFLOW = "J:\\work buddy\\workflows\\\u25b6\u25b7SeedVR2放大工作流API.json"

# ── 配置读取 ──────────────────────────────────────────────────────────


def _config() -> Dict[str, Any]:
    try:
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import amazingdraw_paths  # type: ignore

        return json.loads(Path(amazingdraw_paths.config_file()).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _comfy_base(cfg: Dict[str, Any]) -> str:
    """拼 ComfyUI 地址。配置里可能已经是完整 URL，也可能只是 host。"""
    raw = str(cfg.get("comfyui_url") or "").strip()
    if raw:
        return raw.rstrip("/")
    host = str(cfg.get("comfyui_host") or "127.0.0.1").strip()
    # host 里可能已经带 http://
    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/")
    port = cfg.get("comfyui_port") or 8188
    return f"http://{host}:{port}"


def _comfy_output_dir(cfg: Dict[str, Any]) -> Path:
    comfy = str(cfg.get("comfyui_dir") or "~/ComfyUI")
    return Path(comfy) / "output"


def _comfy_input_dir(cfg: Dict[str, Any]) -> Path:
    """LoadImage 读的是 input/ 目录。"""
    comfy = str(cfg.get("comfyui_dir") or "~/ComfyUI")
    return Path(comfy) / "input"


def _archive_dir(cfg: Dict[str, Any]) -> Path:
    return Path(str(cfg.get("output_dir_archive") or cfg.get("output_dir") or ""))


def _workflow_path(cfg: Dict[str, Any]) -> Path:
    """优先用配置里的 upscale_workflow，回退到默认路径。"""
    cand = str(cfg.get("upscale_workflow") or "").strip()
    if cand and Path(cand).is_file():
        return Path(cand)
    return Path(DEFAULT_WORKFLOW)


# ── ComfyUI 交互 ──────────────────────────────────────────────────────


def _http_json(url: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 30.0):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw.strip() else {}


def _comfy_alive(base: str) -> bool:
    try:
        _http_json(f"{base}/system_stats", timeout=5)
        return True
    except Exception:
        return False


def _upload_to_output(src: Path, out_dir: Path) -> str:
    """把图片复制进 ComfyUI input 目录，返回文件名。

    LoadImage 只认 input/ 里的文件，所以必须先落地。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"upscale-src-{uuid.uuid4().hex[:10]}{src.suffix or '.png'}"
    dst = out_dir / name
    shutil.copy2(src, dst)
    return name


def _build_prompt(
    wf: Dict[str, Any],
    image_name: str,
    *,
    multiplier: float = 2.0,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """在原始工作流上替换输入图、放大倍数、种子。"""
    import copy

    p = copy.deepcopy(wf)

    for nid, node in p.items():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type") or ""
        ins = node.setdefault("inputs", {})

        # 输入图
        # LoadImageOutput 只能从 ComfyUI 的 output 索引里选「已生成的」图，
        # 直接塞文件名会 400。改成 LoadImage —— 它读 input 目录里的任意文件。
        if ct == "LoadImageOutput":
            node["class_type"] = "LoadImage"
            node.pop("_meta", None)
            node["_meta"] = {"title": "加载图像"}
            ins.clear()
            ins["image"] = image_name
            ins["upload"] = "image"
        elif ct == "LoadImage":
            ins["image"] = image_name
            ins["upload"] = "image"
        # 放大倍数
        if ct == "ResizeImageMaskNode":
            ins["resize_type"] = "scale by multiplier"
            ins["resize_type.multiplier"] = multiplier
        # 种子
        if ct == "KSampler" and seed is not None:
            ins["seed"] = seed
        # 输出前缀
        if ct == "SaveImage":
            ins["filename_prefix"] = "SeedVR2_upscale"

    return p


def _submit(base: str, prompt: Dict[str, Any]) -> str:
    payload = {"prompt": prompt, "client_id": f"amazingdraw-upscale-{uuid.uuid4().hex[:8]}"}
    res = _http_json(f"{base}/prompt", payload, timeout=60)
    pid = str(res.get("prompt_id") or "")
    if not pid:
        raise HTTPException(status_code=502, detail=f"ComfyUI 未返回 prompt_id: {str(res)[:200]}")
    return pid


def _wait(base: str, prompt_id: str, timeout: float = 600.0, interval: float = 2.0) -> Dict[str, Any]:
    """轮询 /history 直到该 prompt 完成。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            hist = _http_json(f"{base}/history/{prompt_id}", timeout=20)
        except Exception:
            hist = {}
        item = hist.get(prompt_id)
        if item:
            status = (item.get("status") or {}).get("status_str")
            if status in ("success", "error"):
                return item
            if item.get("outputs"):
                return item
        time.sleep(interval)
    raise HTTPException(status_code=504, detail=f"放大超时（{int(timeout)}s）")


def _first_output_image(item: Dict[str, Any]) -> Optional[str]:
    """从 history 里取第一张输出图文件名。"""
    outputs = item.get("outputs") or {}
    for _nid, out in outputs.items():
        for img in (out.get("images") or []):
            fn = img.get("filename")
            if fn:
                return str(fn)
    return None


def _read_png_text(p: Path) -> Dict[str, str]:
    """读 PNG 的 tEXt / iTXt 文本块。"""
    import struct

    out: Dict[str, str] = {}
    try:
        data = p.read_bytes()
    except Exception:
        return out
    if len(data) < 8 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return out
    i = 8
    while i + 8 <= len(data):
        try:
            ln = struct.unpack(">I", data[i:i + 4])[0]
            typ = data[i + 4:i + 8].decode("latin-1", errors="replace")
        except Exception:
            break
        body = data[i + 8:i + 8 + ln]
        if typ == "tEXt" and b"\x00" in body:
            k, v = body.split(b"\x00", 1)
            out[k.decode("latin-1", errors="replace")] = v.decode("utf-8", errors="replace")
        elif typ == "iTXt":
            parts = body.split(b"\x00", 5)
            if len(parts) >= 6:
                out[parts[0].decode("latin-1", errors="replace")] = parts[5].decode(
                    "utf-8", errors="replace"
                )
        elif typ == "IDAT":
            break
        i += 12 + ln
    return out


def _write_png_text_chunk(p: Path, key: str, value: str) -> None:
    """写入 tEXt 块；已存在同名键则替换掉。

    高清图的 prompt 键里存的是放大工作流参数，没有提示词，
    所以不能简单地「存在就跳过」，要把旧块删掉再写新的。
    """
    import struct
    import zlib

    data = p.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return

    payload = key.encode("latin-1") + b"\x00" + value.encode("utf-8")
    chunk = struct.pack(">I", len(payload)) + b"tEXt" + payload
    chunk += struct.pack(">I", zlib.crc32(b"tEXt" + payload) & 0xFFFFFFFF)

    # 逐块扫描：删掉同名 tEXt，找第一个 IDAT 位置
    i = 8
    insert_at = None
    keep_parts = [data[:8]]
    while i + 8 <= len(data):
        try:
            ln = struct.unpack(">I", data[i:i + 4])[0]
            typ = data[i + 4:i + 8]
        except Exception:
            break
        total = 12 + ln
        block = data[i:i + total]
        if typ == b"IDAT" and insert_at is None:
            insert_at = len(b"".join(keep_parts))
        if typ == b"tEXt":
            body = data[i + 8:i + 8 + ln]
            if b"\x00" in body:
                k = body.split(b"\x00", 1)[0]
                if k == key.encode("latin-1"):
                    i += total
                    continue  # 跳过同名块
        keep_parts.append(block)
        i += total

    if insert_at is None:
        # 没有 IDAT 说明文件异常，放弃
        return

    # insert_at 是按拼接后的偏移算的，重新算一次更稳
    out = data[:8]
    i = 8
    inserted = False
    while i + 8 <= len(data):
        try:
            ln = struct.unpack(">I", data[i:i + 4])[0]
            typ = data[i + 4:i + 8]
        except Exception:
            break
        total = 12 + ln
        if typ == b"IDAT" and not inserted:
            out += chunk
            inserted = True
        if typ == b"tEXt":
            body = data[i + 8:i + 8 + ln]
            if b"\x00" in body and body.split(b"\x00", 1)[0] == key.encode("latin-1"):
                i += total
                continue
        out += data[i:i + total]
        i += total
    out += data[i:]

    p.write_bytes(out)


def _copy_prompt_metadata(src: Path, dst: Path) -> None:
    """把原图的 prompt 文本块补进目标 PNG。

    放大后的图只记录了放大工作流参数，没有提示词；
    补上原图的 prompt，虚拟卡才能读到。
    """
    info = _read_png_text(src)
    prompt = info.get("prompt")
    if not prompt:
        return
    _write_png_text_chunk(dst, "prompt", prompt)


# ── 卡片读写 ──────────────────────────────────────────────────────────


def _cards_dir() -> Path:
    cfg = _config()
    return Path(os.path.expanduser("~")) / ".amazingdraw" / "cards"


def _load_card(card_id: str) -> Tuple[Path, Dict[str, Any]]:
    d = _cards_dir()
    p = d / f"{card_id}.json"
    if not p.is_file():
        raise HTTPException(status_code=404, detail=f"卡片不存在: {card_id}")
    return p, json.loads(p.read_text(encoding="utf-8"))


def _save_card(path: Path, card: Dict[str, Any]) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _resolve_source(card: Dict[str, Any], cfg: Dict[str, Any]) -> Optional[Path]:
    """找卡片对应的原始 PNG。归档盘优先，其次 ComfyUI output。"""
    name = str(card.get("render_image") or "").strip()
    if not name:
        return None
    cands: List[Path] = []
    arch = _archive_dir(cfg)
    if str(arch):
        cands.append(arch / name)
    cands.append(_comfy_output_dir(cfg) / name)
    out_dir = Path(str(cfg.get("output_dir") or ""))
    if str(out_dir):
        cands.append(out_dir / name)
    for c in cands:
        if c.is_file():
            return c
    return None


# ── 端点 ──────────────────────────────────────────────────────────────


@router.get("/api/upscale/meta")
def meta() -> Dict[str, Any]:
    cfg = _config()
    wf = _workflow_path(cfg)
    base = _comfy_base(cfg)
    return {
        "available": wf.is_file(),
        "workflow": str(wf),
        "comfyui": base,
        "comfyui_alive": _comfy_alive(base),
        "archive_dir": str(_archive_dir(cfg)),
        "output_dir": str(_comfy_output_dir(cfg)),
        "note": "把已完成卡片转高清：复制进 ComfyUI output → SeedVR2 放大 → 回写归档",
    }


@router.post("/api/upscale/card")
def upscale_card(req: Dict[str, Any]) -> Dict[str, Any]:
    """把一张卡片的图转高清。"""
    card_id = str(req.get("card_id") or "").strip()
    if not card_id:
        raise HTTPException(status_code=400, detail="缺少 card_id")

    cfg = _config()
    wf_path = _workflow_path(cfg)
    if not wf_path.is_file():
        raise HTTPException(status_code=503, detail=f"放大工作流不存在: {wf_path}")

    base = _comfy_base(cfg)
    if not _comfy_alive(base):
        raise HTTPException(status_code=503, detail="ComfyUI 未运行，请先启动")

    path, card = _load_card(card_id)
    src = _resolve_source(card, cfg)
    if src is None:
        raise HTTPException(status_code=404, detail=f"找不到原图: {card.get('render_image')}")

    multiplier = float(req.get("multiplier") or 2.0)
    if multiplier not in (1.5, 2.0, 3.0, 4.0):
        multiplier = 2.0
    seed = req.get("seed")
    seed = int(seed) if seed not in (None, "") else None

    # 1) 复制进 ComfyUI input（LoadImage 只能读 input/）
    in_dir = _comfy_input_dir(cfg)
    out_dir = _comfy_output_dir(cfg)
    try:
        staged = _upload_to_output(src, in_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"复制到 ComfyUI input 失败: {exc}") from exc

    # 2) 提交
    try:
        wf = json.loads(wf_path.read_text(encoding="utf-8"))
        prompt = _build_prompt(wf, staged, multiplier=multiplier, seed=seed)
        pid = _submit(base, prompt)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"提交放大任务失败: {exc}") from exc

    # 3) 等结果
    timeout = float(req.get("timeout") or 600)
    item = _wait(base, pid, timeout=timeout)
    out_name = _first_output_image(item)
    if not out_name:
        raise HTTPException(status_code=502, detail=f"放大完成但没找到输出图: {str(item)[:300]}")

    # 4) 复制回归档盘
    arch = _archive_dir(cfg)
    arch.mkdir(parents=True, exist_ok=True)
    stem = Path(str(card.get("render_image") or "upscaled")).stem
    new_name = f"{stem}-高清.png"
    src_out = out_dir / out_name
    if not src_out.is_file():
        # ComfyUI 有时输出到子目录
        for sub in out_dir.rglob(out_name):
            if sub.is_file():
                src_out = sub
                break
    dst = arch / new_name
    try:
        shutil.copy2(src_out, dst)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"复制放大图回归档失败: {exc}") from exc

    # 4.5) 把原图的 prompt 元数据补进高清图
    # 放大工作流的 PNG 里只记录放大参数，没有提示词，
    # 不补的话高清图变成虚拟卡时读不到 prompt。
    try:
        _copy_prompt_metadata(src, dst)
    except Exception:
        pass

    # 5) 回写卡片
    old = str(card.get("render_image") or "")
    card["upscale_from"] = old
    card["render_image"] = new_name
    card.setdefault("history", []).append({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "action": "upscaled",
        "changes": {
            "from": old,
            "to": new_name,
            "multiplier": multiplier,
            "workflow": wf_path.name,
            "prompt_id": pid,
        },
    })
    _save_card(path, card)

    # 6) 清掉临时源图
    try:
        (in_dir / staged).unlink(missing_ok=True)
    except Exception:
        pass

    return {
        "ok": True,
        "card_id": card_id,
        "from": old,
        "to": new_name,
        "image_url": f"/images/{urllib.request.quote(new_name)}",
        "multiplier": multiplier,
        "prompt_id": pid,
        "archive": str(dst),
    }
