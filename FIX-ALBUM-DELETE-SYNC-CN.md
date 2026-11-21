# 修：手动删图后前端不同步

> 2026-11-16。在归档目录手动删掉图片，相册里还显示打不开的破图。

---

## 根因：只检查「有没有记录」不检查「文件在不在」

`api_albums.py` 原来的判断：

```python
def _has_image(card: dict) -> bool:
    return bool(card.get("image_url") or card.get("render_image"))
```

只要卡片 JSON 里还留着 `render_image` 字段就认为「有图」，
但文件早就被你删了 —— 相册照样列出来，显示成破图。

---

## 修法

### 1. 相册过滤：检查文件真实存在

```python
def _has_image(card: dict) -> bool:
    if not (card.get("image_url") or card.get("render_image")):
        return False
    name = str(card.get("render_image") or "").strip()
    if not name:
        return bool(card.get("image_url"))
    return _image_file_exists(name)
```

`_image_file_exists()` 复用现成的 `_resolve_card_image()` 去磁盘上找。

### 2. 加 3 秒缓存，避免几百张卡全盘搜

相册池可能有几百张卡，每张都全盘搜太慢。加一层按文件名的短时缓存：

```python
_IMG_EXISTS_CACHE: Dict[str, tuple] = {}
_IMG_CACHE_TTL = 3.0

def _image_file_exists(name: str) -> bool:
    base_name = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    now = time.time()
    hit = _IMG_EXISTS_CACHE.get(base_name)
    if hit and now - hit[1] < _IMG_CACHE_TTL:
        return hit[0]
    ...
```

**3 秒 TTL** —— 你删完图刷新页面就能看到变化，又不会每次都扫盘。

查不到时默认「存在」，避免配置异常时误伤。

### 3. 卡片列表加 `image_missing` 标记

`api_cards.py` 的 `list_cards()` 里：

```python
img_path = _attach_card_image_fields(card, config)
...
cards.append({
    ...
    "image_missing": bool(card.get("render_image")) and img_path is None,
})
```

`img_path is None` 就说明卡片记了图名但磁盘上找不到。

### 4. 前端显示「文件缺失」角标

`cards.js` 里：

```javascript
div.className = `sidebar-card-item ... ${card.image_missing ? 'image-missing' : ''}`;

const missingBadge = card.image_missing
  ? `<span class="card-missing-badge" title="图片文件已被删除（不在归档目录里）">
       <i class="fa-solid fa-triangle-exclamation"></i> 文件缺失
     </span>`
  : "";
```

样式：

```css
.sidebar-card-item.image-missing { opacity: 0.65; }
.sidebar-card-item.image-missing .card-person {
  text-decoration: line-through;
  text-decoration-color: rgba(251, 191, 36, 0.6);
}
.card-missing-badge { color: #fbbf24; background: rgba(251,191,36,.12); ... }
```

卡片半透明 + 标题划掉 + 黄色角标。

### 5. 新增清理端点

```
POST /api/cards/cleanup-missing-image
Body: { "dry_run": true }   // 可选，只看不删
```

返回：

```json
{ "ok": true, "dry_run": true, "count": 59, "cards": [...] }
```

正式删除时返回 `removed` 与 `errors`。

---

## 验证

### 当前状态

```
卡片总数: 248
文件缺失: 59
相册池:   187  （已过滤缺失的）
相册破图: 0
```

### 浏览器端到端（5/5）

```
PASS  相册有卡片（100 张）
PASS  相册无破图（0 张）
PASS  卡片列表有 image_missing 标记（59 张）
PASS  清理端点可用（dry_run 检出 59 张）
PASS  相册数量 < 卡片总数
```

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/api_albums.py` | `_has_image()` 检查文件真实存在；新增 `_image_file_exists()` + 3 秒缓存；新增 `invalidate_image_cache()` |
| `scripts/webui/api_cards.py` | `list_cards()` 加 `image_missing` 标记；新增 `POST /api/cards/cleanup-missing-image` 端点 |
| `static/js/cards.js` | 卡片列表显示「文件缺失」角标 |
| `static/css/09-prompt-skills.css` | 缺失标记样式 |
| `static/index.html` | `cards.js?v=1.16.0`、`09-prompt-skills.css?v=1.7.0` |

---

## 用法

**平时**：手动删图后刷新页面，相册里就看不到了。卡片列表里那张会显示「文件缺失」角标。

**想彻底清掉**：调清理端点（dry_run 先看一眼）：

```bash
# 只看不删
curl -X POST http://127.0.0.1:8318/api/cards/cleanup-missing-image \
  -H "Content-Type: application/json" -d '{"dry_run": true}'

# 确认后真删
curl -X POST http://127.0.0.1:8318/api/cards/cleanup-missing-image \
  -H "Content-Type: application/json" -d '{}'
```

目前检测到 **59 张**孤儿卡片，需要清理的话告诉我，我可以帮你跑。

---

## 待办：另外两个 bug

这次只修了「删除同步」。你提的「出图不同步到归档」还有两个独立问题没动：

### Bug A：`python3` 解析到了假的

```
which python3 → C:\Users\bagmh\AppData\Local\Microsoft\WindowsApps\python3
python3 --version → (空)
rc = 49
```

这是 Windows 应用商店的 **0 字节存根**，不是真 Python。
真实的是 `J:\Python312\python.exe`（3.12.10）。

`cu-deliver.sh` 里所有 `python3` 调用全部失败（`_cfg` / 读 done / 改名 / 上传）。
手工跑就复现了 `rc=49`，deliver 日志只有两行就断。

### Bug B：归档图的 mtime 是旧值

```
归档测试-云海-测试.png   创建=11-18 00:26   修改=11-15 12:23
```

图确实进了归档盘（创建时间是新的），但 `shutil.copy2` 保留了源文件的旧 mtime。
按「修改时间」排序自然看不到新图，**看起来像没同步**。

这两个修好归档才会真正恢复正常。
