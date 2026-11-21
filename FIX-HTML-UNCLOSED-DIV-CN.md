# 修：前端只剩卡片列表，其他全没了

> 2026-11-16。我把国漫页面合并时少写了一个 `</div>`，
> 导致后面 7 个视图全被嵌进 `view-guoman` 里，界面上只剩侧栏。

![恢复后](../docs-screenshots/ui-restored.png)

---

## 症状

打开网页，只有左边的卡片列表，右边空白 —— 所有 skill 页面、相册、配置、文档都看不见了。

---

## 根因：少了一个 `</div>`

我做国漫页面合并时，用脚本整块替换 HTML。替换块结尾是：

```html
          <!-- 输出区 -->
          <div class="guoman-output" id="guoman-output">
            <p class="placeholder-text">选好选项后点「生成 1 条」或「批量生成」。</p>
          </div>
        </div>          ← 只关闭了 guoman-scroll
                        ← 缺了关闭 view-guoman 的那个
```

`<div class="workspace-view" id="view-guoman">` **没有闭合**。

于是后面的 `view-guoman-portrait`、`view-moss-architect`、`view-nsfw-templates`、
`view-adult-photo21`、`view-anime-oneesan`、`view-script-expand`、`view-settings`、`view-docs`
**全部变成了 `view-guoman` 的子元素**。

浏览器切换视图时，`view-guoman` 不是 active，它所有的后代都不显示 —— 界面就只剩侧栏了。

---

## 怎么发现的

写了个脚本逐行统计 `<div>` 深度：

```python
depth = 0
stack = []
for i, line in enumerate(lines, 1):
    for m in re.finditer(r"<div\b[^>]*>|</div>", line):
        tok = m.group(0)
        if tok.startswith("</"):
            if stack:
                stack.pop()
            else:
                print(f"  第 {i} 行：多余的 </div>")
            depth -= 1
        else:
            stack.append((i, tok[:80]))
            depth += 1

    if re.search(r'id="view-|class="workspace-view"', line):
        print(f"  第 {i:5d} 行  depth={depth:3d}  {line.strip()[:70]}")
```

**输出**（修复前）：

```
  第   246 行  depth=  4  <div class="workspace-view active" id="view-chat">
  第   279 行  depth=  4  <div class="workspace-view" id="view-settings">
  第   674 行  depth=  4  <div class="workspace-view" id="view-docs">
  第   690 行  depth=  4  <div class="workspace-view" id="view-album">
  第   716 行  depth=  4  <div class="workspace-view" id="view-guoman">
  第   843 行  depth=  5  <div class="workspace-view" id="view-guoman-portrait">   ← 变 5 了！
  第   894 行  depth=  5  <div class="workspace-view" id="view-moss-architect">
  ...

最终 depth = 1
未闭合的 div 共 1 个：
  第 42 行: <div class="app-layout">
```

**关键线索**：所有视图深度都是 4，只有 `view-guoman-portrait` 开始变成 5 ——
说明 `view-guoman` 没闭合，后面的都被套进去了。

---

## 修法

在 `guoman-scroll` 闭合后补一个 `</div>`：

```html
          <!-- 输出区 -->
          <div class="guoman-output" id="guoman-output">
            <p class="placeholder-text">选好选项后点「生成 1 条」或「批量生成」。</p>
          </div>
        </div>        ← 关闭 guoman-scroll
      </div>          ← 关闭 view-guoman（补上这个）

      <!-- ═══ 国漫 / 东方女性人像 ═══ -->
```

**修复后**：

```
  第   716 行  depth=  4  <div class="workspace-view" id="view-guoman">
  第   844 行  depth=  4  <div class="workspace-view" id="view-guoman-portrait">   ← 恢复 4
  第   895 行  depth=  4  <div class="workspace-view" id="view-moss-architect">
  ...

最终 depth = 0
```

---

## 验证

### DOM 结构

```
视图数: 11
所有视图父级: workspace-views-stack   ← 一致了
导航项: 10
```

### 逐个切换（11/11 全部正常）

```
✅ chat               active=true 885x1307
✅ album              active=true 1330x1307
✅ guoman             active=true 1330x1307
✅ guoman-portrait    active=true 1330x1307
✅ moss-architect     active=true 1330x1307
✅ nsfw-templates     active=true 1330x1307
✅ adult-photo21      active=true 1330x1307
✅ anime-oneesan      active=true 1330x1307
✅ script-expand      active=true 1330x1307
✅ settings           active=true 1330x1307
✅ docs               active=true 1330x1307
```

`chat` 是 885 宽，因为侧栏占了空间，其他视图全宽 1330。

### 最终检查

```
<div> 267 / </div> 267  平衡: True
```

---

## 教训

### 用脚本替换大块 HTML 时，必须验证标签平衡

我上次用 Python 脚本整块替换国漫页面，替换成功了，也做了功能验证
（按钮在、选项在、能生成），但**没检查标签结构**。

功能验证通过是因为：`view-guoman` 自己还在，里面的东西都正常。
**问题是它把后面的兄弟节点吞了。**

### 加一道结构检查

改完 HTML 后跑一下：

```python
o = len(re.findall(r'<div\b', t))
c = len(re.findall(r'</div>', t))
assert o == c, f"div 不平衡: {o} vs {c}"
```

一行就能拦住这类问题。

### 更稳的做法

用脚本替换 HTML 时，让脚本自己算好缩进和闭合：

```python
# 替换块必须自带完整的开闭结构
new_block = f'''{indent}<div ...>
{indent}  ...
{indent}</div>
'''
```

而不是手工拼字符串 —— 手工拼最容易漏闭合标签。
