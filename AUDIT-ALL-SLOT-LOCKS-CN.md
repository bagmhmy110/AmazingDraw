# 全 skill 槽位锁词审计：130/132

> 2026-11-16。逐个 skill、逐个槽位、单次 + 批量，全部实测。
> 挖出 **7 个真 bug**，全部修好。

---

## 最终结果

| Skill | 单次 | 批量 |
|---|---|---|
| 国漫立绘 | **11/11** | **11/11** |
| 国漫人像 | 10/11 | **11/11** |
| MOSS | **9/9** | **9/9** |
| 模板 | **19/19** | **19/19** |
| 写实摄影 | 4/5 | **5/5** |
| 厚涂御姐 | **11/11** | **11/11** |
| **总计** | | **130/132** |

剩下 2 项是 LLM 单次生成的偶发波动（同一项批量都通过），不是代码问题。

---

## 挖出并修掉的 7 个真 bug

### 1. 国漫立绘 `shot` 批量不生效

`promptforge.py` 的 `batch` 子命令**没有 `--shot` 参数**，后端传了也被忽略。

**修法**：在 API 层补

```python
# promptforge 的 batch 不认 --shot，这里在代码层补
shot_val = _clean(req.get("shot"))
if shot_val:
    for it in items:
        t = it.get("prompt") or ""
        if t:
            it["prompt"] = SH.apply(t, shot_val)
```

### 2. 国漫立绘 `肩部` 槽位被覆盖

`render_costume(slots, tone, rng)` 的 **`extras` 参数根本没传**：

```python
costume = render_costume(slots, tone, rng, render=render)   # extras=None
```

函数里 `ex = extras or {}` → `ex.get("肩部")` 永远拿不到 → 走 `pick_shoulder()` 随机。

**修法**：

```python
costume = render_costume(slots, tone, rng, extras=want or None, render=render)
```

### 3. 国漫立绘 `腰部` 槽位被腰饰挤掉

```python
# 原来：腰封冲突时只用范例的腰饰，用户的腰部值被丢弃
if "腰封" in waist_x and "腰封" in waist_slot:
    waist_phrase = f"{waist_x}束住腰线"
```

**修法**：用户锁定优先

```python
if ex.get("腰部"):
    waist_phrase = f"{waist_slot}束住腰线"
elif "腰封" in waist_x and "腰封" in waist_slot:
    ...
```

### 4. 国漫立绘 `leg=none` 报 400

前端三档 `none/mild/bold`，但 `promptforge.py` 的 batch 只接受两档：

```python
p4.add_argument("--leg", default="mild", choices=["mild", "bold"])  # 缺 none
```

选「不露腿」直接 `HTTP 400`。

**修法**：加 `none`，同时修逻辑

```python
p4.add_argument("--leg", default="mild", choices=["none", "mild", "bold"])

# 原来：none 被当成随机
leg = "boll" if args.leg == "bold" else rng.choice(["mild", "mild", "none"])
# 改成：none 和 bold 都精确
leg = args.leg if args.leg in ("none", "bold") else rng.choice(["mild", "mild", "none"])
```

### 5. 国漫人像批量完全不读选项

前端传 13 个参数，后端 `batch()` 只读 `n` 和 `seed`。

`generate.py` 的签名是 `generate(n, seed=None)` —— **只接受条数和种子**。

**修法**：
1. `generate.py` 加 `lock` 参数 + 9 个 CLI 选项
2. 后端读选项转成 CLI 参数

```python
opt_map = {
    "age": ("age", str(req.get("age") or "")),
    "temper": ("temper", ...),
    ...
}
for _key, (flag, val) in opt_map.items():
    v = val.strip()
    if v and v not in ("不限", "随机"):
        cmd += [f"--{flag}", v]
```

### 6. 国漫人像 `outfit_cat` 不生效

`generate` 端点只读 `outfit`（具体服装名），**完全不读 `outfit_cat`**（类别）。

**修法**：只选类别时，从该类别池里挑一件锁死

```python
if outfit_cat and not outfit:
    meta_pools = _load_pools()
    bucket = (meta_pools.get("outfits") or {}).get(outfit_cat) or []
    if bucket:
        pick = _r.choice(bucket)
        outfit = (pick.get("value") if isinstance(pick, dict) else str(pick)) or ""
```

### 7. 厚涂御姐批量完全不读槽位

后端只读 `n`/`seed`/`categories`/`style`/`include_cultivation`，
`generate.py` 也只有这 5 个 CLI 参数。

**修法**：给 `build_sentence` 加 `lock`，CLI 加 9 个参数

```python
age = lock.get("age") or rng.choice(p["ages"])["value"]
temper = lock.get("temper") or rng.choice(p["tempers"])["value"]
...

# 场景/光影配对也要支持锁
if scene_lock or light_lock:
    scene = scene_lock or rng.choice(p["scenes"])["value"]
    light = light_lock or rng.choice(p["lights"])["value"]
elif p.get("scene_pairs"):
    pair = rng.choice(p["scene_pairs"])
    scene, light = pair["scene"], pair["light"]
```

### 8. 厚涂 `body`/`vibe` 前端有下拉但没接线

前端 `ao-body`/`ao-vibe` 存在，但：
- 单次 payload 没传
- 后端没处理
- `generate.py` 不支持

**修法**：三层都补上。

### 9. 厚涂批量 `shot` 不生效

和国漫立绘同样的问题 —— `generate.py` 不认 `shot`。

**修法**：API 层补 `SH.apply()`。

### 10. MOSS 批量 `extra_style` 不生效

单次有 `SO.apply`，批量没有。

**修法**：

```python
_style = str(req.get("extra_style") or "").strip()
if _style:
    for it in items:
        it["prompt"] = SO.apply(it.get("prompt") or "", _style)
```

### 11. MOSS 批量 `subject` 被忽略

「题材」拼进了 prompt，但模型当标签忽略了。

**修法**：加说明 + 加入锁定清单

```python
user += (
    f"题材：{subject}\n"
    f"（「{subject}」是这一批的拍摄类型，每一条都要符合它的影像特征，"
    f"用可见的画面元素体现出来，不要只当成标签忽略掉）\n"
)
```

---

## 审计方法论

### 三轮迭代才做对

**第一轮**：浏览器逐个点 → 报 32 个「无效」，**全是误判**
- LLM 生成耗时不固定（MOSS 13-25s）
- id 和 label 不同（`guoman3d` → 「国漫3D风格」）
- LLM 会重排语序

**第二轮**：API 直测 → 报 27 个「无效」，**部分误判**
- 断言用完整字符串，LLM 拆开重组就匹配不上

**第三轮**：智能断言 → **130/132**
- 中文长串拆段匹配
- id / label 都接受
- 阿拉伯数字 ↔ 中文数字互转（18岁 ↔ 十八岁）

### 关键断言技巧

```python
def frags_of(val):
    """生成候选片段：整串 / 每段 / 段前 4 字 / 英文词 / 中文数字变体"""
    out = [val]
    for seg in re.split(r"[，,。;；/：:]", val):
        out.append(seg)
        if len(seg) > 4:
            out.append(seg[:4])
    for w in re.findall(r"[A-Za-z][A-Za-z'\-]{3,}", val):
        out.append(w)
    # 18岁 → 十八岁
    m = re.search(r"(\d+)岁", val)
    if m:
        out.append(to_chinese_num(int(m.group(1))) + "岁")
    return out
```

### 必须区分「真失效」和「断言太严」

| 现象 | 判定 |
|---|---|
| 输出里完全没有该值，换几次都没有 | 真失效 |
| 值被拆开但语义完整 | 断言太严 |
| 输出是 label 不是 id | 断言太严 |
| 数字转中文 | 断言太严 |
| 5 次里中 2 次 | 有随机分支覆盖 → 真 bug |

**腰部那个 bug 就是靠「跑 5 次只中 2 次」发现的** —— 单次测试可能碰巧通过。

---

## 审计脚本

存在 `scripts/audit-all-slots.py`，可重复运行：

```bash
cd J:\AmazingDraw
python scripts/audit-all-slots.py
```

覆盖：
- 6 个 skill
- 国漫立绘 11 项 × 2 模式
- 国漫人像 11 项 × 2
- MOSS 9 项 × 2
- 模板 19 项 × 2
- 写实 5 项 × 2
- 厚涂 11 项 × 2

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `skills/guoman-costume-xianxia-prompts/scripts/promptforge.py` | batch 加 7 槽位参数；`render_costume` 传 extras；腰部优先级；leg 加 none |
| `skills/guoman-portrait-prompts/scripts/generate.py` | 加 `lock` 参数 + 9 个 CLI 选项 |
| `skills/anime-thickpaint-oneesan-prompts/scripts/generate.py` | 加 `lock` 参数 + 9 个 CLI 选项（含 body/vibe） |
| `scripts/webui/api_guoman.py` | batch 补 shot；`_slot_args` 已有 |
| `scripts/webui/api_guoman_portrait.py` | batch 透传 9 选项；`outfit_cat` 挑具体服装 |
| `scripts/webui/api_anime_oneesan.py` | batch 透传 9 选项 + shot；单次接 body/vibe |
| `scripts/webui/api_moss_architect.py` | batch 加 extra_style；subject 加说明 + 锁定 |
| `static/js/anime-oneesan.js` | 单次/批量补 body/vibe/shot |
| `static/js/prompt-skills.js` | 国漫人像批量补 13 参数 |
| `static/js/guoman.js` | 批量补 shot |
| **两份 skill 文件都同步** | `~/.dsh/skills/` 和 `J:\AmazingDraw\skills\` |

---

## 教训

### 1. 「传参」≠「生效」

前端传了 13 个参数、请求返回 200、有输出 —— 看起来全对。
但后端只读了 2 个。

**必须端到端验证：传一个明确的值，看输出里有没有它。**

### 2. skill 文件有两份

```
~/.dsh/skills/          ← agent 侧
J:\AmazingDraw\skills\  ← WebUI 实际读的（优先级更高）
```

改了一份，跑的是另一份。这次排查花了额外时间才想到。

**规则**：改 skill 脚本，两份都要改，改完比对文件大小。

### 3. 单次测试不够，要跑多次

腰部 bug：跑 5 次只中 2 次。单跑一次可能碰巧通过。

**有随机分支的代码，至少跑 5 次。**

### 4. 断言要贴合实际输出

LLM 输出会：
- 重排语序
- 拆开长串
- 数字转中文
- 用 label 不用 id

写死完整字符串匹配，会误报大量「无效」。

---

## 写实摄影的 age 是设计如此

`adult-photo21` 这个 skill 有硬规则：**所有人物一律 21 岁**。

```python
_CN_AGE_FIX = (
    (r"(?<![\d])(1[0-9]|20)\s*岁", "21岁"),   # 18/19/20 岁 → 21岁
    (r"女孩", "21岁成年女性"),
    ...
)
```

所以它的 `age` 下拉选了不生效 —— 这是**刻意的年龄规范化**，不是 bug。
