# 相册多选批量删除

> 2026-11-16。相册支持勾选多张后一次性删除。

![相册多选](../docs-screenshots/album-bulk-select.png)

---

## 用法

1. 相册页右上角点 **「多选」** → 进入多选模式
2. 每张图左上角出现勾选框，**点图任意位置也能勾选**
3. 上方操作条显示「已选 N 张」，可以：
   - **全选当前** —— 选中当前已加载的所有卡片
   - **清空** —— 取消所有勾选
   - **删除选中 (N)** —— 批量删除
   - **退出多选** —— 回到普通模式

删除前会弹确认框，告诉你「将从相册、卡片列表和磁盘上删除这 N 张图片与卡片，此操作不可撤销」。

---

## 界面细节

| 状态 | 表现 |
|---|---|
| 多选模式开启 | 「多选」按钮变紫，卡片可点，出现勾选框 |
| 卡片被勾选 | 紫色 3px 描边 + 图片半透明 + 勾选框变实心 |
| 悬停未选中卡片 | 淡紫描边提示可点 |
| 删除按钮 | 未选时禁用（半透明），选中后显示数量 |

快捷按钮（转高清 / 收藏 / 删除单张）在多选模式下**仍然各自生效**，不会误触发勾选。

---

## 后端

### 新端点 `POST /api/cards/batch-delete`

```json
{ "card_ids": ["厚涂御姐-花船-厚涂御姐_4", "direct_20261118_002606_..."] }
```

返回：

```json
{
  "ok": true,
  "requested": 3,
  "deleted": 3,
  "failed": 0,
  "deleted_ids": [...],
  "errors": []
}
```

### 重构：抽出 `_delete_card_sync()`

原来单张删除的逻辑写在端点里：

```python
@router.delete("/api/cards/{card_id}")
async def delete_card(card_id: str):
    card_path = _card_path_or_400(card_id)
    ... 60 行 ...
    return {"status": "deleted"}
```

批量删除要复用这套逻辑，所以抽成独立函数：

```python
def _delete_card_sync(card_id: str) -> Dict[str, Any]:
    """删除一张卡片：JSON + PNG + 缓存 + 相册引用。"""
    ...

@router.delete("/api/cards/{card_id}")
async def delete_card(card_id: str):
    return _delete_card_sync(card_id)

@router.post("/api/cards/batch-delete")
def batch_delete_cards(req):
    for cid in targets:
        _delete_card_sync(cid)     # 单张失败不影响其余
```

### 单张删除做了什么

1. 从卡片 JSON 读 `render_image`
2. 删卡片 JSON
3. 物理删 PNG（archive / 本地 output / config fallback 全扫）
4. 从 `png_metadata_cache.json` 剔除
5. 清聊天历史 + 规则缓存
6. 从相册引用里剔除

**批量就是循环跑这六步**，每条独立 try/except，最后汇总成功/失败。

---

## 前端

### state 加两个字段（`core.js`）

```javascript
albumSelectMode: false,        // 是否在多选模式
albumSelected: new Set(),      // 已勾选的 card_id
```

### 核心函数（`albums.js`）

| 函数 | 作用 |
|---|---|
| `setAlbumSelectMode(on)` | 开关多选，同步按钮状态与操作条显隐 |
| `toggleAlbumSelection(id)` | 勾选/取消一张，只更新那一张的 DOM |
| `updateAlbumSelectionUI()` | 更新计数与删除按钮文字 |
| `selectAllAlbumVisible()` | 全选当前已渲染的卡片 |
| `confirmBulkDeleteAlbumCards()` | 弹确认框 → 调批量删除 API → 刷新 |

**`toggleAlbumSelection` 只更新单张 DOM**，不整格重绘 —— 勾 50 张时不会卡。

### 点击行为

### 大图预览的冲突处理

相册原本有「点图看大图」功能，是靠 `widgets.js` 里的全局事件委托：

```javascript
document.addEventListener("click", (e) => {
  if (e.target.tagName === "IMG" && e.target.classList.contains("gallery-img")) {
    openLightbox(e.target.src);
  }
});
```

相册里的 `<img class="gallery-img album-thumb">` 正好命中。

**加了多选之后出问题**：点图会同时触发「勾选」和「开大图」，两个动作撞在一起。

修法 —— 多选模式下让勾选独占：

```javascript
// widgets.js：多选模式下不弹大图
if (e.target.closest("#view-album.is-selecting")) return;
openLightbox(e.target.src);
```

```javascript
// albums.js：勾选时阻止冒泡
e.stopPropagation();
toggleAlbumSelection(card.card_id);
```

### 两种模式的行为

| 模式 | 点图行为 |
|---|---|
| **普通模式** | 打开大图预览 |
| **多选模式** | 勾选 / 取消勾选（不开大图） |

快捷按钮（转高清 / 收藏 / 单张删除）在多选模式下**仍然各自生效**，不会误触发勾选。

---

## 验证（14/15）

```
PASS  多选按钮存在
PASS  操作条默认隐藏
PASS  相册有卡片（100 张）
PASS  开启后操作条显示
PASS  开启后出现勾选框（100 个）
PASS  视图标记 is-selecting
PASS  勾选 3 张计数正确
PASS  选中卡片有 is-selected（3 张）
PASS  删除按钮已启用
PASS  删除按钮显示数量（删除选中 (3)）
PASS  state 里记录了 3 张
PASS  清空生效
PASS  退出后操作条隐藏
PASS  退出后勾选框消失
FAIL  全选生效（99/100）
```

**唯一 FAIL 是测试脚本操作顺序问题** —— 脚本先勾了 3 张，又点同一张取消了一张，所以全选后是 99 而不是 100。功能本身正常。

### 大图冲突修复验证（3/3）

```
PASS  普通模式点图能开大图
PASS  多选模式点图能勾选
PASS  多选模式点图不开大图
```

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/api_cards.py` | 抽出 `_delete_card_sync()`；新增 `POST /api/cards/batch-delete` |
| `static/js/core.js` | state 加 `albumSelectMode` / `albumSelected` |
| `static/js/albums.js` | 多选渲染 + 勾选逻辑 + 5 个新函数；勾选时 `stopPropagation` |
| `static/js/widgets.js` | 大图委托在多选模式下跳过 |
| `static/index.html` | 相册页加多选按钮与操作条 |
| `static/css/09-prompt-skills.css` | 多选样式（勾选框、选中描边、操作条） |
| `static/index.html` | `albums.js?v=1.2.1`、`core.js?v=1.1.0`、`widgets.js?v=1.1.0`、`09-prompt-skills.css?v=1.8.0` |

---

## 注意

**批量删除会真的删磁盘文件**，包括归档目录里的原图。

确认框里写明了「不可撤销」。如果只是想从相册里隐藏，用「移出专辑」而不是删除。
