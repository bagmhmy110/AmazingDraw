# 固定画框缩放

> 2026-11-15。图片被锁在固定大小的画框里缩放，不再跟着图片长大撑破页面。

---

## 交互

| 操作 | 效果 |
|---|---|
| 点图打开 | 弹出**固定画框**（`min(92vw, 1040px)` × `min(86vh, 1200px)`） |
| **滚轮** | 在画框内缩放 1× ~ 8×，以光标位置为锚点 |
| **拖拽** | 放大后平移，超出画框的部分被裁掉 |
| **双击** | 1× ⇄ 2.5× |
| **`+` / `-` / `0`** | 键盘放大 / 缩小 / 重置 |
| **Esc / 点背景 / ✕** | 关闭 |

左上角实时显示倍率（如 `2.01×`），1× 时自动隐藏。

---

## 核心：画框尺寸与图片解耦

### 之前的问题

```css
.lightbox-content {
  max-width: 90%;      /* 跟着内容走 */
  max-height: 90%;
}
#lightbox-img {
  max-height: 90vh;    /* 跟着视口走 */
}
```

画框没有确定尺寸，图片放大就往外顶，视觉上「整个窗口在变大」。

### 现在：画框先钉死

```css
.lightbox-overlay .lightbox-content {
  width: min(92vw, 1040px);
  height: min(86vh, 1200px);
  max-width: 92vw;
  max-height: 86vh;
  overflow: hidden;              /* ← 关键：超出裁掉 */
  background: #0b0b0d;
  border-radius: 14px;
  transform: none;               /* 画框自身不参与缩放 */
}

.lightbox-overlay #lightbox-img {
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
  object-fit: contain;
  transform-origin: center center;
  will-change: transform;
}
```

图片的 `transform: scale()` 只改变**绘制**，不改变布局盒子，
加上画框 `overflow: hidden`，视觉上就是「在窗口里放大」。

---

## 平移边界要按画框算，不是按图片

这是固定画框后必须改的地方。原来用 `img.getBoundingClientRect() / scale`
推算基准尺寸，但图片被 `max-width/height: 100%` 约束过，
`getBoundingClientRect()` 拿到的是**缩放后的渲染尺寸**，除回去会偏。

改成用 `naturalWidth/Height` 和画框尺寸算 contain 后的基准：

```js
const baseSize = () => {
  const fw = frame.clientWidth;
  const fh = frame.clientHeight;
  const nw = img.naturalWidth || fw;
  const nh = img.naturalHeight || fh;
  const r = Math.min(fw / nw, fh / nh);   // contain 比例
  return { w: nw * r, h: nh * r };
};

const clampPan = () => {
  if (scale <= 1.001) { tx = 0; ty = 0; return; }
  const { w: bw, h: bh } = baseSize();
  const fw = frame.clientWidth;
  const fh = frame.clientHeight;
  const maxX = Math.max(0, (bw * scale - fw) / 2);
  const maxY = Math.max(0, (bh * scale - fh) / 2);
  tx = Math.min(maxX, Math.max(-maxX, tx));
  ty = Math.min(maxY, Math.max(-maxY, ty));
};
```

**图片比画框小的方向上 `maxX/maxY` 会是 0**，即居中锁定，不会出现
「图片在画框里飘」的怪异手感。

### 缩放锚点也改用画框中心

```js
const frect = frame.getBoundingClientRect();
const cx = frect.left + frect.width / 2;
const cy = frect.top + frect.height / 2;
```

因为图片在画框内居中，未平移时画框中心 === 图片中心，
但用画框算不受图片 transform 影响，更稳。

---

## 验证（Chrome headless + CDP 真实运行时）

| 检查 | 结果 | 实测值 |
|---|---|---|
| 画框固定尺寸 | PASS | 1040 × 780 |
| 初始图片适配画框 | PASS | 图片 437×779，装进 1040×780 |
| 画框 overflow hidden | PASS | `hidden` |
| **放大后画框尺寸不变** | PASS | 仍 1040 × 780 |
| **放大后图片超出画框（被裁切）** | PASS | 图片渲染 878×1566 > 画框 |
| 倍率角标显示 | PASS | `2.01×` |
| 拖拽被边界钳制 | PASS | 拖 5000px，实际只移动 393.9px |
| 缩回 1× 居中 | PASS | `translate(0px, 0px) scale(1)` |
| 重置后角标隐藏 | PASS | — |
| Esc 关闭 | PASS | — |

**10/10 通过。**

注意「放大后画框尺寸不变」+「图片超出画框」这两条同时 PASS ——
这就是固定画框的核心证明：图片长大了，窗口没长大。

---

## 缓存刷新

```html
<link rel="stylesheet" href="css/06-components.css?v=1.14.0">
<script src="js/widgets.js?v=1.11.0"></script>
```

浏览器里如果还开着旧标签，**Ctrl+F5 硬刷新**。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `static/css/06-components.css` | 画框固定尺寸 + `overflow: hidden`；关闭按钮移到框内；倍率角标样式 |
| `static/js/widgets.js` | `baseSize()` 按画框算基准；`clampPan()` 按画框算边界；锚点改用画框中心；倍率角标更新 |
| `static/index.html` | 加 `lightbox-zoom-level` 元素；升版本号 |
