# MOSS Layout 模式 — 草稿结构与坐标编译

> **仅在被选中时使用。** 用于：精确的文字位置、海报、平面广告、多个独立定位的分栏、
> 或确实需要坐标的受约束物件摆放。
> 「细节很多」本身**不构成**使用 Layout 的理由。

Layout 的流程：在心里写出草稿（draft），然后**只输出**它的编译结果。

---

## 一、内部草稿 schema

```json
{
  "width": 1536,
  "height": 1024,
  "bbox_coord_space": "abs",
  "bbox_format": "xyxy",
  "summary": {
    "caption": "A description of the entire coherent image",
    "meta": ["optional medium"],
    "canvas": "single",
    "palette": ["optional colors"]
  },
  "items": [
    { "label": "object", "caption": "Visible appearance of the placed object", "bbox": [176, 224, 800, 864] }
  ]
}
```

---

## 二、校验规则

### 根键

- 根键**恰好**是：`width`、`height`、`bbox_coord_space`、`bbox_format`、`summary`、`items`。
- 六者**全部必填**。

### 画布尺寸

- `width` 与 `height` 必须是**正整数且能被 16 整除**。
- 它们**必须**与真实的生成画布一致。
- 明确的尺寸优先；若用户给了不兼容的显式尺寸，**报告冲突**，而不是悄悄改掉。
- 只给了宽高比时：选择兼容的尺寸；否则默认 `1024x1024`，但若媒介暗示了更合适的形状则可调整。

### bbox 草稿格式

- 草稿中固定写 `bbox_coord_space="abs"`、`bbox_format="xyxy"`。
- `[x_min, y_min, x_max, y_max]` 是**从左上角起算的真实像素边缘坐标**。
- 约束：`0 <= x_min < x_max <= width`，`0 <= y_min < y_max <= height`，坐标须为有限数值。

### summary

- 必填非空 `caption`。
- 可选 `meta`／`palette`：由非空字符串组成的数组。
- 可选 `canvas`：`"single"`、`"multi_panel"` 或 `"collage"`。
- **不得**出现其他 summary 字段。

### items

- 必须是**非空的一维扁平数组**（flat array）。
- 每个 item 必填：
  - `label`，且**恰好**是 `"object"`、`"character"` 或 `"text"` 之一
  - 非空 `caption`
  - `bbox`
- 可选 item 键：`text`、`tags`、`palette`；`tags`／`palette` 为字符串数组。
- `label` 为 `"text"` 的 item **必须**带非空 `text` 字段，内容就是可见文字本身，一字不差。
- 不得引入未知键，不得嵌套 `children`／`parent`／编辑器 ID。

### bbox 语义

- bbox **不是**可见边框。场景需要时可以重叠或共享方框。
- 用连贯的可见分组；只有独立摆放的东西才拆开。
- 显示的文案在所选像素尺寸下必须真正可读：分配合适的面积、阅读顺序与视觉层级。
- **不得**改动用户指定的文案、拼写、标点或换行。
  文字字符串里的字面换行在序列化时写成 JSON 转义 `\n`。

---

## 三、坐标换算：草稿 `[x1,y1,x2,y2]` → 模型面向的整数 yxyx 框

```
[ floor(round(y1, 9)) - height/2,
  floor(round(x1, 9)) - width/2,
  ceil (round(y2, 9)) - height/2,
  ceil (round(x2, 9)) - width/2 ]
```

- `floor`／`ceil` 向外取整，以**包含**草稿区域。
- `round(v, 9)` 先把数值精度圆整到小数点后九位。
- 输出顺序是 **TOP、LEFT、BOTTOM、RIGHT**，各自相对**画布中心**度量。
- 宽高都是 16 的倍数，故其一半必为整数。
- 校验结果满足 `top < bottom` 且 `left < right`。

**禁止**：

- 归一化到 0–1
- 交换轴序
- 静默裁掉非法框
- 不经过换算就把框重新居中

### 换算示例

画布 `1536x1024`，草稿 bbox `[176, 224, 800, 864]`

```
top    = floor(224) - 1024/2 =  224 - 512 = -288
left   = floor(176) - 1536/2 =  176 - 768 = -592
bottom = ceil (864) - 1024/2 =  864 - 512 =  352
right  = ceil (800) - 1536/2 =  800 - 768 =   32
```

→ 最终 `bbox: [-288, -592, 352, 32]`

---

## 四、最终 Layout 输出结构（严格照此）

```json
{"summary":{"caption":"..."},"items":[{"label":"object","caption":"...","bbox":[-288,-592,352,32]}],"bbox_coord_space":"abs_centralized","bbox_format":"yxyx"}
```

- 草稿里用到的合法可选 `summary`／`item` 字段予以保留。
- **最终 Layout JSON 中排除 `width` 与 `height`。**
- 坐标空间固定为 `"abs_centralized"`，格式固定为 `"yxyx"`。
- 序列化为**单独一个物理行**的合法紧凑 JSON：换行写成转义 `\n`，Unicode 字符原样保留。
- **不要**在 JSON 外围加 Markdown 代码块或任何解释文字。

### 语言约定（重要）

- **键名一律保持英文原样**：`summary`、`caption`、`items`、`label`、`text`、`bbox`、`tags`、`palette`、`bbox_coord_space`、`bbox_format` 等，不翻译、不改名。
- **所有值用中文写**：`summary.caption`、每个 item 的 `caption` 都是中文散文。
- **例外：`label` 的值必须保持英文枚举**——只能是 `"object"`、`"character"`、`"text"`，不得写成"物体""人物""文字"。
- **例外：`text` 字段保持可见文字原语言原样**，一字不差，不翻译、不改标点与大小写。中文招牌就写中文，英文招牌就写英文。
- 族裔硬约束在 Layout 模式下同样生效：每个 `label:"character"` 的 caption 都必须写明亚洲族裔与可见特征。

---

## 五、回答前的复核清单

- [ ] 每个 item 的坐标都按公式算过
- [ ] 文字 item 的 `text` 与用户文案逐字一致（含标点与换行）
- [ ] 所有必填字段齐备
- [ ] 实际画布尺寸选择正确，宽高为 16 的倍数
- [ ] 每个框 `top < bottom` 且 `left < right`
- [ ] 输出是单行紧凑 JSON
- [ ] **所有 `label:"character"` 的 item 及其 caption 中的人物都是亚洲人**（中国／日本／韩国／其他亚洲族裔），且写明了可见特征
- [ ] 键名全为英文，`caption` 值为中文，`label` 值仍是英文枚举
- [ ] `text` 字段与用户可见文案逐字一致，未被翻译

> LLM 的算术不如官方 Python 编译器可靠。优先使用整数框与易于核验的摆放位置，
> 并且**绝不**声称编译器（compile_prompt.py）被执行过。
