# 国漫 skill：立绘与批量合并成一个页面

> 2026-11-16。原来是「立绘成稿 / 批量生产」两个模式切换，各有一套字段。
> 现在合成单一表单，一套选项 + 三个按钮。

![合并后](../docs-screenshots/guoman-merged.png)

---

## 改了什么

### 之前

```
[ 立绘成稿 ] [ 批量生产 ]     ← 模式切换

调性 / 场景 / 露腿 / 姿势 / 裸露 / 机位
服装槽位（折叠，仅立绘模式可用）
条数 / 调性池 / 场景池（仅批量模式显示）

[ 生成提示词 ] [ 生成并出图 ] [ 导出 ]
```

**问题**：
- 切模式时字段显隐变化，容易看漏
- 服装槽位在批量模式下被隐藏，锁了也不生效
- 批量时场景走「场景池」输入框，单个场景下拉被隐藏

### 现在

```
调性 / 场景 / 露腿分级 / 姿势 / 裸露范围 / 机位构图     ← 6 个主字段

▸ 服装槽位（可选 · 锁定后该槽不再随机）      ← 折叠
▸ 批量选项（条数 · 调性池 · 场景池）         ← 折叠

[ 生成 1 条 ] [ 生成并出图 ] [ 批量生成 ] [ 导出 ]
```

**一套字段，三个按钮** —— 选什么，单条和批量都按这个来。

---

## 字段排列

| 位置 | 字段 | 单条 | 批量 |
|---|---|---|---|
| 第一排 | 调性 | ✅ | ✅（单条用这个，批量走调性池） |
| 第一排 | 场景 | ✅ | ✅（单条用这个，批量走场景池） |
| 第一排 | 露腿分级 | ✅ | ✅ |
| 第一排 | 姿势 | ✅ | ✅ |
| 第一排 | 裸露范围 | ✅ | ✅ |
| 第一排 | 机位构图 | ✅ | ✅ |
| 折叠一 | 服装槽位 ×7 | ✅ | ✅ ← **新增生效** |
| 折叠二 | 条数 / 调性池 / 场景池 | — | ✅ |

**关键改动**：服装槽位在批量里也生效了。

---

## 后端改动

### `promptforge.py`：batch 子命令加 7 个槽位参数

原来只有 `portrait` 子命令支持：

```python
p3.add_argument("--color", help="指定配色")
p3.add_argument("--fabric", help="指定材质")
...
```

`batch` 没有。加上：

```python
p4.add_argument("--color", help="锁定配色")
p4.add_argument("--fabric", help="锁定材质")
p4.add_argument("--pattern", help="锁定纹样")
p4.add_argument("--sleeve", help="锁定袖型")
p4.add_argument("--skirt", help="锁定裙装结构")
p4.add_argument("--waist", help="锁定腰部")
p4.add_argument("--shoulder", help="锁定肩部")
```

### `cmd_batch` 把槽位传给 `build_portrait`

```python
want = {
    "配色": getattr(args, "color", None),
    "材质": getattr(args, "fabric", None),
    "纹样": getattr(args, "pattern", None),
    "袖型": getattr(args, "sleeve", None),
    "裙装结构": getattr(args, "skirt", None),
    "腰部": getattr(args, "waist", None),
    "肩部": getattr(args, "shoulder", None),
}
p = build_portrait(d, rng, tone, scene, leg, render=args.render,
                   want={k: v for k, v in want.items() if v} or None,
                   pose=getattr(args, "pose", None),
                   exposure=getattr(args, "exposure", "none"))
```

**注意 `want` 用中文键名** —— `assemble()` 认的是「配色」「材质」这些，
不是 `color`/`fabric`。

### `api_guoman.py`：batch 端点展开 slots

```python
slots = req.get("slots") or {}
if isinstance(slots, dict):
    for key in ("color", "fabric", "pattern", "sleeve", "skirt", "waist", "shoulder"):
        val = _clean(slots.get(key))
        if val:
            args += [f"--{key}", val]
```

---

## 前端改动

### `index.html`：删模式切换，重排字段

去掉整个 `guoman-mode-row`，把批量字段从 `guoman-batch-row` 改成折叠区：

```html
<details class="guoman-slot-fold" id="guoman-batch-fold">
  <summary>
    <i class="fa-solid fa-layer-group"></i>
    批量选项
    <span class="guoman-slot-count">条数 · 调性池 · 场景池</span>
  </summary>
  <div class="guoman-field-row">
    <label class="guoman-field">
      <span class="guoman-label">条数</span>
      <input type="number" id="guoman-batch-n" value="20" min="1" max="500">
    </label>
    ...
  </div>
</details>
```

按钮区加「批量生成」：

```html
<button class="guoman-btn primary" id="guoman-generate">生成 1 条</button>
<button class="guoman-btn" id="guoman-generate-direct">生成并出图</button>
<button class="guoman-btn" id="guoman-generate-batch">批量生成</button>
<button class="guoman-btn" id="guoman-export">导出</button>
```

### `guoman.js`：删 setMode，拆 doGenerate / doBatch

**删掉**：
- 整个 `setMode()` 函数（32 行）
- 模式按钮绑定循环
- 初始化里的 `setMode("portrait")`
- `state.mode` 的所有引用

**拆分**：

```javascript
// 生成 1 条
async function doGenerate() {
  const r = await apiPost("/portrait", collectPortraitPayload());
  renderSingle(r, "portrait");
}

// 批量生成
async function doBatch() {
  const r = await apiPost("/batch", collectBatchPayload());
  renderBatch(r);
}
```

**批量 payload 带上槽位**：

```javascript
const slotsB = collectSlots();
if (Object.keys(slotsB).length) payload.slots = slotsB;
```

---

## 验证

### 后端：批量锁定配色

```
批量带 slots: {"color": "墨黑与暗金"}，生成 3 条

✅ 一位东方仙侠风格的绝美女子以俯身探看的姿态...
✅ 一位东方宫廷风格的绝美女王以高位坐姿居中占据画面...
✅ 一位东方仙侠风格的绝美成熟女子以半身姿态居中占据画面核心...

锁定生效: 3/3
```

三条都是「墨黑与暗金」配色，其他槽位（裙装、纹样、袖型）各自随机。

### 浏览器（9/10）

```
PASS  模式切换已移除
PASS  有「生成 1 条」
PASS  有「生成并出图」
PASS  有「批量生成」
PASS  有「导出」
PASS  主字段 6 个
PASS  两个折叠区（槽位+批量）
PASS  服装槽位 7 个
PASS  单条生成成功（1 条）
FAIL  批量生成成功（断言数 .guoman-card，实际外层包了一层）
```

**唯一 FAIL 是断言问题** —— 批量结果渲染成 `批量结果 · 2 条` 的容器，
里面的卡片选择器层级不同。状态栏显示「已生成 2 条」，功能正常。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `skills/guoman-costume-xianxia-prompts/scripts/promptforge.py` | batch 加 7 个槽位参数；`cmd_batch` 传 `want` |
| `scripts/webui/api_guoman.py` | batch 端点展开 `slots` 成 `--color` 等 |
| `static/index.html` | 删模式切换；批量字段改折叠；加「批量生成」按钮 |
| `static/js/guoman.js` | 删 `setMode`；拆 `doGenerate` / `doBatch`；批量带 slots |
| `static/index.html` | `guoman.js?v=1.13.0` |

---

## 一个坑

`want` 的键名必须是**中文**：

```python
want = {"配色": ..., "材质": ..., "纹样": ...}   # ✅
want = {"color": ..., "fabric": ...}            # ❌ 被忽略
```

`assemble()` 里是：

```python
for slot in d.slots:              # d.slots 是 ["配色", "材质", "纹样", ...]
    if slot in want and want[slot]:
```

我第一次用了英文键名，锁了等于没锁 —— 而且**不报错**，静默失效。
