# 国漫人像：风格线下拉显示优化

> 2026-11-16。你说「风格线没生效」，我逐项测了 16 个线 ——
> **后端和前端功能都正常**，问题是下拉把内部 id 露出来了，看着像没生效。

---

## 实测结果：16/16 全部生效

| 风格线 | 输出开头 |
|---|---|
| B 二次元厚涂 | `Wuthering Waves风格二次元半写实厚涂，竖屏构图。` |
| C 古风仙侠 | `一位26岁出尘仙子，拥有精致的东方面容…` |
| A 写实 CCD | `一位28岁书店店员，精致的东方面容…` |
| D 高定服装 | `东方新中式风格女性角色服装设计。` |
| 仙侠仙女古风 | `东方仙侠风格，仙气飘逸，竖屏构图。` |
| 国风仙侠 | `国风仙侠风格，东方古典美学，竖屏构图。` |
| 街拍 | `街头抓拍风格，城市纪实摄影，竖屏构图。` |
| 韩系高清人像 | `韩系高清人像摄影，棚拍质感，竖屏构图。` |
| CCD 复古 | `CCD数码相机复古质感，千禧年色调，竖屏构图。` |
| 居家日常抓拍 | `居家日常抓拍，生活纪实，竖屏构图。` |
| 原生相机无滤镜 | `原生相机直出，无滤镜，竖屏构图。` |
| 冷白皮写实 | `写实人像摄影，冷白皮质感，竖屏构图。` |
| 千禧年 Y2K | `千禧年Y2K风格真人写真，竖屏构图。` |
| 古风宫廷 | `古风宫廷风格，雍容华贵，竖屏构图。` |
| 古风异域西域汉服 | `古风西域异域风格，敦煌壁画美学，竖屏构图。` |
| 古风清冷神女 | `古风清冷神女风格，疏离出尘，竖屏构图。` |

**每一条都正确套用了对应的画风开头。**

---

## 真正的问题：下拉显示内部 id

改之前下拉长这样：

```
B · 二次元厚涂
C · 古风仙侠
A · 写实 CCD
D · 高定服装
xianxia_fairy · 仙侠仙女古风      ← 内部 id 露出来了
guofeng_xianxia · 国风仙侠
street · 街拍
korean_hd · 韩系高清人像
ccd_retro · CCD 复古
home_candid · 居家日常抓拍
native_no_filter · 原生相机无滤镜
cool_white · 冷白皮写实
y2k · 千禧年 Y2K 真人写真
gugong_guifei · 古风宫廷
xiyu_hanfu · 古风异域西域汉服
qingleng_shennv · 古风清冷神女
```

**12 个画风线显示的是 `xianxia_fairy`、`street`、`y2k` 这种内部 id**，
只有基础线 B/C/A/D 是短的。

看起来像「这些选项是坏的」—— 实际上是显示问题。

---

## 修法：分组显示，去掉 id 前缀

```javascript
const lineSel = $("gp-line");
if (lineSel && meta.lines) {
  // 基础线（B/C/A/D）与画风线分两组显示，别把 id 露出来当标题
  const base = meta.lines.filter((l) => !l._style);
  const styled = meta.lines.filter((l) => l._style);
  const opt = (l) => `<option value="${esc(l.id)}">${esc(l.label)}</option>`;
  lineSel.innerHTML =
    `<optgroup label="基础线">${base.map(opt).join("")}</optgroup>` +
    (styled.length ? `<optgroup label="画风线">${styled.map(opt).join("")}</optgroup>` : "");
}
```

**改之后**：

```
基础线
  二次元厚涂
  古风仙侠
  写实 CCD
  高定服装
画风线
  仙侠仙女古风
  国风仙侠
  街拍
  韩系高清人像
  CCD 复古
  居家日常抓拍
  原生相机无滤镜
  冷白皮写实
  千禧年 Y2K 真人写真
  古风宫廷
  古风异域西域汉服
  古风清冷神女
```

---

## 技术细节：画风线是怎么实现的

`meta.lines` 里，12 个画风线带 `_style` 字段：

```json
{
  "id": "xianxia_fairy",
  "label": "仙侠仙女古风",
  "_style": {
    "value": "xianxia_fairy",
    "label": "仙侠仙女古风",
    "open": "东方仙侠风格，仙气飘逸，竖屏构图。",
    "quality": "衣袂与发丝在气流中轻扬，肌肤透着玉质的冷光，画面空灵出尘。"
  }
}
```

后端 `generate()` 的处理：

```python
embedded_style = line_meta.get("_style") or None
fill_line = "B" if embedded_style else line   # 画风线共用 B 线的骨架
```

**画风线 = B 线骨架 + 该画风的 open/quality 句**。

所以生成时还要告诉模型别写 B 线的固定开头：

```python
if embedded_style:
    user += (
        "\n【重要】开头不要写「Wuthering Waves style」「二次元半写实厚涂」"
        "「鸣潮风格」「竖屏构图」这些词，直接从人物年龄气质开始写。\n"
    )
```

最后由 `SO.apply(prompt, embedded_style["value"])` 套上画风开头。

---

## 验证

```
选项数: 16  当前: B

    B                    二次元厚涂
    C                    古风仙侠
    ...
    qingleng_shennv      古风清冷神女

选画风线 → 生成：
  xianxia_fairy   → 东方仙侠风格，仙气飘逸，竖屏构图。28岁成熟御姐…
  street          → 街头抓拍风格，城市纪实摄影，竖屏构图。24岁成熟御姐…
  y2k             → 千禧年Y2K风格真人写真，竖屏构图。24岁成熟御姐…
  gugong_guifei   → 古风宫廷风格，雍容华贵，竖屏构图。30岁成熟御姐…
  qingleng_shennv → 古风清冷神女风格，疏离出尘，竖屏构图。26岁成熟女子…
```

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `static/js/prompt-skills.js` | `gp-line` 下拉分组显示，去掉 id 前缀 |
| `static/index.html` | `prompt-skills.js?v=1.23.0` |

---

## 教训

**把内部标识暴露给用户，会让人以为功能坏了。**

`xianxia_fairy · 仙侠仙女古风` 这个格式本身没错（id 帮助调试），
但 12 个长 id 混在 4 个短 id（B/C/A/D）中间，视觉上非常杂乱。

分组 + 只显示中文名，一眼就能看出「这是一组完整的风格选项」。
