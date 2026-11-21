# 修：相册出现重复图（归档里只有一张）

> 2026-11-16。相册里同一张图显示两次，但归档盘里只有一个文件。

---

## 根因：本地和归档各自 `unique()`，名字错位

`cu-deliver.sh` 里：

```python
local_path = unique(src.parent / fname)          # 在 ComfyUI output 里判断
archive_path = unique(Path(archive_dir) / fname) # 在归档盘里判断
```

**两个目录独立判断重名**，结果会分叉：

| | 本地 output | 归档盘 |
|---|---|---|
| 已有文件 | 无 `石窟_1.png` | 有 `石窟_1.png` |
| `unique()` 结果 | `石窟_1.png` | `石窟_2.png` |

卡片记录的 `render_image` 是**本地那个名字**（`石窟_1.png`），
但归档盘里新图实际叫 `石窟_2.png`。

于是：

- 归档盘：`石窟_1.png`（旧图）+ `石窟_2.png`（新图）
- 卡片 A 指向 `石窟_1.png`
- 卡片 B 也指向 `石窟_1.png`（因为按本地名写的）

**相册里就出现两张卡片指向同一张图。**

---

## 修法 1：归档跟随本地名字

```python
local_path = unique(src.parent / fname)
archive_path = None
if archive_dir and Path(archive_dir).is_dir():
    # 归档必须跟随本地取到的名字 ——
    # 原来两边各自 unique()，本地拿到 _1、归档拿到 _2，
    # 卡片记录的 render_image 是本地名，归档里却是另一个名，导致错位与重复卡片。
    archive_path = Path(archive_dir) / local_path.name
    if archive_path.exists():
        archive_path = unique(archive_path)
```

先取本地的唯一名，归档**沿用这个名字**；只有归档里真的撞了才再 unique。

---

## 修法 2：相册端按图片去重（兜底）

即使将来再次错位，相册也不显示重复。

`api_albums.py` 的 `_filter_pool()`：

```python
pooled = [c for c in cards if _in_default_pool(c, include_unrendered)]

# 按图片文件名去重：同一张图被多张卡片引用时只显示一张（保留最早的）。
_seen_img: dict = {}
_deduped: List[dict] = []
for c in pooled:
    img = str(c.get("render_image") or "").strip()
    if not img:
        _deduped.append(c)
        continue
    key = img.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if key in _seen_img:
        continue
    _seen_img[key] = c.get("card_id")
    _deduped.append(c)
pooled = _deduped
```

`cards` 列表本身按时间排序，所以**保留的是最早那张**。

---

## 清理已有的重复卡片

找出 4 组重复：

| 图片 | 保留 | 删除 |
|---|---|---|
| 厚涂御姐-石窟-厚涂御姐_1.png | `direct_20261117_223840` | `direct_20261120_120809` |
| 厚涂御姐-雪寺-厚涂御姐_1.png | `direct_20261119_010648` | `direct_20261120_120812` |
| 厚涂御姐-雪山-厚涂御姐_1.png | `direct_20261120_004306` | `direct_20261120_120806` |
| 厚涂御姐-镜湖-厚涂御姐_1.png | `厚涂御姐-镜湖-厚涂御姐_1` | `direct_20261120_120817` |

**清理策略**：
- 每组保留**最早**那张（时间戳更早 = 原图对应的卡）
- 后来的删除
- **先备份**到 `C:\Users\bagmh\.amazingdraw\cards_dup_backup`
- **不物理删 PNG**（图只有一张，两张卡共享，删图会一起坏）

---

## 验证

### 卡片层

```
清理前: 287 张卡片，4 组重复（每组 2 张指向同一图）
清理后: 283 张卡片，0 组重复
备份:   4 个 JSON 在 cards_dup_backup
```

### 相册层

```
相册条目: 268
有图的:   268
不同图片: 268
重复:     0  ✅
```

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/gpu-pipeline/cu-deliver.sh` | 归档路径跟随本地 `unique()` 结果 |
| `card_engine_core/gpu-pipeline/cu-deliver.sh` | 同步 |
| `scripts/webui/api_albums.py` | `_filter_pool()` 按 `render_image` 去重 |

---

## 遗留

**这 4 张被删卡片的 prompt 内容丢了**（备份 JSON 里还在，需要可以恢复）。

如果想找回：

```bash
# 从备份恢复某一张
copy "C:\Users\bagmh\.amazingdraw\cards_dup_backup\<card_id>.<时间戳>.json" ^
     "C:\Users\bagmh\.amazingdraw\cards\<card_id>.json"
```

---

## 教训

**同一份数据在两个位置独立生成标识，必然分叉。**

`unique()` 的设计前提是「目标目录里有什么」，但这里有**两个目标目录**，
它们的内容不同步 → 同一个逻辑文件名映射出两个物理文件名。

正确做法是：**先生成一个权威名字，其他地方都跟着它**。
