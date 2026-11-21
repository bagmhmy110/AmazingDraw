# 三个新 skill 接入（各自独立）

> 2026-11-15。把三个 prompt skill 接进 WebUI，**各自独立页面、独立 API、独立导航入口**，不合并。

| Skill | 导航 | 页面 |
|---|---|---|
| `guoman-portrait-prompts` | 国漫人像 · Portrait | 四条风格线人像 |
| `moss-image-prompt-architect` | MOSS · Architect | Caption / Layout |
| `nsfw-prompt-templates-asian` | 模板 · Templates | 14 模块组装 |

---

## 一、国漫人像（guoman-portrait-prompts）

![国漫人像](../docs-screenshots/skill-guoman-portrait.png)

### 四条风格线

| 线 | 名称 | 字数 | 说明 |
|---|---|---|---|
| **B** | 二次元厚涂 | 100-180 | 主力线。Wuthering Waves style 开头 |
| **C** | 古风仙侠 | 250-420 | 服装结构密度最高 |
| **A** | 写实 CCD | 120-200 | 生活化抓拍感 |
| **D** | 高定服装 | 150-250 | 纯服装描述 |

### 两种生成

- **生成一条**：走 LLM，按风格线填值扩写
- **批量生成**：直接调 skill 自带 `scripts/generate.py`（内置禁词校验、三元组去重、五类服装均衡轮换）

### 实现要点

批量走脚本、单条走 LLM —— 脚本已经打磨过（500 条零违规零重复），没必要让 LLM 重做。

---

## 二、MOSS-Image 架构师（moss-image-prompt-architect）

![MOSS](../docs-screenshots/skill-moss-architect.png)

### 两种输出模式

| 模式 | 用途 |
|---|---|
| **Caption**（默认） | 中文散文段落。人像、角色、生活场景、产品、建筑、插画 |
| **Layout** | 单行紧凑 JSON + bbox 坐标。海报、精确文字位置、多栏摆放 |

### 硬约束

**所有人物一律亚洲人**（中国/日本/韩国/其他亚洲族裔），且必须通过肤色、眼型、发质、面部结构等**具体可见特征**落地 —— 不是贴个「亚洲人」标签了事。

实测输出示例：

> 一个浅麦色皮肤、细长内双眼、短直睫毛、颧骨平缓、鼻梁不高、下颌圆润的年轻女孩…细软黑发扎成低马尾，额前碎发被夜里的潮气黏在鬓角…

### 批量变体

按 skill 的「步 I」要求：变化落在**场景方案**上（相机距离、视点、时段、地点、衣橱、动作阶段），不是只换形容词；各条体现不同亚洲族裔与地域。

---

## 三、NSFW 模板词库（nsfw-prompt-templates-asian）

![NSFW 模板](../docs-screenshots/skill-nsfw-templates.png)

### 14 模块 · 按组装顺序

**必读槽（7 个，各取 1 词条）**
```
场景主题 → 景别构图 → 裸露液体 → 服装专项 → 光影氛围 → 姿势动作 → 表情眼神
```

**选读槽（7 个，取 3-5 个）**
```
风格胶片 · 妆容专项 · 发型饰品 · 瑕疵细节 · 纹身标记 · 道具宠物 · 人格卡片
```

### 两种用法

- **按槽组装**：填好各槽词条 → 按顺序串联
- **自由扩写**：一句话想法 → 按索引方向扩写
- **浏览模块**：展开可查看任一模块的完整词库

### 设计取舍：词条必须用户填

这个 skill 的 markdown 里**混着章节标题、联动说明、索引表**。自动抽词会抽到「信号词」「开始/进入」这类非词条内容。

所以 assemble 端点要求至少填一个槽位：

```python
if not filled and not theme:
    raise HTTPException(400, "请至少填写一个槽位词条（或填主题）。词库混有章节标题，自动抽词不可靠，需要你指定。")
```

代码只负责**排序 + 串联**，不做「猜词」。

### 边界

仅成年虚构角色（18+）；不用于现实具体人物的性化图像；不含未成年外貌与年龄暗示。

---

## 关键技术发现：推理模型会「想死」

这三个 skill 都靠 LLM 驱动，接的过程中踩到一个**很硬的坑**。

### 症状

把整份 SKILL.md / references 塞进 system prompt，模型返回：

```
content = ""（空）
reasoning_content = 8319 字（全是思考）
finish_reason = "stop"
```

思考 8000 多字，**正文一个字都没出**。

### 排查过程

| 实验 | 结果 |
|---|---|
| system 极短（19 字） | ✅ content 2 字 |
| system 短（29 字） | ✅ content 85 字 |
| system 中（315 字） | ✅ content 73 字 |
| system 长（2520 字，纯重复） | ✅ content 50 字 |
| **system 含规则文档** | ❌ **content 空，reasoning 8000+ 字** |

**结论：不是长度问题，是「内容像规则文档」的问题。**

模型看到「# 硬性规则」「# 输出格式」「- 禁止…」这类结构化规则，会逐条分析「我该怎么满足这条规则」，把 token 预算全烧在思考上。

### 解法

**不要把参考文档交给模型，改由代码选词、模型只串联。**

```python
# ❌ 之前：把规则文档塞进 system
system = f"严格遵守以下规则：\n{rules}\n{skeleton}\n{expand}"

# ✅ 现在：代码先选好词，模型只做填空扩写
values = {k: random.choice(v) for k, v in pool.items()}
user = f"""按这个句式写：

{template}

填入：
{lines}

直接输出填好的那一段。"""
```

### 效果对比

| 端点 | 改前 | 改后 |
|---|---|---|
| 国漫人像 | ❌ content 空（8319 字思考） | ✅ 45.6s / 176 字 |
| MOSS Caption | ❌ content 空（8568 字思考） | ✅ 46.2s / 509 字（3/3 稳定） |
| NSFW 组装 | ❌ 模型拒绝 | ✅ 17.8s / 100 字 |

---

## 另一个坑：CSS 覆盖了视图隐藏

### 症状

新页面明明加了，导航也点了，但截图里永远是旧页面。

### 原因

```css
/* ❌ 08-guoman.css 原有写法 */
#view-guoman {
  display: flex;   /* ← 覆盖了 .workspace-view 的 display: none */
}
```

`.workspace-view` 默认 `display: none`，只有 `.active` 时才 `display: block`。
但 `#view-guoman` 的 ID 选择器优先级更高，直接写了 `display: flex` ——
**结果这个视图永远可见，盖在所有其他视图上面。**

这是之前就存在的 bug，只是之前没有「同层级的新视图」所以没暴露。

### 修法

```css
/* ✅ 带上 .active */
#view-guoman.active {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
```

我新写的 `09-prompt-skills.css` 一开始也犯了同样的错，一起改了。

**教训：给 `.workspace-view` 写样式时，`display` 必须带 `.active`。**

---

## 验证

### API 层

```
[国漫人像] 45.6s  ok=True len=176
[MOSS]     46.2s  ok=True len=509   （连测 3 次全过）
[NSFW]     17.8s  ok=True len=100
```

### UI 层（20/20）

```
PASS  三个视图 DOM 存在
PASS  三个导航入口存在
PASS  三个 init 函数已暴露
PASS  国漫人像视图 active
PASS  国漫人像 skill 就绪
PASS  四条风格线
PASS  露腿三级
PASS  国漫人生成成功
PASS  MOSS 视图 active
PASS  MOSS skill 就绪
PASS  两种模式
PASS  MOSS 硬约束显示
PASS  MOSS 生成成功
PASS  NSFW 视图 active
PASS  NSFW skill 就绪
PASS  七个必读槽
PASS  七个选读槽
PASS  14 个模块
PASS  NSFW 边界提示
PASS  NSFW 组装成功
```

---

## 修改文件

| 文件 | 说明 |
|---|---|
| `scripts/webui/skill_common.py` | **新增** skill 定位、LLM 调用、markdown 读取 |
| `scripts/webui/api_guoman_portrait.py` | **新增** 国漫人像（4 线 + 批量脚本） |
| `scripts/webui/api_moss_architect.py` | **新增** MOSS（Caption / Layout + 批量变体） |
| `scripts/webui/api_nsfw_templates.py` | **新增** NSFW（14 模块 + 按槽组装） |
| `scripts/webui/web_server.py` | 注册三个 router |
| `static/js/prompt-skills.js` | **新增** 三个页面的前端逻辑 |
| `static/css/09-prompt-skills.css` | **新增** 三页共用样式 |
| `static/index.html` | 三个视图 + 三个导航入口 |
| `static/js/shell.js` | switchView 分发三个新视图 |
| `static/css/08-guoman.css` | **修 bug** `#view-guoman` → `#view-guoman.active` |

### 三个 skill 的独立性

| 层面 | 是否独立 |
|---|---|
| skill 目录 | ✅ 各自独立 |
| API 路由 | ✅ `/api/guoman-portrait/*`、`/api/moss-architect/*`、`/api/nsfw-templates/*` |
| 前端页面 | ✅ 三个 `view-*` |
| 导航入口 | ✅ 三个按钮 |
| LLM 调用 | 共用 `skill_common.llm_chat()`（同一端点，只是封装复用） |

只有最底层的 LLM 调用封装是共用的 —— 那本来就是同一个本地端点，没必要复制三份。
