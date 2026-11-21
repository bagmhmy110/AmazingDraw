# 修：生成图片后参数面板不显示提示词

> 2026-11-16。PROMPT 只显示 `girl`、中文摘要只显示 `仙侠风_2`，完整提示词不见了。

![修好后的参数面板](../docs-screenshots/panel-fixed.png)

---

## 现象

点开一张图，右侧参数面板：

| 位置 | 显示内容 |
|---|---|
| PROMPT | `girl` |
| 中文摘要 | `仙侠风_2` |
| 字数徽章 | `1 words` |

而实际上这张图的提示词有 357 字。

---

## 三层原因，逐层挖出来的

### 第一层：虚拟卡没有 `_render_output`

卡片有两种来源：

| 类型 | 来源 | 有提示词？ |
|---|---|---|
| **真实卡** `direct_*.json` | 投递时写入 | ✅ 有 |
| **虚拟卡** `国漫立绘-xxx.json` | 扫描归档盘 PNG 合成 | ❌ 没有 |

你点的那张 `仙侠风_2` 是虚拟卡。

**为什么有虚拟卡？** 卡片复用机制：同一张卡被连续投递 3 次，
每次更新 `render_image` 指向新图，前面的图就成了孤儿 PNG，
被扫描成虚拟卡。

### 第二层：列表接口不返回 prompt

`/api/cards`（列表）只返回精简字段：

```
card_id, image_url, is_virtual, mode, mtime, narrative,
person, render_image, scene, status, theme, version, workflow_mode
```

没有 `_render_output`。前端 `selectCard()` 先用列表数据预渲染，
降级逻辑只拼出 `subject.trigger` = `girl`。

**修法**：列表接口合成虚拟卡时，把 prompt 一并放进返回对象：

```python
cards.append({
    ...
    "_render_output": {
        "prompt": prompt or "",
        "meta_person": person,
        ...
    },
    "slots": {"clothing": prompt or ""} if prompt else {},
})
```

### 第三层（真凶）：`entry.path` 是 str，不是 Path

前两层修完还是空。加了个临时调试端点，在 WebUI 进程内直接调函数：

```
chunk_keys: ["prompt"]
raw_len: 4566      ← 元数据读到了
picked_len: 357    ← 提示词也挑出来了
```

**函数是好的**，但扫描路径拿到的还是空。

原因：

```python
for entry in os.scandir(scan_path):
    prompt = extract_prompt_from_png(entry.path)   # ← str！
```

`os.scandir()` 的 `entry.path` 是 **`str`**，不是 `Path`。
我重写的 `_read_png_text_chunks` 里用了 `png_path.read_bytes()`，
str 没这个方法 → AttributeError → 被 `except` 吞掉 → 返回空字典。

原来的 Pillow 版本能接受 str（`Image.open()` 支持两种），
我换成 `Path` 方法后反而坏了。

**修法**：函数入口统一转 Path：

```python
def _read_png_text_chunks(png_path) -> dict:
    p = png_path if isinstance(png_path, Path) else Path(str(png_path))
    data = p.read_bytes()
    ...

def extract_prompt_from_png(png_path) -> str:
    p = png_path if isinstance(png_path, Path) else Path(str(png_path))
    ...
```

---

## 还有一个坑：Pillow 没装

原代码：

```python
def extract_prompt_from_png(png_path):
    try:
        from PIL import Image      # ← Pillow 没装，直接抛
        ...
    except Exception as e:
        print(f"Failed...: {e}")
    return ""                      # ← 永远返回空
```

`Pillow` 不是必装依赖，没装就永远读不到提示词。

**修法**：改成内置 PNG chunk 解析，零依赖：

```python
def _read_png_text_chunks(png_path) -> dict:
    """用 struct 直接解析 tEXt / iTXt 块，不依赖 Pillow。"""
    import struct
    out = {}
    data = p.read_bytes()
    i = 8
    while i + 8 <= len(data):
        ln = struct.unpack(">I", data[i:i+4])[0]
        typ = data[i+4:i+8].decode("latin-1")
        body = data[i+8:i+8+ln]
        if typ == "tEXt" and b"\x00" in body:
            k, v = body.split(b"\x00", 1)
            out[k.decode("latin-1")] = v.decode("utf-8")
        elif typ == "iTXt":
            parts = body.split(b"\x00", 5)
            if len(parts) >= 6:
                out[parts[0].decode("latin-1")] = parts[5].decode("utf-8")
        elif typ == "IDAT":
            break
        i += 12 + ln
    return out
```

Pillow 保留作最后的降级路径。

---

## 第四个坑：高清图的元数据里没有提示词

ComfyUI 的 PNG 里，`prompt` 键存的是**整个工作流 JSON**（4652 字符），
需要从中挑出 `CLIPTextEncode` 的 `text` 字段。

但**放大工作流**的 JSON 里只有放大参数，没有提示词 ——
它的终点是 `Image Comparer` 节点，不经过 CLIPTextEncode。

所以高清图的虚拟卡永远读不到 prompt。

**修法**：转高清时，把原图的 `prompt` 元数据补写进高清图：

```python
def _copy_prompt_metadata(src: Path, dst: Path) -> None:
    """把原图的 prompt 文本块补进目标 PNG。"""
    info = _read_png_text(src)
    prompt = info.get("prompt")
    if not prompt:
        return
    _write_png_text_chunk(dst, "prompt", prompt)
```

`_write_png_text_chunk` 要**替换**已有的 `prompt` 块（因为高清图已有该键，
存的是放大参数），不能"存在就跳过"：

```python
# 逐块扫描：删掉同名 tEXt，在第一个 IDAT 前插入新块
if typ == b"tEXt":
    body = data[i+8:i+8+ln]
    if b"\x00" in body and body.split(b"\x00",1)[0] == key.encode("latin-1"):
        i += total
        continue    # 跳过旧块
```

### 补写时不能破坏 PNG

插入 tEXt 块要重新算 CRC，且必须在 IDAT 之前：

```python
payload = key.encode("latin-1") + b"\x00" + value.encode("utf-8")
chunk = struct.pack(">I", len(payload)) + b"tEXt" + payload
chunk += struct.pack(">I", zlib.crc32(b"tEXt" + payload) & 0xFFFFFFFF)
```

实测：12473867 → 12475698 字节（多了 1831），PNG 头正常，能正常打开。

---

## 已修复的历史数据

| 项目 | 数量 |
|---|---|
| 高清图元数据补写 | 15 张 |
| 双重放大图（`-高清-高清`） | 2 张 |
| 虚拟卡 prompt 恢复 | 66 / 66 |

---

## 验证

### 列表接口

```
总卡片 149  真实卡 83  虚拟卡 66
虚拟卡有 prompt: 66 / 66
✅ 全部虚拟卡都有提示词
```

### 浏览器实测

```
✅ 国漫立绘-藏书阁-国漫立绘风-高清: 327 字
✅ 国漫立绘-亭台-战斗风-高清: 494 字
✅ 国漫立绘-亭台-仙侠风_2-高清: 357 字
✅ 厚涂御姐-镜湖-厚涂御姐-高清: 189 字

5 passed / 0 failed
```

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/api_cards.py` | 新增 `_read_png_text_chunks()` / `_pick_positive_text()`（零依赖 PNG 解析）；`extract_prompt_from_png()` 改用它，Pillow 降为兜底；入口统一转 `Path`；列表接口合成虚拟卡时带 `_render_output` 与 `slots` |
| `scripts/webui/api_upscale.py` | 新增 `_read_png_text()` / `_write_png_text_chunk()` / `_copy_prompt_metadata()`；转高清后补写原图 prompt 到高清图 |

---

## 教训

1. **`os.scandir()` 的 `entry.path` 是 str，不是 Path** —— 换实现时容易踩
2. **`except Exception: return ""` 会吞掉所有线索** —— 调试时要能看到真实异常
3. **ComfyUI 的 PNG `prompt` 字段是工作流 JSON** —— 不是提示词文本，要挖
4. **放大工作流不经过 CLIPTextEncode** —— 元数据里没有提示词，得手动搬运
5. **缓存会掩盖修复** —— 改完代码要清 `png_metadata_cache.json`
