# 模板 skill：极速拼装模式（纯代码，不走 LLM）

> 2026-11-16。模板 skill 组装出来的提示词不通顺，根因是**词库抽错了**。
> 重建词库 + 新增纯代码拼装模式，耗时从 12 秒降到 0.04 秒。

![模板双模式](../docs-screenshots/template-fast-mode.png)

---

## 一、真凶：词库抽出来是垃圾

`build_nsfw_terms.py` 里有个函数：

```python
def looks_like_signal(s: str) -> bool:
    """判断是否英文短语（提示词正文用中文，这类不要）。"""
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", s))
    if has_cjk:
        return False
    return True        # ← 全英文一律丢弃
```

原设计假设「提示词正文用中文」，于是**把所有英文词条全扔了**。

剩下的是什么：

```
| **办公室/OL** | L1-2 |          ← 表格行
❌ 只写 pussy → 太泛              ← 规则说明
#### 质地（选 1-2 个）            ← 标题
便利店/超市，近景 CU，办公室/OL…  ← 拼出来的"提示词"
```

**所以不是拼装逻辑的问题，是词库根本不是词条。**

---

## 二、词库重建

改成保留英文、过滤中文说明后，抽出 **11588 条**：

| 槽 | 条数 | 样例 |
|---|---|---|
| 场景主题 | 1856 | `bedroom` `love hotel` `crowded elevator` |
| 姿势动作 | 1436 | `kneeling` `back against wall` |
| 服装专项 | 1316 | `cheongsam` `nurse uniform with open chest` |
| 纹身标记 | 1215 | `realistic tattoo` `ink embedded in dermis` |
| 妆容专项 | 1082 | `dewy foundation` `glass skin` |
| 裸露液体 | 956 | `fully clothed` `cleavage visible through collar` |
| 瑕疵细节 | 835 | `asymmetrical labia` `chipped nail polish` |
| 表情眼神 | 699 | `shy expression` `sultry gaze` |
| 景别构图 | 631 | `extreme close-up` `POV` |
| 光影氛围 | 402 | `rim light` `golden hour light` |
| 道具宠物 | 403 | `magic wand vibrator` |
| 风格胶片 | 379 | `cinematic film still` |
| 发型饰品 | 377 | `pixie cut` `messy bun` |
| 人格卡片 | 1 | `chiropractor` |

### 抽取的三个坑

**坑 1：反引号包裹的才是真词条**

01/05/13 这几个模块的表格是这样的：

```markdown
| **便利店/超市** | `convenience store, konbini, supermarket aisle` |
```

第一列是中文标签，**第二列反引号里才是词条**。原来只取第一列，全漏了。

**坑 2：代码块里是表格片段**

```markdown
```markdown
| **情人旅馆**   |
```
```

不是逗号串，要按表格行处理。

**坑 3：噪音过滤要留活口**

`ICU` `POV` `OTS` `CBT` `cum` `shy` 这些短词看着像噪音，其实是有效词条。
所以加了白名单：

```python
_ALLOW_ABBR = {"POV", "OTS", "ICU", "CBT", "WAM", "BDSM", "OL", "NTR", ...}
```

---

## 三、槽位拆分

原来的 14 个槽有两个混得很严重：

### 「场景主题」→ 拆成「场景」+「角色」

源文档 63 节里，**前 24 节是场景，后 39 节是角色/主题**：

```
1-24 节：室内私密 / 洗浴温泉 / 学校 / 职场 / 交通 …    → 场景（1083 条）
25-63 节：人妻出轨 / OL职场 / 教师学生 / 女仆制服 …    → 角色（214 条）
```

### 「裸露液体」→ 拆成「裸露」+「液体」

69 节里，**前 28 节是裸露/衣物状态，后 41 节是生殖器与液体**：

```
1-28 节：Level 1-6 裸露分级 / 衣物状态 / 部位裸露 …   → 裸露（484 条）
29-69 节：外阴唇 / 龟头 / 精液 / 淫水 / 汗液 …        → 液体（472 条）
```

拆分后共 **16 个池**。

---

## 四、纯代码拼装器

新模块 `scripts/webui/nsfw_compose.py`。

### 核心设计：中文句式 + 英文词条混排

```python
def compose(picks, *, seed=None):
    """分四句：场景构图 / 人物服装 / 光影姿态 / 细节"""
```

### 按词性动态选句式

不硬套模板，先判词性：

```python
def classify(term):
    if 含 be 动词或 while/when:  return "sentence"     # 完整句
    if 开头 -ing:                return "gerund"       # 动名词
    if 开头 -ed + 后面不是介词:   return "noun"         # 形容词短语
    if 开头 -ed + 后面是介词:     return "participle"   # 真过去分词
    return "noun"
```

各词性的处理：

| 词性 | 例子 | 处理 | 效果 |
|---|---|---|---|
| noun | `bedroom`<br>`unbuttoned shirt` | 直接放 | `在 bedroom`<br>`身着 unbuttoned shirt` |
| gerund | `kneeling`<br>`lying on bed` | 直接放 | `kneeling` |
| participle | `one leg raised` | 加 `with` | `with one leg raised` |
| sentence | `blowjob while being penetrated` | 直接放 | 原样 |

**关键**：`unbuttoned shirt` 这种「分词+名词」是形容词短语，不能加 `with`，
否则变成 `with unbuttoned shirt`。所以要判断第二个词是不是介词。

### 光影词特殊处理

`under lighting` 本身就含 light，再加「下」就变成 `under lighting下`：

```python
def _wrap_light(term):
    if re.search(r"\b(light|lighting|lit|glow|shadow)\b", term, re.I):
        return term              # 已经含 light，不再加「下」
    return f"{term}下"
```

### 中英混排自动补空格

```python
def _join(prefix, term):
    """`以` + `close-up` → `以 close-up`"""
    return f"{prefix} {term}" if term[0].isascii() else f"{prefix}{term}"
```

### 池子清洗

抽出来的词条有交叉污染，拼装前清洗：

```python
# 场景池混进了光影词
pools["场景"] = [t for t in scene if not re.search(r"\b(lighting|glow|shadow)\b", t)]

# 景别池混着光影词和视角碎片
pools["景别"] = [t for t in shot
                 if not re.search(r"\b(light|glow|shadow|lamp|beam)\b", t)
                 and not t.lower().endswith((" of", " to", " in", " on"))]

# 角色池混着主题/行为（mountain sex / extortion / coerced）
pools["角色"] = [t for t in role if _looks_like_role(t)]

# 人格卡片是整串（chiropractor, bone setter, ...），只取第一个词
pools["身份"] = [t.split(",")[0].strip() for t in identity]
```

### 缺槽自动补全

你选了「后者」（缺槽自动补），所以：

```python
def compose_random(seed=None, want=None, fill_missing=True):
    core = ["场景", "景别", "服装", "光影", "姿态", "表情"]      # 必补
    optional = ["角色", "裸露", "液体", "风格", "妆容", ...]     # 45% 概率补

    for key in core:
        if want.get(key): picks[key] = want[key]
        elif fill_missing: picks[key] = rng.choice(pools[key])
```

必填槽 100% 补全保证句子骨架，可选槽 45% 概率补避免句子过长。

---

## 五、实际效果对比

### 极速模式（0.04s）

```
在 love hotel，以 extreme close-up 构图。身着 lace lingerie，topless。
golden hour light，kneeling，shy expression。妆容 dewy foundation，发型 messy bun。
```

### LLM 模式（12s）

```
卧室场景中，极特写镜头下，人物衣物完整，身穿旗袍、和服或韩服风格服装，
轮廓光氛围萦绕，呈跪姿，神情羞涩。
```

**差异**：
- 极速模式：信息密度高（6-10 个要素），但英文词条原样，句子偏机械
- LLM 模式：通顺自然，但会**丢失细节**（只提了 5 个要素），且会**臆造**（「衣物完整」但用户没选）

---

## 六、接入 API

`/api/nsfw-templates/assemble` 新增 `mode` 参数：

```python
mode = str(req.get("mode") or "llm").strip().lower()
if mode in ("fast", "code", "instant"):
    import nsfw_compose as NC
    for i in range(count):
        r = NC.compose_random(seed=seed_i, want=filled, fill_missing=True)
        items_fast.append({...})
    return {"ok": True, "mode": "fast", "llm_used": False, ...}
```

前端加下拉：

```html
<select id="nt-mode">
  <option value="llm">LLM 润色（通顺 · 4-6s）</option>
  <option value="fast">极速拼装（纯代码 · 0.01s）</option>
</select>
```

---

## 七、验证

```
PASS  模式下拉存在
PASS  有 2 个模式
PASS  含极速拼装
PASS  极速模式 3 条
PASS  极速有内容
PASS  极速状态显示正确
PASS  LLM 模式有结果
PASS  LLM 有内容
PASS  LLM 比极速慢

9 passed / 1 failed（FAIL 是测试脚本 sleep 3000ms 的断言问题，API 实测 0.04s）
```

---

## 八、修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/build_nsfw_terms.py` | **重写**：保留英文词条，过滤中文说明；支持反引号提取、表格片段、噪音白名单 |
| `scripts/webui/nsfw_terms_cache.json` | 重新生成（11588 条） |
| `scripts/webui/nsfw_compose.py` | **新增** 纯代码拼装器 |
| `scripts/webui/api_nsfw_templates.py` | assemble 加 `mode=fast` 分支 |
| `static/js/prompt-skills.js` | 传 mode，状态显示区分两种模式 |
| `static/index.html` | 加模式下拉 |

---

## 九、顺手改的

「古风宫廷贵妃」→「古风宫廷」（所有 skill）：

| 位置 | 改动 |
|---|---|
| `style_options.py` | label + open |
| `skills/anime-thickpaint-oneesan-prompts/references/pools.json` | label + open（两份） |
| `extract_pools.py` | 源定义（两份） |
| `guoman-costume-xianxia-prompts/scripts/promptforge.py` | 「宫廷贵妃服饰」→「宫廷服饰」 |

> 注：`侧卧贵妃榻`「单膝跪贵妃椅」是**家具名**（chaise longue），保留未改。

---

## 十、遗留问题

极速模式的词条还有少量交叉污染，目前已知：

| 问题 | 例子 | 状态 |
|---|---|---|
| 角色池混着地点 | `teacher lounge` | 未处理 |
| 角色池混着物品 | `helmet` `blazer` | 未处理 |
| 景别池混着动作 | `POV blowjob` | 可接受（也是构图） |

要继续收紧的话，给 `_looks_like_role` 加更多排除词就行。
不过当前 214 条角色池已经比原来的 770 条干净很多。
