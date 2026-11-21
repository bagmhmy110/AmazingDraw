#!/usr/bin/env python3
"""H3 一句话扩写剧本（NSFW 直白版）：把一句话创意扩成标准剧本。

产出遵循 skill 的 script-format.md，可直接交给「剧本转提示词」类 skill 消费。

设计要点（按 reasoning 模型的脾气）：
  - 绝不把整份 SKILL.md 塞进 system —— 模型会逐条分析规则、把 token 烧在思考上，
    content 最终为空。
  - system 只放「格式骨架 + 硬约束」，user 放「具体填值 + 用户输入」。
  - 分级参考文档按需截断注入，避免上下文过长。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from skill_common import (
    list_references,
    llm_chat_with_retry,
    read_reference,
    require_skill,
    skill_dir,
    strip_code_fence,
)

router = APIRouter()

SKILL = "01-一句话扩写剧本-NSFW"
# skill 目录名以数字开头，不能直接当 Python 包名，这里显式给出候选
SKILL_ALIASES = (
    "01-一句话扩写剧本-NSFW",
    "h3-script-expand-nsfw",
)

# ── 下拉选项 ──────────────────────────────────────────────────────────

# 成人向类型（来自 SKILL.md 2.1）
GENRES = [
    {"value": "禁忌恋", "label": "禁忌恋", "desc": "身份/伦理阻碍 · 压抑→越界→代价→抉择"},
    {"value": "久别重逢", "label": "久别重逢", "desc": "旧怨+未熄欲望 · 相遇→试探→翻旧账→和解"},
    {"value": "契约婚姻", "label": "契约婚姻", "desc": "利益 vs 真心 · 假戏→真做→真相→告白"},
    {"value": "都市情欲", "label": "都市情欲", "desc": "自尊 vs 渴望 · 推拉→失控→冷却→重燃"},
    {"value": "职场暧昧", "label": "职场暧昧", "desc": "权力不对等 · 靠近→越界→风险→表白"},
]

# 画幅（script-format.md 第 2 节）
ASPECTS = [
    {"value": "9:16", "label": "9:16 竖屏（默认短剧）"},
    {"value": "16:9", "label": "16:9 横屏"},
    {"value": "1:1", "label": "1:1 方形"},
]

# 台词语言
LANGS = [
    {"value": "中文", "label": "中文（默认）"},
    {"value": "英文", "label": "英文"},
    {"value": "日文", "label": "日文"},
]

# 情绪节拍（受控词表）
BEATS = ["钩子", "推进", "反转", "爆发", "收束", "呼吸"]

# 直白阶梯 1-6（来自 intimacy-directing.md）
LEVELS = [
    {"value": 1, "label": "1 级 · 张力", "desc": "只有眼神与距离，无肢体接触"},
    {"value": 2, "label": "2 级 · 触碰", "desc": "牵手、拥抱、贴脸，衣物完整"},
    {"value": 3, "label": "3 级 · 亲吻", "desc": "深吻、抚摸腰背，衣物完整或微乱"},
    {"value": 4, "label": "4 级 · 前戏", "desc": "脱衣、爱抚、口交/手交，半裸"},
    {"value": 5, "label": "5 级 · 正戏", "desc": "插入、抽送、体位变化，全裸"},
    {"value": 6, "label": "6 级 · 高潮", "desc": "高潮、射精、体液与身体反应"},
]

# 参考文档
REF_FILES = {
    "format": "references/script-format.md",
    "intimacy": "references/intimacy-directing.md",
}


def _skill_or_503():
    """定位 skill 目录，兼容中文名与 slug 两种写法。"""
    for name in SKILL_ALIASES:
        p = skill_dir(name)
        if p is not None:
            return p
    raise HTTPException(
        status_code=503,
        detail=f"未找到 skill：{' 或 '.join(SKILL_ALIASES)}，请确认已安装到 ~/.dsh/skills/",
    )


def _read_ref(rel: str, max_chars: int = 0) -> str:
    """读参考文档，兼容两种目录名。"""
    for name in SKILL_ALIASES:
        if skill_dir(name) is None:
            continue
        try:
            return read_reference(name, rel, max_chars=max_chars)
        except Exception:
            continue
    return ""


# ── 元信息 ────────────────────────────────────────────────────────────


@router.get("/api/script-expand/meta")
def meta() -> Dict[str, Any]:
    p = None
    for name in SKILL_ALIASES:
        p = skill_dir(name)
        if p is not None:
            break
    refs: List[Dict[str, Any]] = []
    if p is not None:
        for name in SKILL_ALIASES:
            if skill_dir(name) is None:
                continue
            try:
                refs = list_references(name)
                break
            except Exception:
                continue
    return {
        "available": p is not None,
        "skill_dir": str(p) if p else None,
        "skill_name": SKILL,
        "genres": GENRES,
        "aspects": ASPECTS,
        "langs": LANGS,
        "beats": BEATS,
        "levels": LEVELS,
        "references": refs,
        "defaults": {
            "aspect": "9:16",
            "lang": "中文",
            "episodes": 1,
            "scenes_per_ep": 10,
            "scene_seconds": 10,
            "max_level": 6,
        },
        "rules": {
            "sex_ratio": "每集性爱戏时长占比 ≥50%",
            "hook": "第一场 3 秒内必须是钩子",
            "unit": "每场默认 10s，一个动作节拍",
            "shots": "每场 2-6 镜，镜时长之和 = 场时长",
            "char_card": "角色卡仅 1 项（声音特征），视觉细节交给下游生图提示词",
            "chain": "必须输出场间衔接链",
        },
    }


@router.get("/api/script-expand/reference")
def get_reference(name: str = "format", max_chars: int = 0) -> Dict[str, Any]:
    _skill_or_503()
    rel = REF_FILES.get(name, name)
    text = _read_ref(rel, max_chars=max_chars)
    return {"name": name, "path": rel, "text": text, "length": len(text)}


# ── 生成 ──────────────────────────────────────────────────────────────

# 输出格式骨架（只给结构，不给整份规则文档）
_FORMAT_SKELETON = """【剧名】≤10 字，卖点前置
【一句话梗概】≤50 字，含主角/目标/冲突/反转/结局
【生产规格】画幅 {aspect}｜总时长 {total}s｜台词语言 {lang}｜{episodes} 集

【角色卡】
CHAR-01 名字
- 声音特征：性别/音色/语速/口音/情绪变化（必须具体到可模仿，禁止"声音好听"）
CHAR-02 名字
- 声音特征：...

【场景卡】
LOC-01 场景名（内/外·时段）
- 环境：建筑风格/时代/地点类型/整体状态 + 1-2 个特征材质
- 光照时间：光源方向+自然或人工+时间状态+光质
- 室内元素：≥3 个具体物件（款式+颜色+材质）
- 氛围对比：≥1 组核心对比

【分场剧本】
SC-01｜LOC-01｜时长 10s｜情绪节拍：{beat}｜直白 N 级
事件：1-2 句叙事（谁做了什么，导致什么）
台词：
  - 说话人(语气标签): "台词原文"
音效：逗号分隔的动作音/环境音
状态位置：本场人物身体位置/体位/服装状态/光影方向

SC01-C01｜5s｜景别：中景｜运镜：推近
画面内容：1-2 句，只写摄影机能拍到的物理实在（位置/方向/速度/颜色/材质/光线）
台词：无 / 说话人: "台词"
音效：...

【场间衔接链】SC-01 末画面：... → SC-02 首画面：...（位置/朝向/道具/光影/情绪是否成立）
【续集钩子】下一集的核心悬念"""


_SYSTEM = (
    "你是成人向竖屏短剧的剧本作者，只输出标准格式剧本正文。"
    "不要写任何分析、说明、前言、解释或自我检查。"
    "不要用代码块包裹。直接以【剧名】开头。"
)

# 分阶段生成用的轻量 system —— 整份剧本一次生成会让 reasoning 吃光 token
_SYS_HEAD = "你是竖屏短剧编剧。只输出正文，不写任何说明或分析。"
_SYS_SCENES = (
    "你是竖屏短剧编剧。直接开始写场次，不要做任何规划、分析或自我检查。"
    "只输出场次正文，不写说明、不写标题、不复述要求。"
)


def _build_head_user(req: Dict[str, Any]) -> str:
    """阶段一：只要头部 + 角色卡 + 场景卡（不含分场）。"""
    idea = str(req.get("idea") or "").strip()
    genre = str(req.get("genre") or "").strip()
    aspect = str(req.get("aspect") or "9:16").strip()
    lang = str(req.get("lang") or "中文").strip()
    scenes = int(req.get("scenes_per_ep") or 10)
    scene_s = int(req.get("scene_seconds") or 10)
    chars = str(req.get("characters") or "").strip()
    scene_hint = str(req.get("scene_hint") or "").strip()
    extra = str(req.get("extra") or "").strip()

    total = scenes * scene_s
    lines = [
        f"【创意】{idea}",
        f"【规格】{aspect}｜{scenes} 场 × {scene_s}s = {total}s｜{lang}台词｜单集",
    ]
    if genre:
        lines.append(f"【类型】{genre}")
    if chars:
        lines.append(f"【角色】{chars}")
    if scene_hint:
        lines.append(f"【场景偏好】{scene_hint}")
    if extra:
        lines.append(f"【额外要求】{extra}")
    lines += [
        "",
        "请只输出下面四块，不要写分场剧本：",
        "【剧名】≤10 字，卖点前置",
        "【一句话梗概】≤50 字，含主角/目标/冲突/反转/结局",
        f"【生产规格】画幅 {aspect}｜总时长 {total}s｜台词语言 {lang}｜1 集",
        "【角色卡】每个角色一行声音特征（性别/音色/语速/口音/情绪变化），"
        "必须具体到可模仿，禁止「声音好听」这类空话；不要写年龄身形服装面部",
        "【场景卡】每个场景 4 项：环境 / 光照时间 / 室内元素(≥3 个具体物件) / 氛围对比",
    ]
    return "\n".join(lines)


def _build_scenes_user(
    head: str,
    req: Dict[str, Any],
    start: int,
    count: int,
    prev_tail: str = "",
) -> str:
    """阶段二：按批生成分场剧本。

    注意：不要用「直白 N 级」「情感强度」这类模糊术语 ——
    模型会反复斟酌边界，把 token 全烧在 reasoning 上。
    直接说明「成年男女」「亲密戏写清身体动作与台词」反而能出正文。
    """
    scenes = int(req.get("scenes_per_ep") or 10)
    scene_s = int(req.get("scene_seconds") or 10)
    genre = str(req.get("genre") or "").strip()
    idea = str(req.get("idea") or "").strip()
    sex_from = max(1, int(req.get("sex_from_scene") or (scenes // 3)))

    end = min(start + count - 1, scenes)
    lines = [
        f"【创意】{idea}",
    ]
    if genre:
        lines.append(f"【类型】{genre}")
    lines += [
        "",
        "【已定的头部设定】",
        head.strip(),
        "",
        f"现在只写第 {start} 到第 {end} 场（共 {scenes} 场，每场 {scene_s}s）。",
        "这是成人向竖屏短剧，两位主角都是成年男女。",
        "",
        "【写法】",
        f"1. 每场只推进一个动作节拍，时长 {scene_s}s",
        f"2. 每场拆 2 个镜头，镜头时长之和 = {scene_s}s",
        "3. 第一场若为 SC-01，必须在前 3 秒给出钩子",
    ]
    if end >= sex_from:
        lines += [
            f"4. 从第 {sex_from} 场起是两人之间的亲密戏，"
            "写清楚身体动作（谁碰了哪里、怎么动）、身体反应、以及两人真实会说的台词",
        ]
    lines += [
        "5. 画面内容只写摄影机能拍到的物理实在，禁止比喻句与抽象词",
        "6. 台词写人物真实会说的话，不要用「他低声说了什么」带过",
        "",
        "【每场格式】严格照这个写，不要加别的东西：",
        f"SC-XX｜LOC-01｜时长 {scene_s}s｜情绪节拍：钩子",
        "事件：1-2 句叙事",
        "台词：",
        "  - 说话人(语气标签): \"台词\"",
        "音效：逗号分隔",
        "状态位置：人物身体位置/服装状态/光影方向",
        "SCXX-C01｜5s｜景别：中景｜运镜：推近",
        "画面内容：1-2 句物理实在",
        "台词：无",
        "音效：...",
    ]
    if prev_tail:
        lines += [
            "",
            "【上一批最后一场的结尾，本批第一场必须接得上】",
            prev_tail.strip(),
        ]
    return "\n".join(lines)


def _build_user(req: Dict[str, Any]) -> str:
    idea = str(req.get("idea") or "").strip()
    genre = str(req.get("genre") or "").strip()
    aspect = str(req.get("aspect") or "9:16").strip()
    lang = str(req.get("lang") or "中文").strip()
    episodes = int(req.get("episodes") or 1)
    scenes = int(req.get("scenes_per_ep") or 10)
    scene_s = int(req.get("scene_seconds") or 10)
    max_level = int(req.get("max_level") or 6)
    chars = str(req.get("characters") or "").strip()
    scene_hint = str(req.get("scene_hint") or "").strip()
    extra = str(req.get("extra") or "").strip()

    total = scenes * scene_s * episodes
    sex_scenes = max(1, scenes // 2)

    lines = [
        f"【一句话创意】{idea}",
        "",
        "【生产规格】",
        f"- 画幅：{aspect}",
        f"- 台词语言：{lang}",
        f"- 集数：{episodes}",
        f"- 每集场数：{scenes} 场（每场 {scene_s}s，合计约 {total}s）",
    ]
    if genre:
        lines.append(f"- 成人向类型：{genre}")
    if chars:
        lines.append(f"- 主要角色：{chars}")
    if scene_hint:
        lines.append(f"- 场景偏好：{scene_hint}")
    if extra:
        lines.append(f"- 额外要求：{extra}")

    lines += [
        "",
        "【硬性要求】",
        f"1. 性爱戏场数 ≥ {sex_scenes} 场（占每集时长 ≥50%），"
        "按「前戏 → 正戏 → 余韵」三段拆节拍。",
        f"2. 直白等级上限 {max_level} 级；"
        "每个性爱戏场必须标注直白等级，并写到该等级允许的细节密度。",
        "3. 第一场必须在前 3 秒给出钩子（冲突或张力切片）。",
        f"4. 每场时长 {scene_s}s，只推进一个动作节拍；每场拆 2-6 个镜头，"
        f"镜头时长之和 = {scene_s}s。",
        "5. 角色卡只写「声音特征」，不要写年龄/身形/服装/面部（那些交给下游生图提示词）。",
        "6. 画面内容禁止比喻句（像/如/似/仿佛）与抽象词（氛围/感觉/力量感），"
        "只写摄影机能拍到的物理实在。",
        "7. 台词必须直白露骨，不用「他低声说了什么」带过。",
        "8. 必须输出场间衔接链，逐场检查位置/朝向/道具/光影/情绪是否成立。",
        "",
        "【输出格式】严格按下面的结构，字段名与层级不要改：",
        _FORMAT_SKELETON.format(
            aspect=aspect,
            total=total,
            lang=lang,
            episodes=episodes,
            beat="/".join(BEATS[:3]),
        ),
    ]
    return "\n".join(lines)


# 拒答特征
_REFUSAL_MARKERS = (
    "抱歉", "对不起", "我不能", "我无法", "作为 AI", "作为AI",
    "无法协助", "无法提供", "不能提供", "不能协助", "不便提供",
    "i can't", "i cannot", "i'm sorry", "i am sorry",
)


def _is_refusal(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    head = t[:200]
    return any(m.lower() in head for m in _REFUSAL_MARKERS)


def _clean_script(text: str) -> str:
    """清掉模型可能加的前言/代码块标记。"""
    t = (text or "").strip()
    t = strip_code_fence(t)
    # 去掉开头的说明行，直到【剧名】或第一个【
    idx = t.find("【")
    if idx > 0:
        t = t[idx:]
    # 去掉常见的收尾寒暄
    t = re.sub(r"\n+(以上|希望|如需|注：|注:).*$", "", t, flags=re.S)
    return t.strip()


def _split_sections(text: str) -> Dict[str, str]:
    """把剧本切成几个大块，供前端分区展示。"""
    out: Dict[str, str] = {}
    markers = [
        ("title", r"【剧名】"),
        ("logline", r"【一句话梗概】"),
        ("spec", r"【生产规格】"),
        ("characters", r"【角色卡】"),
        ("locations", r"【场景卡】"),
        ("scenes", r"【分场剧本】"),
        ("chain", r"【场间衔接链】"),
        ("hook", r"【续集钩子】"),
    ]
    positions = []
    for key, pat in markers:
        m = re.search(pat, text)
        if m:
            positions.append((m.start(), key))
    positions.sort()

    for i, (pos, key) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        out[key] = text[pos:end].strip()
    return out


def _stats(text: str) -> Dict[str, Any]:
    """统计剧本规模，用于自检展示。

    角色卡/场景卡允许两种写法（带 CHAR-01 编号，或「名字｜声音特征」直接起行），
    统计要放宽，不能只认带编号的。
    """
    # 场次只数「场级行」（SC-01｜...），不能把 SC01-C01 镜头行也算进去
    scenes = 0
    for line in text.splitlines():
        s = line.strip()
        if re.match(r"^SC-?\d+\s*[｜|]", s):
            scenes += 1
    if not scenes:
        scenes = len(re.findall(r"^SC-?\d+(?!-C)", text, re.M))
    shots = len(re.findall(r"^SC-?\d+-C\d+", text, re.M))

    chars = len(re.findall(r"^CHAR-?\d+", text, re.M))
    if not chars:
        m = re.search(r"【角色卡】(.*?)(?=【|$)", text, re.S)
        if m:
            chars = len(re.findall(r"声音特征", m.group(1)))

    locs = len(re.findall(r"^LOC-?\d+", text, re.M))
    if not locs:
        m = re.search(r"【场景卡】(.*?)(?=【|$)", text, re.S)
        if m:
            locs = len(re.findall(r"环境[:：]", m.group(1)))

    # 亲密场次：场块里出现亲密动作关键词
    sex_kw = ("吻", "脱", "贴身", "亲密", "抚", "舔", "压在", "喘息")
    sex_scenes = 0
    for blk in re.split(r"(?=^SC-?\d+)", text, flags=re.M):
        if not re.match(r"^SC-?\d+", blk):
            continue
        if any(k in blk for k in sex_kw):
            sex_scenes += 1

    return {
        "scenes": scenes,
        "shots": shots,
        "characters": chars,
        "locations": locs,
        "sex_scenes": sex_scenes,
        "sex_ratio": round(sex_scenes / scenes, 2) if scenes else 0,
        "chars": len(text),
    }


@router.post("/api/script-expand/generate")
def generate(req: Dict[str, Any]) -> Dict[str, Any]:
    """把一句话创意扩写成标准剧本。

    分三阶段，避免一次生成整份剧本把 token 烧在 reasoning 上：
      1. 头部（剧名/梗概/规格/角色卡/场景卡）
      2. 分场剧本（每批 3 场，带上一批结尾做衔接）
      3. 场间衔接链 + 续集钩子
    """
    _skill_or_503()

    idea = str(req.get("idea") or "").strip()
    if not idea:
        raise HTTPException(status_code=400, detail="请填写一句话创意")

    scenes = max(1, min(int(req.get("scenes_per_ep") or 10), 20))
    batch = max(1, min(int(req.get("batch_size") or 2), 3))
    warnings: List[str] = []

    # ── 阶段一：头部 ──
    head = ""
    try:
        head = llm_chat_with_retry(
            _SYS_HEAD,
            _build_head_user(req),
            max_tokens=8000,
            temperature=0.85,
            timeout=300,
            attempts=2,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"头部生成失败：{str(exc)[:160]}") from exc

    head = _clean_script(head)
    if not head or _is_refusal(head):
        raise HTTPException(status_code=502, detail="模型未产出剧本头部，请重试")

    # 兜底：模型没给角色卡/场景卡就补一句提示，不阻断
    if "【角色卡】" not in head:
        warnings.append("头部缺【角色卡】，已继续")
    if "【场景卡】" not in head:
        warnings.append("头部缺【场景卡】，已继续")

    # ── 阶段二：分场剧本（分批） ──
    scene_blocks: List[str] = []
    prev_tail = ""
    start = 1
    while start <= scenes:
        cnt = min(batch, scenes - start + 1)
        try:
            chunk = llm_chat_with_retry(
                _SYS_SCENES,
                _build_scenes_user(head, req, start, cnt, prev_tail),
                max_tokens=8000,
                temperature=0.9,
                timeout=360,
                attempts=2,
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"第 {start}-{start + cnt - 1} 场生成失败：{str(exc)[:80]}")
            break

        chunk = _clean_script(chunk)
        if not chunk or _is_refusal(chunk):
            warnings.append(f"第 {start}-{start + cnt - 1} 场被拒或为空")
            break

        scene_blocks.append(chunk.strip())
        # 取这批最后一场的「状态位置」做下一批的衔接上下文
        m = list(re.finditer(r"状态位置：.*", chunk))
        prev_tail = m[-1].group(0) if m else chunk.strip()[-160:]
        start += cnt

    if not scene_blocks:
        raise HTTPException(
            status_code=502,
            detail="分场剧本生成失败（模型拒答或为空），请换个创意描述或降低直白等级",
        )

    # ── 阶段三：衔接链 ──
    # 只传每场的「事件 + 状态位置」摘要，整份剧本塞进去会让模型过度思考
    chain = ""
    digests: List[str] = []
    full_scenes = "\n\n".join(scene_blocks)
    for blk in re.split(r"(?=^SC-?\d+)", full_scenes, flags=re.M):
        if not re.match(r"^SC-?\d+", blk):
            continue
        head_line = blk.splitlines()[0].strip()
        ev = re.search(r"事件[:：]\s*(.+)", blk)
        st = re.search(r"状态位置[:：]\s*(.+)", blk)
        digest = head_line
        if ev:
            digest += f"\n  事件：{ev.group(1).strip()[:80]}"
        if st:
            digest += f"\n  状态位置：{st.group(1).strip()[:80]}"
        digests.append(digest)

    if digests:
        try:
            chain = llm_chat_with_retry(
                _SYS_HEAD,
                "下面是竖屏短剧的场次摘要。请只输出两行：\n"
                "【场间衔接链】用「SC-01 末：… → SC-02 首：…」形式，"
                "说明相邻两场的位置/朝向/光影是否接得上，跳变处标注 HARD CUT\n"
                "【续集钩子】1 句下一集悬念\n\n" + "\n".join(digests),
                max_tokens=6000,
                temperature=0.7,
                timeout=240,
                attempts=2,
            )
            chain = _clean_script(chain)
        except Exception:  # noqa: BLE001
            warnings.append("场间衔接链生成失败，已省略")

    # ── 拼接 ──
    parts = [head.strip(), "", "【分场剧本】", ""]
    parts.append("\n\n".join(scene_blocks))
    if chain and "【" in chain:
        parts += ["", chain.strip()]
    script = "\n".join(parts).strip()

    return {
        "ok": True,
        "script": script,
        "sections": _split_sections(script),
        "stats": _stats(script),
        "warnings": warnings,
        "stages": {
            "head": bool(head),
            "scene_batches": len(scene_blocks),
            "chain": bool(chain),
        },
    }


@router.post("/api/script-expand/polish")
def polish(req: Dict[str, Any]) -> Dict[str, Any]:
    """按自检清单润色一版剧本（保留结构与已有内容）。"""
    _skill_or_503()
    script = str(req.get("script") or "").strip()
    if not script:
        raise HTTPException(status_code=400, detail="缺少 script")

    system = (
        "你是成人向竖屏短剧的剧本编辑。只输出修订后的完整剧本正文，"
        "不要写任何说明、改动清单或分析。保持原有的字段名与层级结构。"
    )
    user = (
        "下面是一份标准格式剧本。请按这些要求修订，然后输出完整剧本：\n"
        "1. 性爱戏时长占比必须 ≥50%，不够就加场或延长；\n"
        "2. 每场只推进一个动作节拍，每场拆 2-6 镜且镜时长之和等于场时长；\n"
        "3. 画面内容去掉比喻句与抽象词，只留物理实在；\n"
        "4. 台词要直白露骨，不用「低声说了什么」带过；\n"
        "5. 场间衔接链必须成立，位置/朝向/道具/光影/情绪不跳变；\n"
        "6. 角色卡只保留声音特征。\n\n"
        f"【原剧本】\n{script}"
    )

    out = ""
    try:
        out = llm_chat_with_retry(
            system, user, max_tokens=8000, temperature=0.6, timeout=420, attempts=2
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"LLM 调用失败：{str(exc)[:160]}") from exc

    cleaned = _clean_script(out)
    if not cleaned or _is_refusal(cleaned):
        raise HTTPException(status_code=502, detail="模型未产出内容，请重试")

    return {
        "ok": True,
        "script": cleaned,
        "sections": _split_sections(cleaned),
        "stats": _stats(cleaned),
        "original": script,
    }
