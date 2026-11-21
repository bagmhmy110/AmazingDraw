# 国漫出图后 WebUI 不显示 —— 根因与修复

> 2026-11-15。国漫 skill 出的图，文件都在归档盘、卡片 JSON 状态也是 `rendered`，
> 但 WebUI 列表里完全看不到。

---

## 症状

- `I:\BaiduNetdiskDownload\ZDpaotu\国漫立绘-*.png` 三个文件都在
- 卡片 JSON 里 `status: rendered`、`render_image: "国漫立绘-花船-宫廷风.png"`
- WebUI `/api/cards` 返回 24 条，**国漫那 3 条一条都没有**
- 直接 `GET /api/cards/<id>` 返回 **500**

```json
{"detail":"'str' object has no attribute 'get'"}
```

---

## 根因：卡片字段格式不兼容

`cu-submit.sh` 自动建卡时写的是**扁平字符串**：

```json
{
  "person": "国漫立绘",
  "scene": "花船",
  "theme": "宫廷风",
  "subject": {"display_name": "国漫立绘", ...},
  "render_image": "国漫立绘-花船-宫廷风.png"
}
```

但 WebUI 的 `api_cards.py` 假设**所有**字段都是嵌套字典：

```python
# 列表接口（第 441 行，旧）
scene = card.get("scene", {}).get("name", "") or ""

# 单卡接口（第 740 行，旧）
scene = (card.get("scene") or {}).get("name", "") or ""
```

`card.get("scene")` 返回字符串 `"花船"`，再 `.get("name")` 就炸了：
`'str' object has no attribute 'get'`。

### 为什么列表里“看不见”而不是报错

`list_cards()` 的循环体被 `except Exception: pass` 包着：

```python
for f in CARDS_DIR.glob("*.json"):
    try:
        card = json.loads(...)
        ...
        scene = card.get("scene", {}).get("name", "")   # ← 这里抛异常
        ...
        cards.append({...})
    except Exception:
        pass          # ← 静默跳过，卡片就此消失
```

所以异常被吞掉，那张卡直接从列表里“蒸发”了 —— 比报错更难查。

---

## 修复

### 1. 新增 `_deep_str()` 安全取值

兼容两种落盘格式，绝不抛 `AttributeError`：

```python
def _deep_str(card: dict, key: str, sub: str) -> str:
    """安全读取 card[key][sub]。

    兼容两种落盘格式：
      * 结构化：{"subject": {"display_name": "xxx"}}
      * 扁平化：{"subject": "xxx"}（cu-submit.sh 自动建卡、旧版卡片）
    """
    val = card.get(key)
    if isinstance(val, dict):
        inner = val.get(sub)
        return str(inner) if inner else ""
    if isinstance(val, str):
        return val.strip()
    return ""
```

### 2. 列表接口改用它

```python
person = _deep_str(card, "subject", "display_name")
scene = _deep_str(card, "scene", "name")
...
narrative = (
    _deep_str(card, "director", "story_elevation_zh")
    or str(card.get("narrative_zh") or "")
    or _deep_str(card, "creative", "ai_notes")
    or str(card.get("narrative") or "")
)
```

### 3. 单卡接口加类型检查

```python
person = _deep_str(card, "subject", "display_name")
scene = _deep_str(card, "scene", "name")
if (not person or not scene) and card.get("render_image"):
    p2, s2, intent = parse_png_filename(str(card["render_image"]))
    if not isinstance(card.get("subject"), dict):
        card["subject"] = {"display_name": person} if person else {}
    if not isinstance(card.get("scene"), dict):
        card["scene"] = {"name": scene} if scene else {}
    ...
```

原来的代码只判断 `is None`，遇到 `str` 照样崩：

```python
if card.get("scene") is None:      # ← "花船" 不是 None，跳过
    card["scene"] = {}
if not scene and s2:
    card["scene"]["name"] = s2     # ← 字符串下标赋值，TypeError
```

### 4. 顺手修 `render` 字段同类隐患

```python
# 旧：card.get("render") 是 str 时炸
job_id = str(ack.get("job_id") or ((card.get("render") or {}).get("queue_job_id")) or "")

# 新：
_render_block = card.get("render")
_render_job = _render_block.get("queue_job_id") if isinstance(_render_block, dict) else ""
job_id = str(ack.get("job_id") or _render_job or "")
```

---

## 验证

| 检查 | 修复前 | 修复后 |
|---|---|---|
| `/api/cards` 总数 | 24 | **32** |
| 国漫卡在列表里 | ❌ | ✅ 3/3 |
| `GET /api/cards/<id>` | 500 | **200** |
| `image_url` 生成 | null | ✅ 完整路径 |
| 图片实际加载 | — | ✅ 200 / image/png / 1.6MB |
| 侧栏显示 | — | ✅ 「#32 国漫立绘 · 花船 · RENDERED」 |
| 预览区大图 | — | ✅ 784px 正常渲染 |

![国漫图在 WebUI](../docs-screenshots/guoman-in-webui.png)

---

## 教训

1. **`except Exception: pass` 是隐形杀手**。它让“字段格式不兼容”表现为“卡片神秘消失”，
   而不是一条清晰的报错。排查时先找这种静默吞异常的地方。

2. **单卡接口比列表接口更容易暴露问题**。列表吞异常，单卡直抛 500 ——
   以后遇到“列表里没有”，先试 `GET /api/cards/<id>`。

3. **写卡片的代码和读卡片的代码必须对同一份 schema 达成一致**。
   `cu-submit.sh` 写扁平字段，`api_cards.py` 读嵌套字段，两边都没错，
   但没人保证一致。`_deep_str()` 是兼容层，长期应该统一 schema。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/api_cards.py` | 新增 `_deep_str()`；列表/单卡接口改用；`render` 字段加类型检查 |
