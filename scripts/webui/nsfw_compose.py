#!/usr/bin/env python3
"""NSFW 模板 skill：纯代码拼装器（不走 LLM）。

设计目标：
  - 中文连接句式 + 英文词条混排
  - 按词性动态选句式，不硬套模板
  - 缺槽自动补全，保证句子结构完整

词库来源：nsfw_terms_cache.json（由 build_nsfw_terms.py 生成，11588 条英文词条）

槽位拆分说明：
  - 「场景主题」原槽混着场景与角色，按小节名切成「场景」+「角色」
  - 「裸露液体」原槽混着裸露状态、生殖器、液体，切成「裸露」+「液体」
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_CACHE = Path(__file__).resolve().parent / "nsfw_terms_cache.json"

# ── 槽位拆分规则 ──────────────────────────────────────────────────────

# 「场景主题」前 24 节是场景，之后是角色/主题
_SCENE_SECTION_LIMIT = 24

# 「裸露液体」前 28 节是裸露/衣物状态，之后是生殖器与液体
_BODY_SECTION_LIMIT = 28


# ── 词性判定 ──────────────────────────────────────────────────────────

def classify(term: str) -> str:
    """粗分词性，决定用哪种句式。

    noun      名词短语   → 直接放
    gerund    动名词     → 直接放（自带动作语义）
    participle 过去分词  → 加 with
    sentence  完整句     → 直接放
    """
    t = term.strip()
    words = t.split()
    n = len(words)

    # 完整句：含 be 动词或从句连接
    if re.search(r"\b(is|are|was|were|being|while|when)\b", t):
        return "sentence"

    # 动名词开头，或前 3 个词里有 -ing
    if re.match(r"^\w+ing\b", t):
        return "gerund"
    head = " ".join(words[:3])
    if re.search(r"\b\w+ing\b", head) and n >= 2:
        return "gerund"

    # 过去分词开头（one leg raised / hands cuffed）
    # 注意：unbuttoned shirt 是「分词+名词」的形容词短语，不是纯过去分词
    if re.match(r"^\w+(ed|en)\b", t) and n >= 2:
        second = words[1] if n > 1 else ""
        # 第二个词是名词（不是介词/冠词）→ 当形容词短语处理，直接放
        if second and second.lower() not in (
            "in", "on", "at", "by", "with", "from", "to", "into",
            "against", "over", "under", "beside", "across", "around",
        ):
            return "noun"
        return "participle"

    return "noun"


# ── 词库加载 ──────────────────────────────────────────────────────────

def load_terms() -> Dict[str, Any]:
    if not _CACHE.is_file():
        return {}
    try:
        return json.loads(_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _flatten(info: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for arr in (info.get("sections") or {}).values():
        out.extend([t for t in (arr or []) if t])
    return out


# 角色词的特征：职业 / 亲属 / 身份后缀
_ROLE_WORDS = (
    "woman", "girl", "lady", "wife", "mother", "mom", "sister", "daughter",
    "teacher", "nurse", "maid", "hostess", "officer", "student", "idol",
    "actress", "model", "secretary", "assistant", "doctor", "patient",
    "bride", "widow", "housewife", "stepmother", "stepdaughter",
    "coworker", "colleague", "boss", "subordinate", "neighbor", "landlady",
    "cheerleader", "stewardess", "attendant", "receptionist", "therapist",
    "instructor", "tutor", "senpai", "kohai", "office lady", "ol",
    "amateur", "mature", "young", "innocent", "nympho", "dominatrix",
)

# 明显不是角色的词（主题 / 行为 / 状态）
_NOT_ROLE = (
    "sex", "extortion", "coerced", "restrained", "drug", "taboo",
    "fantasy", "lesbian", "threesome", "foursome", "gangbang",
    "exhibitionism", "voyeurism", "bondage", "blackmail", "aphrodisiac",
    "creampie", "bukkake", "irrumatio", "shibari", "kinbaku",
)


def _looks_like_role(term: str) -> bool:
    """判断词条是不是「人」，而不是主题/行为/状态。

    角色池里混着 mountain sex（主题）、extortion（行为）、coerced（状态），
    直接拼进「人物」位置会很怪，这里过滤掉。
    """
    t = term.lower().strip()
    if not t:
        return False

    # 明显不是角色
    if any(w in t for w in _NOT_ROLE):
        return False

    # 含角色特征词
    if any(w in t for w in _ROLE_WORDS):
        return True

    # 单词且是常见职业/身份（hostess / chiropractor / nympho）
    words = t.split()
    if len(words) == 1 and len(t) >= 4:
        # 纯动作（-ing / -ed 结尾）不是角色
        if t.endswith(("ing", "ed")):
            return False
        return True

    return False


def build_pools(terms: Optional[Dict[str, Any]] = None) -> Dict[str, List[str]]:
    """把原始槽位重组成 19 个拼装用池。

    14 个词库槽 + 5 个 persona 槽（人种/年龄/身材/气质/画风）。
    persona 槽由前端下拉提供，不来自词库文件。
    """
    d = terms if terms is not None else load_terms()
    pools: Dict[str, List[str]] = {}

    # 1) 场景主题 → 拆成「场景」+「角色」
    st = d.get("场景主题") or {}
    secs = list((st.get("sections") or {}).items())
    scene_pool: List[str] = []
    role_pool: List[str] = []
    for i, (_name, arr) in enumerate(secs):
        target = scene_pool if i < _SCENE_SECTION_LIMIT else role_pool
        target.extend([t for t in (arr or []) if t])
    pools["场景"] = scene_pool
    pools["角色"] = role_pool

    # 2) 裸露液体 → 拆成「裸露」+「液体」
    bl = d.get("裸露液体") or {}
    secs2 = list((bl.get("sections") or {}).items())
    body_pool: List[str] = []
    liquid_pool: List[str] = []
    for i, (_name, arr) in enumerate(secs2):
        target = body_pool if i < _BODY_SECTION_LIMIT else liquid_pool
        target.extend([t for t in (arr or []) if t])
    pools["裸露"] = body_pool
    pools["液体"] = liquid_pool

    # 3) 其余槽直接映射
    mapping = {
        "景别": "景别构图",
        "服装": "服装专项",
        "光影": "光影氛围",
        "姿态": "姿势动作",
        "表情": "表情眼神",
        "风格": "风格胶片",
        "妆容": "妆容专项",
        "发型": "发型饰品",
        "瑕疵": "瑕疵细节",
        "纹身": "纹身标记",
        "道具": "道具宠物",
        "身份": "人格卡片",
    }
    for key, src in mapping.items():
        pools[key] = _flatten(d.get(src) or {})

    # 4) 池子清洗
    # 场景池里混进了几条光影词（studio lighting rig / glamour cover lighting），剔掉
    pools["场景"] = [
        t for t in pools.get("场景") or []
        if not re.search(r"\b(lighting|light rig|glow|shadow)\b", t, re.I)
    ]
    # 景别池混着光影词与视角碎片（beam of light / rim light / through eyes of）
    pools["景别"] = [
        t for t in pools.get("景别") or []
        if not re.search(r"\b(light|lighting|glow|shadow|lamp|beam)\b", t, re.I)
        and not t.lower().endswith((" of", " to", " in", " on", " with"))
    ]
    # 人格卡片是整串描述（chiropractor, bone setter, ...），只取第一个词
    pools["身份"] = [
        t.split(",")[0].strip() for t in (pools.get("身份") or []) if t
    ]
    # 角色池混进了主题/行为词（mountain sex / extortion / coerced），
    # 只保留「像人」的词条：职业名、亲属称呼、身份标签
    pools["角色"] = [
        t for t in pools.get("角色") or []
        if _looks_like_role(t)
    ]

    return {k: v for k, v in pools.items() if v}


# ── 句式组装 ──────────────────────────────────────────────────────────

def _sp(term: str) -> str:
    """中英混排时给英文词条补前导空格。"""
    t = term.strip()
    if not t:
        return ""
    return f" {t}" if t[0].isascii() and t[0].isalnum() else t


def _join(prefix: str, term: str) -> str:
    """中文前缀 + 英文词条，自动补空格（如 `以 close-up 构图`）。"""
    t = term.strip()
    if not t:
        return prefix
    return f"{prefix} {t}" if t[0].isascii() and t[0].isalnum() else f"{prefix}{t}"


def _wrap_light(term: str) -> str:
    """光影词：本身含 light/lighting 就不要再加「下」。"""
    t = term.strip()
    if re.search(r"\b(light|lighting|lit|glow|shadow)\b", t, re.I):
        return t
    return f"{t}下"


def _wrap_pose(term: str) -> str:
    """姿态按词性给不同处理。"""
    kind = classify(term)
    if kind == "participle":
        return f"with {term}"
    # 名词 / 动名词 / 完整句都直接放
    return term


def _wrap_body(term: str) -> str:
    """裸露状态：过去分词加 with，其余直接放。"""
    kind = classify(term)
    if kind == "participle":
        return f"with {term}"
    return term


def compose(
    picks: Dict[str, str],
    *,
    seed: Optional[int] = None,
) -> str:
    """把选中的词条拼成自然句。

    分三句：
      1. 场景 + 构图
      2. 人物 + 服装 + 裸露
      3. 光影 + 姿态 + 表情
    """
    rng = random.Random(seed) if seed is not None else random.Random()

    def g(key: str) -> str:
        return (picks.get(key) or "").strip()

    sentences: List[str] = []

    # ── 画风：整段提示词的最外层风格，放最开头 ──
    style_extra = g("画风")
    if style_extra:
        sentences.append(f"{style_extra}。")

    # ── 第一句：场景 + 构图 ──
    s1: List[str] = []
    scene = g("场景")
    shot = g("景别")
    if scene:
        s1.append(_join("在", scene))
    if shot:
        s1.append(_join("以", shot) + " 构图")
    if s1:
        sentences.append("，".join(s1) + "。")

    # ── 第二句：人物 + 服装 + 裸露 ──
    s2: List[str] = []
    role = g("角色")
    eth = g("人种")
    age = g("年龄")
    bodyshape = g("身材")
    vibe = g("气质")
    cloth = g("服装")
    body = g("裸露")
    liquid = g("液体")

    # 人物主体：年龄 + 人种 + 身材 + 气质 + 角色，拼成「28岁 中国 丰满 慵懒 人妻」
    subj_bits = [x for x in (age, eth, bodyshape, vibe, role) if x]
    if subj_bits:
        s2.append(" ".join(subj_bits))
    if cloth:
        s2.append(_join("身着", cloth))
    if body:
        s2.append(_wrap_body(body))
    if liquid:
        s2.append(_sp(liquid))
    if s2:
        sentences.append("，".join(x for x in s2 if x) + "。")

    # ── 第三句：光影 + 姿态 + 表情 + 细节 ──
    s3: List[str] = []
    light = g("光影")
    pose = g("姿态")
    face = g("表情")
    style = g("风格")
    if light:
        s3.append(_wrap_light(light))
    if pose:
        s3.append(_wrap_pose(pose))
    if face:
        s3.append(_sp(face))
    if style:
        s3.append(_sp(style))
    if s3:
        sentences.append("，".join(x for x in s3 if x) + "。")

    # ── 第四句（可选）：妆容 / 发型 / 瑕疵 / 纹身 / 道具 / 身份 ──
    s4: List[str] = []
    for key, tpl in (
        ("妆容", "妆容{}"),
        ("发型", "发型{}"),
        ("瑕疵", "细节{}"),
        ("纹身", "纹身{}"),
        ("道具", "道具{}"),
        ("身份", "身份{}"),
    ):
        v = g(key)
        if v:
            s4.append(tpl.format(_sp(v)))
    if s4:
        sentences.append("，".join(s4) + "。")

    text = "".join(sentences)

    # 清理：连续标点、中英之间的多余空格
    text = re.sub(r"，+", "，", text)
    text = re.sub(r"。+", "。", text)
    text = re.sub(r" +", " ", text)
    return text.strip()


def compose_random(
    *,
    seed: Optional[int] = None,
    want: Optional[Dict[str, str]] = None,
    fill_missing: bool = True,
) -> Dict[str, Any]:
    """随机抽词并拼装。

    fill_missing=True 时，缺的槽从词库自动补，保证句子结构完整。
    persona 槽（人种/年龄/身材/气质/画风）不来自词库，只在用户指定时使用。
    """
    rng = random.Random(seed) if seed is not None else random.Random()
    pools = build_pools()
    want = {k: str(v or "").strip() for k, v in (want or {}).items()}

    # 必填槽（决定句子骨架）
    core = ["场景", "景别", "服装", "光影", "姿态", "表情"]
    optional = ["角色", "裸露", "液体", "风格", "妆容", "发型", "瑕疵", "纹身", "道具", "身份"]
    # persona 槽：只用用户给的，不自动补（自动补人种/年龄容易拼出奇怪组合）
    persona = ["画风", "年龄", "人种", "身材", "气质"]

    picks: Dict[str, str] = {}
    for key in core:
        v = want.get(key)
        if v:
            picks[key] = v
        elif fill_missing and pools.get(key):
            picks[key] = rng.choice(pools[key])

    for key in optional:
        v = want.get(key)
        if v:
            picks[key] = v
        elif fill_missing and pools.get(key) and rng.random() < 0.45:
            # 可选槽 45% 概率补，避免句子过长
            picks[key] = rng.choice(pools[key])

    for key in persona:
        v = want.get(key)
        if v:
            picks[key] = v

    text = compose(picks, seed=seed)
    return {
        "prompt": text,
        "elements": picks,
        "kinds": {k: classify(v) for k, v in picks.items()},
    }
