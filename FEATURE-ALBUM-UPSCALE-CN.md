# 相册「转高清」按钮

> 2026-11-15。相册图片悬停时，原来只有收藏和删除两个图标，
> 现在加了第三个：**转高清**，点击自动走 SeedVR2 放大工作流。

![相册三个按钮](../docs-screenshots/album-quick-buttons.png)

从左到右：**紫色魔法棒（转高清）** · 爱心（收藏）· 垃圾桶（删除）

---

## 完整链路

```
点转高清
  ↓
取卡片 render_image（归档盘里的 PNG）
  ↓
复制进 ComfyUI 的 input/        ← LoadImage 只能读这个目录
  ↓
改工作流：输入图 + 放大倍数 + 种子
  ↓
POST /prompt 提交给 ComfyUI
  ↓
轮询 /history/{prompt_id} 等结果
  ↓
放大图复制回归档盘，命名 <原名>-高清.png
  ↓
回写卡片：render_image 指向新图，原图存到 upscale_from
  ↓
刷新相册
```

实测一张 784×1184 的图，**8.1 秒**放大到 1568×2368（1.42MB → 5.50MB）。

---

## 工作流改造

用户指定的工作流：`J:\work buddy\workflows\▶▷SeedVR2放大工作流API.json`

原工作流有 12 个节点，关键三个：

| 节点 | class_type | 作用 |
|---|---|---|
| 152 | `LoadImageOutput` | 输入图 |
| 151 | `ResizeImageMaskNode` | 放大倍数（默认 2x） |
| 222 | `SaveImage` | 输出 |

### 坑 1：LoadImageOutput 只能选「已生成的图」

原节点是：

```json
"152": {
  "inputs": {
    "image": "Moss-20261024232309_00001_.png [output]",
    "refresh": "refresh"
  },
  "class_type": "LoadImageOutput"
}
```

我把 `image` 改成我复制进去的文件名，ComfyUI 直接回 **400 Bad Request** ——
`LoadImageOutput` 是从 output 目录的**历史索引**里选图，不能塞任意文件名。

**修法：换成 `LoadImage`**，它读 `input/` 目录里的任意文件：

```python
if ct == "LoadImageOutput":
    node["class_type"] = "LoadImage"
    node["_meta"] = {"title": "加载图像"}
    ins.clear()
    ins["image"] = image_name
    ins["upload"] = "image"
```

同时把临时文件复制到 `input/` 而不是 `output/`。

### 坑 2：`comfyui_host` 已经是完整 URL

```python
# ❌ 我第一版
host = cfg.get("comfyui_host") or "127.0.0.1"
return f"http://{host}:{port}"
# → http://http://127.0.0.1:8188:8188
```

**修法**：

```python
def _comfy_base(cfg):
    raw = str(cfg.get("comfyui_url") or "").strip()
    if raw:
        return raw.rstrip("/")
    host = str(cfg.get("comfyui_host") or "127.0.0.1").strip()
    if host.startswith(("http://", "https://")):
        return host.rstrip("/")
    port = cfg.get("comfyui_port") or 8188
    return f"http://{host}:{port}"
```

---

## 后端：`scripts/webui/api_upscale.py`

### 端点

| 端点 | 用途 |
|---|---|
| `GET /api/upscale/meta` | 探测工作流、ComfyUI 状态、目录 |
| `POST /api/upscale/card` | 把一张卡片转高清 |

### 请求

```json
{
  "card_id": "国漫立绘-亭台-战斗风",
  "multiplier": 2,
  "seed": null,
  "timeout": 600
}
```

`multiplier` 只接受 1.5 / 2 / 3 / 4，其他值回退到 2。

### 响应

```json
{
  "ok": true,
  "card_id": "国漫立绘-亭台-战斗风",
  "from": "国漫立绘-亭台-战斗风.png",
  "to": "国漫立绘-亭台-战斗风-高清.png",
  "image_url": "/images/...",
  "multiplier": 2,
  "prompt_id": "570d61d7-...",
  "archive": "I:\\BaiduNetdiskDownload\\ZDpaotu\\国漫立绘-亭台-战斗风-高清.png"
}
```

### 卡片回写

```python
old = card["render_image"]
card["upscale_from"] = old          # 保留原图路径
card["render_image"] = new_name     # 指向高清图
card["history"].append({
    "timestamp": ...,
    "action": "upscaled",
    "changes": {
        "from": old, "to": new_name,
        "multiplier": 2,
        "workflow": "▶▷SeedVR2放大工作流API.json",
        "prompt_id": pid,
    },
})
```

**原图不删**，只是卡片不再指向它。想找回就查 `upscale_from`。

---

## 前端：三个按钮

```javascript
frame.innerHTML = `
  <div class="album-tile-quick">
    <button type="button" data-album-upscale title="转高清（SeedVR2 放大）">
      <i class="fa-solid fa-wand-magic-sparkles"></i>
    </button>
    <button type="button" data-album-fav ...>
      <i class="fa-${favorited ? "solid" : "regular"} fa-heart"></i>
    </button>
    <button type="button" data-album-del title="删除卡片">
      <i class="fa-regular fa-trash-can"></i>
    </button>
  </div>`;
```

点击处理：

```javascript
tile.querySelector("[data-album-upscale]")?.addEventListener("click", (e) => {
  e.preventDefault();
  e.stopPropagation();
  upscaleAlbumCard(card, e.currentTarget);
});
```

转高清期间按钮变 spinner 且禁用，完成后变对勾：

```javascript
if (btnEl) {
  btnEl.disabled = true;
  btnEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
}
// ...
if (btnEl) btnEl.innerHTML = '<i class="fa-solid fa-check"></i>';
```

### 样式：紫色区分

```css
.album-tile-quick [data-album-upscale] {
  color: #b8a9ff;                 /* 淡紫，和收藏(粉)/删除(红)区分 */
}

.album-tile-quick [data-album-upscale]:hover {
  color: #fff;
  background: rgba(76, 58, 140, 0.62);
  border-color: rgba(184, 169, 255, 0.5);
}
```

---

## 验证

### 真实放大（784×1184 → 1568×2368）

```
原图  国漫立绘-亭台-战斗风.png        784x1184   1.42 MB
高清  国漫立绘-亭台-战斗风-高清.png   1568x2368  5.50 MB
```

耗时 8.1 秒。画质检查：发丝、刺绣、金属质感都明显更锐利。

### UI（9/9）

```
PASS  upscale meta 可用
PASS  工作流路径正确
PASS  ComfyUI 在线
PASS  三个按钮都在
PASS  有转高清按钮
PASS  转高清按钮有 title
PASS  转高清用了魔法棒图标
PASS  点击成功
PASS  放大完成（按钮恢复）
```

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/api_upscale.py` | **新增** 放大端点（含工作流改造、提交、轮询、回写） |
| `scripts/webui/web_server.py` | 注册 router |
| `static/js/albums.js` | 加转高清按钮 + `upscaleAlbumCard()` |
| `static/css/05-settings.css` | 转高清按钮紫色样式 |

---

## 可调项

| 项 | 位置 | 默认 |
|---|---|---|
| 工作流路径 | `config.json` → `upscale_workflow`，否则用默认常量 | `J:\work buddy\workflows\▶▷SeedVR2放大工作流API.json` |
| 放大倍数 | 请求体 `multiplier` | 2（可选 1.5/2/3/4） |
| 超时 | 请求体 `timeout` | 600 秒 |
| 输出命名 | 代码里 `f"{stem}-高清.png"` | — |

改工作流路径不用改代码：

```json
"upscale_workflow": "J:\\path\\to\\your\\workflow.json"
```

---

## 注意事项

1. **ComfyUI 必须在运行**。没开会返回 503「ComfyUI 未运行，请先启动」。
2. **放大是同步等待**，前端按钮会转圈 8-30 秒。图越大越慢。
3. **同一张图重复转高清**会生成 `-高清.png`、`-高清-高清.png`。想避免得加去重逻辑。
4. **原图保留在归档盘**，只是卡片不再指向它。`upscale_from` 里记着原路径。
