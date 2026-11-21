# -*- coding: utf-8 -*-
"""
build_index.py — 把 references/ 里的两份原始文件解析成结构化索引。

服装词库为「组合词」单分类格式（1100 条，每条固定七槽），
仙侠范例为「N. 正文」格式（31 条）。

产出：
  assets/lexicon.json   1100 条组合词 → 七槽拆解 + 逐槽词频 + 可复现的组合池
  assets/pools.json     31 条仙侠范例 → 六句骨架的槽位词池
  assets/xianxia.json   31 条范例原文逐句切分（供检索/学句式）

用法：
  python scripts/build_index.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "references"
ASSETS = ROOT / "assets"

# 组合词七槽的固定顺序，与词库每条组合词的逗号分句一一对应
COMBO_SLOTS = ["配色", "材质", "纹样", "袖型", "裙装结构", "腰部", "肩部"]

# 词库槽值自带后缀（「月白与银灰配色」「真丝材质」「祥云纹刺绣」）。
# 调性池用裸词更方便组合，所以额外产出一份剥掉后缀的版本。
SLOT_SUFFIX = {
    "配色": "配色",
    "材质": "材质",
    "纹样": "刺绣",
}


def strip_suffix(slot: str, value: str) -> str:
    """剥掉槽值自带的分类后缀，得到裸词。"""
    suf = SLOT_SUFFIX.get(slot)
    if suf and value.endswith(suf) and len(value) > len(suf):
        return value[: -len(suf)]
    return value


def parse_lexicon(path: Path) -> list[dict]:
    """解析 `NNNN. [组合词] a，b，c，d，e，f，g` 格式。"""
    items = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(\d{4})\.\s*\[(.+?)\]\s*(.+?)\s*$", raw.strip())
        if not m:
            continue
        items.append({
            "id": int(m.group(1)),
            "cat": m.group(2).strip(),
            "text": m.group(3).strip(),
        })
    return items


def build_lexicon(path: Path) -> dict:
    items = parse_lexicon(path)
    if not items:
        sys.exit(f"[FATAL] 词库解析为空，检查文件格式：{path}")

    combos, bad = [], []
    for it in items:
        parts = [p.strip() for p in it["text"].split("，")]
        if len(parts) != 7:
            bad.append({"id": it["id"], "parts": len(parts), "text": it["text"]})
            continue
        combos.append({"id": it["id"], **dict(zip(COMBO_SLOTS, parts))})

    if not combos:
        sys.exit(f"[FATAL] 没有解析出任何七槽组合词：{path}")

    # 逐槽词频与去重词表
    slot_vocab: dict[str, dict] = {}
    slot_values: dict[str, list[str]] = {}
    slot_bare: dict[str, list[str]] = {}
    for slot in COMBO_SLOTS:
        c = Counter(x[slot] for x in combos)
        slot_vocab[slot] = dict(c.most_common())
        slot_values[slot] = sorted(c.keys())
        slot_bare[slot] = sorted({strip_suffix(slot, v) for v in c})

    ids = [c["id"] for c in combos]
    missing = [n for n in range(min(ids), max(ids) + 1) if n not in set(ids)]

    return {
        "meta": {
            "source": path.name,
            "total_items": len(items),
            "combo_count": len(combos),
            "combo_malformed": bad,
            "combo_slots": COMBO_SLOTS,
            "slot_suffix": SLOT_SUFFIX,
            "id_range": [min(ids), max(ids)],
            "missing_ids": missing,
            "slot_distinct": {k: len(v) for k, v in slot_values.items()},
        },
        "combos": combos,
        "slot_vocab": slot_vocab,
        "slot_values": slot_values,
        "slot_bare": slot_bare,
    }


# ---------------------------------------------------------------- 仙侠范例

def parse_examples(path: Path) -> list[dict]:
    """解析 `N. 正文` 格式，自动拼接跨行条目。"""
    entries, buf = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(\d{1,2})[.、]\s*(.*)$", line)
        if m:
            if buf:
                entries.append(buf)
            buf = [int(m.group(1)), m.group(2)]
        elif buf is not None:
            buf[1] += line
    if buf:
        entries.append(buf)
    return [{"no": n, "text": t} for n, t in entries]


# 槽位抽取规则：pattern → 槽名（取第一个非空捕获组）
SLOT_RULES = [
    (r"一位(东方[^，]{0,14}?风格)", "风格标签"),
    (r"绝美([\u4e00-\u9fa5]{0,6}?)(?:女子|女王)", "人物修饰"),
    (r"(?:以([\u4e00-\u9fa5]{2,8}?姿态)|(优雅地侧坐|优雅坐姿|正面居中站|正面端坐))", "姿态"),
    (r"眼神([^，。]{2,12}?)(?:地)?(?:直视镜头|望向)", "眼神"),
    (r"唇角(?:微抿)?带着([^，。]{2,14}?)的气质", "气质"),
    (r"女子拥有([^，。]{2,14}?)的?东方面容", "面部"),
    (r"(皮肤[白皙苍白][^，。]{1,10})", "肤质"),
    (r"(眉眼[^，。]{2,8})", "眉眼"),
    (r"眼眸(?:深邃明亮)?(?:呈|呈现)?([\u4e00-\u9fa5]{2,6}(?:色|色调|瞳孔))", "瞳色"),
    (r"嘴唇涂抹([\u4e00-\u9fa5]{2,10})", "唇色"),
    (r"([\u4e00-\u9fa5]{1,4}长直发)", "发色"),
    (r"(如瀑布般[^，。]{0,8}垂至腰际|如丝绸般顺滑飘散至腰际|高高盘成[^，。]{0,8}发髻)", "发式"),
    (r"(?:头顶佩戴|头顶与发侧佩戴|佩戴)([^，。]{2,20}?(?:冠|冕|发饰|发冠|头饰))", "头饰"),
    (r"背景为([^，。]{2,40})", "背景"),
    (r"(?:整体)?采用([^，。]{2,26}?(?:光|光线))", "光线"),
    (r"营造出([^，。]{2,36}?)氛围", "氛围"),
    (r"呈现出([^，。]{2,36}?)气场", "气场"),
]


def build_pools(examples: list[dict]) -> dict:
    pools: dict[str, Counter] = {}
    segs = []

    for ex in examples:
        text = ex["text"]
        sents = [s for s in re.split(r"[。；]", text) if s.strip()]
        segs.append({
            "no": ex["no"],
            "chars": len(text),
            "sentence_count": len(sents),
            "sentences": sents,
        })
        for pat, slot in SLOT_RULES:
            for m in re.finditer(pat, text):
                val = next((g for g in m.groups() if g), None)
                if not val:
                    continue
                val = val.strip("，、 ")
                if 1 <= len(val) <= 40:
                    pools.setdefault(slot, Counter())[val] += 1

    pool_out = {
        k: [{"value": v, "hits": n} for v, n in c.most_common()]
        for k, c in pools.items()
    }
    counts = Counter(s["sentence_count"] for s in segs)
    chars = [s["chars"] for s in segs]

    return {
        "meta": {
            "example_count": len(examples),
            "sentence_count_distribution": dict(sorted(counts.items())),
            "chars_min": min(chars),
            "chars_max": max(chars),
            "chars_avg": sum(chars) // len(chars),
        },
        "pools": pool_out,
        "examples": segs,
    }


# ---------------------------------------------------------------- main

def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)

    lex_src = REF / "01-服装词库-1100条.txt"
    xia_src = REF / "02-仙侠范例31条.txt"

    if not lex_src.exists():
        sys.exit(f"[FATAL] 找不到服装词库：{lex_src}")
    if not xia_src.exists():
        sys.exit(f"[FATAL] 找不到仙侠范例：{xia_src}")

    lex = build_lexicon(lex_src)
    (ASSETS / "lexicon.json").write_text(
        json.dumps(lex, ensure_ascii=False, indent=1), encoding="utf-8")

    exs = parse_examples(xia_src)
    xia = build_pools(exs)
    (ASSETS / "pools.json").write_text(
        json.dumps(xia, ensure_ascii=False, indent=1), encoding="utf-8")
    (ASSETS / "xianxia.json").write_text(
        json.dumps({"meta": xia["meta"], "examples": xia["examples"]},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    m = lex["meta"]
    print(f"[词库] {m['combo_count']} 条七槽组合词（号段 {m['id_range'][0]}-{m['id_range'][1]}）")
    if m["combo_malformed"]:
        print(f"[WARN] 组合词拆槽异常 {len(m['combo_malformed'])} 条")
    if m["missing_ids"]:
        print(f"[WARN] 缺号 {len(m['missing_ids'])} 个：{m['missing_ids'][:12]}")
    print("[逐槽词数] " + " · ".join(f"{k}:{v}" for k, v in m["slot_distinct"].items()))
    print(f"[范例] {xia['meta']['example_count']} 条 / 字数 {xia['meta']['chars_min']}-{xia['meta']['chars_max']}"
          f" 均 {xia['meta']['chars_avg']} / 句数分布 {xia['meta']['sentence_count_distribution']}")
    print(f"[词池] {len(xia['pools'])} 个槽位：" + "、".join(xia["pools"]))
    print(f"[输出] {ASSETS}")


if __name__ == "__main__":
    main()
