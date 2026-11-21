# 国漫人像：选项重排

> 2026-11-16。加了机位构图后，国漫人像的选项挤成一团、右边错位。

![重排后](../docs-screenshots/gp-layout.png)

---

## 根因：容器嵌套错了

HTML 结构原本是这样：

```html
<div class="skill-field-row">          <!-- 外层：CSS 网格 -->
  <label>风格线</label>
  <label>露腿分级</label>
  <label>主题</label>
  <label>额外要求</label>
  <div class="skill-field-row" id="gp-persona"></div>   <!-- 嵌套！ -->
  <div class="skill-field-row" id="gp-look"></div>      <!-- 嵌套！ -->
  <div class="skill-field-row" id="gp-setting"></div>   <!-- 嵌套！ -->
  <div class="skill-field-row" id="gp-outfit-row"></div><!-- 嵌套！ -->
</div>
```

`.skill-field-row` 的 CSS 是：

```css
.skill-field-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}
```

**外层是网格，内层四个 `div` 也是网格** —— 但它们被当成了**外层的网格项**，
于是 4 个 `div` + 4 个 `label` 全挤在同一行，每格只有 160px 宽，右边的字段错位。

---

## 修法：内层移出来

```html
<div class="skill-field-row">
  <label>风格线</label>
  <label>露腿分级</label>
  <label>主题</label>
  <label>额外要求</label>
</div>                                    <!-- ← 这里闭合 -->
<div class="skill-field-row" id="gp-persona"></div>
<div class="skill-field-row" id="gp-look"></div>
<div class="skill-field-row" id="gp-setting"></div>
<div class="skill-field-row" id="gp-outfit-row"></div>
```

四个容器变成**并列的兄弟节点**，各自独立成行。

---

## 现在的五排布局

| 排 | 字段 | 数量 |
|---|---|---|
| 1 | 风格线 · 露腿分级 · 主题 · 额外要求 | 4 |
| 2 | 人种 · 年龄 · 身材 · 气质 | 4 |
| 3 | 人物类型 · 发型 · 性感级别 | 3 |
| 4 | 场景 · 光线 · 姿势 · 机位构图 | 4 |
| 5 | 服装类别 · 服装 | 2 |

**机位构图**原来和场景/光线/姿势挤在第三排的 5 个字段里，现在独立成第四排的 4 个之一。

---

## 检查其他 skill

跑了一遍，只有国漫人像是嵌套的。其余都是并列：

```html
<!-- MOSS -->
</div>
<div class="skill-field-row" id="ma-more"></div>
<div class="skill-field-row" id="ma-persona"></div>

<!-- 写实 -->
</div>
<div class="skill-field-row" id="ap-persona"></div>

<!-- 厚涂 -->
<div class="skill-field-row" id="ao-style-row"></div>
<div class="skill-field-row" id="ao-row1"></div>
<div class="skill-field-row" id="ao-row2"></div>
...
```

---

## 验证（5/5）

```
gp-persona     4 个字段: 人种 / 年龄 / 身材 / 气质
gp-look        3 个字段: 人物类型 / 发型 / 性感级别
gp-setting     4 个字段: 场景 / 光线 / 姿势 / 机位构图
gp-outfit-row  2 个字段: 服装类别 / 服装

服装联动: 149 项 → 29 项（选「传统旗袍」后）

5 passed / 0 failed
```

服装联动仍然正常 —— 换到新容器后事件绑定跟着走，没断。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `static/index.html` | 四个 `skill-field-row` 从嵌套改为并列；新增 `gp-outfit-row` 容器 |
| `static/js/prompt-skills.js` | 服装类别/服装 从 `gp-setting` 拆到 `gp-outfit-row`；机位构图进 `gp-setting` |
| `static/index.html` | `prompt-skills.js?v=1.20.0` |

---

## 教训

**`.skill-field-row` 是网格容器，不能嵌套自己。**

它用 `repeat(auto-fit, minmax(160px, 1fr))` 自动排列，
一旦把另一个 `skill-field-row` 塞进去，内层容器本身会变成一个「网格项」，
里面的字段全部失去布局控制。

这种问题的视觉特征很典型：**第一排挤爆、后面的行错位、右边留大片空白**。
