#!/usr/bin/env python3
"""国漫 / 东方女性人像提示词 API（guoman-portrait-prompts）。

四条风格线：A 写实CCD / B 二次元厚涂 / C 古风仙侠 / D 高定服装。
自带 generate.py 可批量产出，本模块直接调它。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
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
    python_exe,
    read_reference,
    require_skill,
    skill_dir,
    strip_code_fence,
)

router = APIRouter(tags=["guoman-portrait"])

SKILL = "guoman-portrait-prompts"


def _random_seed() -> int:
    """每次调用返回一个新种子，保证批量不复用同一套随机序列。"""
    import random as _random

    return _random.randint(1, 2**31 - 1)


# 四条风格线
LINES = [
    {
        "id": "B",
        "label": "二次元厚涂",
        "desc": "Wuthering Waves style · 御姐 · 国漫立绘 · 旗袍礼裙",
        "hint": "主力线。以 `Wuthering Waves style二次元半写实厚涂，竖屏构图。` 开头",
        "words": "100-180 字",
        "age": "25-30 岁成熟御姐",
    },
    {
        "id": "C",
        "label": "古风仙侠",
        "desc": "仙侠 · 古风 · 国风 · 汉服 · 敦煌 · 神女 · 女侠",
        "hint": "服装结构密度最高，250-420 字",
        "words": "250-420 字",
        "age": "成年仙侠女子",
    },
    {
        "id": "A",
        "label": "写实 CCD",
        "desc": "写实 · CCD 旧照片 · 千禧年 · 学生 · 老师 · 生活流",
        "hint": "生活化抓拍感，避免影楼摆拍",
        "words": "120-200 字",
        "age": "20-30 岁日常女性",
    },
    {
        "id": "D",
        "label": "高定服装",
        "desc": "只要衣服 · 服装设定 · 高定设计 · 角色服装方案",
        "hint": "纯服装描述，不写人物面部",
        "words": "150-250 字",
        "age": "无人物",
    },
] + [
    # ── 追加画风（与四条线并列，同一套词池）──
    {"id": s["value"], "label": s["label"], "desc": s["desc"],
     "hint": s["open"], "words": "100-200 字", "age": "成年女性",
     "_style": s}
    for s in SO.EXTRA_STYLES
]

# 露腿分级
LEG_LEVELS = [
    {"value": "none", "label": "不露腿", "desc": "完全不提腿"},
    {"value": "mild", "label": "含蓄", "desc": "只给裙裾下的腿部线条"},
    {"value": "bold", "label": "大胆", "desc": "高开叉至大腿根部，露出修长双腿"},
]

REF_FILES = {
    "04": "references/04-硬性规则与禁词.md",
    "05": "references/05-风格线骨架.md",
    "06": "references/06-选词与去重.md",
    "07": "references/07-扩写方法与模型链.md",
    "01": "references/01-选词库-十一分类.txt",
    "02": "references/02-国漫服装词库-1200.txt",
    "03": "references/03-仙侠范例31条.txt",
    "08": "references/08-国漫高定服装母模板.txt",
}

# 词池缓存（由 build_guoman_portrait_pools.py 从 skill 的 generate.py 抽出）
_POOLS_CACHE = Path(__file__).resolve().parent / "guoman_portrait_pools.json"
_pools_memo: Optional[Dict[str, Any]] = None


def _load_pools() -> Dict[str, Any]:
    global _pools_memo
    if _pools_memo is not None:
        return _pools_memo
    if not _POOLS_CACHE.is_file():
        _pools_memo = {}
        return _pools_memo
    try:
        _pools_memo = json.loads(_POOLS_CACHE.read_text(encoding="utf-8"))
    except Exception:
        _pools_memo = {}
    return _pools_memo


def _skill_or_503() -> Path:
    return require_skill(SKILL)


@router.get("/api/guoman-portrait/meta")
def meta() -> Dict[str, Any]:
    p = skill_dir(SKILL)
    pools = _load_pools()
    out: Dict[str, Any] = {
        "available": p is not None,
        "skill_dir": str(p) if p else None,
        "lines": LINES,
        "leg_levels": LEG_LEVELS,
        **PO.common_meta(),
        **SH.meta(),
        # 从 skill 的 generate.py 抽出的词池（年龄/气质/发型/性感/姿势/场景/服装）
        "pools": {
            "ages": pools.get("ages") or [],
            "tempers": pools.get("tempers") or [],
            "hairs": pools.get("hairs") or [],
            "sexy": pools.get("sexy") or [],
            "poses": pools.get("poses") or [],
            "scenes": pools.get("scenes") or [],
            "lights": pools.get("lights") or [],
            "outfits": pools.get("outfits") or {},
            "outfit_categories": pools.get("outfit_categories") or [],
            "stats": pools.get("stats") or {},
        },
        "references": [],
        "can_batch": False,
    }
    if p is None:
        return out
    out["references"] = list_references(SKILL)
    out["can_batch"] = (p / "scripts" / "generate.py").is_file()
    # 抽禁词表供前端提示
    try:
        rules = read_reference(SKILL, REF_FILES["04"], max_chars=20000)
        m = _extract_banned(rules)
        out["banned_words"] = m
    except Exception:
        out["banned_words"] = []
    return out


def _extract_banned(text: str) -> List[str]:
    """从 04 文件里抽禁词（``` 代码块里用 · 分隔的那一行）。"""
    words: List[str] = []
    for block in text.split("```"):
        if "·" in block and ("禁词" in block or len(block) < 200):
            for w in block.replace("\n", "·").split("·"):
                w = w.strip()
                if w and 1 < len(w) <= 12 and not w.startswith("#"):
                    words.append(w)
            if words:
                break
    return words[:20]


@router.get("/api/guoman-portrait/reference")
def get_reference(name: str, max_chars: int = 0) -> Dict[str, Any]:
    """按 key（04/05/06…）或相对路径读参考文件。"""
    rel = REF_FILES.get(name, name)
    text = read_reference(SKILL, rel, max_chars=max_chars)
    return {"name": name, "path": rel, "text": text, "length": len(text)}


@router.get("/api/guoman-portrait/index")
def get_index(name: str = "01") -> Dict[str, Any]:
    """抽某个 reference 的索引表。"""
    rel = REF_FILES.get(name, name)
    text = read_reference(SKILL, rel, max_chars=60000)
    return {"name": name, "path": rel, "index": extract_md_index(text)}


@router.post("/api/guoman-portrait/generate")
def generate(req: Dict[str, Any]) -> Dict[str, Any]:
    """单条生成：把骨架 + 规则喂给 LLM，产出提示词 + 元素拆解。"""
    _skill_or_503()
    # 原有四条线是单字母（B/C/A/D），追加画风是 snake_case，不能统一 upper()
    raw_line = str(req.get("line") or "B").strip()
    valid_ids = {x["id"] for x in LINES}
    if raw_line in valid_ids:
        line = raw_line
    elif raw_line.upper() in valid_ids:
        line = raw_line.upper()
    else:
        raise HTTPException(
            status_code=400,
            detail=f"未知风格 {raw_line}，可选：{'、'.join(sorted(valid_ids))}",
        )

    theme = str(req.get("theme") or "").strip()
    leg = str(req.get("leg") or "mild")
    extra = str(req.get("extra") or "").strip()
    pick = bool(req.get("pick", True))

    # 人种 / 年龄 / 身材 / 气质（四个 skill 通用）
    ethnicity = PO.pick_ethnicity(str(req.get("ethnicity") or ""))
    age = PO.pick_age(str(req.get("age") or ""))
    body = str(req.get("body") or "").strip()
    vibe = str(req.get("vibe") or "").strip()

    # 本 skill 专属词池：气质档 / 发型 / 性感级别 / 姿势 / 场景 / 服装
    temper = str(req.get("temper") or "").strip()
    hair = str(req.get("hair") or "").strip()
    sexy = str(req.get("sexy") or "").strip()
    pose = str(req.get("pose") or "").strip()
    scene = str(req.get("scene") or "").strip()
    light = str(req.get("light") or "").strip()
    outfit = str(req.get("outfit") or "").strip()
    outfit_cat = str(req.get("outfit_cat") or "").strip()

    # 只选了「服装类别」没选具体服装时，从该类别的池子里挑一件锁死
    # （否则类别被忽略，模型会自由发挥出别的品类）
    if outfit_cat and not outfit:
        try:
            import random as _r
            meta_pools = _load_pools()
            outfits_map = meta_pools.get("outfits") or {}
            bucket = outfits_map.get(outfit_cat) or []
            if bucket:
                pick = _r.choice(bucket)
                outfit = (pick.get("value") if isinstance(pick, dict) else str(pick)) or ""
        except Exception:
            pass

    line_meta = next(x for x in LINES if x["id"] == line)

    # 追加画风线：它们共用 B 线的骨架，只是开头/结尾换成该画风
    embedded_style = line_meta.get("_style") or None
    fill_line = "B" if embedded_style else line
    fill_meta = next(x for x in LINES if x["id"] == fill_line)

    # 关键：不要把整份规则文档塞给模型 —— 它会逐条分析规则、把 token 预算耗在思考上，
    # content 最终为空。改成「给句式模板 + 具体填值」，模型只需填充扩写。
    system = "你是中文图像提示词写手。只输出一段中文提示词正文，不要任何分析、解释、思考或复述规则。"
    user = _build_fill_prompt(fill_line, fill_meta, theme, extra, leg)

    # 画风线：模板里自带 B 线的固定开头（Wuthering Waves style…竖屏构图。），
    # 会和画风开头重复，明确要求模型不要写它。
    if embedded_style:
        user += (
            "\n【重要】开头不要写「Wuthering Waves style」「二次元半写实厚涂」"
            "「鸣潮风格」「竖屏构图」这些词，直接从人物年龄气质开始写。\n"
        )

    # 覆盖项：人种/年龄/身材/气质 + 本 skill 的六个词池
    override = []
    if ethnicity:
        override.append(f"人种：{ethnicity}（必须用肤色、眼型、发质等可见特征落地）")
    if age:
        override.append(f"年龄：{age}")
    if body:
        override.append(f"身材：{body}")
    if vibe:
        override.append(f"气质：{vibe}")
    if temper:
        override.append(f"人物类型：{temper}")
    if hair:
        override.append(f"发型：{hair}")
    if sexy:
        override.append(f"性感级别：{sexy}")
    if pose:
        override.append(f"姿势：{pose}（直接用作姿态句，不要套「以X姿态…画面」）")
    if scene:
        override.append(f"场景：{scene}")
    if light:
        override.append(f"光线：{light}")
    if outfit:
        override.append(f"服装：{outfit}")
    if override:
        user += "\n【用户指定，必须覆盖模板默认值】\n" + "\n".join(override) + "\n"

    # 模型可能拒答（选了性感级别/高开叉时尤甚）→ 回退到代码拼装
    llm_used = True
    text = ""
    try:
        text = strip_code_fence(
            llm_chat_with_retry(system, user, max_tokens=4000, temperature=0.85, timeout=240)
        )
    except Exception:
        text = ""

    prompt = _clean_prompt(text)
    if not prompt or _is_refusal(prompt):
        llm_used = False
        prompt = _compose_from_selections(
            fill_line, ethnicity, age, body, vibe,
            temper, hair, sexy, pose, scene, outfit, leg,
        )
    if not prompt:
        raise HTTPException(status_code=502, detail="生成失败")
    # 画风：风格线自带的优先，其次用 extra_style（兼容旧调用）
    if embedded_style:
        # 先去掉模板残留的 B 线固定开头（Wuthering Waves / 鸣潮 / 二次元半写实厚涂），
        # 再套画风开头，最后统一去重「竖屏构图」——
        # 注意顺序：清理必须在套画风之后，因为画风开头本身也含「竖屏构图」。
        prompt = _strip_b_prefix(prompt)
        prompt = SO.apply(prompt, embedded_style["value"])
        prompt = _dedupe_portrait_tag(prompt)
    else:
        prompt = SO.apply(prompt, str(req.get("extra_style") or ""))

    # 机位构图（追加到末尾）
    shot_val = str(req.get("shot") or "").strip()
    if shot_val:
        prompt = SH.apply(prompt, shot_val)

    return {
        "ok": True,
        "line": line,
        "line_label": line_meta["label"],
        "prompt": prompt,
        "breakdown": None,
        "llm_used": llm_used,
        "raw": text,
    }


# 各风格线的填值模板（模型只需把值串成通顺段落）
_FILL_TEMPLATES = {
    "B": (
        "Wuthering Waves style二次元半写实厚涂，竖屏构图。"
        "{age}，{hair}。身着{outfit}，{detail}，精致的东方面容。{sexy}。"
        "{pose}。场景：{scene}，{light}。"
    ),
    "C": (
        "一位{age}，{face}，{hair}。身着{outfit}，{detail}。"
        "{pose}，{scene}，{light}，{mood}。"
    ),
    "A": (
        "一位{age}，{face}，{hair}，{makeup}。身着{outfit}。"
        "{pose}，{scene}，{light}。{style}。"
    ),
    "D": (
        "东方{style}风格女性角色服装设计。{outfit}，{detail}。"
        "{color}，{fabric}，{trim}。"
    ),
}

# 各线可选词池（来自 skill 词库的浓缩版，代码侧随机选，模型只串联）
_POOLS = {
    "B": {
        "age": ["24岁成熟御姐", "26岁成熟女子", "28岁成熟御姐", "30岁成熟御姐"],
        "hair": ["深棕齐肩短发，层次分明", "雾灰蓝长发自然垂落微卷", "乌黑长发高马尾，利落清爽", "栗色大卷发披肩"],
        "outfit": ["杏粉缎面梅纹旗袍", "赭红短款提花旗袍", "墨黑丝绒修身长裙", "月白真丝交领上衣配高腰阔腿裤"],
        "detail": ["立领，双侧高开叉至腰际", "短裙摆，开叉至腰际，露腰贴身", "包臀剪裁，背部镂空", "收腰设计，袖口荷叶边"],
        "sexy": ["高开叉至大腿根部，露出修长双腿，突出丰满胸部曲线", "贴身剪裁勾勒腰臀曲线", "开叉至大腿根部露出修长双腿", "肩颈线条清晰，锁骨明显"],
        "pose": ["侧倚长椅，一条腿微抬，姿态慵懒", "慵懒侧卧，一只手撑头，身体曲线展露", "回身半转，长发甩出一道弧线", "靠墙而立，一手插兜"],
        "scene": ["酒店屋顶泳池边，蓝夜星空，水面倒映灯光", "雨夜便利店屋檐下，霓虹倒映湿路面", "午后咖啡馆窗边，百叶窗投下条纹光", "老式公寓阳台，晾衣绳与远处楼群"],
        "light": ["蓝夜波光", "冷蓝霓虹", "暖金斜阳", "柔和窗光"],
    },
    "C": {
        "age": ["24岁清冷女侠", "26岁出尘仙子", "28岁冷艳神女", "22岁灵动剑修"],
        "face": ["精致的东方面容，肤若凝脂，眼眸清冷", "精致的东方面容，眉眼疏淡含霜", "精致的东方面容，唇色极淡，神情不悲不喜", "精致的东方面容，眸光澄澈"],
        "hair": ["墨黑长发高束，两缕碎发贴颊", "乌发松松挽起，几缕垂落肩头", "青丝编成长辫垂在胸前", "银白长发披散至腰后"],
        "outfit": ["月白与银灰配色交领紧身广袖裙", "青鸾仙裙，花瓣形裙摆", "霜蓝渐变长裙，层叠纱质", "雪白与淡金配色仙衣"],
        "detail": ["银线云纹刺绣，宽阔织锦腰带", "肩部银叶刺绣，腰束玉带", "广袖垂落如水，裙摆层层散开", "胸前银色叶片与花朵刺绣"],
        "pose": ["侧身立于竹影中，一手按剑", "倚栏半坐，广袖垂落", "回眸半转，衣袂翻飞", "盘膝而坐，双手结印于膝前"],
        "scene": ["月下竹林，薄雾低浮", "仙山云海，远处山峰若隐若现", "古木亭台，纱幔垂落", "雪山之巅，寒风卷起细雪"],
        "light": ["冷月光透过竹叶洒下斑驳", "柔和梦幻侧逆光", "霞光漫射", "清冷顶光垂直落下"],
        "mood": ["清冷疏离，仙气凛然", "空灵出尘，静谧悠远", "孤高出尘，寒意逼人", "飘逸灵动，灵气充盈"],
    },
    "A": {
        "age": ["22岁女大学生", "25岁职场女性", "28岁书店店员", "20岁邻家女孩"],
        "face": ["精致的东方面容，素颜清透", "精致的东方面容，淡妆", "精致的东方面容，眉眼温柔"],
        "hair": ["黑色长直发自然垂落", "栗棕齐肩发微卷", "黑发扎成低马尾", "深棕短发"],
        "makeup": ["几乎无妆，唇色自然", "薄涂豆沙色唇釉", "清透底妆，眼尾一抹浅棕"],
        "outfit": ["白色棉质衬衫配牛仔裙", "米色针织开衫内搭白T", "浅灰卫衣配运动裤", "碎花连衣裙"],
        "pose": ["坐在窗边翻书", "站在便利店货架前挑选", "倚着栏杆望向远处", "蹲在路边系鞋带"],
        "scene": ["午后图书馆靠窗位置", "傍晚的街道人行道", "雨天的公交站台", "堆满杂物的出租屋"],
        "light": ["百叶窗投下的条纹光", "傍晚的橙色斜阳", "阴天柔和的漫射光", "路灯下的暖黄光斑"],
        "style": ["CCD 数码相机质感，轻微噪点", "千禧年胶片色偏，青绿调", "手机随手拍，构图随意", "生活流抓拍，不摆拍"],
    },
    "D": {
        "style": ["仙侠", "宫廷", "战斗", "暗黑", "新中式"],
        "outfit": ["齐胸襦裙", "交领长袍", "高腰马面裙", "抹胸曳地长裙"],
        "detail": ["上身为交领紧身设计，胸前装饰银色云纹刺绣", "上身为深V低胸设计，肩部龙鳞状护肩", "立领盘扣，袖口滚边", "露肩设计，腰部镂空"],
        "color": ["月白与银灰配色", "朱红与赤金配色", "墨黑与暗金配色", "天青与湖蓝配色"],
        "fabric": ["真丝材质", "雪纺材质", "织锦缎材质", "半透明薄纱材质"],
        "trim": ["璎珞项链在光里点出冷亮的一笔", "宽阔织锦腰带束住腰线", "流苏腰饰压住整体轮廓", "层叠纱裙在光下泛着微光"],
    },
}


def _build_fill_prompt(line: str, line_meta: Dict[str, Any], theme: str, extra: str, leg: str) -> str:
    """构造「填值模板」prompt：代码先选好词，模型只负责串成通顺段落。"""
    import random as _rnd

    pool = _POOLS.get(line, _POOLS["B"])
    values = {k: _rnd.choice(v) for k, v in pool.items() if v}

    # 露腿分级影响 sexy / detail
    if line in ("B", "C") and leg == "none":
        values.pop("sexy", None)
    elif leg == "bold" and line in ("B", "C"):
        values["sexy"] = "裙摆高开叉至大腿根部，露出修长双腿"

    if theme:
        values["scene"] = theme

    tpl = _FILL_TEMPLATES.get(line, _FILL_TEMPLATES["B"])
    # 只保留模板里出现过的键
    import re as _re
    need = set(_re.findall(r"\{(\w+)\}", tpl))
    filled = {k: v for k, v in values.items() if k in need}

    lines = "\n".join(f"{k} = {v}" for k, v in filled.items())
    prompt = f"""按下面这个句式写一条提示词：

{tpl}

填入：
{lines}
"""
    if extra:
        prompt += f"\n额外要求：{extra}\n"
    prompt += (
        f"\n直接输出填好并扩写后的那一段中文提示词（{line_meta['words']}）。"
        "不要输出模板、不要解释、不要分点。"
    )
    return prompt


def _clean_prompt(text: str) -> str:
    """清掉模型可能加的前言/标题/分点。"""
    import re as _re

    t = (text or "").strip()
    # 去掉常见前言行
    t = _re.sub(r"^(以下是|这是|提示词[:：]|【提示词】)\s*", "", t)
    # 去掉 markdown 标题
    t = _re.sub(r"^#{1,6}\s*.*$", "", t, flags=_re.M)
    # 合并成一段
    t = _re.sub(r"\s*\n+\s*", "", t)
    return t.strip()


# B 线模板固定开头（画风线要把它去掉）
_B_PREFIX = "Wuthering Waves style二次元半写实厚涂，竖屏构图。"


def _dedupe_portrait_tag(text: str) -> str:
    """只保留第一处「竖屏构图」，其余连同紧邻标点删掉。

    套完画风后调用 —— 画风开头自带一次「竖屏构图」，
    模型正文里可能又补一次，会变成「…竖屏构图。竖屏构图。30岁…」。
    """
    import re as _re

    t = (text or "").strip()
    if not t:
        return t
    first = t.find("竖屏构图")
    if first < 0:
        return t
    head = t[: first + len("竖屏构图")]
    tail = t[first + len("竖屏构图"):]
    tail = _re.sub(r"[，。、；：]?\s*竖屏构图[。，、；：]?", "", tail)
    t = head + tail
    t = _re.sub(r"[，。、；：]{2,}", "。", t)
    t = _re.sub(r"^[，。、；：\s]+", "", t)
    return t.strip()


def _strip_b_prefix(text: str) -> str:
    """去掉提示词里残留的 B 线固定开头与重复的「竖屏构图」。

    画风线共用 B 线骨架，模型经常会：
      - 原样保留模板开头的「Wuthering Waves style二次元半写实厚涂，竖屏构图。」
      - 把它改写成「Wuthering Waves风格二次元半写实厚涂」「鸣潮风格二次元半写实厚涂」
      - 或自己补一句「竖屏构图」
    这些都会和画风开头撞在一起，必须清掉。
    """
    import re as _re

    t = (text or "").strip()
    if not t:
        return t

    # 1) 删掉 Wuthering Waves / 鸣潮 相关的整句（含紧随的竖屏构图）
    #    覆盖：Wuthering Waves style / Wuthering Waves风格 / 鸣潮风格 / 鸣潮
    t = _re.sub(
        r"(?:Wuthering\s*Waves(?:\s*style)?|鸣潮(?:风格|画风)?)"
        r"[^。，]*?"
        r"(?:竖屏构图)?[。，]?",
        "",
        t,
        flags=_re.I,
    )

    # 2) 只保留第一处「竖屏构图」，其余删掉
    first = t.find("竖屏构图")
    if first >= 0:
        head = t[: first + len("竖屏构图")]
        tail = t[first + len("竖屏构图"):]
        tail = _re.sub(r"[，。、；：]?\s*竖屏构图[。，、；：]?", "", tail)
        t = head + tail

    # 3) 清掉句首与连续标点、以及残留的「二次元半写实厚涂」碎片
    t = _re.sub(r"^[，。、；：\s]+", "", t)
    # 「风格二次元半写实厚涂」「二次元半写实厚涂质感」这类碎片
    t = _re.sub(
        r"[，。]?\s*(?:风格)?\s*二次元半写实厚涂(?:质感|风格)?\s*[，。]?",
        "，",
        t,
    )
    t = _re.sub(r"[，。、；：]{2,}", "。", t)
    t = _re.sub(r"^[，。、；：\s]+", "", t)
    t = _re.sub(r"[，。]$", "。", t)
    return t.strip()


# 模型偶尔回这类拒答话术，不能当正文
_REFUSAL_MARKERS = (
    "sorry", "i can't", "i cannot", "cannot respond",
    "无法响应", "我不便", "不便协助", "不会按", "这类内容", "该请求", "这个请求", "抱歉",
)


def _is_refusal(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    low = t.lower()
    if any(m in low for m in _REFUSAL_MARKERS):
        return True
    meta = sum(1 for m in ("提示词", "模板", "输出", "该", "上述") if m in t)
    return meta >= 2 and len(t) < 300


def _compose_from_selections(
    line: str,
    ethnicity: str,
    age: str,
    body: str,
    vibe: str,
    temper: str,
    hair: str,
    sexy: str,
    pose: str,
    scene: str,
    outfit: str,
    leg: str,
) -> str:
    """代码拼装兜底：模型拒答时按选中的词直接组一段。

    结构与 _FILL_TEMPLATES 一致，只是把「模型串联」换成「代码拼接」。
    """
    import random as _rnd

    pool = _POOLS.get(line, _POOLS["B"])
    v = {k: _rnd.choice(vals) for k, vals in pool.items() if vals}

    # 用户选中项优先
    if hair:
        v["hair"] = hair
    if outfit:
        # 服装值形如「浅青立领紧身旗袍，领口盘扣，高开叉至大腿根部」
        parts = [p.strip() for p in outfit.split("，") if p.strip()]
        v["outfit"] = parts[0] if parts else outfit
        if len(parts) > 1:
            v["detail"] = "，".join(parts[1:])
    if sexy:
        v["sexy"] = sexy
    if pose:
        v["pose"] = pose
    if scene:
        v["scene"] = scene
    if temper:
        v["age"] = f"{age or v.get('age', '')}{temper}".strip()
    elif age:
        v["age"] = age
    if ethnicity:
        v["face"] = f"{ethnicity}，{v.get('face', '精致的东方面容')}"
    if vibe:
        v["mood"] = vibe
    if body:
        v["body"] = body

    tpl = _FILL_TEMPLATES.get(line, _FILL_TEMPLATES["B"])
    out = tpl
    for k, val in v.items():
        out = out.replace("{" + k + "}", str(val))
    # 清掉没被替换的占位符
    out = re.sub(r"\{[a-z_]+\}", "", out)
    out = re.sub(r"[，。]{2,}", "。", out).strip()
    if not out.endswith("。"):
        out += "。"
    return out


def _split(text: str) -> tuple[str, Optional[str]]:
    t = (text or "").strip()
    for marker in ("【完整提示词】", "【提示词】"):
        if marker in t:
            head, _, body = t.partition(marker)
            bd = head.replace("【选中元素】", "", 1).strip()
            return body.strip(), (bd or None)
    if "【选中元素】" in t:
        bd = t.replace("【选中元素】", "", 1).strip()
        # 拆解里没有正文时，取最后一段非 `键: 值` 的行
        lines = [ln for ln in bd.splitlines() if ln.strip() and ":" not in ln and "：" not in ln]
        return ("\n".join(lines).strip(), bd)
    return t, None


@router.post("/api/guoman-portrait/batch")
def batch(req: Dict[str, Any]) -> Dict[str, Any]:
    """批量：直接调 skill 自带 generate.py（已内置去重与禁词自检）。"""
    p = _skill_or_503()
    script = p / "scripts" / "generate.py"
    if not script.is_file():
        raise HTTPException(status_code=503, detail="skill 缺少 scripts/generate.py")

    n = int(req.get("n") or 20)
    if n < 1 or n > 1000:
        raise HTTPException(status_code=400, detail="条数需在 1~1000 之间")
    seed = req.get("seed")
    # 不传 / 空 / "random" 一律随机 —— 固定种子会让每次批量出一模一样的提示词
    if seed in (None, "", "random", "rand", "auto"):
        seed = _random_seed()
    else:
        try:
            seed = int(seed)
        except (TypeError, ValueError):
            seed = _random_seed()

    with tempfile.TemporaryDirectory(prefix="gmportrait-") as tmp:
        out_txt = Path(tmp) / "prompts.txt"
        out_json = Path(tmp) / "prompts.json"
        # 读取用户选的选项 —— 之前只读了 n/seed，其余全被丢掉
        opt_map = {
            "age": ("age", str(req.get("age") or "")),
            "temper": ("temper", str(req.get("temper") or "")),
            "hair": ("hair", str(req.get("hair") or "")),
            "outfit_cat": ("outfit-cat", str(req.get("outfit_cat") or "")),
            "outfit": ("outfit", str(req.get("outfit") or "")),
            "sexy": ("sexy", str(req.get("sexy") or "")),
            "pose": ("pose", str(req.get("pose") or "")),
            "scene": ("scene", str(req.get("scene") or "")),
            "light": ("light", str(req.get("light") or "")),
        }

        cmd = [
            python_exe(), str(script),
            "-n", str(n),
            "-o", str(out_txt),
            "--json", str(out_json),
            "--seed", str(seed),
        ]
        for _key, (flag, val) in opt_map.items():
            v = val.strip()
            if v and v not in ("不限", "随机", "不限（由风格决定）"):
                cmd += [f"--{flag}", v]
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
                            "prompt": row.get("prompt") or row.get("text") or "",
                            "category": row.get("category"),
                            "elements": row.get("elements") or row.get("breakdown"),
                        })
                    else:
                        items.append({"index": i, "prompt": str(row)})
            except Exception:
                items = []
        if not items and out_txt.is_file():
            lines = [ln.strip() for ln in out_txt.read_text(encoding="utf-8").splitlines() if ln.strip()]
            items = []
            for ln in lines:
                # 形如 `1.xxx` 去掉序号
                body = ln.split(".", 1)[1].strip() if ln[:3].strip().rstrip(".").isdigit() else ln
                items.append({"index": len(items) + 1, "prompt": body})

        # ── 批量也要应用用户选的选项 ──
        # skill 的 generate.py 只认 -n/--seed，不接受选项参数，
        # 所以这里在代码层把「机位构图 / 画风 / 人种 / 年龄 / 身材 / 气质」补上。
        shot_val = str(req.get("shot") or "").strip()
        style_val = str(req.get("extra_style") or "").strip()
        eth_val = PO.pick_ethnicity(str(req.get("ethnicity") or ""))
        age_val = PO.pick_age(str(req.get("age") or ""))
        body_val = str(req.get("body") or "").strip()
        vibe_val = str(req.get("vibe") or "").strip()

        if any([shot_val, style_val, eth_val, age_val, body_val, vibe_val]):
            for it in items:
                t = it.get("prompt") or ""
                if not t:
                    continue
                if style_val:
                    t = SO.apply(t, style_val)
                bits = [x for x in (age_val, eth_val, body_val, vibe_val) if x]
                if bits and not any(x in t for x in bits):
                    t = "，".join(bits) + "，" + t
                if shot_val:
                    t = SH.apply(t, shot_val)
                it["prompt"] = t

        return {"ok": True, "count": len(items), "items": items, "stdout": (res.stdout or "")[:1500]}
