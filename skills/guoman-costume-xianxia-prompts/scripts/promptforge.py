# -*- coding: utf-8 -*-
"""
promptforge.py — 国漫服装装配 + 古风仙侠立绘成稿。

词库只有七槽组合词（配色/材质/纹样/袖型/裙装结构/腰部/肩部），
没有独立分类词条，所以服装部分完全由七槽构成，不再有「上装结构/配饰/鞋履/边饰/动态」
这些分类槽位。人物侧（面部/发饰/姿态/场景）是写作层，不依赖词库。

四个子命令：
  lookup   按槽位 / 关键词查词库
  combo    七槽装配一条纯服装提示词（线 D）
  portrait 六句骨架成稿一条古风/仙侠立绘（线 C）
  batch    批量产出 N 条，带去重与禁词自检

示例：
  python scripts/promptforge.py lookup --list
  python scripts/promptforge.py lookup --slot 袖型 --kw 凤凰
  python scripts/promptforge.py combo --seed 7 --pick
  python scripts/promptforge.py combo --color 墨黑与暗金 --sleeve 三层纱袖
  python scripts/promptforge.py portrait --tone 暗黑 --scene 废墟 --leg bold --seed 11
  python scripts/promptforge.py batch -n 50 -o out.txt --json out.json --seed 2024
  python scripts/promptforge.py verify          # 词库改动后必跑
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tone_profile as TP  # noqa: E402
import example_lexicon as EX  # noqa: E402
import render_profile as RP  # noqa: E402
import hk_profile as HK  # noqa: E402
import real_profile as RL  # noqa: E402
import sweet_profile as SW  # noqa: E402
import gauze_profile as GZ  # noqa: E402
import exposure_profile as EXP  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

# ---------------------------------------------------------------- 禁词

BANNED = [
    "九宫格", "渔网", "丝袜", "青涩", "大波浪发型", "机顶直闪",
    "皮肤白皙细腻如瓷",
]

# 词库/范例里的合法表达 → 成稿要改写掉的写法（禁词规避）
REWRITE = {
    "皮肤白皙细腻如瓷": "肤若凝脂，肌肤细腻透亮",
    "白皙细腻如瓷": "肤若凝脂，肌肤细腻透亮",
    "皮肤白皙如玉": "肤色莹白，肤质细腻",
    "皮肤苍白如玉": "肤色冷白，肌理细腻",
    "修长白皙的双腿": "修长的双腿",
    "修长白皙双腿": "修长双腿",
    "白皙的双腿": "修长的双腿",
    "白皙双腿": "修长双腿",
    "露出白皙": "露出",
}

LEG_MILD_POOL = [
    "衣料垂坠的走向勾勒出修长双腿的线条",
    "裙裾下露出修长双腿的轮廓",
    "长裙贴着小腿垂下，腿线清晰",
    "裙摆垂到脚踝，走起来露出小腿线条",
]
LEG_BOLD_POOL = [
    "裙摆高开叉至大腿根部，露出修长双腿",
    "高开叉的裙摆从胯侧一路开到腿根，整条腿露在外面",
    "裙摆斜开一道高衩，大腿线条一览无余",
]


def scrub(text: str) -> str:
    out = text
    for bad, good in sorted(REWRITE.items(), key=lambda kv: -len(kv[0])):
        out = out.replace(bad, good)
    for bad in BANNED:
        if bad in out:
            out = out.replace(bad, "")
    out = re.sub(r"[，、]{2,}", "，", out).strip("，、 ")
    # 用户要求：立绘不描述眉眼/眼眸/唇色。所有渲染路径最终都过这里，统一剔掉。
    return strip_face_words(out)


def lint(text: str) -> list[str]:
    return [b for b in BANNED if b in text]


# 用户要求：立绘不描述眉眼 / 眼眸 / 唇色。
# 妆容池与五官池里天然含这些词条，选词时先剔除掉含这些词的片段。
FACE_WORD_BLOCK = ("眉眼", "眼眸", "唇色", "唇形", "唇峰", "唇珠",
                   "嘴唇", "唇上", "唇线", "唇釉", "眼影", "眼线",
                   "眼妆", "眼窝", "眼尾", "卧蚕", "眉毛", "眉形", "眉峰")


def strip_face_words(text: str) -> str:
    """把描述眉眼/眼眸/唇的片段从逗号分隔的串里剔掉。

    例：「底妆清透有光泽，眼尾压了一点深色，唇色裸棕」
        → 「底妆清透有光泽」
    """
    if not text:
        return text
    parts = [p.strip() for p in re.split(r"[，、]", text) if p.strip()]
    keep = [p for p in parts if not any(w in p for w in FACE_WORD_BLOCK)]
    out = "，".join(keep)
    return out.strip("，、 ")


# ---------------------------------------------------------------- 数据

def load(name: str) -> dict:
    p = ASSETS / name
    if not p.exists():
        sys.exit(f"[FATAL] 缺少索引 {p}，先跑 python scripts/build_index.py")
    return json.loads(p.read_text(encoding="utf-8"))


class Data:
    def __init__(self) -> None:
        self.lex = load("lexicon.json")
        self.pools = load("pools.json")
        self.combos = self.lex["combos"]
        self.slot_values = self.lex["slot_values"]
        self.slot_bare = self.lex["slot_bare"]
        self.slot_vocab = self.lex["slot_vocab"]
        self.slots = self.lex["meta"]["combo_slots"]
        self.pool = {k: [x["value"] for x in v]
                     for k, v in self.pools["pools"].items()}


D: Data | None = None


def data() -> Data:
    global D
    if D is None:
        D = Data()
    return D


def match_bare(d: Data, slot: str, want: str) -> str | None:
    """在裸词表里精确或模糊匹配一个值。"""
    bare = d.slot_bare[slot]
    if want in bare:
        return want
    cand = [k for k in bare if want in k]
    return cand[0] if cand else None


# ---------------------------------------------------------------- lookup

def cmd_lookup(args) -> None:
    d = data()
    if args.list:
        m = d.lex["meta"]
        print(f"词库：{m['combo_count']} 条七槽组合词  "
              f"号段 {m['id_range'][0]}-{m['id_range'][1]}")
        print()
        for slot in d.slots:
            print(f"{slot:<6} {len(d.slot_values[slot]):>3} 个词值")
        print()
        print("调性：", "、".join(TP.COSTUME_POOL))
        print("场景：", "、".join(TP.SCENE_BASE))
        print()
        print("裸露档位（--exposure）：")
        for lv in EXP.EXPOSURE_LEVELS:
            print(f"  {lv:<14} {EXP.EXPOSURE_LABELS[lv]:<16} {EXP.EXPOSURE_DESC[lv]}")
        print()
        print("姿势：--pose 传具体句子，或留空按调性随机")
        return

    # --pose / --exposure 专用查询
    if getattr(args, "poses", False):
        tones = [args.tone] if args.tone in TP.COSTUME_POOL else list(TP.COSTUME_POOL)
        for tone in tones:
            opts = EXP.pose_options(tone)
            print(f"\n== {tone} 姿势 ({len(opts)}) ==")
            for p in opts:
                tag = "[动作]" if EXP.is_action_pose(p) else "[构图]"
                print(f"  {tag} {p}")
        return

    if getattr(args, "exposures", False):
        print("裸露档位：")
        for lv in EXP.EXPOSURE_LEVELS:
            print(f"  {lv:<14} {EXP.EXPOSURE_LABELS[lv]:<16} {EXP.EXPOSURE_DESC[lv]}")
        return

    if args.slot:
        slots = [s for s in d.slots if args.slot in s]
        if not slots:
            sys.exit(f"[FATAL] 没有匹配「{args.slot}」的槽位。可用：{'、'.join(d.slots)}")
    else:
        slots = d.slots

    kw = args.kw
    total = 0
    for slot in slots:
        vals = d.slot_values[slot]
        if kw:
            vals = [v for v in vals if kw in v]
        if not vals:
            continue
        total += len(vals)
        print(f"\n== {slot} ({len(vals)}) ==")
        for v in vals:
            print("  " + v)
    if not total:
        print(f"[空] 槽位={slots} 关键词={kw!r} 没有命中")


# ---------------------------------------------------------------- combo（线 D）

def assemble(d: Data, rng: random.Random, tone: str | None,
             want: dict) -> dict:
    """七槽装配。给了 tone 就在该调性池里抽，否则走词库全量。"""
    slots = {}
    for slot in d.slots:
        if slot in want and want[slot]:
            v = match_bare(d, slot, want[slot])
            if v is None:
                sys.exit(f"[FATAL] 「{want[slot]}」不在 {slot} 槽位中，"
                         f"用 lookup --slot {slot} 查可用值")
            slots[slot] = v
        elif tone:
            slots[slot] = rng.choice(TP.COSTUME_POOL[tone][slot])
        else:
            slots[slot] = rng.choice(d.slot_bare[slot])
    return slots


def render_costume(slots: dict, tone: str, rng: random.Random,
                   extras: dict | None = None, render: str = "clean") -> str:
    """七槽 + 范例组件 → 高密度服装描述。

    只用七槽会显得空（范例里每条都有上装结构、护肩、浮雕纹样、璎珞、光感收尾）；
    只用范例组件会散（没有配色材质这些骨架）。两层合并才有范例的密度。

    段落顺序对齐范例：
      上装+主裙 → 胸前肩部装饰 → 腰部 → 裙摆 → 配饰 → 光感
    """
    ex = extras or {}
    top = ex.get("上装") or rng.choice(EX.TOP_BY_TONE[tone])

    # 「浮雕」在装饰、护肩、光感三处都会出现（金属浮雕花纹 / 金属浮雕护肩 /
    # 丝绸与金属的高光质感）。三处叠加会变成「浮雕」×3，所以后抽的避开前面的。
    ornament = ex.get("装饰") or rng.choice(EX.ORNAMENT_BY_TONE[tone])

    def pick_shoulder() -> str:
        pool = EX.SHOULDER_BY_TONE[tone]
        if "浮雕" in ornament:
            fresh = [s for s in pool if "浮雕" not in s]
            return rng.choice(fresh) if fresh else rng.choice(pool)
        return rng.choice(pool)

    shoulder = ex.get("肩部") or pick_shoulder()
    # 腰部两个来源：范例的「腰饰」（宽阔金色腰带类）与词库的「腰部」槽。
    # 两者都是腰封/腰带，直接并列会重复（「复杂腰封束住腰线，精致腰封压住轮廓」）。
    # 只在语义不重叠时才并列，否则用腰饰替代腰部槽。
    waist_x = ex.get("腰饰") or rng.choice(EX.WAIST_BY_TONE[tone])

    # 袖型词条自带形态（「月牙袖口」「垂坠长袖」「宽大水袖」），
    # 后面再接动词会重复或不合物理（「垂坠长袖垂落」「贴身窄袖展开」）。
    # 只有宽松袖才「展开」，窄袖贴身垂着就好。
    sleeve = slots["袖型"]
    NARROW = ("窄袖", "贴身", "窄长")
    if any(k in sleeve for k in ("垂坠", "垂落", "层叠", "飘")):
        sleeve_phrase = sleeve
    elif any(k in sleeve for k in NARROW):
        sleeve_phrase = sleeve
    elif any(k in sleeve for k in ("广袖", "水袖", "宽袖", "大袖", "纱袖")):
        sleeve_phrase = f"{sleeve}随动作展开"
    else:
        sleeve_phrase = f"{sleeve}垂在身侧"
    waist_slot = slots["腰部"]
    # 用户锁定了腰部槽：优先用锁定的值，避免被范例腰饰挤掉
    if ex.get("腰部"):
        waist_phrase = f"{waist_slot}束住腰线"
    elif "腰封" in waist_x and "腰封" in waist_slot:
        waist_phrase = f"{waist_x}束住腰线"
    elif "腰带" in waist_x and "腰带" in waist_slot:
        waist_phrase = f"{waist_x}束住腰线"
    else:
        waist_phrase = f"{waist_x}束住腰线，{waist_slot}压住整体轮廓"
    acc = ex.get("配饰") or rng.choice(EX.ACCESSORY_BY_TONE[tone])

    # 光感收束里也带「金属」，装饰已用「金属浮雕」时优先选不带金属的
    if render == "ccd":
        glow_pool = EX.CCD_GLOW[tone]
    elif render == "gauze":
        glow_pool = EX.GAUZE_GLOW
    else:
        glow_pool = EX.GLOW_BY_TONE[tone]
    if "金属" in ornament:
        fresh_g = [g for g in glow_pool if "金属" not in g]
        glow = ex.get("光感") or (rng.choice(fresh_g) if fresh_g
                                  else rng.choice(glow_pool))
    else:
        glow = ex.get("光感") or rng.choice(glow_pool)

    s1 = (f"{slots['裙装结构']}，上身为{top}，{slots['配色']}配色，"
          f"{slots['材质']}材质")
    # 「露肩设计」不是「装饰」，是结构，不能写成「装饰X与露肩设计」。
    if "露肩" in shoulder or "不对称" in shoulder:
        shoulder_phrase = f"肩部为{shoulder}"
        s2 = (f"胸前装饰{ornament}，{shoulder_phrase}，"
              f"{slots['纹样']}刺绣沿着衣缘蔓延")
    else:
        s2 = (f"胸前与肩部装饰{ornament}与{shoulder}，"
              f"{slots['纹样']}刺绣沿着衣缘蔓延")
    s3 = f"{sleeve_phrase}，{waist_phrase}"
    if render == "ccd":
        s4 = f"{acc}在画面里只有一点微光，{glow}"
    else:
        s4 = f"{acc}在光里点出冷亮的一笔，{glow}"
    return "，".join([s1, s2]) + "。" + "，".join([s3, s4]) + "。"

def cmd_combo(args) -> None:
    d = data()
    rng = random.Random(args.seed)
    want = {
        "配色": args.color, "材质": args.fabric, "纹样": args.pattern,
        "袖型": args.sleeve, "裙装结构": args.skirt,
        "腰部": args.waist, "肩部": args.shoulder,
    }
    tone = args.tone or "仙侠"
    slots = assemble(d, rng, args.tone, want)

    core = render_costume(slots, tone, rng)
    tail = "高级感，电影级角色设计，收藏级国漫角色立绘，高精度服装细节"
    text = scrub(f"东方{tone}风格女性角色服装设计。{core}{tail}")

    if args.pick:
        print("【选中元素】")
        for k, v in slots.items():
            print(f"  {k}: {v}")
        print("\n【完整提示词】")
    print(text)

    bad = lint(text)
    if bad:
        print(f"\n[LINT-FAIL] 命中禁词：{bad}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------- portrait（线 C）

TONE_STYLE_NAME = {
    "仙侠": ["清冷仙子长裙", "九天仙女华服", "女剑仙白袍", "云海仙衣",
             "月华仙裙", "星辰仙袍", "灵蝶仙衣", "青鸾仙裙"],
    "宫廷": ["唐风宫廷华服", "东方贵族长裙", "皇族女性礼服", "王朝公主华服",
             "宫廷服饰", "凤纹宫装", "东方皇家礼服", "皇后礼服"],
    "战斗": ["东方女侠劲装", "古风战斗服", "修身侠客服", "武林女侠装",
             "东方轻甲", "短打劲装", "女剑士战袍", "女将军战甲"],
    "暗黑": ["黑紫魔女长裙", "暗金妖姬华服", "黑莲礼裙", "血月长裙",
             "紫黑薄纱长裙", "妖花纹华服", "夜蝶华服", "暗月女王礼服"],
    "新中式": ["新中式高定礼服", "现代东方长裙", "改良旗袍长裙",
               "东方剪裁礼裙", "国风晚礼服", "国风高级定制服",
               "现代云锦礼服", "都市东方礼服"],
}


def render_face(p: dict, rng: random.Random) -> str:
    """第二句：面部描述。压低跨条重复率，同时保证语法成立。

    「{面部}」是名词性中心语，只能出现在「拥有/有一张/是」之后。

    注意：**不写眉眼 / 眼眸 / 唇色** —— 只保留面部轮廓与肤质。
    """
    face, skin = p["面部"], p["肤质"]

    return rng.choice([
        f"女子拥有{face}，{skin}",
        f"她有一张{face}，{skin}",
        f"她的脸是{face}，{skin}",
        f"面孔是{face}，{skin}",
        f"这张{face}上，{skin}",
    ])


def build_portrait(d: Data, rng: random.Random, tone: str, scene_key: str,
                   leg: str, style_hint: str | None = None,
                   want: dict | None = None, render: str = "clean",
                   pose: str | None = None,
                   exposure: str = "none") -> dict:
    want = want or {}
    exposure = exposure if exposure in EXP.EXPOSURE_LEVELS else "none"

    # 港风与御姐写实都是独立风格线，不读仙侠七槽词库
    if render == "hk80s":
        return _build_hk(d, rng, scene_key, leg)
    if render == "real":
        return _build_real(d, rng, scene_key, leg)
    if render == "sweet":
        return _build_sweet(d, rng, scene_key, leg)

    if render == "gauze":
        return _build_gauze(d, rng, scene_key, leg)

    slots = assemble(d, rng, tone, want)
    # 把用户锁定的槽位也传进 render_costume，否则 ex.get("肩部") 等永远拿不到，
    # 会走 pick_xxx() 随机 —— 表现为「锁了肩部但输出是别的护肩」。
    costume = render_costume(slots, tone, rng, extras=want or None, render=render)

    style_item = style_hint or rng.choice(TONE_STYLE_NAME[tone])

    if render == "ccd":
        return _build_ccd(d, rng, tone, scene_key, leg, style_item,
                          costume, slots, want)

    scene_base = TP.SCENE_BASE.get(scene_key, TP.SCENE_BASE["云海"])
    mood = (TP.SCENE_MOOD_OVERRIDE.get((tone, scene_key))
            or TP.SCENE_MOOD[tone])
    light = TP.LIGHT_OVERRIDE.get((tone, scene_key), "柔和自然光")

    a_pool, b_pool, c_pool, noun = TP.AURA_TAIL[tone]

    # 人物层三句共用一批形容词（清冷/冷艳/雍容…），各自独立抽会导致
    # 一条里同一个词出现三次。按顺序抽，后抽的避开前面已用过的。
    # 判断必须是子串级：气质句里没有独立的「清冷」词条，只有
    # 「唇角带笑却带着不容靠近的清冷」，用整串比对永远匹配不上。
    def pick_no_overlap(pool: list[str], taken: str) -> str:
        fresh = [x for x in pool if x not in taken]
        return rng.choice(fresh) if fresh else rng.choice(pool)

    # 语义关键词：从池子里抽出的句子要检查是否携带已在别句出现过的核心词
    KEYWORDS = ["清冷", "冷艳", "雍容", "凌厉", "威仪", "明艳", "端庄",
                "疏离", "慵懒", "魅惑", "高傲", "压迫", "松弛", "知性"]

    def core_words(text: str) -> set[str]:
        return {k for k in KEYWORDS if k in text}

    def pick_avoiding(pool: list[str], banned: set[str]) -> str:
        fresh = [x for x in pool if not (core_words(x) & banned)]
        return rng.choice(fresh) if fresh else rng.choice(pool)

    gaze = pick_avoiding(TP.GAZE_POOL[tone], core_words(light))
    # 光影句也参与避让（「灯笼暖光里掺着一层清冷的月白」自带「清冷」）
    used_core = core_words(gaze) | core_words(light)

    mood_pick = pick_avoiding(TP.MOOD_POOL[tone], used_core)
    used_core |= core_words(mood_pick)

    face = pick_avoiding(TP.FACE_POOL[tone], used_core)
    used_core |= core_words(face)

    used = gaze + mood_pick + face + light

    def avoid(pool: list[str]) -> str:
        fresh = [x for x in pool if x not in used and not (core_words(x) & used_core)]
        return rng.choice(fresh) if fresh else rng.choice(pool)

    a, b, c = avoid(a_pool), avoid(b_pool), avoid(c_pool)

    # ── 姿势：显式指定优先，否则从该调性全池抽 ──
    pose_pool = EXP.pose_options(tone)
    pose_text = pose if pose else rng.choice(pose_pool)
    pose_is_action = EXP.is_action_pose(pose_text)

    # ── 裸露分级：改写服装句 + 追加身体叙事 ──
    costume_final = costume
    exposure_extra = ""
    if exposure != "none":
        tpl = EXP.COSTUME_OVERRIDE.get(exposure)
        if tpl:
            # costume_head = 服装正文的第一句（上装+配色+材质那一段）
            head = costume.split("。")[0] if "。" in costume else costume
            costume_final = tpl.format(
                costume=costume,
                costume_head=head + "。",
                costume_hint=EXP.BOTH_COSTUME_HINT.get(tone, ""),
            )
        exposure_extra = EXP.BODY_NOTE.get(exposure, "")

    return {
        "风格标签": f"东方{tone}风格",
        "人物修饰": rng.choice(["绝美年轻女子", "绝美女子", "绝美成熟女子", "绝美女王"]),
        "姿态": pose_text,
        "姿态是动作": pose_is_action,
        "眼神": gaze,
        "气质": mood_pick,
        "面部": rng.choice(TP.FACE_POOL[tone]),
        "肤质": rng.choice(TP.SKIN_POOL[tone]),
        "眉眼": rng.choice(TP.BROW_POOL[tone]),
        "眼眸": rng.choice(TP.EYE_POOL[tone]),
        "唇色": rng.choice(TP.LIP_POOL[tone]),
        "发色": rng.choice(TP.HAIR_COLOR[tone]),
        "发式": rng.choice(TP.HAIR_STYLE_LONG),
        "发式短": rng.choice(TP.HAIR_STYLE_SHORT),
        "头饰": rng.choice(EX.HAIR_ORNAMENT_BY_TONE[tone]),
        "额饰": rng.choice(EX.FOREHEAD_BY_TONE[tone]),
        "耳饰": rng.choice(EX.EARRING_BY_TONE[tone]),
        "颈饰": rng.choice(EX.NECKLACE_BY_TONE[tone]),
        "风格款": style_item,
        "服装": costume_final,
        "裸露": exposure,
        "裸露档位": EXP.EXPOSURE_LABELS.get(exposure, ""),
        "身体": exposure_extra,
        "动态": rng.choice(TP.MOTION_POOL[tone]),
        "场景": mood + scene_base,
        "光线": light,
        "氛围": f"{a}、{b}且充满{c}的{noun}",
        "调性": tone,
        "句式": rng.choice([0, 1]),
        # 全裸/露下时不写腿（避免与裸露句重复描述同一部位）
        "腿部": ("" if exposure in ("both", "lower") else
                 rng.choice(LEG_MILD_POOL) if leg == "mild"
                 else rng.choice(LEG_BOLD_POOL) if leg == "bold" else ""),
        "slots": slots,
    }


def _build_ccd(d: Data, rng: random.Random, tone: str, scene_key: str,
               leg: str, style_item: str, costume: str, slots: dict,
               want: dict) -> dict:
    """CCD 渲染层：服装保持调性，人物/光影/氛围换成生活化抓拍。

    核心反差就在这里 —— 仙侠的衣冠，配一台千禧年傻瓜相机的画质。
    """
    scene_base = TP.SCENE_BASE.get(scene_key, TP.SCENE_BASE["云海"])
    mood = (RP.CCD_SCENE_MOOD_OVERRIDE.get((tone, scene_key))
            or RP.CCD_SCENE_MOOD[tone])
    light = RP.CCD_LIGHT.get(scene_key, "现场自然光")

    a, b, c, noun = RP.CCD_AURA[tone]
    gaze = rng.choice(RP.CCD_GAZE[tone])
    mood_pick = rng.choice(RP.CCD_MOOD[tone])

    return {
        "渲染": "ccd",
        "风格标签": f"东方{tone}风格",
        "人物修饰": rng.choice(["年轻女子", "女子", "成熟女子", "姑娘",
                                 "年轻姑娘", "少妇", "少女", "年轻女人"]),
        "姿态": rng.choice(RP.CCD_POSE[tone]),
        "眼神": gaze,
        "气质": mood_pick,
        "面部": rng.choice(TP.FACE_POOL[tone]),
        "肤质": rng.choice(RP.CCD_SKIN[tone]),
        "眉眼": rng.choice(TP.BROW_POOL[tone]),
        "眼眸": rng.choice(TP.EYE_POOL[tone]),
        "唇色": rng.choice(RP.CCD_LIP[tone]),
        "发色": rng.choice(TP.HAIR_COLOR[tone]),
        "发式": rng.choice(TP.HAIR_STYLE_LONG),
        "发式短": rng.choice(TP.HAIR_STYLE_SHORT),
        # 发饰配饰保持仙侠原样 —— 这是反差的关键
        "头饰": rng.choice(EX.HAIR_ORNAMENT_BY_TONE[tone]),
        "额饰": rng.choice(EX.FOREHEAD_BY_TONE[tone]),
        "耳饰": rng.choice(EX.EARRING_BY_TONE[tone]),
        "颈饰": rng.choice(EX.NECKLACE_BY_TONE[tone]),
        "风格款": style_item,
        "服装": costume,
        "动态": rng.choice(RP.CCD_MOTION[tone]),
        "场景": mood + scene_base,
        "光线": light,
        "氛围": f"{a}、{b}的{c}",
        "调性": tone,
        "句式": rng.choice([0, 1]),
        "腿部": (rng.choice(LEG_MILD_POOL) if leg == "mild"
                 else rng.choice(LEG_BOLD_POOL) if leg == "bold" else ""),
        "slots": slots,
    }




def _build_gauze(d: Data, rng: random.Random, scene_key: str, leg: str) -> dict:
    """古风纱裙飘逸：仙侠调性的收窄模式。

    七槽全部锁在纱绸类，裙装锁叠层纱，动态锁飘动，光影锁透光。
    纱裙的成立靠三件事：材质是纱、裙摆是叠层、画面有两处在飘。
    """
    scene_base = TP.SCENE_BASE.get(scene_key, TP.SCENE_BASE["云海"])
    mood = GZ.GAUZE_SCENE_MOOD.get(scene_key, "风穿过回廊的")
    light = GZ.GAUZE_LIGHT.get(scene_key, "逆光从背后打过来，纱料透出光的轮廓")

    # 七槽：材质/裙装/袖型锁定纱类，其余照仙侠池抽
    slots = {
        "配色": rng.choice(TP.COSTUME_POOL["仙侠"]["配色"]),
        "材质": rng.choice(GZ.GAUZE_FABRIC),
        "纹样": rng.choice(TP.COSTUME_POOL["仙侠"]["纹样"]),
        "袖型": rng.choice(GZ.GAUZE_SLEEVE),
        "裙装结构": rng.choice(GZ.GAUZE_SKIRT),
        "腰部": rng.choice(TP.COSTUME_POOL["仙侠"]["腰部"]),
        "肩部": rng.choice(TP.COSTUME_POOL["仙侠"]["肩部"]),
    }

    costume = render_costume(slots, "仙侠", rng, render="gauze")

    # 飘逸必须至少两处：动态 + 裙摆物理
    motions = rng.sample(GZ.GAUZE_MOTION, 2)
    skirt_motion = rng.choice(GZ.GAUZE_SKIRT_MOTION)

    a, b, c, noun = rng.choice(GZ.GAUZE_AURA)
    gaze = rng.choice(TP.GAZE_POOL["仙侠"])
    mood_pick = rng.choice(TP.MOOD_POOL["仙侠"])
    face = rng.choice(TP.FACE_POOL["仙侠"])
    used = gaze + mood_pick + face + light

    def avoid(pool):
        fresh = [x for x in pool if x not in used]
        return rng.choice(fresh) if fresh else rng.choice(pool)

    return {
        "渲染": "gauze",
        "场景键": scene_key,
        "场景": mood + scene_base,
        "光线": light,
        "服装": costume,
        "slots": slots,
        "动态1": motions[0],
        "动态2": motions[1],
        "裙摆动态": skirt_motion,
        "风格款": rng.choice(TONE_STYLE_NAME["仙侠"]),
        "人物修饰": rng.choice(["绝美女子", "绝美年轻女子", "绝美成熟女子", "绝美女仙"]),
        "姿态": rng.choice(GZ.GAUZE_POSE),
        "眼神": gaze,
        "气质": mood_pick,
        "面部": face,
        "肤质": rng.choice(TP.SKIN_POOL["仙侠"]),
        "眉眼": rng.choice(TP.BROW_POOL["仙侠"]),
        "眼眸": rng.choice(TP.EYE_POOL["仙侠"]),
        "唇色": rng.choice(TP.LIP_POOL["仙侠"]),
        "发色": rng.choice(TP.HAIR_COLOR["仙侠"]),
        "发式": rng.choice(TP.HAIR_STYLE_LONG),
        "发式短": rng.choice(TP.HAIR_STYLE_SHORT),
        "头饰": rng.choice(EX.HAIR_ORNAMENT_BY_TONE["仙侠"]),
        "额饰": rng.choice(EX.FOREHEAD_BY_TONE["仙侠"]),
        "耳饰": rng.choice(EX.EARRING_BY_TONE["仙侠"]),
        "颈饰": rng.choice(EX.NECKLACE_BY_TONE["仙侠"]),
        "氛围": f"{a}、{b}且充满{c}的{noun}",
        "调性": "仙侠",
        "句式": rng.choice([0, 1]),
        "腿部": (rng.choice(LEG_MILD_POOL) if leg == "mild"
                 else rng.choice(LEG_BOLD_POOL) if leg == "bold" else ""),
    }


def render_gauze(p: dict) -> str:
    """纱裙飘逸骨架：人物 → 面部 → 发饰 → 服装 → 两处飘动 → 场景透光"""
    style = p["句式"]
    s1 = (f"一位东方仙侠风格的{p['人物修饰']}{p['姿态']}，"
          f"她{p['眼神']}，{p['气质']}。")
    s2 = render_face_ccd(p, random.Random()) + "。"

    neck = p["颈饰"]
    if not neck.startswith("颈部"):
        neck = "颈部佩戴" + neck
    if style == 0:
        s3 = (f"{p['发色']}色{p['发式']}，头顶佩戴{p['头饰']}，"
              f"{p['额饰']}，耳畔垂挂{p['耳饰']}，{neck}。")
    else:
        s3 = (f"她的头发是{p['发色']}色的，{p['发式短']}，"
              f"头顶佩戴{p['头饰']}，{p['额饰']}，耳畔垂挂{p['耳饰']}，{neck}。")

    s4 = f"身着{p['风格款']}。{p['服装']}"
    if not s4.endswith("。"):
        s4 += "。"

    # 纱裙的核心：两处以上在飘 + 裙摆的物理感
    s5 = f"{p['动态1']}，{p['动态2']}，{p['裙摆动态']}。"
    if p["腿部"]:
        s5 += f"{p['腿部']}。"

    s6 = f"背景为{p['场景']}，{p['光线']}，营造出{p['氛围']}氛围。"
    return scrub(s1 + s2 + s3 + s4 + s5 + s6)


def _sweet_leg(costume: str, leg: str) -> str:
    if leg == "none":
        return ""
    is_pants = costume in SW.PANTS_OUTFITS
    if leg == "bold":
        pool = SW.SWEET_LEG_BOLD_PANTS if is_pants else SW.SWEET_LEG_BOLD_SKIRT
    else:
        pool = SW.SWEET_LEG_MILD_PANTS if is_pants else SW.SWEET_LEG_MILD_SKIRT
    import random as _r
    return _r.choice(pool)


def _build_sweet(d: Data, rng: random.Random, scene_key: str, leg: str) -> dict:
    """甜妹软萌 · 真人写实：独立风格线。

    年龄边界：全部成年女性（默认 20-26 岁）。
    甜 = 面部圆润饱满 + 粉调妆 + 会笑 + 浅色柔软衣着。
    不是幼态 —— 幼态词在 SW.BANNED_JUVENILE 里全部禁掉。
    """
    scene = SW.SWEET_SCENE.get(scene_key, SW.SWEET_SCENE["咖啡店"])
    light = SW.SWEET_LIGHT.get(scene_key, "窗外的自然光从侧面进来")

    costume = rng.choice(SW.SWEET_OUTFIT)
    detail = rng.choice(SW.SWEET_DETAIL_BY_OUTFIT.get(costume, ["衣角塞得很整齐"]))

    return {
        "渲染": "sweet",
        "场景键": scene_key,
        "场景": scene,
        "光线": light,
        "服装": costume,
        "服装细节": detail,
        "脸型": rng.choice(SW.SWEET_FACE_SHAPE),
        "眉眼": rng.choice(SW.SWEET_BROW),
        "眼型": rng.choice(SW.SWEET_EYE),
        "鼻": rng.choice(SW.SWEET_NOSE),
        "唇形": rng.choice(SW.SWEET_LIP),
        "肤质": rng.choice(SW.SWEET_SKIN),
        "妆容": rng.choice(SW.SWEET_MAKEUP),
        "发式": rng.choice(SW.SWEET_HAIR),
        "配饰": rng.choice(SW.SWEET_ACCESSORY),
        "姿态": rng.choice(SW.SWEET_POSE_BY_SCENE.get(
            scene_key, SW.SWEET_POSE_BY_SCENE["咖啡店"])),
        "眼神": rng.choice(SW.SWEET_GAZE),
        "气质": rng.choice(SW.SWEET_MOOD),
        "氛围": rng.choice(SW.SWEET_AURA),
        "腿部": _sweet_leg(costume, leg),
    }


def render_sweet(p: dict) -> str:
    """甜妹骨架：{画质}。{姿态+笑}。{面部}。{妆发}。{衣着}。{场景+光}。{氛围}"""
    subj = random.Random(hash((p["服装"], p["发式"], p["场景"], p["配饰"]))).choice([
        "一个年轻女孩", "年轻女孩", "女孩", "她",
        "这位姑娘", "一个女孩", "姑娘",
    ])
    s1 = (f"{SW.SWEET_OPEN}。{subj}{p['姿态']}，"
          f"{p['眼神']}，{p['气质']}。")

    # 不写眉眼 / 眼眸 / 唇 —— 只保留鼻形。
    feat = [p["鼻"]]
    rng2 = random.Random(hash((p["服装"], p["姿态"], p["配饰"], p["发式"])))
    rng2.shuffle(feat)
    # 脸型池是完整描述句（「脸型圆润饱满，苹果肌很明显」），
    # 不能接在「五官是」后面，所以单独成句；五官另起一句。
    feat2 = "，".join(feat)
    s2 = f"{p['脸型']}，{p['肤质']}。{feat2}。"

    s3 = f"{strip_face_words(p['妆容'])}，{p['发式']}，{p['配饰']}。"
    s4 = f"穿{p['服装']}，{p['服装细节']}。"
    s5 = f"场景是{p['场景']}，{p['光线']}。"
    if p["腿部"]:
        s5 += f"{p['腿部']}。"
    s6 = f"整体是{p['氛围']}人像。"
    return scrub(s1 + s2 + s3 + s4 + s5 + s6)


def _real_leg(costume: str, leg: str) -> str:
    """按服装类型选腿部句。"""
    if leg == "none":
        return ""
    is_pants = costume in RL.PANTS_OUTFITS
    if leg == "bold":
        pool = RL.REAL_LEG_BOLD_PANTS if is_pants else RL.REAL_LEG_BOLD_SKIRT
    else:
        pool = RL.REAL_LEG_MILD_PANTS if is_pants else RL.REAL_LEG_MILD_SKIRT
    import random as _r
    return _r.choice(pool)


def _build_real(d: Data, rng: random.Random, scene_key: str, leg: str) -> dict:
    """御姐冷艳 · 真人写实：独立风格线。

    真实感靠骨相 + 皮肤纹理 + 布光，不靠「仙气」；
    冷艳靠不笑 + 直视 + 下颌微收，不靠「高贵疏离」。
    """
    scene = RL.REAL_SCENE.get(scene_key, RL.REAL_SCENE["落地窗公寓"])
    light = RL.REAL_LIGHT.get(scene_key, "单点射灯自上方打下来")

    costume = rng.choice(RL.REAL_OUTFIT)
    detail = rng.choice(RL.REAL_DETAIL_BY_OUTFIT.get(costume, ["剪裁很利落"]))

    return {
        "渲染": "real",
        "场景键": scene_key,
        "场景": scene,
        "光线": light,
        "服装": costume,
        "服装细节": detail,
        "骨相": rng.choice(RL.REAL_FACE_SHAPE),
        "眉眼": rng.choice(RL.REAL_BROW),
        "眼型": rng.choice(RL.REAL_EYE),
        "鼻": rng.choice(RL.REAL_NOSE),
        "唇形": rng.choice(RL.REAL_LIP),
        "肤质": rng.choice(RL.REAL_SKIN),
        "妆容": rng.choice(RL.REAL_MAKEUP),
        "发式": rng.choice(RL.REAL_HAIR),
        "配饰": rng.choice(RL.REAL_ACCESSORY),
        "姿态": rng.choice(RL.REAL_POSE_BY_SCENE.get(
            scene_key, RL.REAL_POSE_BY_SCENE["落地窗公寓"])),
        "眼神": rng.choice(RL.REAL_GAZE),
        "气质": rng.choice(RL.REAL_MOOD),
        "氛围": rng.choice(RL.REAL_AURA),
        "腿部": _real_leg(costume, leg),
    }


def render_real(p: dict) -> str:
    """御姐写实骨架：{画质}。{骨相}。{妆发}。{衣着}。{场景+光}。{氛围}"""
    subj = random.Random(hash((p["服装"], p["发式"], p["场景"], p["配饰"]))).choice([
        "一位成熟女性", "成熟女性", "女人", "一个女人",
        "她", "这位女性", "一名女性",
    ])
    s1 = (f"{RL.REAL_OPEN}。{subj}{p['姿态']}，"
          f"{p['眼神']}，{p['气质']}。")

    # 骨相 + 五官：顺序轮换，避免跨条塌陷。
    # 注意：**不写眉眼 / 眼眸 / 唇色** —— 只保留骨相、肤质与鼻形。
    feat = [p["鼻"]]
    rng2 = random.Random(hash((p["服装"], p["姿态"], p["配饰"], p["发式"])))
    rng2.shuffle(feat)
    lead2 = rng2.choice(["", "脸是", "五官是", "骨相上，", "这张脸"])
    body2 = "，".join([p["骨相"], p["肤质"]] + feat)
    s2 = (lead2 + body2 if lead2 else body2) + "。"

    s3 = f"{strip_face_words(p['妆容'])}，{p['发式']}，{p['配饰']}。"
    s4 = f"穿{p['服装']}，{p['服装细节']}。"
    s5 = f"场景是{p['场景']}，{p['光线']}。"
    if p["腿部"]:
        s5 += f"{p['腿部']}。"
    s6 = f"整体是{p['氛围']}人像。"
    return scrub(s1 + s2 + s3 + s4 + s5 + s6)


def _hk_leg(costume: str, leg: str) -> str:
    """按服装类型选腿部句：裤装配裤管，裙装配裙摆。"""
    if leg == "none":
        return ""
    is_pants = costume in HK.PANTS_OUTFITS
    if leg == "bold":
        pool = HK.HK_LEG_BOLD_PANTS if is_pants else HK.HK_LEG_BOLD_SKIRT
    else:
        pool = HK.HK_LEG_MILD_PANTS if is_pants else HK.HK_LEG_MILD_SKIRT
    import random as _r
    return _r.choice(pool)


def _build_hk(d: Data, rng: random.Random, scene_key: str, leg: str) -> dict:
    """1980s 港式复古：独立风格线，不套仙侠服装词库。

    港风的成立靠胶片质感 + 霓虹夜色 + 当时的衣着妆发，
    所以这一层自带服装/发型/妆容池，不读 tone_profile 的仙侠词表。
    """
    scene = HK.HK_SCENE.get(scene_key, HK.HK_SCENE["霓虹街"])
    light = HK.HK_LIGHT.get(scene_key, "霓虹灯做主光")

    costume = rng.choice(HK.HK_COSTUME)
    detail = rng.choice(HK.HK_DETAIL_BY_OUTFIT.get(costume, ["衣角没塞好"]))

    return {
        "渲染": "hk80s",
        "场景键": scene_key,
        "场景": scene,
        "光线": light,
        "服装": costume,
        "服装细节": detail,
        "发式": rng.choice(HK.HK_HAIR),
        "唇色": rng.choice(HK.HK_MAKEUP_LIP),
        "眉眼": rng.choice(HK.HK_BROW),
        "肤质": rng.choice(HK.HK_SKIN),
        "配饰": rng.choice(HK.HK_ACCESSORY),
        "姿态": rng.choice(HK.HK_POSE_BY_SCENE.get(scene_key,
                                                          HK.HK_POSE_BY_SCENE["霓虹街"])),
        "眼神": rng.choice(HK.HK_GAZE),
        "气质": rng.choice(HK.HK_MOOD),
        "氛围": rng.choice(HK.HK_AURA),
        "腿部": _hk_leg(costume, leg),
    }


def render_hk(p: dict) -> str:
    """港风骨架：{胶片}。{人物+姿态}。{妆发}。{衣着}。{场景+光}。{氛围}"""
    subj = random.Random(hash((p["服装"], p["发式"], p["场景"]))).choice([
        "一位香港女人", "女人", "年轻女人", "一个女人",
        "她", "港岛的女人", "这个女人",
    ])
    s1 = (f"{HK.FILM_OPEN}。{subj}{p['姿态']}，"
          f"{p['眼神']}，{p['气质']}。")
    # 妆发句：组件顺序轮换，压低跨条重复（港风组件少，固定语序会撞成一片）
    comps = [p["肤质"], p["眉眼"], p["唇色"], p["发式"]]
    rng2 = random.Random(hash((p["服装"], p["姿态"], p["配饰"])))
    rng2.shuffle(comps)
    lead = rng2.choice(["", "妆面是", "脸上的妆", "妆容"])
    s2 = (lead + "，".join(comps) if lead else "，".join(comps)) + "。"
    s3 = (f"穿{p['服装']}，{p['服装细节']}，{p['配饰']}。")
    s4 = f"场景是{p['场景']}，{p['光线']}。"
    if p["腿部"]:
        s4 += f"{p['腿部']}。"
    s5 = f"整体是{p['氛围']}旧照片。"
    return scrub(s1 + s2 + s3 + s4 + s5)


def render_face_ccd(p: dict, rng: random.Random) -> str:
    """CCD 版面部描述：脸要干净，且前 24 字不能恒定。

    clean 版的「这张{面部}上」会让每条前 24 字一样，批量时重复率爆掉。
    这里把组件打散，引导语也轮换。

    注意：**不写眉眼 / 眼眸 / 唇色** —— 只保留面部轮廓与肤质。
    """
    face, skin = p["面部"], p["肤质"]

    comps = [skin]
    rng.shuffle(comps)
    body = "，".join(comps)

    lead = rng.choice([
        f"{face}，{body}",
        f"她有一张{face}，{body}",
        f"脸上是{face}，{body}",
        f"五官是{face}，{body}",
        f"面孔{face}，{body}",
    ])
    return lead


def render_ccd(p: dict) -> str:
    """CCD 骨架：{质感库}，{人物+姿态}。{发饰}。身着{服装}。{光影}。{规避}"""
    style = p["句式"]
    r = RP.get("ccd")

    if style == 0:
        s1 = (f"{r['open']}。一位{p['风格标签']}的{p['人物修饰']}{p['姿态']}，"
              f"{p['眼神']}，{p['气质']}。")
    else:
        s1 = (f"{r['open']}。{p['人物修饰']}，{p['姿态']}，"
              f"{p['眼神']}，{p['气质']}。")

    s2 = render_face_ccd(p, random.Random()) + "。"

    if style == 0:
        s3 = (f"{p['发色']}色{p['发式']}，{p['头饰']}，"
              f"{p['额饰']}，耳畔垂挂{p['耳饰']}。")
    else:
        s3 = (f"头发是{p['发色']}色的，{p['发式短']}，{p['头饰']}，"
              f"{p['额饰']}，耳畔垂挂{p['耳饰']}。")

    s4 = f"身着{p['风格款']}。{p['服装']}"
    if not s4.endswith("。"):
        s4 += "。"
    s4 += f"{p['动态']}。"
    if p["腿部"]:
        s4 += f"{p['腿部']}。"

    s5 = (f"场景是{p['场景']}，{p['光线']}，"
          f"整体是{p['氛围']}的旧照片。")
    s6 = f"{r['close']}。" if r["close"] else ""

    return scrub(s1 + s2 + s3 + s4 + s5 + s6)


def render_portrait(p: dict) -> str:
    """六句骨架 → 一段可直接生图的中文提示词。"""
    if p.get("渲染") == "hk80s":
        return render_hk(p)
    if p.get("渲染") == "real":
        return render_real(p)
    if p.get("渲染") == "sweet":
        return render_sweet(p)
    if p.get("渲染") == "gauze":
        return render_gauze(p)
    if p.get("渲染") == "ccd":
        return render_ccd(p)
    style = p["句式"]
    # 动作姿态自带完整动词，不能套「以X姿态…画面」的构图句式
    if p.get("姿态是动作"):
        s1 = (f"一位{p['风格标签']}的{p['人物修饰']}{p['姿态']}，"
              f"她{p['眼神']}，{p['气质']}。")
    else:
        s1 = (f"一位{p['风格标签']}的{p['人物修饰']}{p['姿态']}，"
              f"她{p['眼神']}，{p['气质']}。")
    s2 = render_face_ccd(p, random.Random()) + "。"

    # S3：发色 + 发式 + 头饰 + 额饰 + 耳饰 + 颈饰（范例的发饰密度：冠+额前+耳畔+颈，四层叠加）
    # 颈饰词条有带「颈部佩戴」前缀的也有不带的，统一补引导词
    neck = p["颈饰"]
    if not neck.startswith("颈部"):
        neck = "颈部佩戴" + neck
    if style == 0:
        s3 = (f"{p['发色']}色{p['发式']}，头顶佩戴{p['头饰']}，"
              f"{p['额饰']}，耳畔垂挂{p['耳饰']}，{neck}。")
    else:
        s3 = (f"她的头发是{p['发色']}色的，{p['发式短']}，"
              f"头顶佩戴{p['头饰']}，{p['额饰']}，耳畔垂挂{p['耳饰']}，{neck}。")

    # 全裸时不再说「身着X」，改成赤裸陈述；其余档位保留「身着」前缀
    if p.get("裸露") == "both":
        s4 = p["服装"]
    else:
        s4 = f"身着{p['风格款']}。{p['服装']}"
    # 服装句已自带收尾句号；动态与腿部各自成句
    if not s4.endswith("。"):
        s4 += "。"
    # 裸露档位的身体叙事（紧跟服装句，描述裸露状态下的身体）
    if p.get("身体"):
        s4 += f"{p['身体']}"
        if not s4.endswith("。"):
            s4 += "。"
    # 动态词条若与服装句重复（如「丝绸自然垂坠」接「衣料垂坠…」），换一个
    dyn = p["动态"]
    if dyn in p["服装"]:
        alt = [m for m in TP.MOTION_POOL[p["调性"]] if m not in p["服装"]]
        dyn = alt[0] if alt else dyn
    # 全裸时衣物已褪，不能再写「纱裙飘动/衣料垂坠」这类依附衣物的动态
    if p.get("裸露") == "both":
        dyn = ""
    # 露上时上装已褪，避免「长袖/广袖展开」这类上装动态
    elif p.get("裸露") == "upper" and any(
        k in dyn for k in ("袖", "衣", "纱", "裙", "披帛")
    ):
        dyn = ""
    if dyn:
        s4 += f"{dyn}。"
    if p["腿部"]:
        s4 += f"{p['腿部']}。"

    if style == 0:
        s5 = f"背景为{p['场景']}，{p['光线']}，营造出{p['氛围']}氛围。"
    else:
        # 光影词条分两类：短名词（「柔和梦幻侧逆光」）需要接「擦过轮廓」，
        # 长句（「顶光从正上方垂直落下…」）本身已完整，再接动词会成病句。
        light = p["光线"]
        if "轮廓" in light or "，" in light:
            join = f"{light}，整张画面是{p['氛围']}的调子。"
        else:
            join = f"{light}擦过轮廓，整张画面是{p['氛围']}的调子。"
        s5 = f"场景落在{p['场景']}，{join}"

    return scrub(s1 + s2 + s3 + s4 + s5)


def cmd_portrait(args) -> None:
    d = data()
    rng = random.Random(args.seed)
    # 各渲染层用自己的场景表
    if args.render == "hk80s":
        scene = args.scene or args.hk_scene
    elif args.render == "real":
        scene = args.scene or args.real_scene
    elif args.render == "sweet":
        scene = args.scene or args.sweet_scene
    else:
        scene = args.scene or "云海"

    # 七槽锁词：命令行给了就锁定该槽，未给的按调性随机
    want = {}
    for slot, attr in (("配色", "color"), ("材质", "fabric"), ("纹样", "pattern"),
                       ("袖型", "sleeve"), ("裙装结构", "skirt"),
                       ("腰部", "waist"), ("肩部", "shoulder")):
        val = getattr(args, attr, None)
        if val:
            want[slot] = val

    p = build_portrait(d, rng, args.tone, scene, args.leg, args.style,
                       want=want, render=args.render,
                       pose=getattr(args, "pose", None),
                       exposure=getattr(args, "exposure", "none"))
    text = render_portrait(p)

    if args.pick:
        print("【选中元素】")
        for k, v in p.items():
            if k == "slots" or not v:
                continue
            print(f"  {k}: {v}")
        print("\n【完整提示词】")
    print(text)

    bad = lint(text)
    if bad:
        print(f"\n[LINT-FAIL] 命中禁词：{bad}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------- batch

def cmd_batch(args) -> None:
    d = data()
    rng = random.Random(args.seed)
    tones = [t.strip() for t in args.tones.split(",") if t.strip()]
    scenes = [s.strip() for s in args.scenes.split(",") if s.strip()]

    # 港风：场景用 HK 表，调性不参与
    if args.render == "hk80s":
        scenes = [s for s in scenes if s in HK.HK_SCENE] or list(HK.HK_SCENE)
    if args.render == "real":
        scenes = [s for s in scenes if s in RL.REAL_SCENE] or list(RL.REAL_SCENE)
    if args.render == "sweet":
        scenes = [s for s in scenes if s in SW.SWEET_SCENE] or list(SW.SWEET_SCENE)
    if args.render == "gauze":
        scenes = [s for s in scenes if s in GZ.GAUZE_LIGHT] or list(GZ.GAUZE_LIGHT)
    for t in tones:
        if t not in TP.COSTUME_POOL:
            sys.exit(f"[FATAL] 未知调性 {t}，可选：{'、'.join(TP.COSTUME_POOL)}")
    if args.render not in ("hk80s", "real", "sweet", "gauze"):
        for s in scenes:
            if s not in TP.SCENE_BASE:
                sys.exit(f"[FATAL] 未知场景 {s}，可选：{'、'.join(TP.SCENE_BASE)}")

    out, seen_triple, seen_text = [], set(), set()
    dup = 0
    guard = 0
    while len(out) < args.n and guard < args.n * 80:
        guard += 1
        if args.render == "hk80s":
            tone = "港风"
        elif args.render == "real":
            tone = "御姐"
        elif args.render == "sweet":
            tone = "甜妹"
        elif args.render == "gauze":
            tone = "仙侠"
        else:
            tone = rng.choice(tones)
        scene = rng.choice(scenes)
        # 三档都按用户选的来；只有 mild 保留「偶尔不露」的自然感
        leg = args.leg if args.leg in ("none", "bold") else rng.choice(["mild", "mild", "none"])
        # 裸露范围与姿势透传给 build_portrait（批量里同样生效）
        # 七槽锁词同理：用户锁了哪个槽，批量每条都用那个值
        want = {
            "配色": getattr(args, "color", None),
            "材质": getattr(args, "fabric", None),
            "纹样": getattr(args, "pattern", None),
            "袖型": getattr(args, "sleeve", None),
            "裙装结构": getattr(args, "skirt", None),
            "腰部": getattr(args, "waist", None),
            "肩部": getattr(args, "shoulder", None),
        }
        p = build_portrait(d, rng, tone, scene, leg, render=args.render,
                           want={k: v for k, v in want.items() if v} or None,
                           pose=getattr(args, "pose", None),
                           exposure=getattr(args, "exposure", "none"))
        text = render_portrait(p)
        if lint(text):
            continue
        triple = (p.get("风格款") or p.get("服装"), scene, p["姿态"])
        if triple in seen_triple or text in seen_text:
            dup += 1
            continue
        seen_triple.add(triple)
        seen_text.add(text)
        out.append({"no": len(out) + 1, "tone": tone, "scene": scene, "text": text})

    body = "\n\n".join(f"{i['no']}. {i['text']}" for i in out)
    if args.out:
        Path(args.out).write_text(body + "\n", encoding="utf-8")
        print(f"[写出] {args.out}  {len(out)} 条")
    else:
        print(body)

    if args.json:
        Path(args.json).write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[写出] {args.json}")

    fails = sum(1 for i in out if lint(i["text"]))
    dist = {}
    for i in out:
        dist[i["tone"]] = dist.get(i["tone"], 0) + 1
    print(f"[自检] 产出 {len(out)} 条 / 去重丢弃 {dup} 次 / 禁词违规 {fails} 条")
    print("[分布] " + " · ".join(f"{k}:{v}" for k, v in dist.items()))
    if fails:
        sys.exit(1)


# ---------------------------------------------------------------- verify

def cmd_verify(args) -> None:
    """词库改动后的自检：调性池词值是否仍全部存在于词库。"""
    d = data()
    errs = TP.validate_against_lexicon(d.slot_bare)
    unused = TP.unused_values(d.slot_bare)

    # 场景 × 调性的光影必须填满，缺格会回落成「柔和自然光」，
    # 撞上「暗室/近乎无光」这类场景就自相矛盾了。
    missing_light = [(t, s) for t in TP.COSTUME_POOL for s in TP.SCENE_BASE
                     if (t, s) not in TP.LIGHT_OVERRIDE]

    m = d.lex["meta"]
    print(f"[词库] {m['combo_count']} 条 / 号段 {m['id_range'][0]}-{m['id_range'][1]}")
    print("[逐槽] " + " · ".join(
        f"{k}:{len(d.slot_values[k])}" for k in d.slots))

    if unused:
        print(f"[未覆盖] {sum(len(v) for v in unused.values())} 个词库词值未被任何调性使用：")
        for k, v in unused.items():
            print(f"  {k}: {'、'.join(v)}")
    else:
        print("[覆盖] 词库全部词值已被五个调性覆盖")

    total_cells = len(TP.COSTUME_POOL) * len(TP.SCENE_BASE)
    if missing_light:
        print(f"[光影缺格] {len(missing_light)}/{total_cells} 格未定义（会回落成柔和自然光）：")
        for t, s in missing_light:
            print(f"  ({t}, {s})")
    else:
        print(f"[光影] {total_cells} 格全部已定义")

    # 范例组件也要检查：每个调性在每一层都得有货，否则 rng.choice 会 IndexError
    ex_errs = []
    EX_LAYERS = {
        "上装": EX.TOP_BY_TONE, "肩部": EX.SHOULDER_BY_TONE,
        "装饰": EX.ORNAMENT_BY_TONE, "腰饰": EX.WAIST_BY_TONE,
        "配饰": EX.ACCESSORY_BY_TONE, "光感": EX.GLOW_BY_TONE,
        "发饰": EX.HAIR_ORNAMENT_BY_TONE, "额饰": EX.FOREHEAD_BY_TONE,
        "耳饰": EX.EARRING_BY_TONE, "颈饰": EX.NECKLACE_BY_TONE,
    }
    for layer, table in EX_LAYERS.items():
        for tone in TP.COSTUME_POOL:
            if tone not in table or not table[tone]:
                ex_errs.append(f"{layer}/{tone} 缺词")
    if ex_errs:
        print(f"[范例层缺词] {len(ex_errs)} 项：")
        for e in ex_errs:
            print("  - " + e)
    else:
        n = sum(len(v) for t in EX_LAYERS.values() for v in t.values())
        print(f"[范例层] {len(EX_LAYERS)} 层 × 5 调性全部有货（共 {n} 条）")

    if errs or missing_light or ex_errs:
        if errs:
            print(f"[FAIL] {len(errs)} 项调性池与词库不一致：")
            for e in errs:
                print("  - " + e)
        sys.exit(1)
    print("[PASS] 调性池与词库一致，光影表与范例层完整")


# ---------------------------------------------------------------- CLI

def main() -> None:
    ap = argparse.ArgumentParser(
        description="国漫服装装配 + 古风仙侠立绘提示词生成器（七槽版）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("lookup", help="按槽位/关键词查词库")
    p1.add_argument("--slot", help="槽位名（支持模糊，如 袖 / 裙 / 腰）")
    p1.add_argument("--kw", help="关键词过滤")
    p1.add_argument("--list", action="store_true", help="列出槽位与调性/场景")
    p1.add_argument("--poses", action="store_true", help="列出可选姿势（配 --tone 限定）")
    p1.add_argument("--exposures", action="store_true", help="列出裸露档位")
    p1.add_argument("--tone", choices=list(TP.COSTUME_POOL), help="配 --poses 时限定调性")
    p1.set_defaults(func=cmd_lookup)

    p2 = sub.add_parser("combo", help="七槽装配一条纯服装提示词（线 D）")
    p2.add_argument("--seed", type=int, default=None)
    p2.add_argument("--tone", choices=list(TP.COSTUME_POOL), help="按调性取池")
    p2.add_argument("--color", help="指定配色，如 墨黑与暗金")
    p2.add_argument("--fabric", help="指定材质")
    p2.add_argument("--pattern", help="指定纹样")
    p2.add_argument("--sleeve", help="指定袖型")
    p2.add_argument("--skirt", help="指定裙装结构")
    p2.add_argument("--waist", help="指定腰部")
    p2.add_argument("--shoulder", help="指定肩部")
    p2.add_argument("--pick", action="store_true", help="同时打印选中元素拆解")
    p2.set_defaults(func=cmd_combo)

    p3 = sub.add_parser("portrait", help="六句骨架成稿一条立绘（线 C）")
    p3.add_argument("--tone", default="仙侠", choices=list(TP.COSTUME_POOL), help="调性")
    p3.add_argument("--scene", default=None,
                    help="场景：国漫用 TP.SCENE_BASE，港风用 HK.HK_SCENE")
    p3.add_argument("--hk-scene", default="霓虹街", choices=list(HK.HK_SCENE),
                    help="港风场景（配合 --render hk80s）")
    p3.add_argument("--real-scene", default="落地窗公寓", choices=list(RL.REAL_SCENE),
                    help="御姐写实场景（配合 --render real）")
    p3.add_argument("--sweet-scene", default="咖啡店", choices=list(SW.SWEET_SCENE),
                    help="甜妹软萌场景（配合 --render sweet）")
    p3.add_argument("--leg", default="mild", choices=["none", "mild", "bold"], help="露腿分级")
    p3.add_argument("--style", help="指定风格款，如 清冷仙子长裙")
    p3.add_argument("--pose", help="指定姿势（动作或构图），留空按调性随机")
    p3.add_argument("--exposure", default="none", choices=list(EXP.EXPOSURE_LEVELS),
                    help="裸露范围：none 全遮 / half_covered 擦边 / upper 露上 / "
                         "lower 露下 / half_nude 半裸 / both 全裸")
    p3.add_argument("--seed", type=int, default=None)
    p3.add_argument("--render", default="clean", choices=list(RP.RENDER) + ["hk80s", "real", "sweet", "gauze"],
                    help="渲染层：clean 商业级 / ccd 千禧年旧照片")
    # 服装七槽锁词：锁定后该槽不再随机（与 combo 一致）
    p3.add_argument("--color", help="指定配色，如 墨黑与暗金")
    p3.add_argument("--fabric", help="指定材质")
    p3.add_argument("--pattern", help="指定纹样")
    p3.add_argument("--sleeve", help="指定袖型")
    p3.add_argument("--skirt", help="指定裙装结构")
    p3.add_argument("--waist", help="指定腰部")
    p3.add_argument("--shoulder", help="指定肩部")
    p3.add_argument("--pick", action="store_true", help="同时打印选中元素拆解")
    p3.set_defaults(func=cmd_portrait)

    p4 = sub.add_parser("batch", help="批量产出（带去重与禁词自检）")
    p4.add_argument("-n", type=int, default=20, help="条数")
    p4.add_argument("-o", "--out", help="输出 txt 路径")
    p4.add_argument("--json", help="同时输出 json 路径")
    p4.add_argument("--seed", type=int, default=2024)
    p4.add_argument("--tones", default="仙侠,宫廷,战斗,暗黑,新中式")
    p4.add_argument("--scenes", default="庭院,云海,樱林,废墟,暗室,亭台,雪山,夜市,宫殿,竹林")
    p4.add_argument("--leg", default="mild", choices=["none", "mild", "bold"])
    p4.add_argument("--exposure", default="none", choices=list(EXP.EXPOSURE_LEVELS),
                    help="裸露范围：none 全遮 / half_covered 擦边 / upper 露上 / "
                         "lower 露下 / half_nude 半裸 / both 全裸")
    p4.add_argument("--pose", default=None,
                    help="指定姿势（动作或构图），留空按调性随机")
    p4.add_argument("--render", default="clean", choices=list(RP.RENDER) + ["hk80s", "real", "sweet", "gauze"])
    # 七槽锁词：锁定后批量里该槽不再随机（与 portrait 子命令一致）
    p4.add_argument("--color", help="锁定配色")
    p4.add_argument("--fabric", help="锁定材质")
    p4.add_argument("--pattern", help="锁定纹样")
    p4.add_argument("--sleeve", help="锁定袖型")
    p4.add_argument("--skirt", help="锁定裙装结构")
    p4.add_argument("--waist", help="锁定腰部")
    p4.add_argument("--shoulder", help="锁定肩部")
    p4.set_defaults(func=cmd_batch)

    p5 = sub.add_parser("verify", help="校验调性池与词库是否一致（改词库后必跑）")
    p5.set_defaults(func=cmd_verify)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
