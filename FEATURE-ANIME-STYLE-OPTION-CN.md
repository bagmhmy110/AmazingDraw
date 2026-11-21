# 厚涂御姐：新增风格选项（含国漫 3D）

> 2026-11-15。给「厚涂 · Oneesan」页面加了风格下拉，共 4 种，其中新增 **国漫 3D 风格**。

![风格下拉](../docs-screenshots/anime-style.png)

---

## 四种风格

| value | 名称 | 开头句 |
|---|---|---|
| `thickpaint` | 二次元半写实厚涂（默认） | `Wuthering Waves style二次元半写实厚涂，竖屏构图。` |
| `guoman3d` | **国漫 3D 风格** | `国漫3D风格，次世代高精度渲染，竖屏构图。` |
| `gamecg` | 3A 游戏 CG | `3A游戏CG角色原画，虚幻引擎5渲染，竖屏构图。` |
| `guofeng` | 国风厚涂 | `国风厚涂插画，东方古典美学，竖屏构图。` |

### 除开头句，还有质感句

| 风格 | 结尾质感句 |
|---|---|
| thickpaint | （无） |
| **guoman3d** | 立体感强，肌肤有次表面散射的通透质感，发丝根根分明，衣料织纹与金属配饰反光真实。 |
| gamecg | 影视级材质细节，体积光穿过空气，景深层次分明，皮肤与布料质感达到实拍级别。 |
| guofeng | 笔触带水墨晕染的呼吸感，色彩沉稳内敛，衣料纹样有工笔的精细，画面留白透气。 |

---

## 关键设计：只换开头和结尾，词池共用

**风格只改两句，七个词池（650 服装 / 100 发型 / 100 姿态 / 100 场景）完全共用。**

换风格不会换人物、服装、场景 —— 同一个 seed 下，四种风格的差异只在开头句和结尾质感句。

这样设计的原因：你原本的规则文档里，词池是「二次元厚涂御姐」的专用词库，
强行给国漫 3D 另造一套词库没必要，也违背了「复用」的初衷。

---

## 实现

### 1. 词池加 `styles`

`extract_pools.py` 里定义风格表：

```python
STYLES = [
    {
        "value": "thickpaint",
        "label": "二次元半写实厚涂（默认）",
        "open": "Wuthering Waves style二次元半写实厚涂，竖屏构图。",
        "desc": "漫潮官方画风 · 半写实厚涂 · 笔触感与光影层次",
        "quality": "",
    },
    {
        "value": "guoman3d",
        "label": "国漫 3D 风格",
        "open": "国漫3D风格，次世代高精度渲染，竖屏构图。",
        "desc": "3D 立体感 · 次世代渲染 · 材质与皮肤次表面散射",
        "quality": "立体感强，肌肤有次表面散射的通透质感，发丝根根分明，衣料织纹与金属配饰反光真实。",
    },
    ...
]
```

产出到 `pools.json` 的 `styles` 字段。

### 2. 生成时按风格取开头/质感

`generate.py`：

```python
def build_sentence(p, rng, *, category=None, with_stockings=0.4, style=None):
    styles = p.get("styles") or []
    style_meta = None
    if styles:
        if style:
            style_meta = next((s for s in styles if s["value"] == style), None)
        if style_meta is None:
            style_meta = styles[0]      # 默认二次元厚涂
    open_sentence = (style_meta or {}).get("open") or p.get("style_open") or ""
    quality = (style_meta or {}).get("quality") or ""

    # ... 拼词池 ...

    text = (
        f"{open_sentence}"
        f"{age}{temper}，{hair}。"
        f"{body}"
        f"场景：{scene}。{light}。"
        f"{quality}"
    )
```

### 3. CLI 加 `--style`

```bash
python generate.py -n 20 --style guoman3d
```

### 4. API 透传

`/meta` 返回 `styles`；`/generate` 和 `/batch` 都接收 `style` 参数。

### 5. 前端风格下拉放最上方

```javascript
const styles = meta.styles || [];
const opts = styles
  .map((s) => `<option value="${esc(s.value)}">${esc(s.label)}</option>`)
  .join("");
styleRow.innerHTML = `
  <label class="skill-field">
    <span class="skill-label">风格</span>
    <select id="ao-style">${opts}</select>
    <em class="skill-hint" id="ao-style-hint"></em>
  </label>`;
```

切换时下方实时显示该风格的说明。

---

## 实测四种输出

### 二次元半写实厚涂（默认）

> **Wuthering Waves style二次元半写实厚涂，竖屏构图。** 25岁风情成熟女性，奶油色中长卷发，两侧微外翻。
> 身着酒红丝绒吊带迷你裙，细吊带，贴身高腰，裙摆极短露腿，精致的东方面容…

### 国漫 3D 风格

> **国漫3D风格，次世代高精度渲染，竖屏构图。** 29岁知性成熟女性，青柠绿短卷发，轻快。
> 身着绯金缎面鎏金旗袍，立领盘扣，双侧开衩，华贵，精致的东方面容…
> 场景：老式暗房，红光罩灯，相片晾挂。暗红工作光。**立体感强，肌肤有次表面散射的通透质感，发丝根根分明，衣料织纹与金属配饰反光真实。**

### 3A 游戏 CG

> **3A游戏CG角色原画，虚幻引擎5渲染，竖屏构图。** 26岁冷艳成熟女性，浅藤紫齐胸披发…

### 国风厚涂

> **国风厚涂插画，东方古典美学，竖屏构图。** 27岁风情成熟女性，青柠绿短卷发，轻快…

---

## 验证（13/13）

```
PASS  风格下拉存在
PASS  4 种风格
PASS  含国漫3D
PASS  国漫3D 标签正确
PASS  默认是厚涂
PASS  风格提示显示
PASS  厚涂开头正确
PASS  国漫3D 开头正确
PASS  3A CG 开头正确
PASS  国风 开头正确
PASS  国漫3D 有质感句
PASS  四种都含必含词
PASS  四种都无禁词
```

四种风格的提示词都保留了「精致的东方面容」这个必含词，也都没有命中任何禁词。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `~/.dsh/skills/anime-thickpaint-oneesan-prompts/scripts/extract_pools.py` | 新增 `STYLES` 定义 |
| `~/.dsh/skills/anime-thickpaint-oneesan-prompts/scripts/generate.py` | `build_sentence` 接 style；CLI 加 `--style` |
| `~/.dsh/skills/anime-thickpaint-oneesan-prompts/references/pools.json` | 重新生成（含 `styles`） |
| `~/.dsh/skills/anime-thickpaint-oneesan-prompts/SKILL.md` | 补风格池说明 |
| `scripts/webui/api_anime_oneesan.py` | meta 返回 styles；generate/batch 接 style |
| `static/js/anime-oneesan.js` | 风格下拉 + 提示 |
| `static/index.html` | `ao-style-row` 容器 |

---

## 想加更多风格怎么办

在 `extract_pools.py` 的 `STYLES` 里加一条，跑一次 `extract_pools.py`，重启 WebUI 即可：

```python
{
    "value": "your_style_id",
    "label": "你的风格名",
    "open": "开头句，竖屏构图。",
    "desc": "下拉下方的说明",
    "quality": "结尾质感句（可为空字符串）",
},
```

前端下拉会自动多一项，不用改 JS。
