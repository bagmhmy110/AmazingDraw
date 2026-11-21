# 生成按钮统一：条数 + 生成

> 2026-11-16。所有 skill 改成和写实一样的布局 ——
> 一个「条数」输入 + 一个「生成」按钮，条数决定单条还是批量。

![国漫立绘](../docs-screenshots/btn-guoman.png)

---

## 改动前后

### 之前

```
[ 生成 1 条 ] [ 生成并出图 ] [ 批量生成 ] [ 导出 ]
                     ↑ 独立的批量按钮

批量选项（折叠）
  条数 / 调性池 / 场景池
```

两套按钮、两套参数，容易搞混。

### 现在

```
条数 [1] [ 生成 ] [ 生成并出图 ] [ 导出 ]
```

**条数 = 1** → 走单次接口
**条数 > 1** → 走批量接口

一套按钮、一套参数。

---

## 各 skill 落地

| Skill | 条数 id | 生成按钮 | 说明 |
|---|---|---|---|
| 国漫立绘 | `guoman-count` | `guoman-generate` | 移除批量选项折叠区 |
| 国漫人像 | `gp-count` | `gp-generate` | 移除 `gp-batch` 按钮 |
| MOSS | `ma-count` | `ma-generate` | 移除 `ma-batch` 按钮 |
| 写实摄影 | `ap-count` | `ap-generate` | **本来就是样板，没动** |
| 厚涂御姐 | `ao-count` | `ao-generate` | 移除 `ao-batch` 按钮 |
| **模板** | — | `nt-assemble` | **不动**（14 模块组装逻辑不同） |

---

## 实现

### 前端：一个函数判断走哪条路

**国漫立绘（`guoman.js`）**

```javascript
async function doGenerate() {
  const n = Math.max(1, Number($("guoman-count")?.value || 1));
  ...
  if (n > 1) {
    // 批量：调性/场景池从当前下拉取
    const payload = {
      n, seed: "random",
      tones: tone, scenes: scene,
      leg: $("guoman-leg")?.value || "mild",
    };
    // 其余选项照旧
    if (exposure) payload.exposure = exposure;
    if (shot) payload.shot = shot;
    if (pose) payload.pose = pose;
    const slots = collectSlots();
    if (Object.keys(slots).length) payload.slots = slots;

    const r = await apiPost("/batch", payload);
    renderBatch(r);
  } else {
    const r = await apiPost("/portrait", collectPortraitPayload());
    renderSingle(r, "portrait");
  }
}
```

**国漫人像 / MOSS（`prompt-skills.js`）**

```javascript
const _n = Math.max(1, Number($("gp-count")?.value || 1));
if (_n > 1) {
  const r = await apiPost("/api/guoman-portrait/batch", {
    n: _n, seed: "random",
    line, leg, temper, hair, sexy, scene, light, pose, shot,
    outfit_cat, outfit, ...collectPersona("gp"), extra_style,
  });
  renderCards("gp-output", r.items || [], {...});
  return;
}
// 否则走单次
```

**厚涂（`anime-oneesan.js`）**

```javascript
const _an = Math.max(1, Number($("ao-count")?.value || 1));
if (_an > 1) {
  const batchPayload = { ...payload, n: _an };
  delete batchPayload.category;
  const catB = $("ao-category")?.value || "";
  batchPayload.categories = catB ? [catB] : [];
  const rb = await apiPost("/batch", batchPayload);
  renderCards(rb.items || []);
  return;
}
const r = await apiPost("/generate", payload);
```

**复用了单次的 payload** —— 批量时直接 `{...payload, n}`，
保证「一套参数两个入口」真的成立。

### 国漫立绘：删掉批量选项折叠区

原来有个「批量选项」折叠区，里面有独立的三组参数：

```html
<details id="guoman-batch-fold">
  条数 / 调性池 / 场景池
</details>
```

**全部删掉**，改用主表单里的「调性」「场景」下拉。
批量时从这两个下拉取当前值当池子。

---

## 踩到的坑：`__random__` 哨兵值

改完第一版测试，国漫立绘批量报错：

```
400 [FATAL] 未知调性 __random__，可选：仙侠、宫廷、战斗、暗黑、新中式
```

**原因**：调性下拉的默认值是 `__random__`（前端哨兵），
单次端点有 `_resolve_random()` 解析它，**批量端点不认**。

**修法**：前端先展开

```javascript
let tone = $("guoman-tone")?.value || "仙侠";
if (tone === "__random__") {
  const TONES = ["仙侠", "宫廷", "战斗", "暗黑", "新中式"];
  tone = TONES[Math.floor(Math.random() * TONES.length)];
}
let scene = $("guoman-scene")?.value || "";
if (scene === "__random__") {
  const pool = (state.meta && state.meta.scenes) || [];
  scene = pool.length ? pool[Math.floor(Math.random() * pool.length)] : "";
}
```

场景也一样处理。

---

## 验证

### 布局（6/6）

```
PASS  国漫立绘: 条数+生成同行、无批量按钮
PASS  国漫人像: 条数+生成同行、无批量按钮
PASS  MOSS: 条数+生成同行、无批量按钮
PASS  写实（样板）: 条数+生成同行、无批量按钮
PASS  厚涂御姐: 条数+生成同行、无批量按钮
PASS  模板保持原样
```

### 功能（3/3）

```
PASS  国漫立绘 条数=2 → 状态「已生成 2 条」
PASS  厚涂    条数=3 → 卡片 3 张，状态「已生成 3 条」
PASS  国漫人像 条数=2 → 卡片 2 张，状态「已生成 2 条」
```

---

## 清理的死代码

| 删掉的东西 | 位置 |
|---|---|
| `doBatch()` 函数 | `guoman.js` |
| `guoman-generate-batch` 按钮 + 绑定 | `index.html` / `guoman.js` |
| `guoman-batch-fold` 折叠区 | `index.html` |
| `guoman-batch-n` / `guoman-batch-tones` / `guoman-batch-scenes` | `index.html` |
| `gp-batch` 按钮 + 绑定（30 行） | `index.html` / `prompt-skills.js` |
| `ma-batch` 按钮 + 绑定 | `index.html` / `prompt-skills.js` |
| `ao-batch` 按钮 + 绑定 | `index.html` / `anime-oneesan.js` |

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `static/index.html` | 5 个 skill 的按钮区改成「条数 + 生成」；删批量折叠区 |
| `static/js/guoman.js` | `doGenerate` 按条数分流；删 `doBatch`；`__random__` 展开 |
| `static/js/prompt-skills.js` | 国漫人像 + MOSS 按条数分流；删两个批量绑定 |
| `static/js/anime-oneesan.js` | 厚涂按条数分流；删批量绑定 |
| `static/css/09-prompt-skills.css` | 加 `.guoman-inline` 样式 |
| `static/index.html` | `prompt-skills.js?v=1.22.0`、`anime-oneesan.js?v=1.9.0`、`guoman.js?v=1.15.0`、`09-prompt-skills.css?v=1.9.0` |

---

## 模板 skill 为什么不动

模板的「按槽组装」是**14 模块组装**，它的 `count` 本来就是「组装几条」，
而且有独立的 `nt-mode`（极速/LLM）选择 —— 结构和其他 skill 不一样。

保持原样。
