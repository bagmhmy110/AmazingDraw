# 所有 skill 的提示词可直接编辑

> 2026-11-15。六个 skill 生成出来的提示词，现在点进去就能改，改完直接出图。

![可编辑提示词](../docs-screenshots/prompt-editable.png)

---

## 效果

- 提示词区变成可编辑（`contenteditable`）
- 鼠标悬停左边出现淡紫竖线，聚焦后变实线 + 淡紫底
- 聚焦时下方提示「编辑中 · Ctrl+Enter 出图」
- **编辑后「生成图片」「复制」按钮自动同步**，不用手动确认
- **Ctrl+Enter 直接出图**

---

## 覆盖范围

六个 skill 页面的全部提示词展示点：

| 页面 | 位置 |
|---|---|
| 国漫 | 立绘提示词卡片 + 批量结果每条 |
| 国漫人像 | 生成结果卡片 |
| MOSS | 生成结果卡片 |
| 模板 | 组装结果卡片 |
| 写实 | 生成结果卡片 |
| 厚涂 | 生成结果卡片 |

---

## 实现

### 共享模块 `static/js/prompt-edit.js`

```javascript
window.PromptEdit = { html, read, syncButtons, bind };
```

**渲染**（替换原来的只读 div）：

```javascript
// 改前
`<div class="skill-prompt">${esc(p)}</div>`

// 改后
`${window.PromptEdit.html(p)}`
```

内部用 `contenteditable` 而不是 `textarea` —— 高度能自动撑开，长提示词不用内部滚动。

**事件委托**（每个页面初始化时绑一次）：

```javascript
window.PromptEdit?.bind($("view-guoman-portrait"));
```

绑定三件事：

| 事件 | 作用 |
|---|---|
| `input` / `blur` | 把编辑后的文本同步到按钮的 `data-render` / `data-copy` |
| `paste` | 只保留纯文本，去掉富文本样式 |
| `keydown` | Ctrl+Enter 同步并触发出图 |

### 同步逻辑

```javascript
function syncButtons(cardEl) {
  const text = read(cardEl);          // 用 innerText 拿纯文本
  if (!text) return;
  cardEl.querySelectorAll("[data-render]").forEach((b) => {
    b.setAttribute("data-render", text);
  });
  cardEl.querySelectorAll("[data-copy]").forEach((b) => {
    b.setAttribute("data-copy", text);
  });
}
```

**用 `innerText` 而不是 `textContent`** —— contenteditable 编辑会产生 `<div>` 和 `<br>`，
`textContent` 会拿到没有换行的粘连文本。

### 粘贴只留纯文本

```javascript
root.addEventListener("paste", (e) => {
  const box = e.target.closest("[data-prompt-editable]");
  if (!box) return;
  e.preventDefault();
  const text = (e.clipboardData || window.clipboardData).getData("text/plain");
  document.execCommand("insertText", false, text);
});
```

否则从网页复制会带进 `<span style="...">` 之类的标签，污染提示词。

---

## 样式

```css
.skill-prompt.is-editable {
  cursor: text;
  border-left: 3px solid transparent;
  outline: none;
  min-height: 2.4em;
}

.skill-prompt.is-editable:hover {
  border-left-color: rgba(108, 92, 231, 0.35);
  background: rgba(108, 92, 231, 0.03);
}

.skill-prompt.is-editable:focus {
  border-left-color: #6c5ce7;
  background: rgba(108, 92, 231, 0.07);
  box-shadow: inset 0 0 0 1px rgba(108, 92, 231, 0.2);
}

.skill-prompt.is-editable:focus::after {
  content: "编辑中 · Ctrl+Enter 出图";
  ...
}
```

---

## 验证（9/9）

```
PASS  PromptEdit 已加载
PASS  国漫人像 可编辑（contenteditable=true）
PASS  厚涂 可编辑
PASS  写实 可编辑
PASS  国漫人像 有内容（160 字）
PASS  厚涂 有内容（173 字）
PASS  写实 有内容（116 字）
PASS  编辑后按钮同步
PASS  编辑后复制同步
```

编辑测试：把提示词改成「这是我手动修改后的提示词内容，用于测试编辑同步。」后，
按钮的 `data-render` 和 `data-copy` 都同步成了这句。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `static/js/prompt-edit.js` | **新增** 可编辑组件 |
| `static/js/prompt-skills.js` | 两处替换 + 三个页面 bind |
| `static/js/adult-photo21.js` | 一处替换 + bind |
| `static/js/anime-oneesan.js` | 一处替换 + bind |
| `static/js/guoman.js` | 两处替换 + bind |
| `static/css/09-prompt-skills.css` | 可编辑样式 |
| `static/index.html` | 引入 prompt-edit.js |

---

## 用法提示

- **改完直接点「生成图片」**，用的是改后的版本
- **Ctrl+Enter** 更快，不用移动鼠标
- 从别处粘贴提示词时，只会带纯文本，不会带格式
- 想恢复原文？重新点一次「生成」即可
