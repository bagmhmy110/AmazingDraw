#!/usr/bin/env python3
"""Skill 接入的公共工具：目录探测、LLM 调用、markdown 读取。

三个 prompt skill（guoman-portrait / moss-architect / nsfw-templates）共用这一层，
但各自有独立的 API 路由与前端页面，不合并。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

# 仓库自带的 skills 目录（clone 下来即可用）
_REPO_SKILLS = Path(__file__).resolve().parent.parent.parent / "skills"

# skill 根目录候选：环境变量优先，其次仓库内置，最后各 agent 的 skills 目录
_SKILLS_ROOT_CANDIDATES = (
    os.environ.get("AMAZINGDRAW_SKILLS_ROOT"),
    str(_REPO_SKILLS),
    str(Path(os.path.expanduser("~")) / ".dsh" / "skills"),
    str(Path(os.path.expanduser("~")) / ".workbuddy-ai" / "skills"),
    str(Path(os.path.expanduser("~")) / ".claude" / "skills"),
    str(Path(os.path.expanduser("~")) / ".codex" / "skills"),
)


def skills_roots() -> List[Path]:
    """所有存在的 skills 根目录（按优先级）。"""
    out: List[Path] = []
    for cand in _SKILLS_ROOT_CANDIDATES:
        if not cand:
            continue
        p = Path(cand)
        if p.is_dir() and p not in out:
            out.append(p)
    return out


def skills_root() -> Path:
    roots = skills_roots()
    return roots[0] if roots else Path(os.path.expanduser("~")) / ".dsh" / "skills"


def skill_dir(name: str) -> Optional[Path]:
    """定位某个 skill 目录（必须含 SKILL.md）。跨多个 skills 根目录查找。"""
    for root in skills_roots():
        p = root / name
        if (p / "SKILL.md").is_file():
            return p
    return None


def require_skill(name: str, hint: str = "") -> Path:
    p = skill_dir(name)
    if p is None:
        raise HTTPException(
            status_code=503,
            detail=f"未找到 skill「{name}」。请安装到 {skills_root()} 或设置 AMAZINGDRAW_SKILLS_ROOT。{hint}",
        )
    return p


def python_exe() -> str:
    return sys.executable or "python3"


def read_reference(skill: str, rel_path: str, max_chars: int = 0) -> str:
    """读取 skill 的 references 文件（相对 skill 根）。"""
    base = require_skill(skill)
    target = (base / rel_path).resolve()
    # 防目录穿越
    if base.resolve() not in target.parents and target.parent != base.resolve():
        raise HTTPException(status_code=400, detail="非法路径")
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {rel_path}")
    text = target.read_text(encoding="utf-8", errors="replace")
    if max_chars and len(text) > max_chars:
        text = text[:max_chars] + f"\n\n…（已截断，原文件 {len(text)} 字）"
    return text


def list_references(skill: str) -> List[Dict[str, Any]]:
    """列出 skill 的 references 目录。"""
    base = require_skill(skill)
    ref = base / "references"
    if not ref.is_dir():
        return []
    out = []
    for f in sorted(ref.glob("*")):
        if f.is_file():
            out.append({
                "name": f.name,
                "size": f.stat().st_size,
                "size_kb": round(f.stat().st_size / 1024, 1),
            })
    return out


def extract_md_index(text: str) -> List[Dict[str, str]]:
    """从 markdown 里抽出「📋 索引」表格，转成 [{chapter, desc}]。"""
    rows: List[Dict[str, str]] = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2:
            continue
        # 跳过表头与分隔行
        if set(cells[0]) <= set("-: ") or cells[0] in ("章节", "#"):
            continue
        # 去掉 emoji 与 markdown 强调
        clean = re.sub(r"[*`]", "", cells[0]).strip()
        emoji = ""
        m = re.match(r"^([\U0001F300-\U0001FAFF\u2600-\u27BF]+)\s*", clean)
        if m:
            emoji = m.group(1)
            clean = clean[m.end():].strip()
        if not clean:
            continue
        rows.append({
            "chapter": clean,
            "emoji": emoji,
            "desc": re.sub(r"[*`]", "", cells[1]).strip() if len(cells) > 1 else "",
            "note": re.sub(r"[*`]", "", cells[2]).strip() if len(cells) > 2 else "",
        })
    return rows


# ── LLM 调用 ──────────────────────────────────────────────────────────────


def _llm_config() -> Dict[str, Any]:
    """从运行期 config.json 取 LLM 配置。"""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import amazingdraw_paths  # type: ignore

        cfg_path = amazingdraw_paths.config_file()
        cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
        return cfg.get("llm") or {}
    except Exception:
        return {}


def llm_chat(
    system: str,
    user: str,
    *,
    max_tokens: int = 2048,
    temperature: float = 0.8,
    timeout: float = 120.0,
) -> str:
    """调用 OpenAI 兼容端点，返回纯文本。

    注意：hy4free 这类推理模型会把思考过程写进 `reasoning_content`，
    且思考会吃掉 token 预算。大 system prompt 时若 max_tokens 不够，
    `content` 会为空、正文根本出不来。所以：
      * 默认 token 预算给足（调用方按需加大）
      * content 为空时明确报错，而不是拿 reasoning 当正文
    """
    cfg = _llm_config()
    base_url = str(cfg.get("base_url") or "").rstrip("/")
    model = str(cfg.get("model") or "")
    api_key = str(cfg.get("api_key") or "")
    if not base_url or not model:
        raise HTTPException(status_code=503, detail="未配置 LLM（config.json → llm.base_url / llm.model）")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        raise HTTPException(status_code=502, detail=f"LLM HTTP {exc.code}: {body}") from exc
    except Exception as exc:
        raise HTTPException(status_code=504, detail=f"LLM 调用失败: {exc}") from exc

    try:
        choices = data.get("choices") or []
        msg = choices[0].get("message") or {}
        finish = str(choices[0].get("finish_reason") or "")
        text = msg.get("content")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM 返回格式异常: {str(data)[:300]}") from exc

    content = str(text or "").strip()
    reasoning = str(msg.get("reasoning_content") or "").strip()

    if not content:
        # 思考吃光了预算：给出可操作的错误，而不是把思考当正文
        raise HTTPException(
            status_code=502,
            detail=(
                f"LLM 未产出正文（content 为空，finish_reason={finish or '?'}，"
                f"思考内容 {len(reasoning)} 字）。"
                "多半是 max_tokens 被 reasoning 吃光，请调高 max_tokens 或精简 system prompt。"
            ),
        )
    return content


def llm_chat_with_retry(
    system: str,
    user: str,
    *,
    max_tokens: int = 2048,
    temperature: float = 0.8,
    timeout: float = 120.0,
    attempts: int = 3,
) -> str:
    """带重试的 llm_chat。

    推理模型（hy4free 这类）偶发会把 token 预算全烧在 reasoning 上、
    content 返回空。这不是稳定复现的，重试一次通常就好。
    每次重试略微降低 temperature，让模型更快收敛。
    """
    last: Optional[HTTPException] = None
    for i in range(max(1, attempts)):
        try:
            return llm_chat(
                system,
                user,
                max_tokens=max_tokens,
                temperature=max(0.3, temperature - i * 0.15),
                timeout=timeout,
            )
        except HTTPException as exc:
            last = exc
            # 只有「content 为空」这类可重试错误才重试
            detail = str(getattr(exc, "detail", "") or "")
            if "content 为空" not in detail and "未产出正文" not in detail:
                raise
    if last is not None:
        raise last
    raise HTTPException(status_code=502, detail="LLM 调用失败")


def strip_code_fence(text: str) -> str:
    """去掉模型可能包上的 ``` 围栏。"""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()
