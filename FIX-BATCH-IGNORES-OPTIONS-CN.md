# 修：批量生成忽略选项

> 2026-11-16。发现 MOSS 和国漫人像的「批量生成」完全不看下拉选项，
> 只用了想法/条数/种子。

---

## 问题

### MOSS 批量

**前端只传 3 个参数：**

```javascript
const r = await apiPost("/api/moss-architect/batch", {
  idea,
  n: Number($("ma-batch-n")?.value || 5),
  subject: $("ma-subject")?.value || "",
});
```

**后端也只读 2 个：**

```python
def batch(req):
    idea = str(req.get("idea") or "").strip()
    subject = str(req.get("subject") or "").strip()
    # 其余全部忽略
```

对比单条生成，它传了 9 个参数：

```javascript
mode / subject / extra / scene / light / shot / aspect / extra_style / persona×4
```

### 国漫人像批量

更严重 —— 前端只传 `n` 和 `seed`：

```javascript
const r = await apiPost("/api/guoman-portrait/batch", {
  n: Number($("gp-batch-n")?.value || 20),
  seed: $("gp-seed")?.value?.trim() || 2024,
});
```

---

## 修法

### MOSS 批量

**前端补齐参数：**

```javascript
const r = await apiPost("/api/moss-architect/batch", {
  idea,
  n: Number($("ma-batch-n")?.value || 5),
  mode: $("ma-mode")?.value || "caption",
  subject: $("ma-subject")?.value || "",
  extra: $("ma-extra")?.value?.trim() || "",
  scene: $("ma-scene")?.value || "",
  light: $("ma-light")?.value || "",
  shot: $("ma-shot")?.value || "",
  aspect: $("ma-aspect")?.value || "",
  extra_style: $("ma-style")?.value || "",
  ...collectPersona("ma"),
});
```

**后端读取并拼进 user 提示词：**

```python
subject = str(req.get("subject") or "").strip()
scene = str(req.get("scene") or "").strip()
light = str(req.get("light") or "").strip()
shot = str(req.get("shot") or "").strip()
aspect = str(req.get("aspect") or "").strip()
extra = str(req.get("extra") or "").strip()
ethnicity = PO.pick_ethnicity(str(req.get("ethnicity") or ""))
age = PO.pick_age(str(req.get("age") or ""))
body = str(req.get("body") or "").strip()
vibe = str(req.get("vibe") or "").strip()

user = f"想法：{idea}\n"
if subject: user += f"题材：{subject}\n"
if scene:   user += f"场景：{scene}\n"
if light:   user += f"光线：{light}\n"
if shot:    user += f"机位构图：{shot}\n"
if aspect:  user += f"画幅：{aspect}\n"
if age:     user += f"年龄：{age}\n"
if body:    user += f"身材：{body}\n"
if vibe:    user += f"气质：{vibe}\n"
if extra:   user += f"额外要求：{extra}\n"
```

**关键：告诉模型哪些是锁定的**

批量要「各条不同」，但用户选了的不能变。加一段约束：

```python
locked = [
    name for name, val in (
        ("场景", scene), ("光线", light), ("机位构图", shot), ("画幅", aspect),
        ("年龄", age), ("身材", body), ("气质", vibe),
    ) if val
]
if locked:
    user += (
        f"\n【必须遵守】{'、'.join(locked)} 是用户指定的，"
        "每一条都必须体现，不能变化。\n"
        "只在未锁定的维度上做差异（衣橱、动作阶段、时段细节、族裔等）。\n"
    )
```

**人种也要动态处理** —— 原来 system 里写死「各条之间体现不同亚洲族裔」，
用户锁定人种后要改成「固定为 X」：

```python
system = f"""...
- {'各条之间体现不同亚洲族裔与地域，避免全是一个模子' if not ethnicity else f'所有条目的人物族裔固定为「{ethnicity}」，不要变化'}
..."""
```

### 国漫人像批量

这个更麻烦 —— 批量是调 skill 自己的 `generate.py`：

```python
cmd = [python, "generate.py", "-n", str(n), "-o", out_txt, "--json", out_json, "--seed", str(seed)]
```

而 `generate.py` **只认 4 个参数**：

```python
ap.add_argument("-n", "--num")
ap.add_argument("-o", "--out")
ap.add_argument("--json")
ap.add_argument("--seed")
```

选项根本传不进去。

**修法：脚本生成完，代码层补上选项**

```python
# skill 的 generate.py 只认 -n/--seed，不接受选项参数，
# 所以这里在代码层把选项补上。
shot_val = str(req.get("shot") or "").strip()
style_val = str(req.get("extra_style") or "").strip()
eth_val = PO.pick_ethnicity(str(req.get("ethnicity") or ""))
age_val = PO.pick_age(str(req.get("age") or ""))
body_val = str(req.get("body") or "").strip()
vibe_val = str(req.get("vibe") or "").strip()

if any([shot_val, style_val, eth_val, age_val, body_val, vibe_val]):
    for it in items:
        t = it.get("prompt") or ""
        if not t:
            continue
        if style_val:
            t = SO.apply(t, style_val)          # 画风套首尾
        bits = [x for x in (age_val, eth_val, body_val, vibe_val) if x]
        if bits and not any(x in t for x in bits):
            t = "，".join(bits) + "，" + t      # 人物信息补句首
        if shot_val:
            t = SH.apply(t, shot_val)           # 机位追加末尾
        it["prompt"] = t
```

**顺序很重要**：画风 → 人物信息 → 机位。机位必须最后，因为它要追加到末尾。

---

## 验证

### MOSS 批量（3 条，6 个选项）

```
耗时 13.8s  生成 3 条

--- 第1条 ---
凌晨零点后的深夜便利店收银台前，一位25岁的中国汉族女性站在冷白荧光灯直射下，
中近景，平视，35mm，竖构图3:4；她黑色齐肩直发，黄调肤色，内双眼皮...
体现: ['场景', '光线', '机位', '画幅', '族裔', '年龄']

--- 第2条 ---
凌晨两三点间的深夜便利店饮料冷柜前，一位25岁的中国汉族女性在冷白荧光灯直射下站着...
体现: ['场景', '光线', '机位', '画幅', '族裔', '年龄']

--- 第3条 ---
临近打烊时分的深夜便利店靠窗高脚桌椅旁，一位25岁的中国汉族女性...
体现: ['场景', '光线', '机位', '画幅', '族裔', '年龄']
```

**6 个选项全部体现，同时保持变化**（不同时段、不同货架位置、不同衣着、不同动作）。

### 国漫人像批量（2 条）

```
--- 第1条 ---
25岁，中国汉族女性，身形纤细，肩窄腰细，神情清冷疏离，
CCD数码相机复古质感，千禧年色调，竖屏构图。Wuthering Waves style...
...以仰拍，低机位贴近地面取景。
体现: ['画风', '机位', '族裔', '年龄']
```

人种在句首，机位在末尾，画风套在外面。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `static/js/prompt-skills.js` | MOSS 批量补 9 个参数；国漫人像批量补 13 个参数 |
| `scripts/webui/api_moss_architect.py` | batch 读 9 个选项；拼进 user；加「必须遵守」约束；人种动态处理 |
| `scripts/webui/api_guoman_portrait.py` | batch 在代码层补画风/人物信息/机位 |
| `static/index.html` | `prompt-skills.js?v=1.18.0` |

---

## 教训

**「批量」和「单条」是两条独立的代码路径，很容易漏同步。**

单条生成时把所有选项都传了、后端也读了，看起来一切正常。
批量是后加的，前端复制了骨架但只传了必填项，后端也只读必填项 —— 两边都没错，
只是**用户选的东西被静默丢弃**。

这类问题的特征：
- 请求成功（200）
- 输出正常（有内容）
- 只是内容不符合预期

**自查方法**：加一个「选项是否生效」的断言测试，逐个下拉验证。
之前做过的 `audit_api.py` 就是干这个的 —— 但它只测了单条，没测批量。
