# 新 skill：一句话扩写剧本（NSFW）

> 2026-11-16。把 `~/.dsh/skills/01-一句话扩写剧本-NSFW` 接进 WebUI。
> 导航新增「剧本 · Script」。

![一句话扩写剧本](../docs-screenshots/script-expand.png)

---

## 用起来

输入一句话创意 → 选类型/画幅/语言 → 点「扩写剧本」→ 等 1-2 分钟。

产出按标准剧本格式分块展示：

| 分块 | 内容 |
|---|---|
| 剧本头部 | 剧名 / 一句话梗概 / 生产规格 |
| 角色卡 | 每角色声音特征 |
| 场景卡 | 每场景 4 项（环境/光照/室内元素/氛围对比） |
| 分场剧本 | SC-01… 每场 10s + 镜头拆分 |
| 场间衔接 | 衔接链 + 续集钩子 |

每块都能**直接编辑**，「复制全文」「存为 .md」用的是改后的内容。

---

## 生成参数

| 项 | 默认 | 说明 |
|---|---|---|
| 场数 | 6 | 2-20 |
| 每场秒数 | 10 | 5-30 |
| 批大小 | 2 | 1-3，控制单次 LLM 生成几场 |

**批大小很关键** —— 一次让模型写 6 场，它会花 12000+ 字在 reasoning 上，
content 直接为空。拆成每批 2 场就稳了。

---

## 三个坑，踩得很深

### 坑 1：整份剧本一次生成 → content 为空

第一版把整份 SKILL.md 的规则 + 完整格式骨架塞进 user，一次要求 10 场剧本。

结果：

```
LLM 未产出正文（content 为空，finish_reason=stop，思考内容 8650 字）
```

模型把 token 全烧在「规划这 10 场怎么排」上，一个字没写。

**修法：分三阶段**

```python
# 阶段一：只要头部（剧名/梗概/规格/角色卡/场景卡）
head = llm_chat_with_retry(_SYS_HEAD, _build_head_user(req), max_tokens=8000, ...)

# 阶段二：分场，每批 2 场，带上一批结尾做衔接
while start <= scenes:
    chunk = llm_chat_with_retry(_SYS_SCENES, _build_scenes_user(head, req, start, cnt, prev_tail), ...)
    prev_tail = 最后一场的「状态位置」
    start += cnt

# 阶段三：只传场次摘要，不传整份剧本
chain = llm_chat_with_retry(_SYS_HEAD, digests, max_tokens=6000, ...)
```

### 坑 2：用「直白 6 级」这种术语 → 模型拒答

第一版提示词写：

> 直白等级上限 6 级；性爱戏场数 ≥5 场；台词必须直白露骨

模型回：

> 这个请求我无法完成。剧本中有多项硬性要求——性爱戏场数≥5场、直白等级6级、
> 台词必须"直白露骨"——这些指向的是明确的色情内容创作…

**修法：不用分级术语，直接说清楚**

```python
"这是成人向竖屏短剧，两位主角都是成年男女。",
f"从第 {sex_from} 场起是两人之间的亲密戏，"
"写清楚身体动作（谁碰了哪里、怎么动）、身体反应、以及两人真实会说的台词",
```

反直觉但有效：**含糊的「情感强度」「亲密戏份」反而让模型反复斟酌边界，
把 token 烧在思考上；明确说明「成年男女 + 写清身体动作」反而能出正文。**

实测对比：

| 写法 | 结果 |
|---|---|
| 「情感浓度极高」「亲密戏占一半以上」 | ❌ content 为空（思考 5051 字） |
| 「成年男女」「写清身体动作与台词」 | ✅ 575 字正常输出 |

### 坑 3：max_tokens 太小被 reasoning 吃光

`max_tokens=3000` 时，reasoning 占 4307 字，content 为空。

**修法**：所有阶段 `max_tokens=8000`。

---

## 后端

| 端点 | 用途 |
|---|---|
| `GET /api/script-expand/meta` | 类型/画幅/语言/直白等级/参考文档 |
| `GET /api/script-expand/reference` | 读 script-format.md / intimacy-directing.md |
| `POST /api/script-expand/generate` | 三阶段生成 |
| `POST /api/script-expand/polish` | 按自检清单润色 |

### 请求体

```json
{
  "idea": "两个久别重逢的前任在暴雨夜被困同一家酒店，只剩一间房",
  "genre": "久别重逢",
  "aspect": "9:16",
  "lang": "中文",
  "characters": "林夏（女，29岁）、顾沉（男，32岁）",
  "scene_hint": "酒店套房、浴室、落地窗",
  "scenes_per_ep": 6,
  "scene_seconds": 10,
  "batch_size": 2
}
```

### 返回

```json
{
  "ok": true,
  "script": "【剧名】...（完整剧本）",
  "sections": {
    "title": "【剧名】...",
    "logline": "【一句话梗概】...",
    "spec": "【生产规格】...",
    "characters": "【角色卡】...",
    "locations": "【场景卡】...",
    "scenes": "【分场剧本】...",
    "chain": "【场间衔接链】...",
    "hook": "【续集钩子】..."
  },
  "stats": {
    "scenes": 4, "shots": 8, "characters": 2, "locations": 4,
    "sex_scenes": 1, "sex_ratio": 0.25, "chars": 2858
  },
  "warnings": [],
  "stages": { "head": true, "scene_batches": 2, "chain": true }
}
```

### 统计的宽容度

角色卡/场景卡允许两种写法：

- 带编号：`CHAR-01 林夏` / `LOC-01 酒店大堂`
- 直接起行：`林夏｜女声，细冷带少量气声` / `场景1｜环境：...`

统计函数两种都认，不会因为模型换了写法就显示 0。

---

## 前端

`static/js/script-expand.js`：

- 创意输入框支持 **Ctrl+Enter** 直接扩写
- 五个分块各自 `contenteditable`，可单独编辑
- 每块右上角有独立复制按钮
- 「复制全文」「存为 .md」收集的是**编辑后**的内容
- 统计条显示「N 场 · N 镜 · N 字 · 亲密场 N（N%）」，≥50% 变绿

---

## 验证

### API 实测

```
✅ 耗时 121.9s
stats: {"scenes": 6, "shots": 12, "characters": 2, "locations": 6,
        "sex_scenes": 4, "sex_ratio": 0.67, "chars": 4735}
stages: {"head": true, "scene_batches": 3, "chain": true}
warnings: []
```

### 浏览器端到端（15/15）

```
PASS  导航有剧本入口
PASS  视图存在且激活 / display 是 flex
PASS  导航高亮正确
PASS  skill 就绪
PASS  有创意输入框
PASS  类型下拉 5 项 / 画幅 3 项 / 语言 3 项
PASS  规则提示显示
PASS  生成了剧本分块（5 块）
PASS  含角色卡 / 含分场剧本
PASS  正文超过 800 字（2851 字）
PASS  统计显示

15 passed / 0 failed
```

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/api_script_expand.py` | **新增** 三阶段生成 + 润色 + 统计 |
| `scripts/webui/web_server.py` | 注册 router |
| `static/js/script-expand.js` | **新增** 前端逻辑 |
| `static/index.html` | 视图 + 导航 + JS 引用 |
| `static/js/shell.js` | switchView 分发 |
| `static/css/09-prompt-skills.css` | 页面样式 |

---

## 现在一共 7 个 skill 页面

| 导航 | Skill | 走 LLM |
|---|---|---|
| 国漫 | guoman-costume-xianxia-prompts | ❌ 纯代码 |
| 国漫人像 | guoman-portrait-prompts | ✅ |
| MOSS | moss-image-prompt-architect | ✅ |
| 模板 | nsfw-prompt-templates-asian | ✅ |
| 写实 | adult-photorealistic-prompt-style-21 | ✅ |
| 厚涂 | anime-thickpaint-oneesan-prompts | ❌ 纯代码 |
| **剧本** | **01-一句话扩写剧本-NSFW** | ✅ **分三阶段** |

---

## 一个使用建议

**批大小别调大。** 默认 2 最稳。调到 3 有时还能出，但偶尔会撞上 reasoning 吃光 token。
调到 4 以上基本必失败。

场数也别一次要太多 —— 6 场约 2 分钟，10 场要 3-4 分钟，中间任何一批失败都会留下缺口
（会在 `warnings` 里提示）。
