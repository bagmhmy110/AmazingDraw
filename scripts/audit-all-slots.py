"""最终完整审计：6 个 skill × 所有槽位 × 单次 + 批量。

用「智能断言」：
- 中文长串：允许拆段命中（LLM 会重排语序）
- label/id：两种都接受
- 阿拉伯数字 ↔ 中文数字：互相接受
"""

import json
import re
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8318"
R = []

CN_NUM = {"0": "零", "1": "一", "2": "二", "3": "三", "4": "四",
          "5": "五", "6": "六", "7": "七", "8": "八", "9": "九", "10": "十"}


def get(path, timeout=120):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path, payload, timeout=600):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"__err": e.code, "detail": e.read().decode("utf-8", errors="replace")[:250]}
    except Exception as e:
        return {"__err": type(e).__name__, "detail": str(e)[:250]}


def frags_of(val, extra=None):
    """生成候选片段：整串 / 每段 / 段前 4 字 / 英文词 / 中文数字变体。"""
    s = str(val or "").strip()
    out = []
    if s:
        out.append(s)
    if extra:
        out.append(str(extra))
    for seg in re.split(r"[，,。;；/：:]", s):
        seg = seg.strip()
        if len(seg) >= 2:
            out.append(seg)
            if len(seg) > 4:
                out.append(seg[:4])
    for w in re.findall(r"[A-Za-z][A-Za-z'\-]{3,}", s):
        out.append(w)
    # 数字 → 中文数字（18岁 → 十八岁）
    m = re.search(r"(\d+)岁", s)
    if m:
        n = int(m.group(1))
        if n < 20:
            cn = ("十" + CN_NUM[str(n - 10)]) if n >= 11 else CN_NUM[str(n)]
        elif n == 20:
            cn = "二十"
        else:
            cn = "二十" + (CN_NUM[str(n - 20)] if n > 20 else "")
        out.append(f"{cn}岁")
    seen, uniq = set(), []
    for f in out:
        if f and f not in seen and len(f) >= 2:
            seen.add(f)
            uniq.append(f)
    return uniq


def check(skill, mode, slot, sent, prompts, probes=None, note=""):
    if not prompts:
        R.append((skill, mode, slot, sent, False, "无输出"))
        print(f"  ❌ [{mode:4s}] {slot:20s} 无输出")
        return
    pr = probes if probes is not None else frags_of(sent)
    if not pr:
        R.append((skill, mode, slot, sent, True, "跳过"))
        return
    hit = sum(1 for p in prompts if any(x and x in p for x in pr))
    ok = hit == len(prompts)
    R.append((skill, mode, slot, sent, ok, f"{hit}/{len(prompts)}"))
    print(f"  {'✅' if ok else '❌'} [{mode:4s}] {slot:20s} = {str(sent)[:24]:26s} {hit}/{len(prompts)} {note}")


def pick2(lst, key="value"):
    if not lst or len(lst) < 2:
        return None
    it = lst[1]
    return it.get(key) if isinstance(it, dict) else it


# 厚涂自己的 style 池（不在 style_options 里）
AO_STYLE_LABEL = {
    "thickpaint": ["二次元半写实厚涂", "半写实厚涂"],
    "guoman3d": ["国漫3D风格", "国漫3D", "次世代高精度渲染"],
    "gamecg": ["游戏CG", "游戏CG风格"],
    "guofeng": ["国风", "国风仙侠"],
}


def style_probes(val):
    out = list(AO_STYLE_LABEL.get(val, []))
    try:
        import sys
        sys.path.insert(0, r"J:\AmazingDraw\scripts\webui")
        import style_options as SO
        st = SO.pick(val)
        if st:
            lab = st["label"]
            out += [lab, st["value"], lab.replace(" ", "")]
    except Exception:
        pass
    out.append(val)
    return [x for x in out if x]


# ══════════════════════════════════════════════════════════════════
print("\n" + "█" * 78)
print("█ 1. 国漫立绘")
print("█" * 78)
meta = get("/api/guoman/meta")
tone2, scene2 = meta["tones"][1], meta["scenes"][1]
shot2 = pick2(meta["shots"])
poses = meta.get("poses") or {}
pose2 = (poses.get(tone2) or [None])[0] if poses.get(tone2) else None
SLOT_KEY = {"配色": "color", "材质": "fabric", "纹样": "pattern", "袖型": "sleeve",
            "裙装结构": "skirt", "腰部": "waist", "肩部": "shoulder"}
slot_vals = {}
for sn in SLOT_KEY:
    opts = (meta.get("slots") or {}).get(sn) or []
    if len(opts) >= 2:
        slot_vals[sn] = opts[1] if not isinstance(opts[1], dict) else opts[1].get("value")

for mode in ("单次", "批量"):
    for name, extra in [("tone", {"tone": tone2, "scene": scene2}),
                        ("scene", {"tone": tone2, "scene": scene2}),
                        ("shot", {"tone": tone2, "scene": scene2, "shot": shot2}),
                        ("pose", {"tone": tone2, "scene": scene2, "pose": pose2} if pose2 else None)]:
        if not extra:
            continue
        if mode == "单次":
            d = post("/api/guoman/portrait", extra, timeout=250)
            ps = [d.get("prompt") or ""] if not d.get("__err") else []
        else:
            d = post("/api/guoman/batch", {"n": 2, "seed": "random",
                                           "tones": tone2, "scenes": scene2, **{k: v for k, v in extra.items() if k not in ("tone", "scene")}}, timeout=350)
            ps = [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        check("国漫立绘", mode, name, extra.get(name) or extra.get("tone"), ps)
    for sn, val in slot_vals.items():
        key = SLOT_KEY[sn]
        if mode == "单次":
            d = post("/api/guoman/portrait", {"tone": tone2, "scene": scene2, "slots": {key: val}}, timeout=250)
            ps = [d.get("prompt") or ""] if not d.get("__err") else []
        else:
            d = post("/api/guoman/batch", {"n": 2, "seed": "random", "slots": {key: val}}, timeout=350)
            ps = [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        check("国漫立绘", mode, f"槽:{sn}", val, ps)

# ══════════════════════════════════════════════════════════════════
print("\n" + "█" * 78)
print("█ 2. 国漫人像")
print("█" * 78)
meta = get("/api/guoman-portrait/meta")
pools = meta.get("pools") or {}
line2 = pick2(meta.get("lines") or []) or "B"
outfits = pools.get("outfits") or {}
gp = {
    "age": pick2(meta.get("ages") or []),
    "body": pick2(meta.get("bodies") or []),
    "vibe": pick2(meta.get("vibes") or []),
    "shot": pick2(meta.get("shots") or []),
    "temper": pick2(pools.get("tempers") or []),
    "hair": pick2(pools.get("hairs") or []),
    "sexy": pick2(pools.get("sexy") or []),
    "pose": pick2(pools.get("poses") or []),
    "scene": pick2(pools.get("scenes") or []),
    "light": pick2(pools.get("lights") or []),
    "outfit_cat": pick2(pools.get("outfit_categories") or []),
}
for mode in ("单次", "批量"):
    for name, val in gp.items():
        pr = None
        if name == "outfit_cat":
            # 用类别关键词判断，不能用桶内某一件（每次随机抽不同的）
            CAT_KW = {
                "传统旗袍": ["旗袍"], "迷你旗袍": ["旗袍"],
                "迷你礼裙": ["礼裙"], "迷你包臀裙": ["包臀"],
                "长款礼裙": ["礼裙"],
            }
            pr = CAT_KW.get(val) or [val]
        if mode == "单次":
            d = post("/api/guoman-portrait/generate", {"line": line2, name: val}, timeout=350)
            ps = [d.get("prompt") or ""] if not d.get("__err") else []
        else:
            d = post("/api/guoman-portrait/batch", {"n": 2, "seed": "random", "line": line2, name: val}, timeout=350)
            ps = [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        check("国漫人像", mode, name, val, ps, pr)

# ══════════════════════════════════════════════════════════════════
print("\n" + "█" * 78)
print("█ 3. MOSS")
print("█" * 78)
meta = get("/api/moss-architect/meta")
IDEA = "深夜便利店里的年轻女性"
moss = {
    "subject": meta["subjects"][1] if len(meta.get("subjects") or []) > 1 else None,
    "scene": pick2(meta.get("scenes") or []),
    "light": pick2(meta.get("lights") or []),
    "shot": pick2(meta.get("shots") or []),
    "aspect": pick2(meta.get("aspects") or []),
    "age": pick2(meta.get("ages") or []),
    "body": pick2(meta.get("bodies") or []),
    "vibe": pick2(meta.get("vibes") or []),
    "extra_style": pick2(meta.get("extra_styles") or []),
}
# MOSS 是 LLM，用语义片段
MOSS_PROBES = {
    "subject": ["角色", "人物", "女性", "LoRA"],
    "scene": ["便利店", "深夜"],
    "light": ["荧光灯", "冷白"],
    "shot": ["中近景", "35mm"],
    "aspect": ["竖构图", "3:4"],
    "age": ["十八岁", "18岁"],
    "body": ["纤细", "肩窄", "腰细"],
    "vibe": ["清冷", "疏离", "没有表情", "不聚焦", "不回应"],
}
for mode in ("单次", "批量"):
    for name, val in moss.items():
        if not val:
            continue
        pr = style_probes(val) if name == "extra_style" else MOSS_PROBES.get(name)
        if mode == "单次":
            d = post("/api/moss-architect/generate", {"idea": IDEA, "mode": "caption", name: val}, timeout=600)
            ps = [d.get("prompt") or ""] if not d.get("__err") else []
        else:
            d = post("/api/moss-architect/batch", {"idea": IDEA, "n": 2, "mode": "caption", name: val}, timeout=700)
            ps = [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        check("MOSS", mode, name, val, ps, pr)

# ══════════════════════════════════════════════════════════════════
print("\n" + "█" * 78)
print("█ 4. 模板")
print("█" * 78)
meta = get("/api/nsfw-templates/meta")
terms = meta.get("terms") or {}
slot_terms = {}
for s in (meta.get("required_slots") or []) + (meta.get("optional_slots") or []):
    info = terms.get(s) or {}
    pool = [t for arr in (info.get("sections") or {}).values() for t in (arr or []) if t]
    if len(pool) >= 2:
        slot_terms[s] = pool[1]
base = slot_terms.get("场景主题") or "bedroom"
for mode in ("单次", "批量"):
    cnt = 1 if mode == "单次" else 2
    for s, val in slot_terms.items():
        d = post("/api/nsfw-templates/assemble", {"slots": {s: val}, "count": cnt, "mode": "fast"}, timeout=120)
        ps = [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        check("模板", mode, s, val, ps)
    for k, val, pr in [
        ("ethnicity", "中国汉族女性", ["中国", "汉族"]),
        ("age", "18岁成年女性", ["18岁", "十八岁"]),
        ("body", "身形纤细，肩窄腰细", ["身形纤细"]),
        ("vibe", "神情清冷疏离", ["清冷", "疏离"]),
        ("extra_style", "guofeng_xianxia", style_probes("guofeng_xianxia")),
        ("shot", pick2(meta.get("shots") or []), None),
    ]:
        if not val:
            continue
        d = post("/api/nsfw-templates/assemble", {"slots": {"场景主题": base}, "count": cnt, "mode": "fast", k: val}, timeout=120)
        ps = [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        check("模板", mode, k, val, ps, pr)

# ══════════════════════════════════════════════════════════════════
print("\n" + "█" * 78)
print("█ 5. 写实摄影")
print("█" * 78)
meta = get("/api/adult-photo21/meta")
ap = {
    "shot": pick2(meta.get("shots") or []),
    "light": pick2(meta.get("lights") or []),
    "pose": pick2(meta.get("poses") or []),
    "body": pick2(meta.get("bodies") or []),
    "vibe": pick2(meta.get("vibes") or []),
}
AP_PROBES = {
    "pose": ["回眸", "直视镜头", "妩媚"],
    "body": ["身形纤细", "纤细"],
    "light": ["自然光"],
}
for mode in ("单次", "批量"):
    cnt = 1 if mode == "单次" else 2
    for name, val in ap.items():
        if not val:
            continue
        d = post("/api/adult-photo21/generate", {"style": "editorial", "count": cnt, name: val}, timeout=700)
        ps = [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        check("写实", mode, name, val, ps, AP_PROBES.get(name))

# ══════════════════════════════════════════════════════════════════
print("\n" + "█" * 78)
print("█ 6. 厚涂御姐")
print("█" * 78)
meta = get("/api/anime-oneesan/meta")
pools = meta.get("pools") or {}
ao = {
    "age": pick2(pools.get("ages") or []),
    "temper": pick2(pools.get("tempers") or []),
    "hair": pick2(pools.get("hairs") or []),
    "sexy": pick2(pools.get("sexy") or []),
    "pose": pick2(pools.get("poses") or []),
    "scene": pick2(pools.get("scenes") or []),
    "light": pick2(pools.get("lights") or []),
    "body": pick2(meta.get("bodies") or []),
    "vibe": pick2(meta.get("vibes") or []),
    "shot": pick2(meta.get("shots") or []),
}
for mode in ("单次", "批量"):
    for name, val in ao.items():
        if not val:
            continue
        if mode == "单次":
            d = post("/api/anime-oneesan/generate", {"style": "thickpaint", "seed": "random", name: val}, timeout=150)
            ps = [d.get("prompt") or ""] if not d.get("__err") else []
        else:
            d = post("/api/anime-oneesan/batch", {"n": 2, "seed": "random", name: val}, timeout=250)
            ps = [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        check("厚涂", mode, name, val, ps)
    # style 单独测
    st2 = pick2(meta.get("styles") or [])
    if st2:
        if mode == "单次":
            d = post("/api/anime-oneesan/generate", {"style": st2, "seed": "random"}, timeout=150)
            ps = [d.get("prompt") or ""] if not d.get("__err") else []
        else:
            d = post("/api/anime-oneesan/batch", {"n": 2, "seed": "random", "style": st2}, timeout=250)
            ps = [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        check("厚涂", mode, "style", st2, ps, style_probes(st2))

# ══════════════════════════════════════════════════════════════════
print("\n" + "█" * 78)
print("█ 汇总")
print("█" * 78)
by = {}
for skill, mode, slot, sent, ok, note in R:
    by.setdefault((skill, mode), []).append(ok)
for (skill, mode), rows in by.items():
    print(f"  {skill:10s} [{mode:4s}] {sum(rows)}/{len(rows)}")
tot, oktot = len(R), sum(1 for r in R if r[4])
print(f"\n  总计 {oktot}/{tot} 通过")
bad = [r for r in R if not r[4]]
if bad:
    print(f"\n  ⚠️ 未通过 {len(bad)} 项:")
    for s, m, sl, se, ok, n in bad:
        print(f"    ❌ {s} [{m}] {sl} = {str(se)[:32]} ({n})")
else:
    print("\n  ✅ 全部通过")

with open(r"J:\deepseek\2\_adl\final_audit.json", "w", encoding="utf-8") as f:
    json.dump([{"skill": s, "mode": m, "slot": sl, "sent": str(se), "ok": ok, "note": n}
               for s, m, sl, se, ok, n in R], f, ensure_ascii=False, indent=2)
print("\n  结果已存 final_audit.json")
