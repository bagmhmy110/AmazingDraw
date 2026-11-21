#!/usr/bin/env python3
"""MOSS-Image 提示词架构师 API（moss-image-prompt-architect）。

纯指令型 skill：把一句话想法扩成 Caption（中文散文）或 Layout（紧凑 JSON）。
没有自带脚本，全部由 LLM 按 SKILL.md + references 执行。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

import style_options as SO
import persona_options as PO

from skill_common import (
    list_references,
    llm_chat_with_retry,
    read_reference,
    require_skill,
    skill_dir,
    strip_code_fence,
)

router = APIRouter(tags=["moss-architect"])

SKILL = "moss-image-prompt-architect"

MODES = [
    {
        "value": "caption",
        "label": "Caption（默认）",
        "desc": "中文散文段落。人像、角色、生活场景、产品、建筑、插画",
    },
    {
        "value": "layout",
        "label": "Layout",
        "desc": "单行紧凑 JSON + bbox 坐标。海报、精确文字位置、多栏独立摆放",
    },
]

# 题材（下拉）
SUBJECTS = [
    "人像", "角色 LoRA 演示", "生活场景", "多人场景",
    "产品摄影", "建筑", "插画", "平面设计", "动漫渲染",
    "街头抓拍", "室内空间", "美食", "宠物", "运动",
]

# 画风（下拉，与题材并列；MOSS 的输出模式是格式选择，不适合放画风）
# 12 种画风统一来自 style_options.EXTRA_STYLES

# 场景 / 地点（下拉，覆盖常见拍摄环境）
SCENES = [
    {"value": "", "label": "不限"},
    {"value": "深夜便利店", "label": "深夜便利店"},
    {"value": "咖啡馆靠窗座位", "label": "咖啡馆窗边"},
    {"value": "老式公寓出租屋", "label": "出租屋"},
    {"value": "地铁站台", "label": "地铁站台"},
    {"value": "雨天的街道", "label": "雨天街道"},
    {"value": "图书馆书架间", "label": "图书馆"},
    {"value": "办公室工位", "label": "办公室"},
    {"value": "便利店门口屋檐下", "label": "便利店屋檐"},
    {"value": "天台上晾衣绳旁", "label": "天台"},
    {"value": "医院走廊", "label": "医院走廊"},
    {"value": "夜市的摊位前", "label": "夜市"},
    {"value": "健身房器械区", "label": "健身房"},
    {"value": "海边礁石", "label": "海边"},
    {"value": "山间小路", "label": "山间"},
    {"value": "老式电梯轿厢", "label": "电梯轿厢"},
    {"value": "理发店镜子前", "label": "理发店"},
    {"value": "书店角落", "label": "书店"},
]

# 光线（下拉）
LIGHTS = [
    {"value": "", "label": "不限"},
    {"value": "冷白荧光灯直射", "label": "冷白荧光灯"},
    {"value": "傍晚斜射的橙色自然光", "label": "傍晚斜光"},
    {"value": "阴天柔和的漫射光", "label": "阴天漫射"},
    {"value": "百叶窗投下的条纹光", "label": "百叶窗条纹光"},
    {"value": "单侧暖色台灯", "label": "暖色台灯"},
    {"value": "霓虹招牌的彩色反光", "label": "霓虹反光"},
    {"value": "正午顶光，阴影短促", "label": "正午顶光"},
    {"value": "逆光，边缘有光晕", "label": "逆光"},
    {"value": "走廊尽头的一束窄光", "label": "窄光束"},
    {"value": "手机屏幕的冷光打在脸上", "label": "屏幕光"},
]

# 构图 / 机位（下拉）
SHOTS = [
    {"value": "", "label": "不限"},
    {"value": "中近景，平视，35mm", "label": "中近景 平视 35mm"},
    {"value": "特写，略低机位，50mm", "label": "特写 低机位 50mm"},
    {"value": "全身，正面平视，35mm", "label": "全身 正面 35mm"},
    {"value": "三分之四侧角，85mm，浅景深", "label": "三分之四侧角 85mm"},
    {"value": "俯拍，高机位，广角", "label": "俯拍 广角"},
    {"value": "仰拍，低机位贴近地面", "label": "仰拍 低机位"},
    {"value": "过肩视角，前景有遮挡", "label": "过肩 前景遮挡"},
    {"value": "镜面反射构图", "label": "镜面反射"},
]

# 画幅（下拉）
ASPECTS = [
    {"value": "", "label": "不限"},
    {"value": "竖构图 3:4", "label": "竖构图 3:4"},
    {"value": "竖构图 9:16", "label": "竖构图 9:16"},
    {"value": "横构图 16:9", "label": "横构图 16:9"},
    {"value": "方形 1:1", "label": "方形 1:1"},
    {"value": "宽幅 21:9", "label": "宽幅 21:9"},
]

REF_FILES = {
    "caption": "references/caption-architecture.md",
    "layout": "references/layout-compile.md",
    "checks": "references/checks-and-boundaries.md",
}


def _skill_or_503():
    return require_skill(SKILL)


@router.get("/api/moss-architect/meta")
def meta() -> Dict[str, Any]:
    p = skill_dir(SKILL)
    out = {
        "available": p is not None,
        "skill_dir": str(p) if p else None,
        "modes": MODES,
        "subjects": SUBJECTS,
        "scenes": SCENES,
        "lights": LIGHTS,
        "shots": SHOTS,
        "aspects": ASPECTS,
        "references": list_references(SKILL) if p else [],
        "hard_constraint": "所有人物一律为亚洲人（中国/日本/韩国/其他亚洲族裔）",
        **PO.common_meta(),
        **SO.meta(),
    }
    return out


@router.get("/api/moss-architect/reference")
def get_reference(name: str = "caption", max_chars: int = 0) -> Dict[str, Any]:
    rel = REF_FILES.get(name, name)
    text = read_reference(SKILL, rel, max_chars=max_chars)
    return {"name": name, "path": rel, "text": text, "length": len(text)}


@router.post("/api/moss-architect/generate")
def generate(req: Dict[str, Any]) -> Dict[str, Any]:
    """把想法扩成 MOSS-Image 提示词。"""
    _skill_or_503()
    idea = str(req.get("idea") or "").strip()
    if not idea:
        raise HTTPException(status_code=400, detail="请填写想法")

    mode = str(req.get("mode") or "caption").strip().lower()
    if mode not in ("caption", "layout"):
        raise HTTPException(status_code=400, detail="mode 只能是 caption 或 layout")

    subject = str(req.get("subject") or "").strip()
    extra = str(req.get("extra") or "").strip()

    # 新增下拉：场景 / 光线 / 机位 / 画幅 / 人种 / 年龄 / 身材 / 气质
    scene = str(req.get("scene") or "").strip()
    light = str(req.get("light") or "").strip()
    shot = str(req.get("shot") or "").strip()
    aspect = str(req.get("aspect") or "").strip()
    ethnicity = PO.pick_ethnicity(str(req.get("ethnicity") or ""))
    age = PO.pick_age(str(req.get("age") or ""))
    body = str(req.get("body") or "").strip()
    vibe = str(req.get("vibe") or "").strip()

    # 不要把整份 SKILL.md 塞给模型 —— 它会逐条分析规则、把 token 预算耗在思考上。
    # 实测：system 越"像规则文档"，reasoning 越长、content 越可能为空。
    # 这里只给最简写作要点。
    if mode == "caption":
        fmt_rule = "输出一段纯中文散文，连续不分行。只输出提示词本身。"
    else:
        fmt_rule = (
            "输出单行紧凑 JSON：键名英文，`caption` 与 `summary.caption` 的值为中文。"
            "只输出 JSON 本身。"
        )

    eth_rule = (
        f"人物必须写成「{ethnicity}」，并用肤色、眼型、发质、面部结构等可见特征落地。"
        if ethnicity
        else "人物一律亚洲人，用肤色、眼型、发质、面部结构等可见特征落地。"
    )

    system = (
        "你是图像提示词写手。直接写提示词，不分析、不解释。\n"
        f"{fmt_rule}\n"
        f"{eth_rule}\n"
        "写具体可见的细节与空间关系，避开白T、咖啡馆、柔和窗光、金时刻这类陈词滥调。"
    )

    user = f"想法：{idea}\n"
    if subject:
        user += f"题材：{subject}\n"
    if scene:
        user += f"场景：{scene}\n"
    if light:
        user += f"光线：{light}\n"
    if shot:
        user += f"机位构图：{shot}\n"
    if aspect:
        user += f"画幅：{aspect}\n"
    if age:
        user += f"年龄：{age}\n"
    if body:
        user += f"身材：{body}\n"
    if vibe:
        user += f"气质：{vibe}\n"
    if extra:
        user += f"额外要求：{extra}\n"
    user += "\n直接写提示词。"

    text = strip_code_fence(
        llm_chat_with_retry(system, user, max_tokens=4000, temperature=0.85, timeout=240)
    )
    if not text:
        raise HTTPException(status_code=502, detail="LLM 未产出内容")

    # 追加画风（只加开头/结尾）
    text = SO.apply(text, str(req.get("extra_style") or ""))

    out: Dict[str, Any] = {
        "ok": True,
        "mode": mode,
        "prompt": text,
        "raw": text,
        "applied": {
            "ethnicity": ethnicity, "age": age, "scene": scene,
            "light": light, "shot": shot, "aspect": aspect,
            "body": body, "vibe": vibe,
        },
    }
    if mode == "layout":
        # 尝试解析成 JSON 便于前端校验坐标
        try:
            out["layout"] = json.loads(text)
            out["valid_json"] = True
        except Exception:
            out["valid_json"] = False
    return out


@router.post("/api/moss-architect/batch")
def batch(req: Dict[str, Any]) -> Dict[str, Any]:
    """批量变体：按步 I 的要求，各条之间变化场景方案而非只换形容词。"""
    _skill_or_503()
    idea = str(req.get("idea") or "").strip()
    if not idea:
        raise HTTPException(status_code=400, detail="请填写想法")
    n = int(req.get("n") or 5)
    if n < 1 or n > 30:
        raise HTTPException(status_code=400, detail="条数需在 1~30 之间")

    # 批量也要读全部选项，否则用户选了不生效
    subject = str(req.get("subject") or "").strip()
    scene = str(req.get("scene") or "").strip()
    light = str(req.get("light") or "").strip()
    shot = str(req.get("shot") or "").strip()
    aspect = str(req.get("aspect") or "").strip()
    extra = str(req.get("extra") or "").strip()
    ethnicity = PO.pick_ethnicity(str(req.get("ethnicity") or ""))
    age = PO.pick_age(str(req.get("age") or ""))
    body = str(req.get("body") or "").strip()
    vibe = str(req.get("vibe") or "").strip()

    # 精简指令，不塞整份 SKILL.md（否则模型逐条分析规则、耗尽 token）
    system = f"""你是 MOSS-Image 提示词架构师。直接产出结果，不做任何分析、不解释、不复述规则。

批量输出格式（严格遵守）：
输出 {n} 条彼此不同的方案，每条一行，格式严格为 `1. <中文提示词>`、`2. <中文提示词>`…

要求：
- 变化落在场景方案上（相机距离、视点、时段、地点、衣橱、动作阶段），不是只换形容词
- {'各条之间体现不同亚洲族裔与地域，避免全是一个模子' if not ethnicity else f'所有条目的人物族裔固定为「{ethnicity}」，不要变化'}
- 每条都是完整的中文散文段落，单行输出
- 人物一律亚洲人，通过具体可见特征落地
- 只输出这 {n} 行，不要任何前言与总结
"""

    user = f"想法：{idea}\n"
    if subject:
        # 「题材」是拍摄类型（人像/产品/插画/角色 LoRA 演示…），
        # 光给个词模型容易忽略，补一句说明让它落到画面语言上。
        user += (
            f"题材：{subject}\n"
            f"（「{subject}」是这一批的拍摄类型，每一条都要符合它的影像特征，"
            f"用可见的画面元素体现出来，不要只当成标签忽略掉）\n"
        )
    if scene:
        user += f"场景：{scene}\n"
    if light:
        user += f"光线：{light}\n"
    if shot:
        user += f"机位构图：{shot}\n"
    if aspect:
        user += f"画幅：{aspect}\n"
    if age:
        user += f"年龄：{age}\n"
    if body:
        user += f"身材：{body}\n"
    if vibe:
        user += f"气质：{vibe}\n"
    if extra:
        user += f"额外要求：{extra}\n"

    # 用户锁定的选项，批量时每条都要遵守（只有未被锁的维度才允许变化）
    locked = [
        name for name, val in (
            ("题材", subject), ("场景", scene), ("光线", light), ("机位构图", shot),
            ("画幅", aspect), ("年龄", age), ("身材", body), ("气质", vibe),
        ) if val
    ]
    if locked:
        user += (
            f"\n【必须遵守】{'、'.join(locked)} 是用户指定的，"
            "每一条都必须体现，不能变化。\n"
            "只在未锁定的维度上做差异（衣橱、动作阶段、时段细节、族裔等）。\n"
        )

    user += f"\n请输出 {n} 条不同方案。"

    text = strip_code_fence(
        llm_chat_with_retry(system, user, max_tokens=6000, temperature=0.95, timeout=300)
    )

    items: List[Dict[str, Any]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        # 去掉 `1.` / `1、` / `- ` 前缀
        import re as _re
        s = _re.sub(r"^\s*\d+[.、)]\s*", "", s)
        s = _re.sub(r"^\s*[-*]\s*", "", s)
        if len(s) < 10:
            continue
        items.append({"index": len(items) + 1, "prompt": s})

    # 画风：批量也要套（单次在 generate 里做了，批量原来漏了）
    _style = str(req.get("extra_style") or "").strip()
    if _style:
        for it in items:
            t = it.get("prompt") or ""
            if t:
                it["prompt"] = SO.apply(t, _style)

    return {"ok": True, "count": len(items), "items": items, "raw": text}
