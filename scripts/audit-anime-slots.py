"""厚涂御姐：全部槽位 × 单次 + 批量，每项跑 3 次。"""

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


def post(path, payload, timeout=300):
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


def frags_of(val):
    s = str(val or "").strip()
    out = [s] if s else []
    for seg in re.split(r"[，,。;；/：:]", s):
        seg = seg.strip()
        if len(seg) >= 2:
            out.append(seg)
            if len(seg) > 4:
                out.append(seg[:4])
    seen, uniq = set(), []
    for f in out:
        if f and f not in seen and len(f) >= 2:
            seen.add(f)
            uniq.append(f)
    return uniq


def style_probes(val):
    AO = {
        "thickpaint": ["二次元半写实厚涂", "半写实厚涂"],
        "guoman3d": ["国漫3D风格", "国漫3D", "次世代高精度渲染"],
        "gamecg": ["游戏CG"],
        "guofeng": ["国风", "国风仙侠"],
    }
    out = list(AO.get(val, []))
    try:
        import sys
        sys.path.insert(0, r"J:\AmazingDraw\scripts\webui")
        import style_options as SO
        st = SO.pick(val)
        if st:
            out += [st["label"], st["value"]]
    except Exception:
        pass
    out.append(val)
    return [x for x in out if x]


def run_check(mode, slot, sent, fetch, probes=None):
    pr = probes if probes is not None else frags_of(sent)
    hits, detail = [], []
    for _ in range(RUNS):
        prompts = fetch()
        if not prompts:
            hits.append(False)
            detail.append("无输出")
            continue
        h = sum(1 for p in prompts if any(x and x in p for x in pr))
        hits.append(h == len(prompts))
        detail.append(f"{h}/{len(prompts)}")
    ok_n = sum(hits)
    status = "stable" if ok_n == RUNS else ("fail" if ok_n == 0 else "unstable")
    mark = {"stable": "✅", "unstable": "⚠️", "fail": "❌"}[status]
    R.append((mode, slot, sent, status, f"{ok_n}/{RUNS}"))
    print(f"  {mark} [{mode:4s}] {slot:16s} = {str(sent)[:24]:26s} {ok_n}/{RUNS}  {detail}")


meta = get("/api/anime-oneesan/meta")
pools = meta.get("pools") or {}
vals = {
    "age": (pools.get("ages") or [{}])[1].get("value") if len(pools.get("ages") or []) > 1 else None,
    "temper": (pools.get("tempers") or [{}])[1].get("value") if len(pools.get("tempers") or []) > 1 else None,
    "hair": (pools.get("hairs") or [{}])[1].get("value") if len(pools.get("hairs") or []) > 1 else None,
    "sexy": (pools.get("sexy") or [{}])[1].get("value") if len(pools.get("sexy") or []) > 1 else None,
    "pose": (pools.get("poses") or [{}])[1].get("value") if len(pools.get("poses") or []) > 1 else None,
    "scene": (pools.get("scenes") or [{}])[1].get("value") if len(pools.get("scenes") or []) > 1 else None,
    "light": (pools.get("lights") or [{}])[1].get("value") if len(pools.get("lights") or []) > 1 else None,
    "body": (meta.get("bodies") or [{}])[1].get("value") if len(meta.get("bodies") or []) > 1 else None,
    "vibe": (meta.get("vibes") or [{}])[1].get("value") if len(meta.get("vibes") or []) > 1 else None,
    "shot": (meta.get("shots") or [{}])[1].get("value") if len(meta.get("shots") or []) > 1 else None,
}
# 人种：从 ethnicity_groups 里取第一个实际值
eth_groups = meta.get("ethnicity_groups") or {}
eth_val = None
for g, arr in eth_groups.items():
    if arr:
        eth_val = arr[1] if len(arr) > 1 else arr[0]
        break
vals["ethnicity"] = eth_val
style_val = (meta.get("styles") or [{}])[1].get("value") if len(meta.get("styles") or []) > 1 else None

print("=" * 76)
print("厚涂御姐：全部槽位 × 3 次")
print("=" * 76)
print("\n可用值:")
for k, v in vals.items():
    print(f"  {k:12s} = {str(v)[:44]}")
print(f"  style        = {style_val}")
print()

for mode in ("单次", "批量"):
    print(f"── {mode} ──")
    for name, val in vals.items():
        if not val:
            continue
        if mode == "单次":
            def f(nm=name, v=val):
                d = post("/api/anime-oneesan/generate", {"style": "thickpaint", "seed": "random", nm: v}, timeout=200)
                return [d.get("prompt") or ""] if not d.get("__err") else []
        else:
            def f(nm=name, v=val):
                d = post("/api/anime-oneesan/batch", {"n": 2, "seed": "random", nm: v}, timeout=300)
                return [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        run_check(mode, name, val, f)

    # style
    if style_val:
        if mode == "单次":
            def f(sv=style_val):
                d = post("/api/anime-oneesan/generate", {"style": sv, "seed": "random"}, timeout=200)
                return [d.get("prompt") or ""] if not d.get("__err") else []
        else:
            def f(sv=style_val):
                d = post("/api/anime-oneesan/batch", {"n": 2, "seed": "random", "style": sv}, timeout=300)
                return [it.get("prompt") or "" for it in (d.get("items") or [])] if not d.get("__err") else []
        run_check(mode, "style", style_val, f, style_probes(style_val))
    print()

print("=" * 76)
print("汇总")
print("=" * 76)
by = {}
for mode, slot, sent, status, ratio in R:
    by.setdefault(mode, []).append(status)
for mode, rows in by.items():
    st = sum(1 for x in rows if x == "stable")
    un = sum(1 for x in rows if x == "unstable")
    fa = sum(1 for x in rows if x == "fail")
    print(f"  [{mode:4s}] 稳定 {st}/{len(rows)}  不稳定 {un}  失效 {fa}")

tot = len(R)
stable = sum(1 for r in R if r[3] == "stable")
print(f"\n  总计 {tot} 项：稳定 {stable}")

bad = [r for r in R if r[3] != "stable"]
if bad:
    print(f"\n  ⚠️ 需关注 {len(bad)} 项:")
    for mode, slot, sent, status, ratio in bad:
        tag = "❌失效" if status == "fail" else "⚠️不稳定"
        print(f"    {tag} [{mode}] {slot} = {str(sent)[:30]}  {ratio}")
else:
    print("\n  ✅ 全部稳定生效")
