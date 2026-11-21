#!/usr/bin/env python3
"""从原始规则文档抽取七大词池，生成 references/pools.json。

原始文档是「提示词规则_二次元厚涂御姐_agent版.md」，
可用 --src 指定路径，默认读 skill 根目录下的 source-rules.md。

产物 pools.json 已随仓库提供，通常不需要重跑；
只有词池需要更新时才执行本脚本。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent
# 原始规则文档：默认放在 skill 根目录，可用 --src 覆盖
SRC = _SKILL_ROOT / "source-rules.md"
OUT = _SKILL_ROOT / "references" / "pools.json"

STYLE_OPEN = "Wuthering Waves style二次元半写实厚涂，竖屏构图。"
REQUIRED = "精致的东方面容"
BANNED = ["九宫格", "渔网", "青涩", "大波浪发型", "机顶直闪", "皮肤白皙细腻如瓷"]

# 风格池：每种风格有自己的开头句 + 质感要点
# 默认是原文档的「二次元半写实厚涂」，其余为扩展
STYLES = [
    {
        "value": "thickpaint",
        "label": "二次元半写实厚涂（默认）",
        "open": "Wuthering Waves style二次元半写实厚涂，竖屏构图。",
        "desc": "漫潮官方画风 · 半写实厚涂 · 笔触感与光影层次",
        "quality": "",
    },
    {
        "value": "guoman3d",
        "label": "国漫 3D 风格",
        "open": "国漫3D风格，次世代高精度渲染，竖屏构图。",
        "desc": "3D 立体感 · 次世代渲染 · 材质与皮肤次表面散射",
        "quality": "立体感强，肌肤有次表面散射的通透质感，发丝根根分明，衣料织纹与金属配饰反光真实。",
    },
    {
        "value": "gamecg",
        "label": "3A 游戏 CG",
        "open": "3A游戏CG角色原画，虚幻引擎5渲染，竖屏构图。",
        "desc": "虚幻引擎5 · 影视级材质 · 体积光与景深",
        "quality": "影视级材质细节，体积光穿过空气，景深层次分明，皮肤与布料质感达到实拍级别。",
    },
    {
        "value": "guofeng",
        "label": "国风厚涂",
        "open": "国风厚涂插画，东方古典美学，竖屏构图。",
        "desc": "水墨晕染 · 工笔重彩 · 留白与意境",
        "quality": "笔触带水墨晕染的呼吸感，色彩沉稳内敛，衣料纹样有工笔的精细，画面留白透气。",
    },
    # ── 追加画风（与原风格并列，同一套词池）──
    {
        "value": "xianxia_fairy",
        "label": "仙侠仙女古风",
        "open": "东方仙侠风格，仙气飘逸，竖屏构图。",
        "desc": "仙气飘逸 · 云海仙山 · 玉质冷光",
        "quality": "衣袂与发丝在气流中轻扬，肌肤透着玉质的冷光，画面空灵出尘。",
    },
    {
        "value": "guofeng_xianxia",
        "label": "国风仙侠",
        "open": "国风仙侠风格，东方古典美学，竖屏构图。",
        "desc": "国风古典 · 水墨远景 · 工笔近景",
        "quality": "水墨晕染的远景与工笔细描的近景交织，衣料纹样带着古典的秩序感。",
    },
    {
        "value": "street",
        "label": "街拍",
        "open": "街头抓拍风格，城市纪实摄影，竖屏构图。",
        "desc": "城市纪实 · 行人虚化 · 手持感",
        "quality": "背景行人虚化，霓虹与店铺招牌形成色块，画面有手持拍摄的轻微倾斜。",
    },
    {
        "value": "korean_hd",
        "label": "韩系高清人像",
        "open": "韩系高清人像摄影，棚拍质感，竖屏构图。",
        "desc": "韩式精修 · 柔和均匀 · 干净通透",
        "quality": "皮肤经过精修但保留质感，五官立体，光线柔和均匀，画面干净通透。",
    },
    {
        "value": "ccd_retro",
        "label": "CCD 复古",
        "open": "CCD数码相机复古质感，千禧年色调，竖屏构图。",
        "desc": "CCD 质感 · 轻微噪点 · 高光溢出",
        "quality": "画面有轻微噪点与色偏，高光溢出，边缘略软，带着旧数码相机的失真。",
    },
    {
        "value": "home_candid",
        "label": "居家日常抓拍",
        "open": "居家日常抓拍，生活纪实，竖屏构图。",
        "desc": "生活痕迹 · 自然窗光 · 不摆拍",
        "quality": "房间里有生活痕迹，光线是窗外的自然光，构图随意不摆拍。",
    },
    {
        "value": "native_no_filter",
        "label": "原生相机无滤镜",
        "open": "原生相机直出，无滤镜，竖屏构图。",
        "desc": "直出无滤镜 · 真实肤色 · 保留瑕疵",
        "quality": "肤色真实不修饰，保留皮肤纹理与细小瑕疵，色彩还原准确。",
    },
    {
        "value": "cool_white",
        "label": "冷白皮写实",
        "open": "写实人像摄影，冷白皮质感，竖屏构图。",
        "desc": "冷白通透 · 瓷质光泽 · 高对比",
        "quality": "肤色冷白通透，在光下泛着细腻的瓷质光泽，与深色背景形成对比。",
    },
    {
        "value": "y2k",
        "label": "千禧年 Y2K 真人写真",
        "open": "千禧年Y2K风格真人写真，竖屏构图。",
        "desc": "Y2K 千禧 · 闪片镭射 · 高饱和",
        "quality": "闪片、镭射与低腰元素在光下反光，色彩饱和度高，带着2000年代的张扬。",
    },
    {
        "value": "gugong_guifei",
        "label": "古风宫廷",
        "open": "古风宫廷风格，雍容华贵，竖屏构图。",
        "desc": "雍容华贵 · 织金锦缎 · 暖调宫灯",
        "quality": "宫灯与朱漆映出暖调，衣料是织金锦缎，配饰繁复沉重，气场压人。",
    },
    {
        "value": "xiyu_hanfu",
        "label": "古风异域西域汉服",
        "open": "古风西域异域风格，敦煌壁画美学，竖屏构图。",
        "desc": "敦煌矿物色 · 鎏金镶边 · 层叠披帛",
        "quality": "石青、赭石与朱砂的矿物配色，鎏金镶边在光下反光，披帛层叠垂落。",
    },
    {
        "value": "qingleng_shennv",
        "label": "古风清冷神女",
        "open": "古风清冷神女风格，疏离出尘，竖屏构图。",
        "desc": "疏离出尘 · 淡漠神情 · 素色冷光",
        "quality": "神情淡漠，眼神不带温度，素色衣料在冷光下几乎没有反光。",
    },
]


def _blocks(text: str):
    """按 ``` 切出所有代码块。"""
    return re.findall(r"```\n(.*?)```", text, re.S)


def _lines(block: str):
    out = []
    for ln in block.splitlines():
        s = ln.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


def build(src: Path | None = None):
    src = Path(src) if src else SRC
    if not src.is_file():
        raise SystemExit(
            f"[FATAL] 找不到原始规则文档：{src}\n"
            "把「提示词规则_二次元厚涂御姐_agent版.md」放到 skill 根目录并改名 "
            "source-rules.md，或用 --src 指定路径。"
        )
    text = src.read_text(encoding="utf-8", errors="replace")
    blocks = _blocks(text)

    # 年龄气质：从正文里抓
    ages = re.findall(r"`(\d+岁)`", text)
    tempers = []
    for m in re.finditer(r"气质：(.+)", text):
        tempers = re.findall(r"`([^`]+)`", m.group(1))
        if tempers:
            break

    # 发型：第一个大代码块（含「深棕齐肩短发」）
    hairs = []
    for b in blocks:
        ls = _lines(b)
        if ls and "短发" in b and "旗袍" not in b and len(ls) > 50:
            hairs = ls
            break

    # 服装：按 `**① 传统旗袍**` 之类的小节标题切
    outfits = {}
    # 用 ## 或 ** 标记的类别
    cat_pat = re.compile(
        r"\*\*(?:[①②③④⑤⑥⑦⑧]\s*)?"
        r"(传统旗袍|迷你旗袍|迷你礼裙|迷你包臀裙|长款礼裙|吊带丝袜池?|修仙女装池?|修仙迷你女装池?)"
        r"[^*]*\*\*"
    )
    marks = [(m.start(), m.group(1)) for m in cat_pat.finditer(text)]
    for i, (pos, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        seg = text[pos:end]
        # 该段里的第一个代码块
        blk = re.search(r"```\n(.*?)```", seg, re.S)
        if not blk:
            continue
        rows = []
        for ln in _lines(blk.group(1)):
            if "|" in ln:
                a, b = ln.split("|", 1)
                rows.append({"value": f"{a.strip()}，{b.strip()}", "label": a.strip()})
        if rows:
            key = name.replace("池", "")
            outfits[key] = rows

    # 性感动词：含「勾勒玲珑曲线」的块
    sexy = []
    for b in blocks:
        if "勾勒玲珑曲线" in b and "|" not in b:
            sexy = _lines(b)
            break

    # 姿态：最大的不含 | 的块，且含「站在拱桥上」
    poses = []
    for b in blocks:
        if "站在拱桥上" in b and "|" not in b:
            poses = _lines(b)
            break

    # 场景光影：含 | 的块，且行数最多
    # 注意：原文档里场景和光影是**配对**的（如「雪后庭院 | 冷白天光」），
    # 拆成两个独立池会导致「雪后庭院 + 暖黄咖啡馆」这种错配。
    scenes, lights = [], []
    seen_light = set()
    pairs = []
    for b in blocks:
        if "山间古寺台阶" in b:
            for ln in _lines(b):
                if "|" not in ln:
                    continue
                a, c = ln.split("|", 1)
                sc, lt = a.strip(), c.strip()
                scenes.append({"value": sc, "label": sc})
                pairs.append({"scene": sc, "light": lt})
                if lt and lt not in seen_light:
                    seen_light.add(lt)
                    lights.append({"value": lt, "label": lt})
            break

    # 丝袜
    stockings = []
    for b in blocks:
        if "吊带丝袜" in b and len(_lines(b)) <= 8:
            stockings = _lines(b)
            break

    return {
        "style_open": STYLE_OPEN,
        "styles": STYLES,
        "required": REQUIRED,
        "banned": BANNED,
        "ages": [{"value": a, "label": a} for a in dict.fromkeys(ages)],
        "tempers": [{"value": t, "label": t} for t in dict.fromkeys(tempers)],
        "hairs": [{"value": h, "label": h} for h in dict.fromkeys(hairs)],
        "outfits": outfits,
        "sexy": [{"value": s, "label": s} for s in dict.fromkeys(sexy)],
        "poses": [{"value": p, "label": p} for p in dict.fromkeys(poses)],
        "scenes": scenes,
        "scene_pairs": pairs,
        "lights": lights,
        "stockings": [{"value": s, "label": s} for s in dict.fromkeys(stockings)],
        "stats": {
            "ages": len(set(ages)),
            "tempers": len(set(tempers)),
            "hairs": len(set(hairs)),
            "outfits": sum(len(v) for v in outfits.values()),
            "outfit_categories": len(outfits),
            "sexy": len(set(sexy)),
            "poses": len(set(poses)),
            "scenes": len(scenes),
            "lights": len(lights),
            "stockings": len(set(stockings)),
        },
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="从原始规则文档抽取七大词池")
    ap.add_argument("--src", help="原始规则文档路径（默认 skill 根目录的 source-rules.md）")
    ap.add_argument("-o", "--out", help=f"输出 JSON 路径（默认 {OUT}）")
    args = ap.parse_args()

    data = build(args.src)
    out = Path(args.out) if args.out else OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in data["stats"].items():
        print(f"{k:20} {v}")
    print(f"\n服装类别: {list(data['outfits'].keys())}")
    print(f"写出: {out}")
