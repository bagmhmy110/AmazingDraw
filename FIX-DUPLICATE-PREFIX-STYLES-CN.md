# 修：画风线重复出现「Wuthering Waves style…竖屏构图」

> 2026-11-15。国漫人像新增的 12 个画风线，生成出来的提示词开头变成
> 「CCD数码相机复古质感，竖屏构图。**Wuthering Waves style二次元半写实厚涂，竖屏构图。**26岁…」

---

## 根因：画风线共用 B 线骨架，模板自带固定开头

画风线（`ccd_retro` / `xianxia_fairy` 等）为了复用词池，用的是 B 线的填充模板：

```python
_FILL_TEMPLATES["B"] = (
    "Wuthering Waves style二次元半写实厚涂，竖屏构图。"   # ← 模板自带
    "{age}，{hair}。身着{outfit}，{detail}，精致的东方面容。{sexy}。"
    "{pose}。场景：{scene}，{light}。"
)
```

而画风又会自己加一层开头：

```python
SO.apply(prompt, "ccd_retro")
# → "CCD数码相机复古质感，千禧年色调，竖屏构图。" + 原文
```

两段开头叠在一起。

---

## 修法：三步清理 + 顺序很关键

### 1. 提示词里明确禁止

```python
if embedded_style:
    user += (
        "\n【重要】开头不要写「Wuthering Waves style」「二次元半写实厚涂」"
        "「鸣潮风格」「竖屏构图」这些词，直接从人物年龄气质开始写。\n"
    )
```

### 2. `_strip_b_prefix()` 清掉残留

模型不一定听话，还会自己改写。实测出现过这些变体：

| 模型写法 | 说明 |
|---|---|
| `Wuthering Waves style二次元半写实厚涂` | 原样保留 |
| `Wuthering Waves风格二次元半写实厚涂` | 把 style 改成「风格」 |
| **`鸣潮风格二次元半写实厚涂`** | 翻译成中文「鸣潮」 |
| `二次元半写实厚涂质感` | 只剩碎片 |

所以正则要覆盖全部：

```python
# 删掉 Wuthering Waves / 鸣潮 相关的整句（含紧随的竖屏构图）
t = re.sub(
    r"(?:Wuthering\s*Waves(?:\s*style)?|鸣潮(?:风格|画风)?)"
    r"[^。，]*?"
    r"(?:竖屏构图)?[。，]?",
    "", t, flags=re.I,
)
# 残留的「风格二次元半写实厚涂」碎片
t = re.sub(
    r"[，。]?\s*(?:风格)?\s*二次元半写实厚涂(?:质感|风格)?\s*[，。]?",
    "，", t,
)
```

### 3. `_dedupe_portrait_tag()` 只留一次「竖屏构图」

```python
def _dedupe_portrait_tag(text):
    first = text.find("竖屏构图")
    if first < 0:
        return text
    head = text[: first + len("竖屏构图")]
    tail = text[first + len("竖屏构图"):]
    tail = re.sub(r"[，。、；：]?\s*竖屏构图[。，、；：]?", "", tail)
    return (head + tail).strip()
```

---

## 关键坑：清理顺序错了会白干

我第一版把清理放在**套画风之前**：

```python
prompt = _strip_b_prefix(prompt)      # 此时只有 0~1 个「竖屏构图」
prompt = SO.apply(prompt, style)      # 画风开头又加了一个
# → 结果还是 2 个
```

因为**画风开头本身含「竖屏构图」**，清理时看不见它。

正确顺序：

```python
prompt = _strip_b_prefix(prompt)              # 1. 去掉 B 线残留
prompt = SO.apply(prompt, embedded_style["value"])   # 2. 套画风开头
prompt = _dedupe_portrait_tag(prompt)         # 3. 最后统一去重
```

实测这一改，违规从 4/12 降到 **0/12**。

---

## 验证

### 12 个画风全部干净

```
OK   xianxia_fairy      残留=0 竖屏=1  len=150
OK   guofeng_xianxia    残留=0 竖屏=1  len=194
OK   street             残留=0 竖屏=1  len=210
OK   korean_hd          残留=0 竖屏=1  len=191
OK   ccd_retro          残留=0 竖屏=1  len=164
OK   home_candid        残留=0 竖屏=1  len=141
OK   native_no_filter   残留=0 竖屏=1  len=159
OK   cool_white         残留=0 竖屏=1  len=202
OK   y2k                残留=0 竖屏=1  len=215
OK   gugong_guifei      残留=0 竖屏=1  len=213
OK   xiyu_hanfu         残留=0 竖屏=1  len=148
OK   qingleng_shennv    残留=0 竖屏=1  len=206

违规 0 / 12
```

### 原有四条线不受影响

```
OK  B  含WW=True(期望True)   竖屏=1
OK  C  含WW=False(期望False) 竖屏=0
OK  A  含WW=False(期望False) 竖屏=0
OK  D  含WW=False(期望False) 竖屏=0
```

B 线保留 Wuthering Waves（那是它的标志），C/A/D 本来就没有。

---

## 修前 vs 修后

**修前：**
> CCD数码相机复古质感，千禧年色调，竖屏构图。**Wuthering Waves style二次元半写实厚涂，竖屏构图。**26岁成熟女子…

**修后：**
> CCD数码相机复古质感，千禧年色调，竖屏构图。26岁成熟女子，乌黑长发高马尾，利落清爽。身着杏粉缎面梅纹旗袍…精致的东方面容。高开叉至大腿根部，露出修长双腿。回身半转，长发甩出一道弧线。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/api_guoman_portrait.py` | 新增 `_strip_b_prefix()` / `_dedupe_portrait_tag()`；画风线提示词加禁止指令；清理顺序调整为「剥前缀 → 套画风 → 去重」 |
