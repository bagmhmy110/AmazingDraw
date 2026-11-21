# 图片适应缩放（无固定画框）

> 2026-11-15。图片本身跟着缩放变大变小，容器跟着图片走，**没有任何固定画框**。

---

## 之前两次都做错的地方

| 版本 | 做法 | 结果 |
|---|---|---|
| v1 | `img` 用 `transform: scale()` | 图片视觉变大，但**布局盒子不变**，不改变占位 |
| v2 | 固定画框 + `overflow: hidden` | 画框钉死 1040×780，图片在里面放大被裁切 |
| **v3（当前）** | **直接改 `img.style.width/height`** | **图片真实尺寸变化，容器跟着长** |

关键区别：`transform: scale()` 只改变**绘制**，`width/height` 改变**布局**。
你要的是后者。

---

## CSS：容器彻底放开

```css
.lightbox-overlay {
  overflow: hidden;        /* 放大超出视口的部分裁掉，不产生滚动条 */
}

/* 容器尺寸完全由图片决定 —— 没有任何固定尺寸 */
.lightbox-overlay .lightbox-content {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: auto;
  height: auto;
  max-width: none;         /* 不限制 */
  max-height: none;        /* 不限制 */
  overflow: visible;
  background: none;        /* 不是画框 */
  border: none;
  border-radius: 0;
  box-shadow: none;
  pointer-events: none;    /* 让点击穿透到 overlay 关闭 */
}

.lightbox-overlay #lightbox-img {
  max-width: none;         /* 不设上限，放大不被夹 */
  max-height: none;
  width: auto;             /* 实际尺寸由 JS 写 px */
  height: auto;
  border-radius: 6px;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.6);
  pointer-events: auto;
  transform-origin: center center;   /* 只用于平移 */
}
```

---

## JS：真正改尺寸

### 1× 基准 = 图片 fit 进视口

```js
const computeBase = () => {
  const nw = img.naturalWidth;
  const nh = img.naturalHeight;
  const availW = Math.max(120, window.innerWidth - 80);
  const availH = Math.max(120, window.innerHeight - 80);
  const r = Math.min(availW / nw, availH / nh, 1);  // 不放大超过原始像素
  baseW = Math.round(nw * r);
  baseH = Math.round(nh * r);
};
```

### 缩放 = 改 width/height

```js
const applySize = () => {
  img.style.width  = `${Math.round(baseW * scale)}px`;
  img.style.height = `${Math.round(baseH * scale)}px`;
  img.style.transform = `translate(${tx}px, ${ty}px)`;   // transform 只做平移
  img.classList.toggle("is-zoomed", scale > 1.001);
  if (level) {
    level.textContent = `${scale.toFixed(2)}×`;
    level.classList.toggle("show", scale > 1.001);
  }
};
```

### 锚点：视口中心

图片在视口里居中，所以用视口中心作坐标原点：

```js
const cx = window.innerWidth / 2;
const cy = window.innerHeight / 2;
const offsetX = e.clientX - cx;
const offsetY = e.clientY - cy;
const ratio = next / prevScale;

tx = offsetX - (offsetX - tx) * ratio;
ty = offsetY - (offsetY - ty) * ratio;
```

### 平移边界：按视口算

```js
const maxX = Math.max(0, (baseW * scale - window.innerWidth) / 2);
const maxY = Math.max(0, (baseH * scale - window.innerHeight) / 2);
```

图片没超出视口的那个方向上 `max = 0`，即居中锁定，不会飘。

### 兜底：外部直接改 src 也能生效

不管图片是怎么被塞进 `#lightbox-img` 的，只要 modal 打开且图片就绪就重算：

```js
img.addEventListener("load", () => {
  if (!modal.classList.contains("open")) return;
  if (!img.naturalWidth || !img.naturalHeight) return;
  computeBase();
  applySize();
});
```

### 窗口 resize 重算

```js
window.addEventListener("resize", () => {
  if (!modal.classList.contains("open") || !img) return;
  const prevScale = scale;
  computeBase();
  scale = prevScale;
  clampPan();
  applySize();
});
```

---

## 验证（Chrome headless + CDP 真实运行时）

视口 1587 × 907，图片原始 784 × 1184：

| 状态 | 图片实际尺寸 | 容器尺寸 | 倍率 |
|---|---|---|---|
| 1× | 548 × 827 | 548 × 827 | 1.00× |
| 1.75× | **958 × 1446** | **958 × 1446** | 1.75× |

**图片和容器同步变大**，这就是「适应缩放」的核心证据。

| 检查 | 结果 |
|---|---|
| 容器无 `max-width` 限制 | PASS（`none`） |
| 容器无背景（不是画框） | PASS（`rgba(0,0,0,0)`） |
| 图片按视口 fit（1×） | PASS（548×827 < 1587×907） |
| 1× 时 `style.width` 有 px 值 | PASS（`548px`） |
| **滚轮后图片真实变大** | PASS（548 → 958） |
| 图片尺寸由 style 驱动 | PASS |
| **容器跟着图片一起变大** | PASS（548 → 958） |
| 放大后可超出视口（可平移） | PASS |
| 倍率角标显示 | PASS |
| 缩回 1× 尺寸还原 | PASS |
| 拖拽改变位移 | PASS |
| Esc 关闭 | PASS |

12/12 实质通过（第 13 条断言写法有误 —— `getComputedStyle` 对 `width:auto` 返回的是
计算后的 px 值而非字符串 `auto`，这反而证明容器没有固定尺寸）。

---

## 交互

| 操作 | 效果 |
|---|---|
| 滚轮 | 图片真实放大/缩小（1× ~ 8×），以光标为锚点 |
| 放大后拖拽 | 平移查看，超出视口的部分被裁 |
| 双击 | 1× ⇄ 2.5× |
| `+` / `-` / `0` | 键盘放大 / 缩小 / 重置 |
| Esc / 点背景 / ✕ | 关闭 |

左上角显示实时倍率。

---

## 缓存

```html
<link rel="stylesheet" href="css/06-components.css?v=1.15.0">
<script src="js/widgets.js?v=1.12.1"></script>
```

**Ctrl+F5 硬刷新**。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `static/css/06-components.css` | 容器去掉固定尺寸/背景/边框；图片去掉 max 限制 |
| `static/js/widgets.js` | `applySize()` 用 width/height 替代 transform:scale；锚点改视口中心；边界按视口算；加 load/resize 兜底 |
