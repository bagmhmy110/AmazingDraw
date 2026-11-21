#!/usr/bin/env python3
"""21 岁成人写实摄影提示词风格 API（adult-photorealistic-prompt-style-21）。

四类语料风格：情趣时尚 / 都市纪实 / 汉服舞台 / 瑜伽体操。
特点：自带 normalize_age.py 做确定性年龄规范化（18/19/20/十几岁 → 21 岁）。
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

import style_options as SO
import persona_options as PO

from skill_common import (
    list_references,
    llm_chat_with_retry,
    python_exe,
    read_reference,
    require_skill,
    skill_dir,
    strip_code_fence,
)

router = APIRouter(tags=["adult-photo21"])

SKILL = "adult-photorealistic-prompt-style-21"

# 四类已学习风格
STYLES = [
    {
        "id": "editorial",
        "label": "成人写真 / 情趣时尚",
        "desc": "中式婚房、酒店套房、办公室、诊所、卧室、亭台",
        "hint": "35mm / 50mm，丝袜、蕾丝、缎面、头纱、发冠、镜面",
    },
    {
        "id": "urban",
        "label": "都市生活 / 性感纪实",
        "desc": "咖啡馆、街道、商店、汽车、舞台、工作室、运动空间",
        "hint": "前景-中景-背景分层，手机、包、饮料、鲜花等叙事物件",
    },
    {
        "id": "hanfu",
        "label": "中国舞蹈 / 汉服舞台",
        "desc": "敦煌、唐、宋、魏晋、汉、明、龟兹、月宫、桂花仙子",
        "hint": "85mm 全身，木质舞台、雕花月门、帷幕、琥珀色聚光灯",
    },
    {
        "id": "yoga",
        "label": "瑜伽 / 体操 / 体育场",
        "desc": "体育场、竞技场、健身房、舞台、庭院、室内摄影棚",
        "hint": "蓝色垫子、观众、泛光灯、横幅、头带、辫发",
    },
] + [
    # ── 追加画风（与四类语料并列，同一套词池）──
    {"id": s["value"], "label": s["label"], "desc": s["desc"],
     "hint": s["open"], "_style": s}
    for s in SO.EXTRA_STYLES
]

# 机位 / 镜头（来自语料常见配置）
SHOTS = [
    {"value": "", "label": "不限"},
    {"value": "正面平视，35mm，全身", "label": "正面平视 35mm 全身"},
    {"value": "低机位仰拍，35mm，从脚尖方向", "label": "低机位仰拍 35mm（拉长腿部）"},
    {"value": "三分之四侧角，50mm，半身", "label": "三分之四侧角 50mm 半身"},
    {"value": "背面机位，35mm，背身构图", "label": "背面机位 35mm（背身）"},
    {"value": "高机位俯拍，35mm，坐姿或跪姿", "label": "高机位俯拍 35mm"},
    {"value": "85mm 全身，舞台侧前方", "label": "85mm 全身（舞台）"},
]

# 光线（skill 明确要求「一句带过」，不写电影光效）
LIGHTS = [
    {"value": "", "label": "不限"},
    {"value": "屋里自然光，很平", "label": "屋里自然光，很平"},
    {"value": "店里日光灯", "label": "店里日光灯"},
    {"value": "傍晚自然光", "label": "傍晚自然光"},
    {"value": "暖色夜灯", "label": "暖色夜灯"},
    {"value": "柔和琥珀色聚光灯", "label": "柔和琥珀色聚光灯（舞台）"},
    {"value": "泛光灯，明亮自然光", "label": "泛光灯（体育场）"},
]

# 姿态倾向（skill 要求姿态大胆，但只用短语概括）
POSES = [
    {"value": "", "label": "按风格自选"},
    {"value": "妩媚回眸，直视镜头", "label": "妩媚回眸"},
    {"value": "跪姿塌腰，臀部朝镜头", "label": "跪姿塌腰（背身）"},
    {"value": "仰躺，单腿高抬", "label": "仰躺单腿高抬"},
    {"value": "靠墙而立，交叉双腿", "label": "靠墙交叉双腿"},
    {"value": "镜前自拍，轻拉衣领", "label": "镜前自拍轻拉衣领"},
    {"value": "坐姿，腰部弧线明显", "label": "坐姿腰部弧线"},
]

REF_FILES = {
    "study": "references/style-study.md",
    "skill": "SKILL.md",
}

# 年龄红线：这些词一旦出现必须规范化
RESIDUAL_PATTERNS = (
    "未成年", "未满十八", "儿童", "小孩", "中学生", "学生妹", "童颜",
    "少女", "少年", "稚嫩", "幼态", "学生感", "年轻女孩", "年轻女性",
)


def _skill_or_503() -> Path:
    return require_skill(SKILL, "（本 skill 位于 ~/.workbuddy-ai/skills/ 下）")


@router.get("/api/adult-photo21/meta")
def meta() -> Dict[str, Any]:
    p = skill_dir(SKILL)
    return {
        "available": p is not None,
        "skill_dir": str(p) if p else None,
        "styles": STYLES,
        "shots": SHOTS,
        "lights": LIGHTS,
        "poses": POSES,
        "references": list_references(SKILL) if p else [],
        "age_rule": "所有人物明确为 21 岁成年人；18/19/20 与模糊年龄表述一律规范化为 21 岁",
        **PO.common_meta(),
        "can_normalize": bool(p and (p / "scripts" / "normalize_age.py").is_file()),
    }


@router.get("/api/adult-photo21/reference")
def get_reference(name: str = "study", max_chars: int = 0) -> Dict[str, Any]:
    rel = REF_FILES.get(name, name)
    text = read_reference(SKILL, rel, max_chars=max_chars)
    return {"name": name, "path": rel, "text": text, "length": len(text)}


# skill 自带的 normalize_age.py 只覆盖英文年龄（18/19/20-year-old）与部分中文词组，
# 中文的「18岁」「女孩」「男孩」这类它会漏掉。这里在 API 层补一层。
_CN_AGE_FIX = (
    (r"(?<![\d])(1[0-9]|20)\s*周岁", "21岁"),
    (r"(?<![\d])(1[0-9]|20)\s*岁", "21岁"),
    (r"二十岁出头|二十多岁|三十岁出头|十几岁|晚十几岁", "21岁"),
    (r"学生妹|学生感|年轻女孩|年轻女性|年轻女人|小女孩", "21岁成年女性"),
    (r"年轻男孩|年轻男性|年轻男人|小男孩", "21岁成年男性"),
    # 单独的「女孩」「男孩」也要规范化（避免残留低龄联想）
    (r"女孩", "21岁成年女性"),
    (r"男孩", "21岁成年男性"),
)


def _normalize_extra(text: str) -> str:
    """补 skill 脚本没覆盖的中文年龄与低龄表述。"""
    import re as _re

    out = text
    for pat, rep in _CN_AGE_FIX:
        out = _re.sub(pat, rep, out)
    # 去重（如「21岁21岁」「21岁成年女性成年女性」）
    out = _re.sub(r"21岁\s*21岁", "21岁", out)
    out = _re.sub(r"21岁成年女性\s*成年女性", "21岁成年女性", out)
    out = _re.sub(r"21岁成年男性\s*成年男性", "21岁成年男性", out)
    out = _re.sub(r"21岁成年女性\s*，?\s*21岁", "21岁成年女性", out)
    out = _re.sub(r"21岁成年男性\s*，?\s*21岁", "21岁成年男性", out)
    return out


# ── 填值模板：代码选词，模型只串联 ────────────────────────────────────

_FILL_POOLS = {
    "editorial": {
        "media": ["写实摄影风格", "纪实感时尚写真", "室内人像摄影"],
        "face": ["五官精致优雅", "眼神妩媚直视镜头", "唇色饱满微张"],
        "hair": ["黑色长发披散", "深棕卷发垂肩", "乌发半挽留两缕贴颊"],
        "outfit": ["白色蕾丝吊带配缎面短裙", "黑色贴身连衣裙，深V领口",
                   "真丝睡袍，腰带松松系着", "蕾丝内衣配半透明纱质外披"],
        "pose": ["跪在床上，腰部塌下去，臀部朝向镜头", "仰躺在床单上，单腿高抬",
                 "靠墙而立，交叉双腿，肩头微侧", "坐在梳妆台前，一只手撩起头发"],
        "env": ["床边散着抱枕、香水和手机", "梳妆台上摆着口红、镜子和首饰盒",
                "地板上丢着丝质睡袍和拖鞋"],
        "bg": ["背景是木质床头和半掩的窗帘", "背景是镜面衣柜和暖色壁灯"],
        "light": ["屋里自然光，很平", "暖色夜灯", "傍晚自然光"],
        "tail": ["一双修长的长腿从裙摆下延伸到画面边缘", "皮肤纹理和布料褶皱清晰可见"],
    },
    "urban": {
        "media": ["都市生活摄影", "街头纪实写真", "日常抓拍"],
        "face": ["妆容清淡，眼神放松", "侧脸线条清晰，微微低头", "直视镜头，唇边带笑"],
        "hair": ["黑长直发自然垂落", "栗棕短发利落", "低马尾，几缕碎发贴颊"],
        "outfit": ["白色紧身针织衫配高腰短裙", "卡其色风衣内搭吊带裙",
                   "牛仔外套配包臀裙", "黑色皮衣配过膝长靴"],
        "pose": ["靠在咖啡馆窗边，一只手扶着杯沿", "坐在台阶上，一条腿伸直",
                 "站在街角回头，风掀起裙摆", "倚着车门，双手插兜"],
        "env": ["桌上放着拿铁、手机和一本翻开的杂志", "手边有购物袋和雨伞",
                "旁边停着自行车，车筐里有鲜花"],
        "bg": ["背景是玻璃橱窗和模糊的行人", "背景是老式店铺招牌和斑马线"],
        "light": ["店里日光灯", "傍晚自然光", "屋里自然光，很平"],
        "tail": ["一双修长的长腿在短裙下延伸", "画面有轻微的手持感"],
    },
    "hanfu": {
        "media": ["中国舞蹈舞台艺术摄影", "汉服舞台写真"],
        "face": ["眉眼含情，神情静定", "妆容古典，眼尾微挑", "唇色朱红，目光低垂"],
        "hair": ["黑色盘发，插着金色步摇", "高髻配珠翠发冠", "长发半挽，簪一朵绢花"],
        "outfit": ["敦煌风格赭红与石青配色齐胸襦裙", "月白与银灰交领广袖长裙",
                   "唐制齐胸衫裙，披帛垂落", "明制马面裙配立领短袄"],
        "pose": ["单臂上举，广袖垂落如水", "旋身回望，披帛甩出一道弧线",
                 "双手交叠于身前，脊背挺直", "侧身而立，一足轻点"],
        "env": ["木质舞台上铺着暗红地毯", "身后是雕花月门与垂落的帷幕",
                "台侧摆着花器与竹影景片"],
        "bg": ["背景是深色幕布与远处的观众席", "背景是宫殿廊柱与朦胧宫灯"],
        "light": ["柔和琥珀色聚光灯", "中性聚光灯从侧前方打下"],
        "tail": ["85mm 全身构图，舞姿完整入画", "衣料织纹与刺绣在光下清晰可辨"],
    },
    "yoga": {
        "media": ["体育摄影", "运动写真", "体操舞台记录"],
        "face": ["素颜，额前有薄汗", "眼神专注，唇微张", "侧脸紧绷，下颌线条明显"],
        "hair": ["黑发扎成高马尾", "编成单侧麻花辫", "短发贴耳，戴着运动发带"],
        "outfit": ["浅灰运动背心配高腰紧身裤", "蓝色体操服，开衩至胯",
                   "白色瑜伽套装，贴身剪裁", "运动短裤配紧身运动内衣"],
        "pose": ["单腿站立，另一腿向后高举", "跪坐在垫子上，上身前倾",
                 "仰躺，双腿向上伸展", "侧身支撑，腰线明显拱起"],
        "env": ["蓝色瑜伽垫铺在木地板上", "场边放着水壶和毛巾",
                "垫子旁散着运动鞋和护腕"],
        "bg": ["背景是观众席与悬挂的横幅", "背景是健身房镜墙和器械"],
        "light": ["泛光灯，明亮自然光", "室内顶灯，光线均匀"],
        "tail": ["一双修长的长腿在动作中完全展开", "肌肉线条与皮肤纹理清晰"],
    },
}

_FILL_TEMPLATE = (
    "一位21岁成年中国女性，{face}，{hair}。身着{outfit}。{pose}。"
    "{env}。{bg}。{light}，{tail}。"
)


def _compose_locally(
    style: str, subject: str, shot: str, light: str, pose: str, extra: str,
) -> str:
    """纯代码拼一条（LLM 失败或拒答时的兜底）。

    原来这个函数被调用但没定义 —— 批量时 LLM 一旦拒答就 NameError。
    """
    import random as _rnd

    pool = _FILL_POOLS.get(style, _FILL_POOLS["editorial"])
    v = {k: _rnd.choice(vals) for k, vals in pool.items()}

    # 用户指定项覆盖（这是锁词能生效的关键）
    if pose:
        v["pose"] = pose
    if light:
        v["light"] = light
    if shot:
        v["tail"] = f"{shot}，{v['tail']}"
    if subject:
        v["env"] = f"{subject}，{v['env']}"

    text = _FILL_TEMPLATE.format(**v)
    if extra:
        text = text.rstrip("。") + f"，{extra}。"
    return text


def _build_fill_prompt(
    style: str, style_meta: Dict[str, Any], subject: str, shot: str,
    light: str, pose: str, extra: str, count: int,
) -> str:
    """构造填值 prompt：代码选好词，模型只负责串成通顺一段。"""
    import random as _rnd

    pool = _FILL_POOLS.get(style, _FILL_POOLS["editorial"])
    v = {k: _rnd.choice(vals) for k, vals in pool.items()}

    # 用户指定项覆盖
    if pose:
        v["pose"] = pose
    if light:
        v["light"] = light
    if subject:
        v["env"] = f"{subject}，{v['env']}"
    if shot:
        v["tail"] = f"{shot}，{v['tail']}"

    lines = "\n".join(f"{k} = {val}" for k, val in v.items())
    p = f"""按下面这个句式写一条提示词：

{_FILL_TEMPLATE}

填入：
{lines}
"""
    if extra:
        p += f"\n额外要求：{extra}\n"
    if count > 1:
        # 只允许在用户没锁的维度上变化 ——
        # 原来写「换姿态/服装/地点」，会把用户锁定的 pose/light 直接冲掉
        locked_names = [
            n for n, v in (("姿态", pose), ("光线", light), ("镜头", shot), ("地点", subject)) if v
        ]
        free_names = [
            n for n, v in (("姿态", pose), ("服装", ""), ("地点", subject),
                           ("光线", light), ("镜头", shot)) if not v
        ]
        vary = "、".join(free_names) if free_names else "细节措辞"
        p += f"\n写 {count} 条，只在这几个维度上做差异：{vary}。"
        if locked_names:
            p += (
                f"\n用户指定的 {'、'.join(locked_names)} 每一条都必须原样体现，不能变化。"
            )
        p += "\n每条一行，格式 `1. 正文`。"
    else:
        p += "\n直接输出填好并扩写后的那一段，不要输出模板。"
    return p


def _run_normalize(text: str, check_only: bool = False) -> Dict[str, Any]:
    p = _skill_or_503()
    script = p / "scripts" / "normalize_age.py"
    if not script.is_file():
        raise HTTPException(status_code=503, detail="skill 缺少 scripts/normalize_age.py")

    # 先本地补中文年龄，再交给 skill 脚本处理英文与其余规则
    pre = _normalize_extra(text)

    with tempfile.TemporaryDirectory(prefix="age21-") as tmp:
        src = Path(tmp) / "input.txt"
        src.write_text(pre, encoding="utf-8")
        cmd = [python_exe(), str(script), str(src)]
        if check_only:
            cmd.append("--check")
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        try:
            res = subprocess.run(
                cmd, cwd=str(p), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=60, env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail="规范化超时") from exc

    final = _normalize_extra((res.stdout or "").strip())
    return {
        "text": final,
        "stderr": (res.stderr or "").strip(),
        "rc": res.returncode,
        "residual": bool(res.returncode == 2),
    }


@router.post("/api/adult-photo21/normalize")
def normalize(req: Dict[str, Any]) -> Dict[str, Any]:
    """把提示词里的年龄表述统一成 21 岁（纯确定性替换，不走 LLM）。"""
    text = str(req.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="文本为空")
    r = _run_normalize(text)
    return {
        "ok": True,
        "original": text,
        "normalized": r["text"],
        "changed": r["text"] != text,
        "residual": r["residual"],
        "residual_msg": r["stderr"] if r["residual"] else "",
    }


# 模型偶尔会回这类拒答话术，不能当成正常提示词。
# 中文拒答往往很长（会解释一堆理由），所以不能用长度做唯一判据 ——
# 改为「出现拒答特征短语」即判定，同时排除正常提示词不会有的元话语。
_REFUSAL_MARKERS = (
    "sorry", "i can't", "i cannot", "cannot respond", "can't help",
    "无法响应", "我不便", "不便协助", "不会按", "不能提供", "无法提供",
    "这类内容", "我不打算", "恕我", "我不会生成", "我不会提供",
    "该请求", "这个请求", "抱歉",
)

# 正常提示词里不会出现的「元话语」特征
_META_MARKERS = (
    "提示词", "模板", "输出成品", "按该", "该模板", "上述", "这个请求", "该请求",
)


def _is_refusal(text: str) -> bool:
    """判断模型是否在拒答，而不是给了提示词。"""
    t = (text or "").strip()
    if not t:
        return True
    low = t.lower()

    # 1) 明确的英文/中文拒答短语
    if any(m in low for m in _REFUSAL_MARKERS):
        # 「抱歉」在正常提示词里几乎不会出现；其余同理
        return True

    # 2) 同时命中多个元话语 + 篇幅短 → 多半是在解释「我不按这个模板输出」
    meta_hits = sum(1 for m in _META_MARKERS if m in t)
    if meta_hits >= 2 and len(t) < 400:
        return True

    return False


@router.post("/api/adult-photo21/generate")
def generate(req: Dict[str, Any]) -> Dict[str, Any]:
    """按风格生成一条写实摄影提示词。"""
    _skill_or_503()
    style = str(req.get("style") or "editorial").strip()
    valid_ids = {x["id"] for x in STYLES}
    if style not in valid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"未知风格 {style}，可选：{'、'.join(sorted(valid_ids))}",
        )

    # 追加画风线：共用 editorial 的词池，只换开头/结尾
    style_meta_all = next(x for x in STYLES if x["id"] == style)
    embedded_style = style_meta_all.get("_style") or None
    fill_style = "editorial" if embedded_style else style

    subject = str(req.get("subject") or "").strip()
    shot = str(req.get("shot") or "").strip()
    light = str(req.get("light") or "").strip()
    pose = str(req.get("pose") or "").strip()
    extra = str(req.get("extra") or "").strip()
    count = int(req.get("count") or 1)
    if count < 1 or count > 20:
        raise HTTPException(status_code=400, detail="条数需在 1~20 之间")

    # 人种 / 年龄 / 身材 / 气质（四个 skill 通用）
    ethnicity = PO.pick_ethnicity(str(req.get("ethnicity") or ""))
    age = PO.pick_age(str(req.get("age") or ""))
    body = str(req.get("body") or "").strip()
    vibe = str(req.get("vibe") or "").strip()

    style_meta = next(x for x in STYLES if x["id"] == fill_style)

    # 关键：system 只留最简纪律。规则写多了推理模型会逐条分析、把 token 预算烧在思考上。
    # 具体写法改由「填值模板」引导 —— 代码先选好词，模型只负责串成一段。
    # 年龄默认 21 岁（这个 skill 的核心规则），用户选了别的就按用户来。
    age_rule = f"人物一律写「{age}」。" if age else "人物一律写「21岁成年女性」。"
    eth_rule = (
        f"人种写「{ethnicity}」，用可见特征落地。" if ethnicity else "人物一律写亚洲人。"
    )
    system = (
        "你是中文写实摄影提示词写手。只输出一段中文提示词，不分析、不解释。\n"
        f"{age_rule}\n"
        f"{eth_rule}\n"
        "姿态大胆但只用一两个短语概括。\n"
        "光线只一句带过。质感写成日常照片。"
    )

    user = _build_fill_prompt(fill_style, style_meta, subject, shot, light, pose, extra, count)

    # 覆盖项：模板里写死了「21岁成年中国女性」，用户指定时要替换
    override = []
    if ethnicity:
        override.append(f"人种：{ethnicity}（替换模板里的「中国女性」，用肤色/眼型/发质落地）")
    if age:
        override.append(f"年龄：{age}（替换模板里的「21岁」）")
    if body:
        override.append(f"身材：{body}")
    if vibe:
        override.append(f"气质：{vibe}")
    if override:
        user += "\n【用户指定，必须覆盖模板默认值】\n" + "\n".join(override) + "\n"

    # LLM 偶发会把 token 预算全烧在 reasoning 上（content 为空），或直接回拒答话术。
    # 这两种情况都回退到代码拼装 —— 模板与词条都来自语料，结构就是 skill 要求的顺序。
    llm_ok = True
    text = ""
    try:
        text = strip_code_fence(
            llm_chat_with_retry(system, user, max_tokens=4000, temperature=0.9, timeout=240, attempts=2)
        )
        if not text or _is_refusal(text):
            llm_ok = False
            text = ""
    except HTTPException:
        llm_ok = False
        text = ""
    except Exception:
        llm_ok = False
        text = ""

    if not llm_ok:
        parts = [_compose_locally(fill_style, subject, shot, light, pose, extra) for _ in range(count)]
        text = "\n".join(f"{i+1}. {p}" for i, p in enumerate(parts))

    # 生成后强制过一遍年龄规范化（双保险）
    import re as _re

    def _safe_norm(s: str) -> Dict[str, Any]:
        """规范化失败不该让整个请求挂掉。"""
        try:
            return _run_normalize(s)
        except Exception:
            return {"text": s, "residual": False, "stderr": "", "rc": 0}

    items: List[Dict[str, Any]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        s = _re.sub(r"^\s*\d+[.、)]\s*", "", s)
        s = _re.sub(r"^\s*[-*]\s*", "", s)
        if len(s) < 8 or _is_refusal(s):
            continue
        norm = _safe_norm(s)
        items.append({
            "index": len(items) + 1,
            "prompt": norm["text"] or s,
            "normalized": norm["text"] != s,
            "residual": norm["residual"],
        })

    # 一条都没解析出来（LLM 给了拒答或格式乱）→ 代码拼装兜底
    if not items:
        llm_ok = False
        parts = [_compose_locally(fill_style, subject, shot, light, pose, extra) for _ in range(count)]
        for p in parts:
            norm = _safe_norm(p)
            items.append({
                "index": len(items) + 1,
                "prompt": norm["text"] or p,
                "normalized": norm["text"] != p,
                "residual": norm["residual"],
            })

    # 画风：风格线自带的优先，其次用 extra_style（兼容旧调用）
    _extra_style = (embedded_style["value"] if embedded_style
                    else str(req.get("extra_style") or ""))
    if _extra_style:
        for it in items:
            it["prompt"] = SO.apply(it.get("prompt") or "", _extra_style)

    return {
        "ok": True,
        "style": style,
        "style_label": style_meta["label"],
        "count": len(items),
        "items": items,
        "llm_used": llm_ok,
        "raw": text,
    }


@router.post("/api/adult-photo21/rewrite")
def rewrite(req: Dict[str, Any]) -> Dict[str, Any]:
    """改写既有提示词：保留原始性感与摄影细节，只规范化年龄与低龄表述。"""
    _skill_or_503()
    text = str(req.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="请贴入要改写的提示词")

    system = (
        "你是提示词改写器。保留原文的场景、动作、服装、道具、构图、灯光、材质与性感气质，"
        "只把年龄与低龄化表述统一成「21岁成年女性」。\n"
        "不改写成小说或对白，不改写成保守日常照，不删掉原始的性感细节。\n"
        "只输出改写后的提示词正文，不解释。"
    )
    user = f"改写下面这条提示词：\n\n{text}\n\n直接输出改写后的正文。"

    # LLM 改写失败或被拒时，退化为「纯确定性规范化」——
    # 这仍然满足 skill 的核心要求（年龄统一），且保留原文所有细节。
    llm_used = True
    out = ""
    try:
        out = strip_code_fence(
            llm_chat_with_retry(system, user, max_tokens=3000, temperature=0.6, timeout=180, attempts=2)
        )
        if not out or _is_refusal(out):
            llm_used = False
            out = ""
    except Exception:
        llm_used = False
        out = ""

    if not out:
        out = text  # 退回原文，交给下面的规范化处理

    # 改写后再跑一次确定性规范化兜底
    norm = _run_normalize(out)
    return {
        "ok": True,
        "llm_used": llm_used,
        "original": text,
        "rewritten": norm["text"] or out,
        "residual": norm["residual"],
        "residual_msg": norm["stderr"] if norm["residual"] else "",
    }
