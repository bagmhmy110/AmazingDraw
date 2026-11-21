#!/usr/bin/env python3
"""NSFW 提示词模板库 API（nsfw-prompt-templates-asian）。

14 个模块按组装顺序排列，纯词库型 skill：
按槽位选模块 → 取词条 → 按顺序拼装成成人向提示词。

边界：仅成年虚构角色（18+），不用于现实具体人物的性化图像。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

import shot_options as SH
import style_options as SO
import persona_options as PO

from skill_common import (
    extract_md_index,
    list_references,
    llm_chat_with_retry,
    read_reference,
    require_skill,
    skill_dir,
    strip_code_fence,
)

router = APIRouter(tags=["nsfw-templates"])

SKILL = "nsfw-prompt-templates-asian"

# 14 模块，按组装顺序
MODULES = [
    {"id": "01", "slot": "场景主题", "file": "references/01-场景主题.md", "required": True,
     "desc": "24 场景章节 + 35 个 JAV 主题 + 场景感官锚定"},
    {"id": "02", "slot": "景别构图", "file": "references/02-景别构图.md", "required": True,
     "desc": "景别 / 视角 / 设备 / 焦段 / 构图 / 画质"},
    {"id": "03", "slot": "裸露液体", "file": "references/03-裸露液体.md", "required": True,
     "desc": "6 级裸露梯度 + 10 类衣物状态 + 生殖器解剖 + 7 类液体"},
    {"id": "04", "slot": "服装专项", "file": "references/04-服装专项.md", "required": True,
     "desc": "东亚服装词库 + 脱衣状态 + 服装×裸露联动"},
    {"id": "05", "slot": "光影氛围", "file": "references/05-光影氛围.md", "required": True,
     "desc": "12 种布光 + 电影感 + 情色专用光 + 色温×情绪"},
    {"id": "06", "slot": "姿势动作", "file": "references/06-姿势动作.md", "required": True,
     "desc": "静态/动态姿势 + 过渡姿态 + 口交深喉 + 颜射 + 插入 + 多人"},
    {"id": "07", "slot": "表情眼神", "file": "references/07-表情眼神.md", "required": True,
     "desc": "表情词库 + 8 种眼神 + 嘴部状态 + 性爱阶段表情流变"},
    {"id": "08", "slot": "风格胶片", "file": "references/08-风格胶片.md", "required": False,
     "desc": "25 种胶片模拟 + 7 种电影镜头风格 + 天气氛围"},
    {"id": "09", "slot": "妆容专项", "file": "references/09-妆容专项.md", "required": False,
     "desc": "底妆/眼妆/唇妆/腮红/美甲 + 风格方向 + 高潮脸"},
    {"id": "10", "slot": "发型饰品", "file": "references/10-发型饰品.md", "required": False,
     "desc": "发型 + 头饰 + 首饰"},
    {"id": "11", "slot": "瑕疵细节", "file": "references/11-瑕疵细节.md", "required": False,
     "desc": "瑕疵库 + 手部/足部 + 体液痕迹 + 光影×皮肤"},
    {"id": "12", "slot": "纹身标记", "file": "references/12-纹身标记.md", "required": False,
     "desc": "图案纹身 + CJK 文字纹身 + 墨水颜色 + 位置锁定"},
    {"id": "13", "slot": "道具宠物", "file": "references/13-道具宠物.md", "required": False,
     "desc": "道具 / 宠物 / 氛围物件"},
    {"id": "14", "slot": "人格卡片", "file": "references/14-人格卡片.md", "required": False,
     "desc": "身份职业人格卡（权力关系 / 行为 / 制服 / 场景）"},
]

# 必读槽（每次各取 1 个）
REQUIRED_SLOTS = [m["slot"] for m in MODULES if m["required"]]
# 选读槽（每次取 3-5 个）
OPTIONAL_SLOTS = [m["slot"] for m in MODULES if not m["required"]]


def _skill_or_503():
    return require_skill(SKILL)


# 词条缓存（由 build_nsfw_terms.py 生成：槽位 → 小节 → 词条）
_TERMS_CACHE = Path(__file__).resolve().parent / "nsfw_terms_cache.json"
_terms_memo: Optional[Dict[str, Any]] = None


def _load_terms() -> Dict[str, Any]:
    """读取「槽位 → 小节 → 词条」缓存，供前端下拉使用。"""
    global _terms_memo
    if _terms_memo is not None:
        return _terms_memo
    if not _TERMS_CACHE.is_file():
        _terms_memo = {}
        return _terms_memo
    try:
        _terms_memo = json.loads(_TERMS_CACHE.read_text(encoding="utf-8"))
    except Exception:
        _terms_memo = {}
    return _terms_memo


@router.get("/api/nsfw-templates/terms")
def terms(slot: str = "") -> Dict[str, Any]:
    """返回某槽位（或全部）的可选词条，按小节分组。"""
    data = _load_terms()
    if slot:
        info = data.get(slot)
        if not info:
            raise HTTPException(status_code=404, detail=f"槽位「{slot}」没有词条缓存")
        return {"slot": slot, **info}
    return {
        "slots": {
            k: {"sections": v.get("sections") or {}, "total": v.get("total", 0)}
            for k, v in data.items()
        }
    }


@router.get("/api/nsfw-templates/meta")
def meta() -> Dict[str, Any]:
    p = skill_dir(SKILL)
    out: Dict[str, Any] = {
        "available": p is not None,
        "skill_dir": str(p) if p else None,
        "modules": MODULES,
        "required_slots": REQUIRED_SLOTS,
        "optional_slots": OPTIONAL_SLOTS,
        "order": " → ".join(REQUIRED_SLOTS),
        "boundary": "仅成年虚构角色（18+）；不用于现实具体人物的性化图像；不含未成年外貌与年龄暗示",
        **PO.common_meta(),
        **SH.meta(),
        **SO.meta(),
        "references": [],
        # 每个槽位的可选词条（按小节分组），供前端做下拉
        "terms": {
            k: {"sections": v.get("sections") or {}, "total": v.get("total", 0)}
            for k, v in _load_terms().items()
        },
    }
    if p is None:
        return out
    out["references"] = list_references(SKILL)
    return out


@router.get("/api/nsfw-templates/index")
def get_index(module: str = "01") -> Dict[str, Any]:
    """抽某个模块的索引表，供前端展示章节。"""
    m = next((x for x in MODULES if x["id"] == module), None)
    if not m:
        raise HTTPException(status_code=400, detail=f"未知模块 {module}，可选 01~14")
    text = read_reference(SKILL, m["file"], max_chars=80000)
    return {
        "module": m["id"],
        "slot": m["slot"],
        "index": extract_md_index(text),
        "length": len(text),
    }


@router.get("/api/nsfw-templates/module")
def get_module(module: str = "01", max_chars: int = 0) -> Dict[str, Any]:
    """读取某个模块的完整内容。"""
    m = next((x for x in MODULES if x["id"] == module), None)
    if not m:
        raise HTTPException(status_code=400, detail=f"未知模块 {module}，可选 01~14")
    text = read_reference(SKILL, m["file"], max_chars=max_chars)
    return {"module": m["id"], "slot": m["slot"], "file": m["file"], "text": text, "length": len(text)}


_REFUSAL_MARKERS = (
    "sorry", "i can't", "i cannot", "cannot respond",
    "无法响应", "我不便", "不便协助", "不会按", "这类内容", "该请求", "这个请求", "抱歉",
)


def _looks_refusal(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    low = t.lower()
    if any(m in low for m in _REFUSAL_MARKERS):
        return True
    # 同时命中多个元话语 + 篇幅短 → 多半在解释「我不按这个来」
    meta = sum(1 for m in ("提示词", "模板", "输出", "该", "上述") if m in t)
    return meta >= 2 and len(t) < 300


def _compose_from_slots(
    ordered: Dict[str, str],
    terms_data: Dict[str, Any],
    auto_slots: List[str],
) -> str:
    """代码拼装：按槽位顺序把值连成一段。

    【由你自选】的槽位，从该槽的词库里随机挑一个具体词条替换掉候选方向。
    """
    import random as _rnd

    parts: List[str] = []
    for slot, val in ordered.items():
        v = str(val or "").strip()
        if not v:
            continue
        if slot in auto_slots or v.startswith("【由你自选】"):
            info = terms_data.get(slot) or {}
            sections = info.get("sections") or {}
            pool: List[str] = []
            for terms in sections.values():
                pool.extend([t for t in (terms or []) if t])
            if pool:
                v = _rnd.choice(pool)
            else:
                # 没词条就跳过这一槽
                continue
        parts.append(v)

    if not parts:
        return ""
    # 用逗号连成一段，末尾加句号
    body = "，".join(p.strip("。，,") for p in parts)
    return body + "。"


@router.post("/api/nsfw-templates/assemble")
def assemble(req: Dict[str, Any]) -> Dict[str, Any]:
    """按组装顺序拼装一条提示词。

    设计取舍：**词条必须由用户从模块里挑，代码不自动抽**。
    这个 skill 的 markdown 里混着章节标题、联动说明、索引表，
    自动抽词会抽到「信号词」「开始/进入」这类非词条内容。
    所以这里要求 `slots` 至少填一个槽，代码只负责排序与串联。
    """
    _skill_or_503()
    theme = str(req.get("theme") or "").strip()
    slots: Dict[str, str] = req.get("slots") or {}
    optional: List[str] = req.get("optional") or []
    count = int(req.get("count") or 1)
    if count < 1 or count > 20:
        raise HTTPException(status_code=400, detail="条数需在 1~20 之间")

    # 过滤空槽
    filled = {k: str(v).strip() for k, v in slots.items() if str(v or "").strip()}

    # 人种 / 年龄 / 身材 / 气质（四个 skill 通用）—— 作为额外槽位并入组装
    ethnicity = PO.pick_ethnicity(str(req.get("ethnicity") or ""))
    age = PO.pick_age(str(req.get("age") or ""))
    body = str(req.get("body") or "").strip()
    vibe = str(req.get("vibe") or "").strip()
    if ethnicity:
        filled["人种"] = ethnicity
    if age:
        filled["年龄"] = age
    if body:
        filled["身材"] = body
    if vibe:
        filled["气质"] = vibe

    # 画风（追加风格）：交给 nsfw_compose 放在整段最前面
    extra_style = str(req.get("extra_style") or "").strip()
    if extra_style:
        try:
            st = SO.pick(extra_style)
            if st:
                filled["画风"] = st.get("label") or extra_style
        except Exception:
            filled["画风"] = extra_style

    if not filled and not theme:
        raise HTTPException(
            status_code=400,
            detail="请至少选一个槽位词条（或填主题）。",
        )

    # ── 极速模式：纯代码拼装，不走 LLM ──
    # mode = "fast" → 用 nsfw_compose 的中文句式 + 英文词条拼装（0.01s）
    # mode = "llm"（默认）→ 走下面的 LLM 路径（4-6s，更通顺但有拒答风险）
    mode = str(req.get("mode") or "fast").strip().lower()
    if mode in ("fast", "code", "instant"):
        import nsfw_compose as NC

        # 槽位名映射：前端用的是模块名（场景主题/景别构图…），
        # nsfw_compose 用的是短名（场景/景别…），不映射会导致用户选的词全被忽略。
        SLOT_ALIAS = {
            "场景主题": "场景",
            "景别构图": "景别",
            "裸露液体": "裸露",      # 原槽混着裸露与液体，优先当裸露
            "服装专项": "服装",
            "光影氛围": "光影",
            "姿势动作": "姿态",
            "表情眼神": "表情",
            "风格胶片": "风格",
            "妆容专项": "妆容",
            "发型饰品": "发型",
            "瑕疵细节": "瑕疵",
            "纹身标记": "纹身",
            "道具宠物": "道具",
            "人格卡片": "身份",
        }
        want: Dict[str, str] = {}
        for k, v in filled.items():
            key = SLOT_ALIAS.get(k, k)
            # 同一目标槽已有值就不覆盖（比如先填了「场景主题」又填了「场景」）
            if key not in want and str(v or "").strip():
                want[key] = str(v).strip()

        items_fast: List[Dict[str, Any]] = []
        base_seed = req.get("seed")
        for i in range(count):
            seed_i = None
            if base_seed not in (None, "", "random"):
                try:
                    seed_i = int(base_seed) + i
                except (TypeError, ValueError):
                    seed_i = None
            r = NC.compose_random(seed=seed_i, want=want, fill_missing=True)
            _fast_prompt = r["prompt"]
            # 机位构图（极速模式也要生效）
            _fast_shot = str(req.get("shot") or "").strip()
            if _fast_shot:
                _fast_prompt = SH.apply(_fast_prompt, _fast_shot)
            items_fast.append({
                "index": i + 1,
                "prompt": _fast_prompt,
                "elements": r["elements"],
                "kinds": r["kinds"],
            })
        return {
            "ok": True,
            "count": len(items_fast),
            "items": items_fast,
            "llm_used": False,
            "mode": "fast",
            "modules_used": [],
            "ordered_slots": list(want.keys()),
            "auto_slots": [],
        }

    use_modules = [m for m in MODULES if m["required"]]
    for slot in optional:
        m = next((x for x in MODULES if x["slot"] == slot and not x["required"]), None)
        if m:
            use_modules.append(m)

    # 按模块顺序排列用户填的词
    ordered: Dict[str, str] = {}
    if theme:
        ordered["场景主题"] = theme if "场景主题" not in filled else f"{theme}，{filled.pop('场景主题')}"
    for m in use_modules:
        if m["slot"] in filled:
            ordered[m["slot"]] = filled[m["slot"]]
    # 补上不在标准槽位里的自定义项
    for k, v in filled.items():
        if k not in ordered:
            ordered[k] = v

    # ── 「不填 / 由模型自选」的槽位：给模型该槽的候选方向，让它自己挑 ──
    # 之前这里直接把空槽跳过，模型收不到任何提示，等于没选。
    terms_data = _load_terms()
    auto_slots: List[str] = []
    for m in use_modules:
        slot = m["slot"]
        if slot in ordered:
            continue
        info = terms_data.get(slot) or {}
        sections = info.get("sections") or {}
        if not sections:
            continue
        # 从每个小节抽 2-3 条候选，拼成「可选方向」
        hints: List[str] = []
        for sec, terms in list(sections.items())[:8]:
            pick = [t for t in (terms or [])[:3] if t]
            if pick:
                hints.append(f"{sec}: {' / '.join(pick)}")
        if hints:
            auto_slots.append(slot)
            ordered[slot] = "【由你自选】参考方向 → " + "；".join(hints[:6])

    lines = "\n".join(f"{slot}：{val}" for slot, val in ordered.items())
    system = (
        "你是中文提示词串联器。把给定的词条按顺序连成一条通顺、连贯的中文图像提示词。"
        "标了【由你自选】的槽位，你要从它给的参考方向里挑一个最协调的词条用进去。"
        "只输出提示词正文，不要任何分析、解释、分点或 Markdown。"
    )
    user = f"""把下面这些词条按顺序连成一条通顺的中文提示词（可适当加连接词，保持信息完整）：

{lines}

直接输出提示词正文。"""
    if auto_slots:
        user += (
            f"\n\n注意：{'、'.join(auto_slots)} 这几槽是【由你自选】，"
            "必须从各自的参考方向里挑一个具体词条用进去，不能省略、不能原样照抄「由你自选」四个字。"
        )
    if count > 1:
        user += f"\n\n请输出 {count} 条不同组合的版本，每条一行，格式 `1. 正文`。"

    text = ""
    llm_used = True
    try:
        text = strip_code_fence(
            llm_chat_with_retry(system, user, max_tokens=3000, temperature=0.85, timeout=180)
        )
    except Exception:
        text = ""

    if not text or _looks_refusal(text):
        # 模型拒答 / 空返回 → 代码按槽位顺序直接拼一条。
        # 每个槽位的值已经在 ordered 里（含【由你自选】的候选方向），
        # 这里改成从候选中随机挑一个具体词条。
        llm_used = False
        text = _compose_from_slots(ordered, terms_data, auto_slots)

    items: List[Dict[str, Any]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or len(s) < 8:
            continue
        s = re.sub(r"^\s*\d+[.、)]\s*", "", s)
        s = re.sub(r"^\s*[-*]\s*", "", s)
        items.append({"index": len(items) + 1, "prompt": s})
    if not items:
        items = [{"index": 1, "prompt": text}]

    # 追加画风（只加开头/结尾，不改其他）
    _extra_style = str(req.get("extra_style") or "")
    if _extra_style:
        for it in items:
            it["prompt"] = SO.apply(it.get("prompt") or "", _extra_style)

    # 机位构图（追加到末尾）
    _shot = str(req.get("shot") or "").strip()
    if _shot:
        for it in items:
            it["prompt"] = SH.apply(it.get("prompt") or "", _shot)

    return {
        "ok": True,
        "count": len(items),
        "items": items,
        "llm_used": llm_used,
        "modules_used": [f"{m['id']} {m['slot']}" for m in use_modules],
        "ordered_slots": ordered,
        # 用户选了「由模型自选」的槽位 —— 已把候选方向交给模型自己挑
        "auto_slots": auto_slots,
        "raw": text,
    }


@router.post("/api/nsfw-templates/expand")
def expand(req: Dict[str, Any]) -> Dict[str, Any]:
    """把一条简短想法扩写成完整提示词。

    不自动抽词（词库混杂），而是把该模块的**索引章节**给模型，
    让它按主题自己挑合适的章节方向再扩写。
    """
    _skill_or_503()
    idea = str(req.get("idea") or "").strip()
    if not idea:
        raise HTTPException(status_code=400, detail="请填写想法")

    # 只给索引（章节名 + 说明），不给整份词库正文
    idx_lines: List[str] = []
    for m in MODULES:
        if not m["required"]:
            continue
        try:
            text = read_reference(SKILL, m["file"], max_chars=20000)
        except Exception:
            continue
        rows = extract_md_index(text)
        if rows:
            chapters = "、".join(r["chapter"] for r in rows[:30])
            idx_lines.append(f"{m['slot']}（可选方向）：{chapters}")

    idx_block = "\n".join(idx_lines)

    system = (
        "你是中文提示词写手。根据给定方向，写一条通顺、连贯、可直接生图的中文提示词。"
        "只输出提示词正文，不要任何分析、解释、分点或 Markdown。"
    )
    user = f"""想法：{idea}

可参考的方向（按槽位）：
{idx_block}

请按「场景 → 景别构图 → 裸露状态 → 服装状态 → 光影 → 姿势 → 表情 → 画质」的顺序，
写一条完整的中文提示词。直接输出正文。"""
    text = strip_code_fence(
        llm_chat_with_retry(system, user, max_tokens=3000, temperature=0.85, timeout=180)
    )
    if not text:
        raise HTTPException(status_code=502, detail="LLM 未产出内容")
    return {"ok": True, "prompt": text, "raw": text}
