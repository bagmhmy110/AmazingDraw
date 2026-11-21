# 修：厚涂批量生成结果重复（去种子 + 治缓存）

> 2026-11-16。连点「批量生成」，出来的提示词一模一样。
> 第一次修只改了逻辑没解决，第二次才找到真凶 —— **浏览器缓存**。

![种子框已移除](../docs-screenshots/seed-removed.png)

---

## 两层原因

### 表层：种子固定

后端和前端都把「没填种子」当成「用 2024」：

```python
seed = 2024 if seed in (None, "") else int(seed)   # 后端
```
```javascript
seed: $("ao-seed")?.value?.trim() || 2024,          // 前端
```

### 真凶：浏览器还在用旧 JS

改完代码重启 WebUI 后，服务端返回的确实是新版：

```javascript
✅ 服务端 JS 已是新版（含 random）
✅ 无 2024 旧逻辑
```

但浏览器加载的还是缓存的旧文件 —— **所以点出来还是重复**。

静态文件没有缓存头，浏览器按默认策略缓存，改了 JS 不清缓存就不生效。

---

## 修法一：去掉种子输入框

既然种子对用户没意义（每次都要随机），直接去掉。

**HTML**：

```html
<!-- 删掉这段 -->
<label class="skill-inline">
  <span>种子</span>
  <input type="number" id="ao-seed" placeholder="2024">
</label>
```

**JS**：不再读 `ao-seed`，直接传 `"random"`：

```javascript
const payload = {
  n: Number($("ao-batch-n")?.value || 20),
  categories: cat ? [cat] : [],
  stockings: $("ao-stockings")?.value ?? "0.4",
  style: $("ao-style")?.value || "",
  include_cultivation: Boolean($("ao-cultivation")?.checked),
  seed: "random",       // ← 固定传 random，后端每次换新种子
};
```

现在界面上只剩：`生成一条 · 批量 [3] 条 · 批量生成`

---

## 修法二：加缓存穿透（这才是根治）

在 `web_server.py` 加中间件，让前端资源一律不缓存：

```python
@app.middleware("http")
async def _no_cache_for_frontend(request, call_next):
    """给前端静态资源加 no-cache，避免改了 JS/CSS 浏览器还在用旧缓存。"""
    resp = await call_next(request)
    path = request.url.path.lower()
    if path.endswith((".html", ".js", ".css")) or path in ("/", ""):
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp
```

**只对 `.html/.js/.css` 生效** —— 图片和字体体积大且不常变，仍走正常缓存。

验证：

```
Cache-Control: no-cache, no-store, must-revalidate
Pragma: no-cache
```

以后改前端代码，**刷新一次就生效**，不用再按 Ctrl+F5。

---

## 后端：空种子 = 每次随机

```python
def _random_seed() -> int:
    """生成一个新的随机种子（0 ~ 999999）。"""
    import random as _r
    return _r.randint(0, 999999)


raw_seed = req.get("seed")
if raw_seed in (None, "", "random", "rand", "auto"):
    seed = _random_seed()
else:
    try:
        seed = int(raw_seed)       # 指定值仍可复现
    except (TypeError, ValueError):
        seed = _random_seed()
```

**API 层仍保留 seed 参数** —— 用 curl 或脚本调时可以指定种子复现某一批，
只是界面上不暴露了。

---

## 验证

### 服务端

```
批量：seed=844610 / 539255 / 725485   ← 全不同
单条：seed=992464 / 736282 / 533306   ← 全不同
指定 seed=88888 两次结果一致           ← 仍可复现
```

### 浏览器（全新 profile，7/7）

```
PASS  种子输入框已移除
PASS  批量按钮仍在
PASS  单条按钮仍在
PASS  加载的是新版 JS（v=1.7.0）
PASS  批量 4 次内容全不同
PASS  批量每批 3 条
PASS  单条 3 次内容全不同

7 passed / 0 failed
```

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `static/index.html` | 删掉种子输入框；`anime-oneesan.js?v=1.6.0` → `v=1.7.0` |
| `static/js/anime-oneesan.js` | 去掉所有 `ao-seed` 引用，固定传 `seed: "random"` |
| `scripts/webui/api_anime_oneesan.py` | 新增 `_random_seed()`；空种子随机；返回值带 `seed` |
| `scripts/webui/web_server.py` | 新增 no-cache 中间件 |

---

## 教训

**「改了代码但现象没变」先怀疑缓存，再怀疑逻辑。**

我第一次修的时候验证了 API 层确实每次不同，但用户看到还是重复 ——
因为浏览器根本没加载新代码。当时应该第一时间查：

```bash
# 服务端返回的文件是不是新版？
curl -s http://127.0.0.1:8318/js/xxx.js | grep "关键字"

# 响应头有没有缓存控制？
curl -I http://127.0.0.1:8318/js/xxx.js
```

这次顺手把 no-cache 中间件加上，以后不会再踩。
