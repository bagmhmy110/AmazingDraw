# 修：批量生成提示词每次都一样

> 2026-11-16。国漫人像和国漫立绘的批量生成，点多次结果完全一样。

---

## 根因：种子写死 2024

### 国漫人像（`api_guoman_portrait.py`）

```python
seed = req.get("seed")
seed = 2024 if seed in (None, "") else int(seed)   # ← 不传就是 2024
```

前端只传 `n`，不传种子 → 永远用 2024 → `random.Random(2024)` 产生同一套序列。

### 国漫立绘（`api_guoman.py`）

同样的问题：

```python
seed = 2024 if seed in (None, "") else int(seed)
```

前端 `guoman.js` 还更进一步：

```javascript
seed: seed ? Number(seed) : 2024,   // ← 用户没填就直接传 2024
```

**两边都写死，双保险地锁死了随机性。**

---

## 修法

### 后端：不传就是真随机

两个 API 都改成：

```python
def _random_seed() -> int:
    """每次调用返回一个新种子，保证批量不复用同一套随机序列。"""
    import random as _random
    return _random.randint(1, 2**31 - 1)


seed = req.get("seed")
if seed in (None, "", "random", "rand", "auto"):
    seed = _random_seed()
else:
    try:
        seed = int(seed)
    except (TypeError, ValueError):
        seed = _random_seed()
```

**兼容三种情况**：
- 不传 → 随机
- 传 `"random"` → 随机
- 传具体数字 → 用那个（复现用）
- 传非法值 → 兜底随机

### 前端：删掉种子输入框

**`index.html`** 删掉两个输入框：

```html
<!-- 国漫人像 -->
<label class="skill-inline">
  <span>种子</span>
  <input type="number" id="gp-seed" placeholder="2024">
</label>

<!-- 国漫立绘 -->
<label class="guoman-field">
  <span class="guoman-label">种子</span>
  <input type="number" id="guoman-seed" placeholder="留空随机" min="0" step="1">
</label>
```

**`prompt-skills.js`** 固定发 `random`：

```javascript
const r = await apiPost("/api/guoman-portrait/batch", {
  n: Number($("gp-batch-n")?.value || 20),
  // 不传种子 —— 后端每次自动换新，点一次换一批
  seed: "random",
  ...
});
```

**`guoman.js`** 同理：

```javascript
const payload = {
  n,
  seed: "random",
  ...
};
```

---

## 验证

### 国漫人像：连点两次

```
第一次: 3 条
第二次: 3 条
完全相同条数: 0/3   ✅

第一次第1条: ...28岁冷艳成熟女性，樱色双马尾垂至腰际...
第二次第1条: ...25岁冷艳成熟女性，樱色双马尾垂至腰际...（年龄和服装都变了）
```

### 国漫立绘：连点两次

```
第一次: 3 条
第二次: 3 条
完全相同条数: 0/3   ✅

第一次第1条: 一位东方新中式风格的绝美成熟女子坐在床沿...
第二次第1条: 一位东方宫廷风格的绝美女子跪坐于锦垫之上...（调性都变了）
```

### 输入框确认移除

```
gp-seed 残留: 无
guoman-seed 残留: 无
```

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/api_guoman_portrait.py` | 加 `_random_seed()`；batch 种子改随机 |
| `scripts/webui/api_guoman.py` | 加 `_random_seed()`；batch 种子改随机 |
| `static/index.html` | 删 `gp-seed` / `guoman-seed` 输入框 |
| `static/js/prompt-skills.js` | 批量固定发 `seed: "random"` |
| `static/js/guoman.js` | 批量固定发 `seed: "random"`；删 `guoman-seed` 引用 |
| `static/index.html` | `prompt-skills.js?v=1.21.0`、`guoman.js?v=1.12.0` |

---

## 备注

**厚涂御姐之前修过同样的问题** —— 它的做法是前端完全移除种子输入框，
批量时发 `seed: "random"`，后端把 `None/"random"/"rand"/"auto"` 都当随机。

这次两个国漫 skill 统一成同一套做法。

**保留数字种子的意义**：如果哪天想复现某一批提示词，
可以直接调 API 传具体数字：

```bash
curl -X POST http://127.0.0.1:8318/api/guoman-portrait/batch \
  -H "Content-Type: application/json" \
  -d '{"n": 20, "seed": 12345}'
```

同样的种子 + 同样的选项 → 同样的输出。
