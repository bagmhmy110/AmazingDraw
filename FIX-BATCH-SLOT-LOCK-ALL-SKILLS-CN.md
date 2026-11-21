# 修：国漫人像批量锁槽不生效 + 全 skill 批量审计

> 2026-11-16。你说「国漫人像的批量锁槽好像没用」—— 确实没用，而且原因比想象的深。

---

## 问题链条

### 第一层：前端传了，后端不读

前端 `prompt-skills.js` 传了 13 个参数：

```javascript
const r = await apiPost("/api/guoman-portrait/batch", {
  n, seed,
  line, leg, temper, hair, sexy, scene, light, pose, shot,
  outfit_cat, outfit, ...collectPersona("gp"), extra_style,
});
```

后端 `batch()` 只读：

```python
n = int(req.get("n") or 20)
seed = req.get("seed")
# 其余 11 个全被丢掉
```

**我上一轮只补了前端传参，没让后端读** —— 修了一半。

### 第二层：脚本根本不收选项

`generate.py` 的签名：

```python
def generate(n, seed=None):
```

**只接受条数和种子**，所有字段内部随机。就算后端读了选项，也没地方传。

### 第三层：有两份 generate.py

```
C:\Users\bagmh\.dsh\skills\guoman-portrait-prompts\scripts\generate.py   29.1 KB（我改的）
J:\AmazingDraw\skills\guoman-portrait-prompts\scripts\generate.py        25.9 KB（WebUI 实际用的）
```

改了一份，跑的是另一份。改了等于没改。

---

## 修法

### 1. 给 `generate.py` 加 lock 参数

```python
def generate(n, seed=None, lock=None):
    """lock: dict，锁定指定字段不再随机。
    可用键：age / temper / hair / outfit_cat / outfit / sexy / pose / scene / light
    outfit / scene / light 可只给子串，做模糊匹配。
    """
    lock = {k: v for k, v in (lock or {}).items() if v}
    ...
    locked_cat = lock.get("outfit_cat") or ""

    while len(out) < n and tries < max_tries:
        # 服装类别：锁了就只在该类别轮换
        if locked_cat and locked_cat in OUTFITS:
            cat = locked_cat
        else:
            cat = CATEGORY_ORDER[idx % len(CATEGORY_ORDER)]

        age = lock.get("age") or rng.choice(AGES)
        temper = lock.get("temper") or rng.choice(TEMPERS)
        hair = lock.get("hair") or rng.choice(HAIRS)

        # 服装：锁定单条时模糊匹配
        outfit_lock = lock.get("outfit") or ""
        if outfit_lock:
            pool = [o for o in OUTFITS[cat] if outfit_lock in o[0]]
            if not pool:
                pool = [o for c in OUTFITS.values() for o in c if outfit_lock in o[0]]
            outfit, detail = rng.choice(pool) if pool else rng.choice(OUTFITS[cat])
        else:
            outfit, detail = rng.choice(OUTFITS[cat])

        sexy = lock.get("sexy") or rng.choice(SEXY)
        pose = lock.get("pose") or rng.choice(POSES)

        # 场景与光线成对；锁场景时在该场景候选里挑光线
        scene_lock = lock.get("scene") or ""
        light_lock = lock.get("light") or ""
        if scene_lock:
            cands = [s for s in SCENES if scene_lock in s[0]] or SCENES
            if light_lock:
                cands = [s for s in cands if light_lock in s[1]] or cands
            scene, light = rng.choice(cands)
        elif light_lock:
            cands = [s for s in SCENES if light_lock in s[1]] or SCENES
            scene, light = rng.choice(cands)
        else:
            scene, light = rng.choice(SCENES)
```

**关键点**：`scene` 和 `light` 在 `SCENES` 里是**成对**的元组，
所以锁场景时要连带挑光线，不能分开处理。

### 2. CLI 加 9 个参数

```python
ap.add_argument("--age", help="锁定年龄，如 25岁")
ap.add_argument("--temper", help="锁定人物类型，如 成熟御姐")
ap.add_argument("--hair", help="锁定发型（子串匹配）")
ap.add_argument("--outfit-cat", help="锁定服装类别，如 传统旗袍")
ap.add_argument("--outfit", help="锁定服装（子串匹配）")
ap.add_argument("--sexy", help="锁定性感级别（子串匹配）")
ap.add_argument("--pose", help="锁定姿势（子串匹配）")
ap.add_argument("--scene", help="锁定场景（子串匹配）")
ap.add_argument("--light", help="锁定光线（子串匹配）")
```

### 3. 后端 batch 透传

```python
opt_map = {
    "age": ("age", str(req.get("age") or "")),
    "temper": ("temper", str(req.get("temper") or "")),
    "hair": ("hair", str(req.get("hair") or "")),
    "outfit_cat": ("outfit-cat", str(req.get("outfit_cat") or "")),
    "outfit": ("outfit", str(req.get("outfit") or "")),
    "sexy": ("sexy", str(req.get("sexy") or "")),
    "pose": ("pose", str(req.get("pose") or "")),
    "scene": ("scene", str(req.get("scene") or "")),
    "light": ("light", str(req.get("light") or "")),
}

for _key, (flag, val) in opt_map.items():
    v = val.strip()
    if v and v not in ("不限", "随机", "不限（由风格决定）"):
        cmd += [f"--{flag}", v]
```

**过滤哨兵值** —— 「不限」「随机」这些不该传给脚本。

### 4. 同步到 repo 那份

```powershell
Copy-Item $dshPath $repoPath -Force
```

---

## 顺带修的 bug：leg=none 报 400

前端三档：

```html
<option value="none">不露腿</option>
<option value="mild" selected>含蓄（默认）</option>
<option value="bold">大胆</option>
```

但 `promptforge.py` 的 `batch` 只接受两档：

```python
p4.add_argument("--leg", default="mild", choices=["mild", "bold"])  # 缺 none
```

选「不露腿」→ `HTTP 400 unrecognized choice`。

**修法**：

```python
p4.add_argument("--leg", default="mild", choices=["none", "mild", "bold"])
```

逻辑也错了：

```python
# 原来：none 被当成随机
leg = "bold" if args.leg == "bold" else rng.choice(["mild", "mild", "none"])

# 改成：none 和 bold 都精确
leg = args.leg if args.leg in ("none", "bold") else rng.choice(["mild", "mild", "none"])
```

---

## 全 skill 批量审计

### 结果：11/11 生效

| Skill | 选项 | 结果 |
|---|---|---|
| **国漫人像** | scene | ✅ 2/2 |
| | pose | ✅ 2/2 |
| | outfit_cat | ✅ 2/2 |
| | light | ✅ 2/2 |
| | sexy | ✅ 2/2 |
| **国漫立绘** | pose | ✅ 2/2 |
| | slots.color | ✅ 2/2 |
| **模板** | 场景主题 | ✅ 2/2 |
| | 服装专项 | ✅ 2/2 |
| | 表情眼神 | ✅ 2/2 |
| **厚涂御姐** | categories | ✅ 2/2 |

### 国漫人像实测

```
锁 scene=山间古寺台阶、pose=拱桥、outfit_cat=传统旗袍

✅ 场景 服装 姿势  → 28岁冷艳御姐，暖栗色及肩短发...身着沙金提花暗旗袍...
✅ 场景 服装 姿势  → 27岁成熟御姐，奶茶棕俏皮短卷发...身着绯紫鎏金纹旗袍...
✅ 场景 服装 姿势  → 28岁知性成熟女性，绯紫挑染长发...身着杏粉缎面梅纹旗袍...

全部锁定生效: 3/3
```

三条都是「传统旗袍」，年龄/发型/场景细节各自随机。

### 国漫立绘 leg 梯度

| leg | 腿词命中数 |
|---|---|
| none | 1, 1 |
| mild | 1, 0 |
| **bold** | **6, 3** |

### 国漫立绘 exposure 梯度

| exposure | 裸露词数 |
|---|---|
| none | 2, 1 |
| half_covered | 2, 2 |
| **upper** | **4, 3** |

两档都有明显梯度。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `skills/guoman-portrait-prompts/scripts/generate.py` | 加 `lock` 参数；加 9 个 CLI 选项；调用处传 lock |
| `~/.dsh/skills/guoman-portrait-prompts/scripts/generate.py` | 同上（两份同步） |
| `scripts/webui/api_guoman_portrait.py` | batch 读 9 个选项并转成 CLI 参数 |
| `skills/guoman-costume-xianxia-prompts/scripts/promptforge.py` | batch 的 leg 加 `none` 档；修正 leg 逻辑 |
| `~/.dsh/skills/guoman-costume-xianxia-prompts/scripts/promptforge.py` | 同上 |

---

## 教训

### 1. 修「传参」不等于修「生效」

上一轮我改了前端，加了 13 个参数，测试时看到请求 200、有输出，就以为好了。
**后端根本没读那些字段。**

以后改这类东西，必须端到端验证：**传一个明确的值，看输出里有没有它。**

### 2. skill 文件有两份，必须同步

```
~/.dsh/skills/          ← agent 侧
J:\AmazingDraw\skills\  ← WebUI 实际读的（优先级更高）
```

改了一份，跑的是另一份。这次排查花了额外时间才想到。

**规则**：改 skill 脚本，两份都要改，改完比对文件大小。

### 3. 选项值域要和前端下拉对齐

前端三档 `none/mild/bold`，后端 `choices=["mild","bold"]` ——
选第一档直接 400。这种不一致不会有编译错误，只有用户点了才知道。
