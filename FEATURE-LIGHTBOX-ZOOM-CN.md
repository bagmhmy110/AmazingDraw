# WebUI 大图滚轮缩放

> 2026-11-15 实现。点击聊天区/相册里的图打开大图后，可用滚轮缩放。

---

## 交互

| 操作 | 效果 |
|---|---|
| **滚轮上滚** | 放大（最大 8×），以**光标位置为锚点** |
| **滚轮下滚** | 缩小（最小 1×，即原始适应尺寸） |
| **放大后拖拽** | 平移查看细节，自动限制在图片边界内 |
| **双击** | 1× ⇄ 2.5× 切换 |
| **`+` / `=`** | 键盘放大 |
| **`-` / `_`** | 键盘缩小 |
| **`0`** | 重置到 1× |
| **Esc / 点背景 / 点 ✕** | 关闭并重置 |

打开大图时底部会浮出一行提示：`滚轮缩放 · 拖拽平移 · 双击还原 · Esc 关闭`，1.6 秒后自动淡出。

---

## 实现

### 1. HTML — 加提示元素（`index.html`）

```html
<div class="lightbox-content">
  <img id="lightbox-img" alt="渲染图预览" decoding="async">
  <button class="btn-close-modal lightbox-close" id="btn-close-lightbox">...</button>
  <div class="lightbox-zoom-hint" id="lightbox-zoom-hint">滚轮缩放 · 拖拽平移 · 双击还原 · Esc 关闭</div>
</div>
```

### 2. CSS — 光标与过渡（`06-components.css`）

```css
.lightbox-overlay #lightbox-img {
  transform-origin: center center;
  transition: transform 0.08s ease-out;
  will-change: transform;
  cursor: zoom-in;
  user-select: none;
  -webkit-user-drag: none;
}
.lightbox-overlay #lightbox-img.is-zoomed  { cursor: grab; transition: none; }
.lightbox-overlay #lightbox-img.is-dragging { cursor: grabbing; transition: none; }
```

拖拽时关掉 `transition`，否则跟手感会变粘。

### 3. JS — 缩放核心（`widgets.js` → `initLightbox`）

**以光标为锚点缩放**是手感的关键。单纯 `scale()` 会让图片从中心膨胀，
光标下的细节会跑掉。做法是把光标相对图片中心的偏移按缩放比例补偿：

```js
const rect = img.getBoundingClientRect();
const cx = rect.left + rect.width / 2;
const cy = rect.top + rect.height / 2;
const offsetX = e.clientX - cx;
const offsetY = e.clientY - cy;
const ratio = next / prevScale;

tx = offsetX - (offsetX - tx) * ratio;
ty = offsetY - (offsetY - ty) * ratio;
scale = next;
```

**边界限制**防止把图拖飞：

```js
const clampPan = () => {
  if (!img || scale <= 1) { tx = 0; ty = 0; return; }
  const rect = img.getBoundingClientRect();
  const baseW = rect.width / scale;      // 还原到未缩放的原始尺寸
  const baseH = rect.height / scale;
  const maxX = Math.max(0, (baseW * scale - baseW) / 2);
  const maxY = Math.max(0, (baseH * scale - baseH) / 2);
  tx = Math.min(maxX, Math.max(-maxX, tx));
  ty = Math.min(maxY, Math.max(-maxY, ty));
};
```

**滚轮必须 `passive: false`** 才能 `preventDefault()`，否则页面会跟着滚：

```js
img.addEventListener("wheel", handler, { passive: false });
```

---

## 验证

用 Chrome headless + CDP 做了真实运行时验证（不是静态断言）：

| 检查 | 结果 |
|---|---|
| 图片加载 | PASS（naturalWidth 736） |
| 滚轮触发缩放 | PASS（`scale(1.15)`） |
| preventDefault 生效（页面不滚） | PASS |
| 放大后光标变 grab | PASS |
| 缩放下限 = 1 | PASS |
| 双击放大到 2.5× | PASS |
| 键盘 0 重置 | PASS |
| 键盘 + 放大 | PASS |
| 拖拽改变位移 | PASS（`translate(45.8px, 40px)`） |
| Esc 关闭 | PASS |

**10/10 通过。**

### 复现验证脚本思路

无 `ws` 模块时，可以手写最小 CDP WebSocket 客户端（HTTP Upgrade 握手 +
frame 编解码），然后用 `Runtime.evaluate` 在页面里派发真实的
`WheelEvent` / `MouseEvent` / `KeyboardEvent`，读取 `img.style.transform`
断言缩放是否生效。

关键点：`/json/list` 里要挑 `type === 'page' && url.includes('8318')`
的 target，否则会连到 Chrome 扩展的 background_page。

---

## 缓存刷新

改了静态资源必须升版本号，否则浏览器用旧的：

```html
<link rel="stylesheet" href="css/06-components.css?v=1.13.0">
<script src="js/widgets.js?v=1.10.0"></script>
```

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `static/index.html` | 加 `lightbox-zoom-hint` 元素；升 2 个版本号 |
| `static/css/06-components.css` | 光标状态、过渡、`will-change`、提示样式 |
| `static/js/widgets.js` | `initLightbox` 重写：滚轮/拖拽/双击/键盘 |
