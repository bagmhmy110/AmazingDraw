# 图片按 skill 名命名

> 2026-11-15。原来四个 skill 生成的图全叫「国漫立绘」，
> 现在按来源 skill 命名：国漫人像 / MOSS / NSFW模板 / 写实摄影。

---

## 根因：person 被硬编码

`api_guoman.py` 的投递端点：

```python
args = [
    bash_executable(), str(submit),
    "--raw", "--prompt", prompt,
    "--person", "国漫立绘",        # ← 写死了
    "--scene", scene,
    "--theme", f"{tone}风",
    ...
]
```

所有 skill 的出图都走这个端点，所以 person 永远是「国漫立绘」。
而文件名由 `cu-deliver.sh` 拼：

```python
name = f"{person}-{scene}-{theme}" if theme else f"{person}-{scene}"
```

→ 全是 `国漫立绘-xxx.png`。

---

## 修法

### 1. 后端接收 person

```python
person = _clean(req.get("person")) or "国漫立绘"   # 没传就回退，兼容旧调用

args = [
    ...
    "--person", person,
    "--theme", theme_suffix,
]
```

### 2. 前端各 skill 传自己的名字

| 页面 | person | theme |
|---|---|---|
| 国漫人像 | `国漫人像` | `人像` |
| MOSS | `MOSS` | `散文` / `排版` |
| 模板 | `NSFW模板` | `模板` |
| 写实 | `写实摄影` | `写实` |

```javascript
bindCardActions("view-guoman-portrait", "国漫人像", "人像");
bindCardActions("view-moss-architect", "MOSS", "散文");
bindCardActions("view-nsfw-templates", "NSFW模板", "模板");
```

`renderPrompt` 多接一个 theme 参数：

```javascript
async function renderPrompt(prompt, tone, scene, btnEl, person, theme) {
  const payload = {
    prompt,
    tone: tone || "国漫立绘",
    scene: scene || "",
    person: person || "国漫立绘",
  };
  if (theme) payload.theme = theme;
  ...
}
```

---

## 两个坑

### 坑 1：theme 不能传空字符串

`cu-submit.sh` 里：

```python
theme = os.environ.get("CU_THEME", "") or "灵感直投"
```

传空会被兜底成「灵感直投」。所以 theme 必须有值。

### 坑 2：theme 必须含中文，否则被丢弃 ⚠️

这个最隐蔽。`parse_prompt_meta.py` 里：

```python
# scene/theme/narrative 仍要求 CJK，避免英文脏缓存进中文 caption
```

**theme 是纯英文会被过滤掉**，然后回退成「灵感直投」。

我一开始给 MOSS 传的 theme 是 `Caption`（英文），结果：

```
person=MOSS  ✅
theme=Caption  ✅（卡片字段对）
文件名=MOSS-便利店-灵感直投_3.png  ❌（theme 被丢弃了）
```

改成中文 `散文` 后立刻正常：

```
文件名=MOSS-便利店-散文.png  ✅
```

**教训：theme 一律用中文。**

### 附带修的：叠字

`person=写实摄影` + `tone=写实摄影` 会拼出 `写实摄影-街道-写实摄影风.png`。

```python
explicit_theme = _clean(req.get("theme"))
if explicit_theme:
    theme_suffix = explicit_theme
elif tone and tone in person:
    theme_suffix = "人像"          # person 已含 tone，用中性词避免叠字
else:
    theme_suffix = f"{tone}风"
```

---

## 验证

### 端到端（4/4）

四个 skill 各投一张，等出图后检查文件名：

```
OK  国漫人像      文件=国漫人像-竹林-人像_2.png
OK  MOSS         文件=MOSS-便利店-散文.png
OK  NSFW模板      文件=NSFW模板-便利店-模板_2.png
OK  写实摄影      文件=写实摄影-街道-写实_3.png
```

每张都满足：
- 卡片 `person` 字段 = skill 名
- 文件名前缀 = skill 名
- theme 段正确
- 无叠字

---

## 命名规则

```
<skill名>-<场景>-<theme>.png
```

| skill | 示例文件名 |
|---|---|
| 国漫人像 | `国漫人像-竹林-人像.png` |
| MOSS | `MOSS-便利店-散文.png` |
| 模板 | `NSFW模板-便利店-模板.png` |
| 写实摄影 | `写实摄影-街道-写实.png` |

相册左侧的「角色」分组也会按这些名字自动归类，四个 skill 会分成四组。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/api_guoman.py` | person 从请求读；theme 叠字处理 |
| `static/js/prompt-skills.js` | `renderPrompt` / `bindCardActions` / `renderCards` 支持 person + theme |
| `static/js/adult-photo21.js` | 传 `person: "写实摄影"` + `theme: "写实"` |

---

## 旧的图怎么办

之前生成的图文件名还是「国漫立绘-xxx」，卡片 person 字段也是「国漫立绘」。
它们会继续归在「国漫立绘」这一组下，不影响新图。

想批量改的话可以写个脚本按卡片历史重命名，但没必要 —— 除非你想让相册分组干净。
