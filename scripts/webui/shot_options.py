#!/usr/bin/env python3
"""机位构图：所有 skill 共用 MOSS 那套机位池。

MOSS 与写实摄影本来就有自己的（MOSS 的 8 项 + 写实的 7 项，各自贴合语料风格）。
其余 skill 统一复用 MOSS 这套 —— 简洁、够用、已在 MOSS 上验证过。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# 直接沿用 MOSS 的机位池（8 项 + 不限）
SHOTS: List[Dict[str, str]] = [
    {"value": "", "label": "不限", "desc": "由词池/模型自行决定"},
    {"value": "中近景，平视，35mm", "label": "中近景 平视 35mm", "desc": "最常用叙事景别，接近人眼视角"},
    {"value": "特写，略低机位，50mm", "label": "特写 低机位 50mm", "desc": "面部或局部占满，略带压迫感"},
    {"value": "全身，正面平视，35mm", "label": "全身 正面 35mm", "desc": "完整人物 + 环境，中性视角"},
    {"value": "三分之四侧角，85mm，浅景深", "label": "三分之四侧角 85mm", "desc": "侧脸轮廓清晰，背景虚化"},
    {"value": "俯拍，高机位，广角", "label": "俯拍 广角", "desc": "压低头身比例，显脆弱"},
    {"value": "仰拍，低机位贴近地面", "label": "仰拍 低机位", "desc": "拉长腿部，气势强"},
    {"value": "过肩视角，前景有遮挡", "label": "过肩 前景遮挡", "desc": "越过肩膀看，带前景层次"},
    {"value": "镜面反射构图", "label": "镜面反射", "desc": "镜子/水面/玻璃，虚实对照"},
]

_BY_VALUE = {s["value"]: s for s in SHOTS if s["value"]}
_BY_LABEL = {s["label"]: s for s in SHOTS if s["value"]}


def pick(value: str) -> Optional[Dict[str, str]]:
    """按 value 或 label 找机位，找不到返回 None。"""
    v = (value or "").strip()
    if not v:
        return None
    return _BY_VALUE.get(v) or _BY_LABEL.get(v)


def apply(text: str, value: str, *, position: str = "end") -> str:
    """把机位句插进提示词。

    position="end"   → 追加到末尾（默认）
    position="start" → 放开头
    """
    shot = pick(value)
    if not shot or not text:
        return text
    frag = shot["value"]
    out = text.strip()
    if frag in out:
        return out
    if out and not out.endswith(("。", "，", ".", ",")):
        out += "。"
    if position == "start":
        return f"以{frag}取景。" + out
    return out + f"以{frag}取景。"


def meta() -> Dict[str, Any]:
    """给各 skill 的 meta 用。"""
    return {"shots": SHOTS}
