# 修：选中 skill 页时导航不高亮

> 2026-11-16。点国漫 / MOSS / 模板 / 写实 / 厚涂，右侧导航栏的高亮一直停在「卡片」上。

![修好后](../docs-screenshots/nav-active.png)

---

## 根因：判断逻辑漏了大部分视图

`shell.js` 里的高亮判定：

```javascript
if (currentView === "settings" || currentView === "docs" || currentView === "album") {
  isActive = view === currentView;        // ← 只有这三个视图能正确高亮
} else {
  isActive = !!mode && mode === "cards";  // ← 其余全落到这里
}
```

**只硬编码了三个视图名。**

点「国漫」时 `currentView === "guoman"`，不匹配那三个 → 走 `else` →
判断 `data-mode === "cards"`，而国漫按钮没有 `data-mode` →
结果**「卡片」按钮被判定为 active**，国漫按钮反而不是。

后来新增的 `guoman-portrait`、`moss-architect`、`nsfw-templates`、
`adult-photo21`、`anime-oneesan` 全都没进那个 if，所以全部失效。

---

## 修法：改成「有 data-view 就按视图名匹配」

```javascript
if (view) {
  // 任何带 data-view 的按钮（含各 skill 页）都按视图名精确匹配
  isActive = view === currentView;
} else {
  // 「卡片」这类没有 data-view 的按钮，用 data-mode 判断
  isActive = !!mode && mode === "cards" && currentView === "chat";
}
```

### 为什么这样改对

导航栏里的按钮分两类：

| 类型 | 属性 | 数量 |
|---|---|---|
| 「卡片」 | 只有 `data-mode="cards"` | 1 |
| 其余九项 | 有 `data-view="xxx"` | 9 |

实测 `data-view` 值：`album`、`guoman`、`guoman-portrait`、
`moss-architect`、`nsfw-templates`、`adult-photo21`、`anime-oneesan`、
`settings`、`docs`。

**改成按 `data-view` 存在与否分流**，以后新增 skill 页不用再改这段代码 ——
只要按钮带 `data-view` 就自动生效。

---

## 顺带修的小问题

原逻辑里 `isActive = !!mode && mode === "cards"` 没有检查 `currentView`，
所以停在某个 skill 页时，「卡片」按钮也会是 active（导致两个按钮同时高亮）。

改成：

```javascript
isActive = !!mode && mode === "cards" && currentView === "chat";
```

只有真正在卡片页（`currentView === "chat"`）时「卡片」才高亮。

---

## 验证（11/11）

逐个点击九个导航项，检查 active 数量与归属：

```
✅ album              active=1 [album]              opacity=1
✅ guoman             active=1 [guoman]             opacity=1
✅ guoman-portrait    active=1 [guoman-portrait]    opacity=1
✅ moss-architect     active=1 [moss-architect]     opacity=1
✅ nsfw-templates     active=1 [nsfw-templates]     opacity=1
✅ adult-photo21      active=1 [adult-photo21]      opacity=1
✅ anime-oneesan      active=1 [anime-oneesan]      opacity=1
✅ settings           active=1 [settings]           opacity=1
✅ docs               active=1 [docs]               opacity=1

回到「卡片」: active=1 [mode:cards]

11 passed / 0 failed
```

每个视图都**恰好一个** active，且归属正确；滑动指示器 `opacity=1` 正常显示。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `static/js/shell.js` | 高亮判定改为「有 `data-view` 按视图名匹配，否则按 `data-mode` + `currentView === "chat"`」 |
| `static/index.html` | `shell.js?v=1.12.0` → `v=1.13.0` |

---

## 教训

**别在条件判断里硬编码视图名清单。**
这次是三个视图写死在 if 里，后面加了六个新视图全都没覆盖到。

改成「按属性存在与否分流」后，新增视图自动生效，不用再回来改。
