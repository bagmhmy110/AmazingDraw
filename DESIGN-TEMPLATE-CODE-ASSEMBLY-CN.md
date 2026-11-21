# 模板 skill：纯代码拼装方案（设计稿，待确认）

> 目标：不走 LLM，用「中文句式 + 英文词条」拼出通顺提示词。
> 状态：**设计阶段，未改代码**。

---

## 一、词库重建（已完成）

### 原来的 bug

`build_nsfw_terms.py` 里有个函数：

```python
def looks_like_signal(s: str) -> bool:
    """判断是否英文信号词串 / 英文短语（提示词正文用中文，这类不要）。"""
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", s))
    if has_cjk:
        return False
    return True        # ← 全英文一律丢弃
```

原设计假设「提示词正文用中文」，于是**把所有英文词条全扔了**，
留下的是表格标签、章节标题、`❌ 只写 pussy → 太泛` 这类规则说明。

**这就是拼出来不通顺的根因** —— 不是拼装逻辑的问题，是词库根本就是垃圾。

### 重建结果

改成保留英文、过滤中文说明后，抽出 **11588 条**：

| 槽 | 条数 | 样例 |
|---|---|---|
| 场景主题 | 1856 | `bedroom` `love hotel` `crowded elevator` |
| 姿势动作 | 1436 | `kneeling` `back against wall` `ass in air` |
| 服装专项 | 1316 | `cheongsam` `nurse uniform with open chest` |
| 纹身标记 | 1215 | `realistic tattoo` `ink embedded in dermis` |
| 妆容专项 | 1082 | `dewy foundation` `glass skin` |
| 裸露液体 | 956 | `fully clothed` `cleavage visible through collar` |
| 瑕疵细节 | 835 | `asymmetrical labia` `chipped nail polish` |
| 表情眼神 | 699 | `shy expression` `sultry gaze` `drool from corner of mouth` |
| 景别构图 | 631 | `extreme close-up` `POV` `oppressive framing` |
| 光影氛围 | 402 | `rim light` `golden hour light` |
| 道具宠物 | 403 | `magic wand vibrator` |
| 风格胶片 | 379 | `cinematic film still` `polaroid snapshot` |
| 发型饰品 | 377 | `pixie cut` `messy bun` |
| 人格卡片 | 1 | `chiropractor` |

---

## 二、颗粒度分析

按词性粗分，各槽主体都是名词短语：

| 槽 | 名词短语 | 动名词 | 长短语 | 其他 |
|---|---|---|---|---|
| 场景主题 | 1262 | 212 | 84 | 单词 257 |
| 景别构图 | 469 | 57 | 39 | 单词 42 |
| 服装专项 | 736 | 228 | 140 | 过去分词 155 |
| 姿势动作 | 390 | 650 | 117 | 单词 164 |
| 表情眼神 | 303 | 224 | — | 过去分词 66 |
| 妆容专项 | 840 | 90 | 63 | 过去分词 65 |

**关键观察**：
- 场景/景别/服装/妆容 → 以名词短语为主，容易套模板
- 姿势/表情 → 动名词多，需要「动作句式」
- 裸露/瑕疵 → 混杂状态描述

---

## 三、句式方案

### 分句结构（你要的「场景一句、人物一句、光影一句」）

```
第一句：场景 + 构图
第二句：人物 + 服装 + 裸露状态
第三句：光影 + 姿态 + 表情
```

### 各槽句式模板

| 槽 | 中文句式 | 填入 `bedroom` 的效果 |
|---|---|---|
| 场景主题 | `场景：{v}` | 场景：bedroom |
| 景别构图 | `构图：{v}` | 构图：extreme close-up |
| 服装专项 | `身着 {v}` | 身着 cheongsam |
| 裸露液体 | `裸露状态：{v}` | 裸露状态：cleavage visible through collar |
| 光影氛围 | `光影：{v}` | 光影：golden hour light |
| 姿势动作 | `姿态：{v}` | 姿态：kneeling |
| 表情眼神 | `表情：{v}` | 表情：shy expression |
| 风格胶片 | `风格：{v}` | 风格：cinematic film still |
| 妆容专项 | `妆容：{v}` | 妆容：dewy foundation |
| 发型饰品 | `发型：{v}` | 发型：pixie cut |
| 瑕疵细节 | `细节：{v}` | 细节：asymmetrical labia |
| 纹身标记 | `纹身：{v}` | 纹身：realistic tattoo |
| 道具宠物 | `道具：{v}` | 道具：magic wand vibrator |
| 人格卡片 | `身份：{v}` | 身份：chiropractor |

**输出效果**：

```
场景：bedroom，构图：extreme close-up。身着 cheongsam，裸露状态：cleavage visible through collar。
光影：golden hour light，姿态：kneeling，表情：shy expression。
```

优点：
- 结构清晰，一眼看出每个词是什么
- 英文词条原样保留（生图模型更认英文）
- 中文标签保证可读性

---

## 四、需要你确认的点

### 1. 「标签式」还是「自然句」

上面是**标签式**（`场景：bedroom`），信息密度高、不易出错。

另一种是**自然句**：

```
在 bedroom 里，以 extreme close-up 构图。身着 cheongsam，cleavage visible through collar。
golden hour light 下，kneeling，shy expression。
```

自然句更像人写的，但套模板时容易别扭（比如 `In waking up to sex` 就语法错）。

### 2. 动名词词条怎么处理

`姿势动作` 里 650 条是动名词（`reaching out while running`、`holding head`）。
套 `姿态：{v}` 会变成 `姿态：reaching out while running`，读起来还行。

但套自然句 `{v}的姿态` 就变成 `reaching out while running的姿态`，中英混杂很怪。

### 3. 「场景主题」槽里混着角色

抽样发现：`subordinate`（下属）、`stepsister`（继妹）、`invisible man`（透明人）其实是**角色**，不是场景。

要不要把这类单独拆成「角色」槽？

### 4. 输出语言

你选了「中文句式 + 英文词条」。那最终提示词是：

```
场景：bedroom，构图：extreme close-up。身着 cheongsam。
```

生图时直接把这句丢给模型，中英混排模型能理解（大部分模型支持）。

**但如果要投给只认英文的模型**（比如某些 SDXL 工作流），可能需要一个「纯英文输出」开关。

---

## 五、工作量估计

| 步骤 | 内容 | 预计 |
|---|---|---|
| 1 | 词库重建 | ✅ 已完成 |
| 2 | 定义 14 个槽的句式模板 | 30 分钟 |
| 3 | 实现 `compose_by_template()` | 1 小时 |
| 4 | 加「极速拼装 / LLM 润色」开关 | 30 分钟 |
| 5 | 前端加模式切换 + 结果展示 | 30 分钟 |
| 6 | 验证（对比两种模式输出） | 30 分钟 |

**总计约 3 小时**。

---

## 六、我的建议

**先做「标签式」**，理由：

1. 最稳，不会出现语法错误
2. 每个词的归属一目了然，方便你调试
3. 如果觉得太机械，再改成自然句只是换个模板的事

**动名词问题**：给姿势槽单独用一个模板 `{v}`（不加「姿态：」前缀），让它自成一句：

```
场景：bedroom，构图：extreme close-up。身着 cheongsam。
reaching out while running，表情：shy expression。
```

**角色混在场景里**：先不动，等你看实际输出再决定要不要拆。
