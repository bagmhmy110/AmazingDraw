"""深度审计：每个槽位跑 3 次，任一次不中即标记为不稳定。

比单次测试更严格：
- 每项跑 3 次（LLM 有随机性，单次可能碰巧通过）
- 记录每次的命中情况
- 分三档：稳定生效 / 不稳定 / 完全失效
"""

import json
import re
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8318"
R = []
RUNS = 3


def get(path, timeout=120):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path, payload, timeout=700):
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


CN_NUM = {"0": "零", "1": "一", "2": "二", "3": "三", "4": "四",
          "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}


def frags_of(val, extra=None):
    s = str(val or "").strip()
    out = [s] if s else []
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
    m = re.search(r"(\d+)岁", s)
    if m:
        n = int(m.group(1))
        if n < 10:
            cn = CN_NUM[str(n)]
        elif n < 20:
            cn = "十" + (CN_NUM[str(n - 10)] if n > 10 else "")
        elif n == 20:
            cn = "二十"
        else:
            cn = "二十" + (CN_NUM[str(n - 20)] if n > 20 else "")
        out.append(cn + "岁")
    seen, uniq = set(), []
    for f in out:
        if f and f not in seen and len(f) >= 2:
            seen.add(f)
            uniq.append(f)
    return uniq


def run_check(skill, mode, slot, sent, fetch, probes=None):
    """跑 RUNS 次，记录每次命中。"""
    pr = probes if probes is not None else frags_of(sent)
    hits = []
    detail = []
    for i in range(RUNS):
        prompts = fetch()
        if not prompts:
            hits.append(False)
            detail.append("无输出")
            continue
        h = sum(1 for p in prompts if any(x and x in p for x in pr))
        hits.append(h == len(prompts))
        detail.append(f"{h}/{len(prompts)}")

    ok_n = sum(hits)
    if ok_n == RUNS:
        status = "stable"
        mark = "✅"
    elif ok_n == 0:
        status = "fail"
        mark = "❌"
    else:
        status = "unstable"
        mark = "⚠️"

    R.append((skill, mode, slot, sent, status, f"{ok_n}/{RUNS}", detail))
    print(f"  {mark} [{mode:4s}] {slot:22s} = {str(sent)[:22]:24s} {ok_n}/{RUNS}  {detail}")
    return status


def pick2(lst, key="value"):
    if not lst or len(lst) < 2:
        return None
    it = lst[1]
    return it.get(key) if isinstance(it, dict) else it


def style_probes(val):
    AO = {
        "thickpaint": ["二次元半写实厚涂", "半写实厚涂"],
        "guoman3d": ["国漫3D风格", "国漫3D", "次世代高精度渲染"],
        "gamecg": ["游戏CG", "游戏CG风格"],
        "guofeng": ["国风", "国风仙侠"],
    }
    out = list(AO.get(val, []))
    try:
        import sys
        sys.path.insert(0, r"J:\AmazingDraw\scripts\webui")
        import style_options as SO
        st = SO.pick(val)
        if st:
            out += [st["label"], st["value"], st["label"].replace(" ", "")]
    except Exception:
        pass
    out.append(val)
    return [x for x in out if x]


# ══════════════════════════════════════════════════════════════════
print("\n" + "█" * 78)
print("█ 1. 国漫立绘（每项 3 次）")
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
            def f(ex=extra):
                d = post("/api/guoman/portrait", ex, timeout=280)
                return [d.get("prompt") or ""] if not d.get("__err") else []
        else:
            def f(ex=extra):
                p = {"n": 2, "seed": "random", "tones": tone2, "scenes": scene2}
                for k in ("shot", "pose"):
                    if ex.get(k):
                        p[k] = ex[k]
                d = post("/api/guoman/batch", p, timeout=380)
                return [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        run_check("国漫立绘", mode, name, extra.get(name) or extra.get("tone"), f)

    for sn, val in slot_vals.items():
        key = SLOT_KEY[sn]
        if mode == "单次":
            def f(v=val, k=key):
                d = post("/api/guoman/portrait", {"tone": tone2, "scene": scene2, "slots": {k: v}}, timeout=280)
                return [d.get("prompt") or ""] if not d.get("__err") else []
        else:
            def f(v=val, k=key):
                d = post("/api/guoman/batch", {"n": 2, "seed": "random", "slots": {k: v}}, timeout=380)
                return [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        run_check("国漫立绘", mode, f"槽:{sn}", val, f)

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
            def f(nm=name, v=val):
                d = post("/api/guoman-portrait/generate", {"line": line2, nm: v}, timeout=380)
                return [d.get("prompt") or ""] if not d.get("__err") else []
        else:
            def f(nm=name, v=val):
                d = post("/api/guoman-portrait/batch", {"n": 2, "seed": "random", "line": line2, nm: v}, timeout=380)
                return [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        if name == "light":
            pr = ["晨雾", "晨光", "薄雾", "清晨"]
        run_check("国漫人像", mode, name, val, f, pr)

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
MOSS_P = {
    "subject": ["角色", "人物", "女性", "LoRA"],
    "scene": ["便利店", "深夜"],
    "light": ["荧光灯", "冷白"],
    "shot": ["中近景", "35mm"],
    "aspect": ["竖构图", "3:4"],
    "age": ["十八岁", "18岁"],
    "body": ["纤细", "肩窄", "腰细"],
    "vibe": ["清冷", "疏离", "没有表情", "不聚焦", "不回应", "冷淡", "漠然", "空茫", "倦怠"],
}
for mode in ("单次", "批量"):
    for name, val in moss.items():
        if not val:
            continue
        pr = style_probes(val) if name == "extra_style" else MOSS_P.get(name)
        if mode == "单次":
            def f(nm=name, v=val):
                d = post("/api/moss-architect/generate", {"idea": IDEA, "mode": "caption", nm: v}, timeout=700)
                return [d.get("prompt") or ""] if not d.get("__err") else []
        else:
            def f(nm=name, v=val):
                d = post("/api/moss-architect/batch", {"idea": IDEA, "n": 2, "mode": "caption", nm: v}, timeout=800)
                return [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        run_check("MOSS", mode, name, val, f, pr)

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
        def f(sl=s, v=val, c=cnt):
            d = post("/api/nsfw-templates/assemble", {"slots": {sl: v}, "count": c, "mode": "fast"}, timeout=120)
            return [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        run_check("模板", mode, s, val, f)
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
        def f(kk=k, v=val, c=cnt):
            d = post("/api/nsfw-templates/assemble", {"slots": {"场景主题": base}, "count": c, "mode": "fast", kk: v}, timeout=120)
            return [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        run_check("模板", mode, k, val, f, pr)

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
AP_P = {"pose": ["回眸", "直视镜头", "妩媚"], "body": ["身形纤细", "纤细"],
        "light": ["自然光", "阳光", "光线", "日光"]}
for mode in ("单次", "批量"):
    cnt = 1 if mode == "单次" else 2
    for name, val in ap.items():
        if not val:
            continue
        def f(nm=name, v=val, c=cnt):
            d = post("/api/adult-photo21/generate", {"style": "editorial", "count": c, nm: v}, timeout=800)
            return [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        run_check("写实", mode, name, val, f, AP_P.get(name))

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
            def f(nm=name, v=val):
                d = post("/api/anime-oneesan/generate", {"style": "thickpaint", "seed": "random", nm: v}, timeout=180)
                return [d.get("prompt") or ""] if not d.get("__err") else []
        else:
            def f(nm=name, v=val):
                d = post("/api/anime-oneesan/batch", {"n": 2, "seed": "random", nm: v}, timeout=280)
                return [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        run_check("厚涂", mode, name, val, f)
    st2 = pick2(meta.get("styles") or [])
    if st2:
        if mode == "单次":
            def f(sv=st2):
                d = post("/api/anime-oneesan/generate", {"style": sv, "seed": "random"}, timeout=180)
                return [d.get("prompt") or ""] if not d.get("__err") else []
        else:
            def f(sv=st2):
                d = post("/api/anime-oneesan/batch", {"n": 2, "seed": "random", "style": sv}, timeout=280)
                return [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        run_check("厚涂", mode, "style", st2, f, style_probes(st2))

# ══════════════════════════════════════════════════════════════════
print("\n" + "█" * 78)
print("█ 汇总")
print("█" * 78)
by = {}
for skill, mode, slot, sent, status, ratio, detail in R:
    by.setdefault((skill, mode), []).append(status)
for (skill, mode), rows in by.items():
    st = sum(1 for x in rows if x == "stable")
    un = sum(1 for x in rows if x == "unstable")
    fa = sum(1 for x in rows if x == "fail")
    print(f"  {skill:10s} [{mode:4s}] 稳定 {st}/{len(rows)}  不稳定 {un}  失效 {fa}")

tot = len(R)
stable = sum(1 for r in R if r[4] == "stable")
unstable = sum(1 for r in R if r[4] == "unstable")
failed = sum(1 for r in R if r[4] == "fail")
print(f"\n  总计 {tot} 项：稳定 {stable} / 不稳定 {unstable} / 失效 {failed}")

bad = [r for r in R if r[4] != "stable"]
if bad:
    print(f"\n  ⚠️ 需要关注 {len(bad)} 项:")
    for skill, mode, slot, sent, status, ratio, detail in bad:
        tag = "❌失效" if status == "fail" else "⚠️不稳定"
        print(f"    {tag} {skill} [{mode}] {slot} = {str(sent)[:30]}  {ratio}  {detail}")
else:
    print("\n  ✅ 全部稳定生效")

with open(r"J:\AmazingDraw\docs-screenshots\deep_audit.json", "w", encoding="utf-8") as f:
    json.dump([{"skill": s, "mode": m, "slot": sl, "sent": str(se), "status": st, "ratio": r, "detail": d}
               for s, m, sl, se, st, r, d in R], f, ensure_ascii=False, indent=2)
print("\n  结果已存 docs-screenshots/deep_audit.json")
