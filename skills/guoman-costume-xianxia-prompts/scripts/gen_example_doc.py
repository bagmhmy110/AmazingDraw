# -*- coding: utf-8 -*-
"""从 example_lexicon.py 生成 references/08-范例词库.md"""
import sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import example_lexicon as EX  # noqa: E402
import tone_profile as TP  # noqa: E402

OUT = ROOT / "references" / "08-范例词库.md"

TONES = ["仙侠", "宫廷", "战斗", "暗黑", "新中式"]

LAYERS = [
    ("上装结构", "TOP_BY_TONE", EX.TOP_BY_TONE,
     "范例里 26/31 条都有「上身为X设计」，是服装密度最大的来源"),
    ("肩部 / 护肩", "SHOULDER_BY_TONE", EX.SHOULDER_BY_TONE,
     "七槽里的 `肩部` 是「花瓣肩饰/云肩」类装饰，这里是「龙鳞状护肩」类护甲，两回事"),
    ("装饰纹样", "ORNAMENT_BY_TONE", EX.ORNAMENT_BY_TONE,
     "胸前的金属浮雕、晶体刺绣、璎珞纹样"),
    ("腰饰", "WAIST_BY_TONE", EX.WAIST_BY_TONE,
     "与七槽的 `腰部` 槽并存；两者都是腰封/腰带时会自动去重"),
    ("配饰", "ACCESSORY_BY_TONE", EX.ACCESSORY_BY_TONE,
     "璎珞项链、宝石吊坠、翠玉等"),
    ("发饰（头饰）", "HAIR_ORNAMENT_BY_TONE", EX.HAIR_ORNAMENT_BY_TONE,
     "范例里发饰密度极高：冠 + 镶嵌 + 额前 + 耳畔四层叠加"),
    ("额饰", "FOREHEAD_BY_TONE", EX.FOREHEAD_BY_TONE,
     "额前印记、细链、宝石额饰"),
    ("耳饰", "EARRING_BY_TONE", EX.EARRING_BY_TONE,
     "长款流苏耳坠为主"),
    ("颈饰", "NECKLACE_BY_TONE", EX.NECKLACE_BY_TONE,
     "金色镂空颈环、银色花朵颈环"),
    ("光感收束", "GLOW_BY_TONE", EX.GLOW_BY_TONE,
     "范例里 28/31 条以「整体衣料呈现X的高光质感」收尾"),
]


def main() -> None:
    L = []
    w = L.append

    w(f"# 范例词库（去重 {len(set(v for tb in LAYERS for vals in tb[2].values() for v in vals))} 条 · 10 层）")
    w("")
    w("从 `02-仙侠范例31条.txt` 抽取的服装结构层与装饰层，")
    w("由 `scripts/example_lexicon.py` 提供，本文件是它的可读版。")
    w("")
    w("**为什么需要这一层**：主词库只有七槽骨架（配色/材质/纹样/袖型/裙装/腰部/肩部），")
    w("光靠它写出来的服装是空的 —— 没有上装结构、没有护肩、没有额饰耳饰、没有光感收尾。")
    w("范例层补的正是这些。")
    w("")
    w("---")
    w("")

    total = 0
    for title, table_name, table, note in LAYERS:
        w(f"## {title}")
        w("")
        w(f"> {note}")
        w("")
        all_vals = []
        for t in TONES:
            vals = table.get(t, [])
            all_vals.extend(vals)
        uniq = sorted(set(all_vals))
        total += len(uniq)
        w(f"**去重后 {len(uniq)} 条**，按调性分流如下：")
        w("")
        for t in TONES:
            vals = table.get(t, [])
            w(f"- **{t}**（{len(vals)}）：" + "、".join(vals))
        w("")

    w("---")
    w("")
    w("## 层级之间的冲突处理")
    w("")
    w("范例层的组件会互相撞词，脚本内置了这些避让：")
    w("")
    w("| 冲突 | 症状 | 处理 |")
    w("|------|------|------|")
    w("| 装饰 vs 护肩 | 「金属浮雕花纹」+「金属浮雕护肩」= 浮雕 ×2 | 装饰含「浮雕」时，护肩避开带浮雕的选项 |")
    w("| 装饰 vs 光感 | 「金属浮雕花纹」+「丝绸与金属的高光」= 金属 ×2 | 装饰含「金属」时，光感优先选不带金属的 |")
    w("| 腰饰 vs 七槽腰部 | 「复杂腰封束住腰线，精致腰封压住轮廓」 | 两者都是腰封/腰带时，只用腰饰替代 |")
    w("| 袖型 vs 动词 | 「垂坠长袖垂落」 | 袖型含「垂坠/层叠/飘/展开」时不再加动词 |")
    w("")
    w("---")
    w("")
    w("## 校验")
    w("")
    w("```bash")
    w("python scripts/promptforge.py verify")
    w("```")
    w("")
    w("会检查 10 层 × 5 调性是否都有词，缺任何一格都会报错并列出。")
    w("")

    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"[写出] {OUT}")
    print(f"[统计] 去重后共 {total} 条 / {len(L)} 行")


if __name__ == "__main__":
    main()
