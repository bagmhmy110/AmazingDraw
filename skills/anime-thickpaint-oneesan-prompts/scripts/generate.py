#!/usr/bin/env python3
"""二次元厚涂御姐提示词批量生成。

用法：
  python generate.py -n 100 -o prompts.txt --json prompts.json --seed 2024
  python generate.py -n 50 --category 传统旗袍,迷你旗袍
  python generate.py -n 20 --include-cultivation --with-stockings 0.6
  python generate.py -n 10 --no-stockings
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REF = Path(__file__).resolve().parent.parent / "references" / "pools.json"

# 五类主线（均衡轮换用）
MAIN_CATEGORIES = ["传统旗袍", "迷你旗袍", "迷你礼裙", "迷你包臀裙", "长款礼裙"]
# 修仙扩展池
CULTIVATION = ["修仙女装", "修仙迷你女装"]


def load_pools() -> Dict[str, Any]:
    if not REF.is_file():
        sys.exit(f"[FATAL] 词池不存在：{REF}\n先跑 scripts/extract_pools.py")
    return json.loads(REF.read_text(encoding="utf-8"))


def lint(text: str, banned: List[str], required: str) -> List[str]:
    """返回命中的问题列表（空 = 通过）。"""
    issues = []
    for w in banned:
        if w in text:
            issues.append(f"禁词:{w}")
    if required not in text:
        issues.append(f"缺必含词:{required}")
    # 形容腿时禁「白皙」
    if "白皙" in text and "腿" in text:
        issues.append("腿白皙")
    return issues


def build_sentence(
    p: Dict[str, Any],
    rng: random.Random,
    *,
    category: Optional[str] = None,
    with_stockings: float = 0.4,
    style: Optional[str] = None,
    lock: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """拼一条提示词，返回 {text, elements}。

    lock: 锁定指定槽位不再随机。
        可用键：age / temper / hair / sexy / pose / scene / light / body / vibe
    """
    lock = {k: v for k, v in (lock or {}).items() if v}
    _body_shape = lock.get("body") or ""
    _vibe = lock.get("vibe") or ""
    _ethnicity = lock.get("ethnicity") or ""
    # 风格：决定开头句与质感句
    styles = p.get("styles") or []
    style_meta = None
    if styles:
        if style:
            style_meta = next((s for s in styles if s["value"] == style), None)
        if style_meta is None:
            # 默认取第一个（二次元半写实厚涂）
            style_meta = styles[0]
    open_sentence = (style_meta or {}).get("open") or p.get("style_open") or ""
    quality = (style_meta or {}).get("quality") or ""

    age = lock.get("age") or rng.choice(p["ages"])["value"]
    temper = lock.get("temper") or rng.choice(p["tempers"])["value"]
    hair = lock.get("hair") or rng.choice(p["hairs"])["value"]
    sexy = lock.get("sexy") or rng.choice(p["sexy"])["value"]
    pose = lock.get("pose") or rng.choice(p["poses"])["value"]

    # 场景 + 光影是配对的（原文档里写成「场景 | 光影」），
    # 分开随机会出现「雪后庭院 + 暖黄咖啡馆」这种错配。
    scene_lock = lock.get("scene") or ""
    light_lock = lock.get("light") or ""
    if scene_lock or light_lock:
        # 锁了场景/光影：优先用锁定的值，避免配对池把用户选择覆盖掉
        scene = scene_lock or rng.choice(p["scenes"])["value"]
        light = light_lock or rng.choice(p["lights"])["value"]
    elif p.get("scene_pairs"):
        pair = rng.choice(p["scene_pairs"])
        scene, light = pair["scene"], pair["light"]
    else:
        scene = rng.choice(p["scenes"])["value"]
        light = rng.choice(p["lights"])["value"]

    # 服装
    outfits = p["outfits"]
    if category and category in outfits:
        pool = outfits[category]
        cat_used = category
    else:
        keys = list(outfits.keys())
        cat_used = rng.choice(keys)
        pool = outfits[cat_used]
    item = rng.choice(pool)
    outfit = item["value"]

    # 丝袜点（40% 默认）
    stockings = ""
    if with_stockings > 0 and rng.random() < with_stockings and p.get("stockings"):
        stockings = rng.choice(p["stockings"])["value"]

    # 拼句
    if stockings:
        body = f"身着{outfit}，{stockings}，精致的东方面容。{sexy}。{pose}。"
    else:
        body = f"身着{outfit}，精致的东方面容。{sexy}。{pose}。"

    # 质感句（部分风格才有，插在场景之后）
    quality_part = f"{quality}" if quality else ""

    # 身材 / 表情气质：锁定了就追加到人物描述后面
    _extra = "，".join(x for x in (_body_shape, _vibe, _ethnicity) if x)
    _extra_part = f"{_extra}。" if _extra else ""

    text = (
        f"{open_sentence}"
        f"{age}{temper}，{hair}。"
        f"{body}"
        f"{_extra_part}"
        f"场景：{scene}。{light}。"
        f"{quality_part}"
    )

    return {
        "text": text,
        "elements": {
            "style": (style_meta or {}).get("value") or "",
            "style_label": (style_meta or {}).get("label") or "",
            "age": age,
            "temper": temper,
            "hair": hair,
            "outfit": outfit,
            "category": cat_used,
            "stockings": stockings,
            "sexy": sexy,
            "pose": pose,
            "scene": scene,
            "light": light,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="二次元厚涂御姐提示词批量生成")
    ap.add_argument("-n", "--num", type=int, default=20, help="生成条数")
    ap.add_argument("-o", "--out", help="输出 txt 路径")
    ap.add_argument("--json", help="输出 json 路径（含元素拆解）")
    ap.add_argument("--seed", type=int, default=2024)
    ap.add_argument("--category", help="限定服装类别（逗号分隔）")
    ap.add_argument("--with-stockings", type=float, default=0.4,
                    help="丝袜概率 0~1，默认 0.4")
    ap.add_argument("--no-stockings", action="store_true", help="完全不加丝袜")
    ap.add_argument("--include-cultivation", action="store_true",
                    help="启用修仙扩展池")
    ap.add_argument("--style", help="风格：thickpaint / guoman3d / gamecg / guofeng")
    # 锁槽：传了就固定该槽位，不传就随机
    ap.add_argument("--lock-age", help="锁定年龄")
    ap.add_argument("--lock-temper", help="锁定气质类型")
    ap.add_argument("--lock-hair", help="锁定发型（子串匹配）")
    ap.add_argument("--lock-sexy", help="锁定性感动词（子串匹配）")
    ap.add_argument("--lock-pose", help="锁定姿态（子串匹配）")
    ap.add_argument("--lock-scene", help="锁定场景（子串匹配）")
    ap.add_argument("--lock-light", help="锁定光影（子串匹配）")
    ap.add_argument("--lock-body", help="锁定身材描述")
    ap.add_argument("--lock-vibe", help="锁定表情气质描述")
    ap.add_argument("--lock-ethnicity", help="锁定人种描述")
    args = ap.parse_args()

    p = load_pools()
    rng = random.Random(args.seed)

    cats: Optional[List[str]] = None
    if args.category:
        cats = [c.strip() for c in args.category.split(",") if c.strip()]
        for c in cats:
            if c not in p["outfits"]:
                sys.exit(f"[FATAL] 未知服装类别 {c}，可选：{'、'.join(p['outfits'].keys())}")

    if not args.include_cultivation:
        # 默认排除修仙池
        p = dict(p)
        p["outfits"] = {k: v for k, v in p["outfits"].items() if k not in CULTIVATION}

    prob = 0.0 if args.no_stockings else max(0.0, min(1.0, args.with_stockings))

    out: List[Dict[str, Any]] = []
    seen: set = set()
    guard = 0
    max_guard = max(200, args.num * 60)

    lock = {
        "age": getattr(args, "lock_age", None),
        "temper": getattr(args, "lock_temper", None),
        "hair": getattr(args, "lock_hair", None),
        "sexy": getattr(args, "lock_sexy", None),
        "pose": getattr(args, "lock_pose", None),
        "scene": getattr(args, "lock_scene", None),
        "light": getattr(args, "lock_light", None),
        "body": getattr(args, "lock_body", None),
        "vibe": getattr(args, "lock_vibe", None),
        "ethnicity": getattr(args, "lock_ethnicity", None),
    }
    lock = {k: v for k, v in lock.items() if v}

    while len(out) < args.num and guard < max_guard:
        guard += 1
        cat = None
        if cats:
            cat = cats[len(out) % len(cats)]
        elif not args.category:
            # 五类均衡轮换
            avail = [c for c in MAIN_CATEGORIES if c in p["outfits"]]
            if avail:
                cat = avail[len(out) % len(avail)]

        row = build_sentence(p, rng, category=cat, with_stockings=prob,
                             style=args.style, lock=lock)
        text = row["text"]

        if text in seen:
            continue
        issues = lint(text, p["banned"], p["required"])
        if issues:
            continue

        seen.add(text)
        out.append({
            "id": len(out) + 1,
            "prompt": text,
            "elements": row["elements"],
        })

    if len(out) < args.num:
        print(f"[WARN] 只产出 {len(out)} 条（目标 {args.num}），词池组合可能不够", file=sys.stderr)

    body = "\n\n".join(f"{r['id']}. {r['prompt']}" for r in out)
    if args.out:
        Path(args.out).write_text(body + "\n", encoding="utf-8")
        print(f"[写出] {args.out}  {len(out)} 条")
    else:
        print(body)

    if args.json:
        Path(args.json).write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[写出] {args.json}")

    # 自检摘要
    fails = sum(1 for r in out if lint(r["prompt"], p["banned"], p["required"]))
    dist: Dict[str, int] = {}
    for r in out:
        c = r["elements"]["category"]
        dist[c] = dist.get(c, 0) + 1
    sock = sum(1 for r in out if r["elements"]["stockings"])

    print(f"[自检] 产出 {len(out)} 条 / 禁词违规 {fails} 条 / 丝袜 {sock} 条"
          f"（{sock * 100 // max(1, len(out))}%）")
    print("[分布] " + " · ".join(f"{k}:{v}" for k, v in dist.items()))
    if fails:
        sys.exit(1)


if __name__ == "__main__":
    main()
