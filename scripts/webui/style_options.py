#!/usr/bin/env python3
"""画风扩展：所有 skill 共用的 12 种追加画风。

设计原则：**只追加开头句与结尾质感句，不动各 skill 已有的词池与逻辑。**
每个 skill 的 meta 都带上这份列表，生成时接收 `extra_style` 参数。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# 12 种追加画风
EXTRA_STYLES: List[Dict[str, str]] = [
    {
        "value": "xianxia_fairy",
        "label": "仙侠仙女古风",
        "open": "东方仙侠风格，仙气飘逸，竖屏构图。",
        "quality": "衣袂与发丝在气流中轻扬，肌肤透着玉质的冷光，画面空灵出尘。",
        "desc": "仙气飘逸 · 云海仙山 · 玉质冷光",
    },
    {
        "value": "guofeng_xianxia",
        "label": "国风仙侠",
        "open": "国风仙侠风格，东方古典美学，竖屏构图。",
        "quality": "水墨晕染的远景与工笔细描的近景交织，衣料纹样带着古典的秩序感。",
        "desc": "国风古典 · 水墨远景 · 工笔近景",
    },
    {
        "value": "street",
        "label": "街拍",
        "open": "街头抓拍风格，城市纪实摄影，竖屏构图。",
        "quality": "背景行人虚化，霓虹与店铺招牌形成色块，画面有手持拍摄的轻微倾斜。",
        "desc": "城市纪实 · 行人虚化 · 手持感",
    },
    {
        "value": "korean_hd",
        "label": "韩系高清人像",
        "open": "韩系高清人像摄影，棚拍质感，竖屏构图。",
        "quality": "皮肤经过精修但保留质感，五官立体，光线柔和均匀，画面干净通透。",
        "desc": "韩式精修 · 柔和均匀 · 干净通透",
    },
    {
        "value": "ccd_retro",
        "label": "CCD 复古",
        "open": "CCD数码相机复古质感，千禧年色调，竖屏构图。",
        "quality": "画面有轻微噪点与色偏，高光溢出，边缘略软，带着旧数码相机的失真。",
        "desc": "CCD 质感 · 轻微噪点 · 高光溢出",
    },
    {
        "value": "home_candid",
        "label": "居家日常抓拍",
        "open": "居家日常抓拍，生活纪实，竖屏构图。",
        "quality": "房间里有生活痕迹，光线是窗外的自然光，构图随意不摆拍。",
        "desc": "生活痕迹 · 自然窗光 · 不摆拍",
    },
    {
        "value": "native_no_filter",
        "label": "原生相机无滤镜",
        "open": "原生相机直出，无滤镜，竖屏构图。",
        "quality": "肤色真实不修饰，保留皮肤纹理与细小瑕疵，色彩还原准确。",
        "desc": "直出无滤镜 · 真实肤色 · 保留瑕疵",
    },
    {
        "value": "cool_white",
        "label": "冷白皮写实",
        "open": "写实人像摄影，冷白皮质感，竖屏构图。",
        "quality": "肤色冷白通透，在光下泛着细腻的瓷质光泽，与深色背景形成对比。",
        "desc": "冷白通透 · 瓷质光泽 · 高对比",
    },
    {
        "value": "y2k",
        "label": "千禧年 Y2K 真人写真",
        "open": "千禧年Y2K风格真人写真，竖屏构图。",
        "quality": "闪片、镭射与低腰元素在光下反光，色彩饱和度高，带着2000年代的张扬。",
        "desc": "Y2K 千禧 · 闪片镭射 · 高饱和",
    },
    {
        "value": "gugong_guifei",
        "label": "古风宫廷",
        "open": "古风宫廷风格，雍容华贵，竖屏构图。",
        "quality": "宫灯与朱漆映出暖调，衣料是织金锦缎，配饰繁复沉重，气场压人。",
        "desc": "雍容华贵 · 织金锦缎 · 暖调宫灯",
    },
    {
        "value": "xiyu_hanfu",
        "label": "古风异域西域汉服",
        "open": "古风西域异域风格，敦煌壁画美学，竖屏构图。",
        "quality": "石青、赭石与朱砂的矿物配色，鎏金镶边在光下反光，披帛层叠垂落。",
        "desc": "敦煌矿物色 · 鎏金镶边 · 层叠披帛",
    },
    {
        "value": "qingleng_shennv",
        "label": "古风清冷神女",
        "open": "古风清冷神女风格，疏离出尘，竖屏构图。",
        "quality": "神情淡漠，眼神不带温度，素色衣料在冷光下几乎没有反光。",
        "desc": "疏离出尘 · 淡漠神情 · 素色冷光",
    },
]

_BY_VALUE = {s["value"]: s for s in EXTRA_STYLES}
_BY_LABEL = {s["label"]: s for s in EXTRA_STYLES}


def pick(value: str) -> Optional[Dict[str, str]]:
    """按 value 或 label 找风格，找不到返回 None。"""
    v = (value or "").strip()
    if not v:
        return None
    return _BY_VALUE.get(v) or _BY_LABEL.get(v)


def apply(text: str, value: str) -> str:
    """把画风套到提示词上：开头加 open，结尾加 quality。

    幂等：如果开头已经以该 open 起头，不重复加。
    """
    style = pick(value)
    if not style or not text:
        return text
    out = text.strip()
    op = style.get("open") or ""
    q = style.get("quality") or ""
    if op and not out.startswith(op):
        out = op + out
    if q and not out.endswith(q):
        out = out + q
    return out


def meta() -> Dict[str, Any]:
    """给各 skill 的 meta 用。"""
    return {"extra_styles": EXTRA_STYLES}
