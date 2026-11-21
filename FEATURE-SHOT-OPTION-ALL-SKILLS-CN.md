# 所有 skill 加「机位构图」选项

> 2026-11-16。MOSS 本来就有机位构图，其余 skill 补齐。

![机位构图](../docs-screenshots/shot-option-all.png)

---

## 复用 MOSS 那套

新建 `scripts/webui/shot_options.py`，直接沿用 MOSS 的 8 项机位：

| value | label | 说明 |
|---|---|---|
| （空） | 不限 | 由词池/模型自行决定 |
| 中近景，平视，35mm | 中近景 平视 35mm | 最常用叙事景别 |
| 特写，略低机位，50mm | 特写 低机位 50mm | 面部占满，略带压迫感 |
| 全身，正面平视，35mm | 全身 正面 35mm | 完整人物 + 环境 |
| 三分之四侧角，85mm，浅景深 | 三分之四侧角 85mm | 侧脸轮廓清晰，背景虚化 |
| 俯拍，高机位，广角 | 俯拍 广角 | 压低头身比例 |
| 仰拍，低机位贴近地面 | 仰拍 低机位 | 拉长腿部，气势强 |
| 过肩视角，前景有遮挡 | 过肩 前景遮挡 | 越过肩膀，带前景 |
| 镜面反射构图 | 镜面反射 | 镜子/水面/玻璃 |

**写实摄影保留自己的 7 项** —— 它的机位贴合语料风格（「低机位仰拍 35mm（拉长腿部）」这类），
换掉反而失真。

---

## 各 skill 落地情况

| Skill | 下拉 id | 项数 | 位置 |
|---|---|---|---|
| 国漫 | `guoman-shot` | 9 | 裸露范围旁边 |
| 国漫人像 | `gp-shot` | 9 | 场景/光线/姿势那一排 |
| MOSS | `ma-shot` | 9 | 原本就有 |
| 模板 | `nt-shot` | 9 | persona 那排（画风旁边） |
| 写实摄影 | `ap-shot` | 7 | 原本就有 |
| 厚涂御姐 | `ao-shot` | 10 | 场景/光线那一排 |

> 厚涂多一项「随机」，因为它的其他下拉都有这个选项，保持一致。

---

## 实现

### 共享模块

```python
def apply(text: str, value: str, *, position: str = "end") -> str:
    """把机位句插进提示词。"""
    shot = pick(value)
    if not shot or not text:
        return text
    frag = shot["value"]
    out = text.strip()
    if frag in out:
        return out
    if out and not out.endswith(("。", "，", ".", ",")):
        out += "。"
    if position == "start":
        return f"以{frag}取景。" + out
    return out + f"以{frag}取景。"
```

**幂等** —— 已经含这个机位就不重复加。

### 各 API 接两处

**meta 加列表：**

```python
out = {
    ...
    **PO.common_meta(),
    **SH.meta(),      # ← 加这行
}
```

**生成时应用：**

```python
shot_val = str(req.get("shot") or "").strip()
if shot_val:
    prompt = SH.apply(prompt, shot_val)
```

各 skill 的应用位置：

| skill | 位置 |
|---|---|
| 国漫 | `guoman_portrait()` 返回前 |
| 国漫人像 | `generate()` 返回前 |
| 模板 | `assemble()` 两处（极速模式 + LLM 模式） |
| 厚涂 | `generate()` 返回前 |

### 前端加下拉

**国漫人像**（`prompt-skills.js`）：

```javascript
setting.innerHTML =
  simpleSelectHtml("gp-scene", "场景", pools.scenes) +
  simpleSelectHtml("gp-light", "光线", pools.lights) +
  simpleSelectHtml("gp-pose", "姿势", pools.poses) +
  simpleSelectHtml("gp-shot", "机位构图", meta.shots) +   // ← 新增
```

**厚涂**（`anime-oneesan.js`）：

```javascript
row4.innerHTML =
  selHtml("ao-scene", "场景", pools.scenes) +
  selHtml("ao-light", "光线", pools.lights) +
  selHtml("ao-shot", "机位构图", meta.shots);   // ← 新增
```

**国漫**（`index.html` + `guoman.js`）：

```html
<label class="guoman-field">
  <span class="guoman-label">机位构图</span>
  <select id="guoman-shot"></select>
</label>
```

```javascript
function fillShotOptions(meta) {
  const sel = $("guoman-shot");
  if (!sel) return;
  const list = meta.shots || [];
  const prev = sel.value || "";
  sel.innerHTML = list
    .map((s) => `<option value="${esc(s.value)}">${esc(s.label)}</option>`)
    .join("");
  sel.value = list.some((s) => s.value === prev) ? prev : "";
}
```

**模板**（`prompt-skills.js`，插在画风后面）：

```javascript
const shotOpts = (meta.shots || [])
  .map((s) => `<option value="${esc(s.value)}">${esc(s.label)}</option>`)
  .join("");
if (shotOpts) {
  ntPersona.insertAdjacentHTML("beforeend",
    `<label class="skill-field">
       <span class="skill-label">机位构图</span>
       <select id="nt-shot">${shotOpts}</select>
     </label>`);
}
```

---

## 验证

### meta 接口

```
guoman             9 项
guoman-portrait    9 项
moss-architect     9 项
nsfw-templates     9 项
adult-photo21      7 项  ← 保留自己的
anime-oneesan      9 项
```

### 实测生效

**厚涂**（选「仰拍，低机位贴近地面」）：

> ...场景：旧上海洋楼回廊，雕花铁栏，落地纱帘透光。蜜色午后光。**以仰拍，低机位贴近地面取景。**

**模板**（极速模式）：

> ...发型 pearl drop earrings，身份 chiropractor。**以仰拍，低机位贴近地面取景。**

### 浏览器（6/6）

```
✅ 国漫: 9 项
✅ 国漫人像: 9 项
✅ MOSS: 9 项
✅ 模板: 9 项
✅ 写实: 7 项（保留自己的）
✅ 厚涂: 10 项（含随机）

6 passed / 0 failed
```

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/shot_options.py` | **新增** 机位池 + `apply()` / `meta()` |
| `scripts/webui/api_guoman.py` | import SH；meta 加 shots；portrait 应用 |
| `scripts/webui/api_guoman_portrait.py` | import SH；meta；generate 应用 |
| `scripts/webui/api_anime_oneesan.py` | import SH；meta；generate 应用 |
| `scripts/webui/api_nsfw_templates.py` | import SH；meta；assemble 两处应用 |
| `static/js/prompt-skills.js` | 国漫人像 + 模板 加下拉 |
| `static/js/anime-oneesan.js` | 厚涂 加下拉 |
| `static/js/guoman.js` | `fillShotOptions()` + 两处 payload |
| `static/index.html` | 国漫加 `guoman-shot` 容器 |
| `static/index.html` | `prompt-skills.js?v=1.17.0`、`anime-oneesan.js?v=1.7.0`、`guoman.js?v=1.11.0` |

---

## 输出位置

机位句**追加到末尾**，格式 `以{机位}取景。`

不插在开头，因为各 skill 的开头都有自己的风格标识（`Wuthering Waves style...`、`国风仙侠。`），
塞进去会打架。
