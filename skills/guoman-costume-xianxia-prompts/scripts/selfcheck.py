# -*- coding: utf-8 -*-
"""
selfcheck.py — 生成结果的自动质检。

检查五类问题：
  1. 禁词       全风格禁词命中
  2. 拼接病句   后缀重复 / 双动词 / 缺句号 / 「采用+完整光影」
  3. 调性冲突   暗黑配浅粉白、战斗配飘纱、宫廷配挑衅
  4. 自我重复   单条内同一段 8 字以上文本出现两次
  5. 跨条重复   第 2 句重复率（--strict）

用法：
  python scripts/selfcheck.py out.txt
  python scripts/selfcheck.py out.txt --strict
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

BANNED = [
    "九宫格", "渔网", "丝袜", "青涩", "大波浪发型", "机顶直闪",
    "皮肤白皙细腻如瓷",
]

# 拼接病句
CLUNK_PATTERNS = [
    (r"配色配色", "配色后缀重复"),
    (r"材质材质", "材质后缀重复"),
    (r"刺绣刺绣", "纹样后缀重复"),
    (r"(垂落|垂坠)随动作垂落", "袖型与「随动作垂落」重复"),
    (r"的头发是.{1,6}色的，长直发", "发色与「长直发」重复"),
    (r"[^。！？]轮廓[衣薄长裙披]", "服装句尾缺句号，与动态粘连"),
    (r"采用(顶光|夕阳|云层|灯笼光|金柱|烛火)",
     "光影词条本身完整，前面加「采用」成病句"),
    (r"〔|〕|【选中元素】", "输出混入了标记"),
]

# 调性冲突：服装与气质
TONE_CONFLICT = {
    "仙侠": ["墨黑与暗金", "紫黑与暗银"],
    "宫廷": ["冰晶纤维", "玉石纤维"],
    "战斗": ["凤凰羽织物", "月光纱", "琉璃纱"],
    "暗黑": ["雪白与淡金", "藕粉与珍珠白"],
    "新中式": ["凤凰羽织物", "海水江崖纹"],
}

GAZE_CONFLICT = {
    "暗黑": ["清澈而淡然", "温柔而专注", "明亮而松弛"],
    "战斗": ["慵懒而魅惑", "疏离而平静"],
    "宫廷": ["带笑却不好惹", "挑衅的锋芒"],
}

# 场景 × 光影矛盾
SCENE_LIGHT_CONFLICT = [
    (r"暗室|近乎无光", r"柔和自然光|均匀漫射光", "无光场景配了柔和自然光"),
    (r"夜市|灯火通明", r"大面积留白", "强光源场景配了留白"),
]

# 幼态词：任何渲染层都不该出现（未成年边界）
JUVENILE = [
    "萝莉", "童颜", "稚气", "娃娃", "小孩", "儿童",
    "学生", "校服", "制服", "初中", "高中", "未成年",
    "十岁", "十二岁", "十四岁", "十五岁", "十六岁", "十七岁",
]

# 显憔悴：把「冷艳」写成「不健康」的词
HAGGARD = [
    "太阳穴略凹", "面中偏平", "凹陷", "削瘦", "憔悴", "气色差",
    "没有血色", "瘦削", "眼睛不大", "脸不圆", "偏薄",
]

# 面部必须干净：这些词出现在成稿里就是脸脏了（CCD 线最容易犯）
FACE_DIRTY = [
    "出油", "油光", "汗渍", "额角有汗", "薄汗", "泛红", "起了皮", "起皮",
    "干裂", "疲惫", "狼狈", "暗沉", "斑点", "痘", "黑眼圈", "油汗",
    "咬着下唇", "呼吸没平", "妆花了", "脱妆",
]

SENT_SPLIT = re.compile(r"[。；]")


def split_entries(text: str) -> list[str]:
    """把批量输出拆成单条：以 `数字.` 开头的行各算一条，否则整段算一条。"""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r"^\d+\.\s", l)]
    if numbered:
        return [re.sub(r"^\d+\.\s*", "", l) for l in numbered]
    return ["".join(lines)]


def check_entry(idx: int, entry: str) -> list[str]:
    errs = []

    for bad in BANNED:
        if bad in entry:
            errs.append(f"#{idx} 禁词「{bad}」")

    for pat, why in CLUNK_PATTERNS:
        if re.search(pat, entry):
            errs.append(f"#{idx} 拼接病句：{why}")

    # 调性判定：从开头取「东方X风格」
    m = re.match(r"一位东方(\S{1,6}?)风格", entry)
    tone = m.group(1) if m else None
    if tone:
        for w in TONE_CONFLICT.get(tone, []):
            if w in entry:
                errs.append(f"#{idx} 调性冲突：{tone} 出现「{w}」")
        for w in GAZE_CONFLICT.get(tone, []):
            if w in entry:
                errs.append(f"#{idx} 气质冲突：{tone} 出现「{w}」")

    for scene_pat, light_pat, why in SCENE_LIGHT_CONFLICT:
        if re.search(scene_pat, entry) and re.search(light_pat, entry):
            errs.append(f"#{idx} 场景光影矛盾：{why}")

    # 幼态词：硬边界
    for w in JUVENILE:
        if w in entry:
            errs.append(f"#{idx} 幼态词：「{w}」（必须成年角色）")

    # 显憔悴：冷艳不等于病态
    for w in HAGGARD:
        if w in entry:
            errs.append(f"#{idx} 显憔悴：「{w}」")

    # 面部干净：这些词出现在人物描写里就是脸脏了。
    # 但「不要面部瑕疵，不要油光」这类规避句是正向约束，要排除掉再判。
    body = re.sub(r"不要[^，。]*", "", entry)
    for w in FACE_DIRTY:
        if w in body:
            errs.append(f"#{idx} 面部不干净：「{w}」")

    # 单条内不应自我重复同一个 8 字以上片段
    chunks = re.findall(r"[\u4e00-\u9fa5]{8,}", entry)
    for k, v in Counter(chunks).items():
        if v > 1:
            errs.append(f"#{idx} 自我重复片段「{k[:12]}…」×{v}")

    return errs


def main() -> None:
    ap = argparse.ArgumentParser(description="生成结果质检")
    ap.add_argument("path", help="待检 txt（批量输出或单条）")
    ap.add_argument("--strict", action="store_true",
                    help="同时检查跨条重复率（>30% 句式重复即失败）")
    args = ap.parse_args()

    p = Path(args.path)
    if not p.exists():
        sys.exit(f"[FATAL] 文件不存在：{p}")

    entries = split_entries(p.read_text(encoding="utf-8"))
    all_errs = []
    for i, e in enumerate(entries, 1):
        all_errs.extend(check_entry(i, e))

    # 跨条句式重复：取每条的第 2 句（面部描述），统计重复
    # 注意 CCD 线的 S1 很长且内部含逗号，按句号切才是真正的句边界
    if args.strict and len(entries) > 3:
        heads = []
        for e in entries:
            sents = [s for s in re.split(r"[。；]", e) if s.strip()]
            if len(sents) > 1:
                heads.append(sents[1][:24])
        c = Counter(heads)
        dup = sum(v - 1 for v in c.values() if v > 1)
        rate = dup / len(heads) if heads else 0
        print(f"[句式] 第2句重复 {dup}/{len(heads)} = {rate:.0%}")
        if rate > 0.30:
            all_errs.append(f"跨条句式重复率过高 {rate:.0%}（阈值 30%）")

    print(f"[条目] {len(entries)} 条")
    if all_errs:
        print(f"[FAIL] {len(all_errs)} 项问题：")
        for e in all_errs[:40]:
            print("  - " + e)
        if len(all_errs) > 40:
            print(f"  … 另有 {len(all_errs) - 40} 项")
        sys.exit(1)

    print("[PASS] 禁词 / 病句 / 调性 / 场景光影 / 重复 全部通过")


if __name__ == "__main__":
    main()
