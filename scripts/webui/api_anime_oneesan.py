#!/usr/bin/env python3
"""二次元厚涂御姐 API（anime-thickpaint-oneesan-prompts）。

七大独立词池 + 固定骨架，脚本批量生成 + LLM 单条精修。
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

import shot_options as SH
import style_options as SO
import persona_options as PO

from skill_common import (
    list_references,
    llm_chat_with_retry,
    python_exe,
    require_skill,
    skill_dir,
    strip_code_fence,
)

router = APIRouter(tags=["anime-oneesan"])

SKILL = "anime-thickpaint-oneesan-prompts"

# 五类主线
MAIN_CATEGORIES = ["传统旗袍", "迷你旗袍", "迷你礼裙", "迷你包臀裙", "长款礼裙"]
# 修仙扩展池
CULTIVATION = ["修仙女装", "修仙迷你女装"]

# 词池缓存
_POOLS_CACHE = Path(__file__).resolve().parent / "anime_oneesan_pools.json"
_pools_memo: Optional[Dict[str, Any]] = None


def _skill_or_503() -> Path:
    return require_skill(SKILL, "（应位于 ~/.dsh/skills/anime-thickpaint-oneesan-prompts）")


def _random_seed() -> int:
    """生成一个新的随机种子（0 ~ 999999）。

    每次批量生成都换种子，避免同样的输入产出完全一样的结果。
    """
    import random as _r

    return _r.randint(0, 999999)


def _load_pools() -> Dict[str, Any]:
    """从 skill 的 references/pools.json 读词池（每次读，便于 skill 更新后生效）。"""
    global _pools_memo
    if _pools_memo is not None:
        return _pools_memo
    p = skill_dir(SKILL)
    if p is None:
        _pools_memo = {}
        return _pools_memo
    f = p / "references" / "pools.json"
    if not f.is_file():
        _pools_memo = {}
        return _pools_memo
    try:
        _pools_memo = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        _pools_memo = {}
    return _pools_memo


@router.get("/api/anime-oneesan/meta")
def meta() -> Dict[str, Any]:
    p = skill_dir(SKILL)
    pools = _load_pools()

    outfits = pools.get("outfits") or {}
    # 服装类别：主线 + 修仙（标注是否扩展）
    cats = []
    for c in MAIN_CATEGORIES:
        if c in outfits:
            cats.append({"value": c, "label": c, "group": "主线"})
    for c in CULTIVATION:
        if c in outfits:
            cats.append({"value": c, "label": c, "group": "修仙扩展"})

    out: Dict[str, Any] = {
        "available": p is not None,
        "skill_dir": str(p) if p else None,
        # 固定骨架
        "style_open": pools.get("style_open") or "Wuthering Waves style二次元半写实厚涂，竖屏构图。",
        "required": pools.get("required") or "精致的东方面容",
        "banned": pools.get("banned") or [],
        # 风格池（含国漫3D）
        "styles": pools.get("styles") or [],
        # 服装类别
        "outfit_categories": cats,
        "main_categories": [c for c in MAIN_CATEGORIES if c in outfits],
        "cultivation_categories": [c for c in CULTIVATION if c in outfits],
        # 七大词池（供前端下拉）
        "pools": {
            "ages": pools.get("ages") or [],
            "tempers": pools.get("tempers") or [],
            "hairs": pools.get("hairs") or [],
            "outfits": outfits,
            "sexy": pools.get("sexy") or [],
            "poses": pools.get("poses") or [],
            "scenes": pools.get("scenes") or [],
            "lights": pools.get("lights") or [],
            "stockings": pools.get("stockings") or [],
            "stats": pools.get("stats") or {},
        },
        # 丝袜概率档
        "stockings_levels": [
            {"value": 0.0, "label": "不加"},
            {"value": 0.2, "label": "20%"},
            {"value": 0.4, "label": "40%（默认）"},
            {"value": 0.6, "label": "60%"},
            {"value": 0.8, "label": "80%"},
            {"value": 1.0, "label": "100%"},
        ],
        # 通用人种/年龄/身材/气质
        **PO.common_meta(),
        **SH.meta(),
        "references": list_references(SKILL) if p else [],
    }
    return out


@router.post("/api/anime-oneesan/batch")
def batch(req: Dict[str, Any]) -> Dict[str, Any]:
    """批量生成：直接调 skill 自带 generate.py。"""
    p = _skill_or_503()
    script = p / "scripts" / "generate.py"
    if not script.is_file():
        raise HTTPException(status_code=503, detail="skill 缺少 scripts/generate.py")

    n = int(req.get("n") or 20)
    if n < 1 or n > 1000:
        raise HTTPException(status_code=400, detail="条数需在 1~1000 之间")

    # seed 处理：
    #   - 传具体值 → 用该值（可复现同一批）
    #   - 传 "random" / 空 / 没传 → 每次换一个新种子
    # 旧行为是空值固定回退 2024，导致每次批量结果完全一样。
    raw_seed = req.get("seed")
    if raw_seed in (None, "", "random", "rand", "auto"):
        seed = _random_seed()
    else:
        try:
            seed = int(raw_seed)
        except (TypeError, ValueError):
            seed = _random_seed()

    with tempfile.TemporaryDirectory(prefix="anime-oneesan-") as tmp:
        out_txt = Path(tmp) / "prompts.txt"
        out_json = Path(tmp) / "prompts.json"
        cmd = [
            python_exe(), str(script),
            "-n", str(n),
            "-o", str(out_txt),
            "--json", str(out_json),
            "--seed", str(seed),
        ]

        cats = req.get("categories") or []
        if isinstance(cats, str):
            cats = [c.strip() for c in cats.split(",") if c.strip()]
        if cats:
            cmd += ["--category", ",".join(cats)]

        if req.get("include_cultivation"):
            cmd.append("--include-cultivation")

        style = str(req.get("style") or "").strip()
        if style:
            cmd += ["--style", style]

        # 锁槽：之前批量只传 n/seed/category/style，其余选项全被丢掉
        for _field in ("age", "temper", "hair", "sexy", "pose", "scene", "light", "body", "vibe", "ethnicity"):
            _val = str(req.get(_field) or "").strip()
            if _val and _val not in ("不限", "随机"):
                cmd += [f"--lock-{_field}", _val]

        stock = req.get("stockings")
        if stock is not None:
            try:
                v = float(stock)
            except (TypeError, ValueError):
                v = 0.4
            if v <= 0:
                cmd.append("--no-stockings")
            else:
                cmd += ["--with-stockings", str(v)]

        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        try:
            res = subprocess.run(
                cmd, cwd=str(p), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=max(180.0, n * 1.2), env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail="批量生成超时") from exc

        if res.returncode != 0:
            raise HTTPException(status_code=400, detail=(res.stderr or "")[:500] or "批量失败")

        items: List[Dict[str, Any]] = []
        if out_json.is_file():
            try:
                data = json.loads(out_json.read_text(encoding="utf-8"))
                rows = data if isinstance(data, list) else (data.get("items") or [])
                for i, row in enumerate(rows, 1):
                    if isinstance(row, dict):
                        items.append({
                            "index": row.get("id") or i,
                            "prompt": row.get("prompt") or "",
                            "elements": row.get("elements"),
                        })
                    else:
                        items.append({"index": i, "prompt": str(row)})
            except Exception:
                items = []
        if not items and out_txt.is_file():
            for ln in out_txt.read_text(encoding="utf-8").splitlines():
                s = ln.strip()
                if not s:
                    continue
                # 形如 `1.xxx`
                if s[:3].strip().rstrip(".").isdigit():
                    s = s.split(".", 1)[1].strip()
                items.append({"index": len(items) + 1, "prompt": s})

        # 机位构图：generate.py 不认 shot，这里在代码层补
        _shot = str(req.get("shot") or "").strip()
        if _shot:
            for it in items:
                t = it.get("prompt") or ""
                if t:
                    it["prompt"] = SH.apply(t, _shot)

        return {
            "ok": True,
            "count": len(items),
            "seed": seed,
            "items": items,
            "stdout": (res.stdout or "")[:1500],
        }


@router.post("/api/anime-oneesan/generate")
def generate(req: Dict[str, Any]) -> Dict[str, Any]:
    """单条生成：按选中的词拼一条（代码拼装，不走 LLM，保证稳定）。"""
    _skill_or_503()
    pools = _load_pools()
    if not pools:
        raise HTTPException(status_code=503, detail="词池未就绪，先跑 scripts/extract_pools.py")

    import random as _rnd

    # 单条生成：不传 seed 就用真随机，保证每次点「生成一条」结果都不同
    raw_seed = req.get("seed")
    if raw_seed in (None, "", "random", "rand", "auto"):
        used_seed = _random_seed()
    else:
        try:
            used_seed = int(raw_seed)
        except (TypeError, ValueError):
            used_seed = _random_seed()
    rng = _rnd.Random(used_seed)

    # 风格：决定开头句与质感句
    styles = pools.get("styles") or []
    want_style = str(req.get("style") or "").strip()
    style_meta = None
    if styles:
        if want_style:
            style_meta = next((s for s in styles if s["value"] == want_style), None)
        if style_meta is None:
            style_meta = styles[0]   # 默认二次元半写实厚涂
    open_sentence = (style_meta or {}).get("open") or pools.get("style_open") or ""
    quality = (style_meta or {}).get("quality") or ""

    # 用户选中项（空则随机）
    def pick(key: str, pool_key: str) -> str:
        v = str(req.get(key) or "").strip()
        if v:
            return v
        lst = pools.get(pool_key) or []
        return rng.choice(lst)["value"] if lst else ""

    age = pick("age", "ages")
    temper = pick("temper", "tempers")
    hair = pick("hair", "hairs")
    sexy = pick("sexy", "sexy")
    pose = pick("pose", "poses")

    # 场景 + 光影配对
    scene = str(req.get("scene") or "").strip()
    light = str(req.get("light") or "").strip()
    if not scene or not light:
        pairs = pools.get("scene_pairs") or []
        if pairs:
            pr = rng.choice(pairs)
            scene = scene or pr["scene"]
            light = light or pr["light"]
        else:
            scene = scene or pick("", "scenes")
            light = light or pick("", "lights")

    # 服装
    outfit_val = str(req.get("outfit") or "").strip()
    cat_used = ""
    if not outfit_val:
        outfits = pools.get("outfits") or {}
        cat = str(req.get("category") or "").strip()
        if not cat:
            avail = [c for c in MAIN_CATEGORIES if c in outfits]
            if req.get("include_cultivation"):
                avail += [c for c in CULTIVATION if c in outfits]
            cat = rng.choice(avail) if avail else ""
        pool = outfits.get(cat) or []
        if pool:
            item = rng.choice(pool)
            outfit_val = item["value"]
            cat_used = cat

    # 丝袜
    stock_prob = req.get("stockings")
    try:
        stock_prob = float(stock_prob) if stock_prob not in (None, "") else 0.4
    except (TypeError, ValueError):
        stock_prob = 0.4
    stockings = ""
    if stock_prob > 0 and rng.random() < stock_prob:
        lst = pools.get("stockings") or []
        if lst:
            stockings = rng.choice(lst)["value"]

    # 拼句
    # body（身材）与 vibe（表情气质）原来前端有下拉但后端没接，选了不生效。
    body_shape = str(req.get("body") or "").strip()
    vibe_val = str(req.get("vibe") or "").strip()
    # 人种：原来「精致的东方面容」是写死的，选了人种也不体现
    eth_val = str(req.get("ethnicity") or "").strip()
    if eth_val and eth_val not in ("不限", "随机"):
        face = f"精致的东方面容，{eth_val}"
    else:
        face = "精致的东方面容"
    if stockings:
        body = f"身着{outfit_val}，{stockings}，{face}。{sexy}。{pose}。"
    else:
        body = f"身着{outfit_val}，{face}。{sexy}。{pose}。"
    extra_bits = "，".join(x for x in (body_shape, vibe_val) if x)
    if extra_bits:
        body += f"{extra_bits}。"
    text = (
        f"{open_sentence}"
        f"{age}{temper}，{hair}。"
        f"{body}"
        f"场景：{scene}。{light}。"
        f"{quality}"
    )

    # 追加画风（只加开头/结尾）
    text = SO.apply(text, str(req.get("extra_style") or ""))

    # 机位构图（追加到末尾）
    shot_val = str(req.get("shot") or "").strip()
    if shot_val:
        text = SH.apply(text, shot_val)

    return {
        "ok": True,
        "prompt": text,
        "seed": used_seed,
        "elements": {
            "style": (style_meta or {}).get("value") or "",
            "style_label": (style_meta or {}).get("label") or "",
            "age": age, "temper": temper, "hair": hair,
            "outfit": outfit_val, "category": cat_used,
            "stockings": stockings, "sexy": sexy, "pose": pose,
            "scene": scene, "light": light,
        },
    }


@router.post("/api/anime-oneesan/polish")
def polish(req: Dict[str, Any]) -> Dict[str, Any]:
    """LLM 精修：把一条拼好的提示词润色得更顺，保持骨架与词池用词。"""
    _skill_or_503()
    text = str(req.get("prompt") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="缺少 prompt")

    system = (
        "你是中文提示词润色器。只输出润色后的一段中文提示词，不分析、不解释。\n"
        "必须保留：开头的「Wuthering Waves style二次元半写实厚涂，竖屏构图。」"
        "以及「精致的东方面容」这七个字。\n"
        "禁止出现：九宫格、渔网、青涩、大波浪发型、机顶直闪、皮肤白皙细腻如瓷。\n"
        "形容腿时不得用「白皙」。"
    )
    user = f"润色下面这条提示词（保持信息完整，只让它读起来更顺）：\n\n{text}\n\n直接输出润色后的正文。"

    out = strip_code_fence(
        llm_chat_with_retry(system, user, max_tokens=2000, temperature=0.7, timeout=180)
    )
    if not out:
        raise HTTPException(status_code=502, detail="LLM 未产出内容")

    # 校验
    issues = []
    if "精致的东方面容" not in out:
        issues.append("缺必含词")
    for w in ("九宫格", "渔网", "青涩", "大波浪发型", "机顶直闪", "皮肤白皙细腻如瓷"):
        if w in out:
            issues.append(f"禁词:{w}")

    return {"ok": True, "prompt": out, "issues": issues, "original": text}
