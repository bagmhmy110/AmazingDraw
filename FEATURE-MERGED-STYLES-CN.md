# 12 种画风并入各 skill 原有风格列表

> 2026-11-15。上一版做成了独立的「画风（追加）」下拉，这次改成**并入原有风格下拉**，不再另开一个。

![画风已并入风格线](../docs-screenshots/merged-styles.png)

---

## 各 skill 现在的风格数

| skill | 原有 | 合并后 | 下拉 |
|---|---|---|---|
| 国漫 | 5 调性 | **17** | 调性 |
| 国漫人像 | 4 条线 | **16** | 风格线 |
| 写实 | 4 类语料 | **16** | 风格 |
| 厚涂 | 4 风格 | **16** | 风格 |
| MOSS | Caption/Layout + 题材 | 画风并入「场景/光线/机位/画幅」那排 | 画风 |
| 模板 | 14 模块 | 画风并入人种那排 | 画风 |

**MOSS 和模板没有「风格」这个概念**（一个是输出格式，一个是模块组装），所以它们各加了一个「画风」下拉，但**放在原有字段行里**，不另开新行。

---

## 12 种画风

| 名称 | 开头句 | 结尾质感句 |
|---|---|---|
| 仙侠仙女古风 | 东方仙侠风格，仙气飘逸，竖屏构图。 | 衣袂与发丝在气流中轻扬，肌肤透着玉质的冷光，画面空灵出尘。 |
| 国风仙侠 | 国风仙侠风格，东方古典美学，竖屏构图。 | 水墨晕染的远景与工笔细描的近景交织，衣料纹样带着古典的秩序感。 |
| 街拍 | 街头抓拍风格，城市纪实摄影，竖屏构图。 | 背景行人虚化，霓虹与店铺招牌形成色块，画面有手持拍摄的轻微倾斜。 |
| 韩系高清人像 | 韩系高清人像摄影，棚拍质感，竖屏构图。 | 皮肤经过精修但保留质感，五官立体，光线柔和均匀，画面干净通透。 |
| CCD 复古 | CCD数码相机复古质感，千禧年色调，竖屏构图。 | 画面有轻微噪点与色偏，高光溢出，边缘略软，带着旧数码相机的失真。 |
| 居家日常抓拍 | 居家日常抓拍，生活纪实，竖屏构图。 | 房间里有生活痕迹，光线是窗外的自然光，构图随意不摆拍。 |
| 原生相机无滤镜 | 原生相机直出，无滤镜，竖屏构图。 | 肤色真实不修饰，保留皮肤纹理与细小瑕疵，色彩还原准确。 |
| 冷白皮写实 | 写实人像摄影，冷白皮质感，竖屏构图。 | 肤色冷白通透，在光下泛着细腻的瓷质光泽，与深色背景形成对比。 |
| 千禧年 Y2K 真人写真 | 千禧年Y2K风格真人写真，竖屏构图。 | 闪片、镭射与低腰元素在光下反光，色彩饱和度高，带着2000年代的张扬。 |
| 古风宫廷贵妃 | 古风宫廷贵妃风格，雍容华贵，竖屏构图。 | 宫灯与朱漆映出暖调，衣料是织金锦缎，配饰繁复沉重，气场压人。 |
| 古风异域西域汉服 | 古风西域异域风格，敦煌壁画美学，竖屏构图。 | 石青、赭石与朱砂的矿物配色，鎏金镶边在光下反光，披帛层叠垂落。 |
| 古风清冷神女 | 古风清冷神女风格，疏离出尘，竖屏构图。 | 神情淡漠，眼神不带温度，素色衣料在冷光下几乎没有反光。 |

---

## 关键：画风线共用原词池

**选中画风线时，用原有基础线跑词库，生成后再套画风的开头/结尾。**

以国漫人像为例：

```python
# LINES = 原有四线 + 12 画风（带 _style 标记）
{"id": "ccd_retro", "label": "CCD 复古", ..., "_style": {...}}

# generate 时
embedded_style = line_meta.get("_style") or None
fill_line = "B" if embedded_style else line        # 画风线用 B 线骨架
...
if embedded_style:
    prompt = SO.apply(prompt, embedded_style["value"])
```

国漫同理：

```python
style_pick = SO.pick(tone)      # 调性是不是画风？
base_tone = "仙侠" if style_pick else tone
args += ["--tone", base_tone]   # 用仙侠跑七槽词库
...
if style_pick:
    _prompt = SO.apply(_prompt, style_pick["value"])
```

所以选「CCD 复古」时，人物/服装/场景都从原词库随机，只是首尾换成 CCD 的调子。

实测输出：

> **CCD数码相机复古质感，千禧年色调，竖屏构图。**Wuthering Waves style二次元半写实厚涂，竖屏构图。30岁成熟御姐，栗色大卷发披肩…场景：午后咖啡馆窗边，百叶窗投下条纹光，柔和窗光，木质桌面与咖啡杯点缀，浅景深。**画面有轻微噪点与色偏，高光溢出，边缘略软，带着旧数码相机的失真。**

---

## 实现

### 1. 厚涂 skill 的 STYLES 直接加 12 条

`extract_pools.py` 的 `STYLES` 从 4 条扩到 16 条，重新跑 `extract_pools.py` 生成 `pools.json`。

前端下拉自动列出，不用改 JS。

### 2. 国漫人像 / 写实：LINES/STYLES 用列表推导追加

```python
LINES = [
    {"id": "B", ...}, {"id": "C", ...}, {"id": "A", ...}, {"id": "D", ...},
] + [
    {"id": s["value"], "label": s["label"], "desc": s["desc"],
     "hint": s["open"], "words": "100-200 字", "age": "成年女性",
     "_style": s}
    for s in SO.EXTRA_STYLES
]
```

### 3. 国漫：meta 的 tones 追加画风 label

```python
tones = list(meta.get("tones") or _DEFAULT_TONES)
style_labels = [s["label"] for s in SO.EXTRA_STYLES]
meta["tones"] = tones + [t for t in style_labels if t not in tones]
```

### 4. 移除独立的 StyleExtras 前端模块

删了 `static/js/style-extras.js`，六个容器的 `*-extra-style` div 也删了。

### 5. id 校验放宽

原来国漫人像的 line 会 `.upper()`，画风 id 是 snake_case 会被改坏：

```python
raw_line = str(req.get("line") or "B").strip()
valid_ids = {x["id"] for x in LINES}
if raw_line in valid_ids:
    line = raw_line
elif raw_line.upper() in valid_ids:
    line = raw_line.upper()
else:
    raise HTTPException(400, ...)
```

---

## 验证

### API（19/20）

```
PASS  国漫人像 16 项 / 含原有四线 / 含仙侠仙女古风 / 含 CCD 复古
PASS  无独立 extra_styles 字段
PASS  写实 16 项 / 含原有四类 / 含千禧年 Y2K
PASS  厚涂 16 项 / 含原有四风格 / 含古风清冷神女
PASS  国漫 17 项 / 含原有五调性 / 含古风宫廷贵妃
PASS  国漫人像 选 CCD 线生成生效
PASS  厚涂 选仙侠仙女生成生效
PASS  原有风格不受影响（B 线 / editorial / thickpaint）
```

（唯一 FAIL 是写实那次 LLM 偶发拒答，重跑即正常，非代码问题）

### UI（13/14）

```
PASS  六个页面都没有独立画风下拉
PASS  国漫人像 16 项 / 写实 16 项 / 厚涂 16 项
PASS  国漫 18 项（5 调性 + 12 画风 + 随机）
PASS  MOSS 画风并入下拉 13 项 / 模板 13 项
PASS  国漫人像选 CCD 生成成功，开头是「CCD数码相机复古质感」
```

（唯一 FAIL 是我断言写 17，实际 18 —— 前端多一个「🎲 随机」，功能正确）

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `~/.dsh/skills/anime-thickpaint-oneesan-prompts/scripts/extract_pools.py` | STYLES 从 4 扩到 16 |
| `~/.dsh/skills/anime-thickpaint-oneesan-prompts/references/pools.json` | 重新生成 |
| `scripts/webui/style_options.py` | 保留（12 种画风定义 + apply） |
| `scripts/webui/api_guoman_portrait.py` | LINES 追加 12 画风；generate 识别 `_style` |
| `scripts/webui/api_adult_photo21.py` | STYLES 追加 12 画风；generate 识别 `_style` |
| `scripts/webui/api_guoman.py` | tones 追加画风 label；portrait 映射回基础调性 |
| `scripts/webui/api_moss_architect.py` | 保留 extra_styles 字段 |
| `scripts/webui/api_nsfw_templates.py` | 保留 extra_styles 字段 |
| `scripts/webui/api_anime_oneesan.py` | 移除 SO.meta（画风已在 pools.json 里） |
| `static/js/prompt-skills.js` | MOSS/模板 画风下拉并入原字段行 |
| `static/js/adult-photo21.js` `anime-oneesan.js` `guoman.js` | 移除 StyleExtras 调用 |
| `static/js/style-extras.js` | **已删除** |
| `static/index.html` | 移除六个 `*-extra-style` 容器与 JS 引用 |
