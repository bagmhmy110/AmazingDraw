# 修：厚涂批量生成时种子不变

> 2026-11-16。连点几次「批量生成」，出来的提示词一模一样。

---

## 根因：空种子固定回退 2024

**后端** `api_anime_oneesan.py`：

```python
seed = req.get("seed")
seed = 2024 if seed in (None, "") else int(seed)   # ← 空值固定 2024
```

**前端** `anime-oneesan.js`：

```javascript
seed: $("ao-seed")?.value?.trim() || 2024,          // ← 空值也固定 2024
```

两边都把「没填种子」当成「用 2024」，所以每次批量结果完全一样。

---

## 修法：空值 = 每次换新种子

### 后端

新增 `_random_seed()`：

```python
def _random_seed() -> int:
    """生成一个新的随机种子（0 ~ 999999）。"""
    import random as _r
    return _r.randint(0, 999999)
```

批量与单条都改成：

```python
raw_seed = req.get("seed")
if raw_seed in (None, "", "random", "rand", "auto"):
    seed = _random_seed()          # 每次换新
else:
    try:
        seed = int(raw_seed)       # 指定值 → 可复现
    except (TypeError, ValueError):
        seed = _random_seed()
```

**关键**：返回值带上实际用的种子

```python
return {
    "ok": True,
    "count": len(items),
    "seed": seed,          # ← 新增，前端可回填
    "items": items,
}
```

### 前端

```javascript
const seedInput = $("ao-seed")?.value?.trim() || "";
const payload = { n: ..., ... };
if (seedInput) payload.seed = seedInput;
else payload.seed = "random";      // ← 明确告诉后端要随机

const r = await apiPost("/batch", payload);
renderCards(r.items || []);

// 回填实际种子，方便复现这一批
if (r.seed != null && $("ao-seed")) {
  $("ao-seed").value = String(r.seed);
}
setStatus(`已生成 ${r.count} 条 · 种子 ${r.seed ?? "-"}`, "ok");
```

---

## 保留的能力：指定种子可复现

种子框**填了值**就用该值，同一批结果可完整复现。实测：

```
seed=88888 两次结果一致: True
```

所以两种用法都在：

| 种子框 | 行为 |
|---|---|
| **留空** | 每次换新种子，结果不重复 |
| **填数字** | 用该值，可复现同一批 |

生成后种子会自动回填到输入框，想复现刚才那批直接再点一次就行。

---

## 验证

### API 层

```
=== 批量：连点 3 次 ===
第1次  seed=243440  3 条
第2次  seed=209984  3 条
第3次  seed=739945  3 条

种子全不同: True  [243440, 209984, 739945]
内容全不同: True

=== 单条：连点 3 次 ===
第1次  seed=867763
第2次  seed=349651
第3次  seed=761966

种子全不同: True
内容全不同: True

=== 指定种子应可复现 ===
seed=88888 两次结果一致: True
```

### 浏览器端到端（6/6）

```
PASS  批量 3 次种子全不同      (17266 / 729953 / 226447)
PASS  批量 3 次内容全不同
PASS  批量种子已回填输入框
PASS  单条 3 次种子全不同      (944481 / 401339 / 570751)
PASS  单条 3 次内容全不同
PASS  状态栏显示种子

6 passed / 0 failed
```

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/api_anime_oneesan.py` | 新增 `_random_seed()`；batch/generate 的空种子改为随机；返回值带 `seed` |
| `static/js/anime-oneesan.js` | 空种子传 `"random"`；生成后回填种子；状态栏显示种子 |
| `static/index.html` | `anime-oneesan.js?v=1.5.0` → `v=1.6.0` |

---

## 顺带说一句

这个坑其他 skill 也可能有。检查方法：

```bash
grep -n 'seed.*2024\|2024.*seed' scripts/webui/*.py static/js/*.js
```

目前只有厚涂是这种「固定默认值」写法，国漫走的是 `_resolve_random`，没这个问题。
