#!/usr/bin/env python3
"""从 guoman-portrait-prompts 的 generate.py 抽出所有可选词池，供前端下拉。

这个 skill 的 generate.py 里已经有完整的词池（AGES/TEMPERS/HAIRS/OUTFITS/SEXY/POSES/SCENES），
直接复用，不重新造词。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

SKILL_ROOT = Path.home() / ".dsh" / "skills" / "guoman-portrait-prompts"
SCRIPTS = SKILL_ROOT / "scripts"

OUT = Path(__file__).resolve().parent / "guoman_portrait_pools.json"


def _load_generate():
    """导入 skill 的 generate.py。"""
    sys.path.insert(0, str(SCRIPTS))
    import generate as G  # type: ignore

    return G


def build() -> Dict[str, Any]:
    G = _load_generate()

    # 年龄：把「25岁」这种拆成 value/label
    ages = [{"value": "", "label": "不限"}]
    for a in getattr(G, "AGES", []):
        ages.append({"value": a, "label": a})

    # 气质
    tempers = [{"value": "", "label": "不限"}]
    for t in getattr(G, "TEMPERS", []):
        tempers.append({"value": t, "label": t})

    # 发型
    hairs = [{"value": "", "label": "不限"}]
    for h in getattr(G, "HAIRS", []):
        hairs.append({"value": h, "label": h})

    # 性感级别
    sexy = [{"value": "", "label": "不限"}]
    for s in getattr(G, "SEXY", []):
        sexy.append({"value": s, "label": s})

    # 姿势（49 条）
    poses = [{"value": "", "label": "不限（按风格自选）"}]
    for p in getattr(G, "POSES", []):
        poses.append({"value": p, "label": p})

    # 场景：generate.py 里是 (场景, 光线) 元组
    scenes: List[Dict[str, str]] = [{"value": "", "label": "不限"}]
    scene_lights: Dict[str, str] = {}
    lights: List[Dict[str, str]] = [{"value": "", "label": "不限（跟随场景）"}]
    _seen_light = set()
    for item in getattr(G, "SCENES", []):
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            sc, lt = item[0], item[1]
            scenes.append({"value": sc, "label": sc})
            scene_lights[sc] = lt
            if lt and lt not in _seen_light:
                _seen_light.add(lt)
                lights.append({"value": lt, "label": lt})
        else:
            scenes.append({"value": str(item), "label": str(item)})

    # 服装：按类别分组，每组是 (服装, 细节) 元组
    outfits: Dict[str, List[Dict[str, str]]] = {}
    raw_outfits = getattr(G, "OUTFITS", {})
    if isinstance(raw_outfits, dict):
        for cat, items in raw_outfits.items():
            rows: List[Dict[str, str]] = []
            for it in items:
                if isinstance(it, (tuple, list)) and len(it) >= 2:
                    rows.append({"value": f"{it[0]}，{it[1]}", "label": it[0]})
                else:
                    rows.append({"value": str(it), "label": str(it)})
            outfits[cat] = rows

    categories = [{"value": "", "label": "不限"}] + [
        {"value": c, "label": c} for c in getattr(G, "CATEGORY_ORDER", [])
    ]

    return {
        "ages": ages,
        "tempers": tempers,
        "hairs": hairs,
        "sexy": sexy,
        "poses": poses,
        "scenes": scenes,
        "lights": lights,
        "scene_lights": scene_lights,
        "outfits": outfits,
        "outfit_categories": categories,
        "stats": {
            "ages": len(ages) - 1,
            "tempers": len(tempers) - 1,
            "hairs": len(hairs) - 1,
            "sexy": len(sexy) - 1,
            "poses": len(poses) - 1,
            "scenes": len(scenes) - 1,
            "lights": len(lights) - 1,
            "outfits": sum(len(v) for v in outfits.values()),
            "outfit_categories": len(outfits),
        },
    }


if __name__ == "__main__":
    data = build()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in data["stats"].items():
        print(f"{k:20} {v}")
    print(f"\n写出: {OUT}")
