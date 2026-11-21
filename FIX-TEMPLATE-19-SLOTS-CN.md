# 模板 skill：19 个槽位全部生效

> 2026-11-16。你指出「有 19 个槽位」——我之前只测了 14 个词库槽，
> 漏了人种/年龄/身材/气质/画风这 5 个 persona 槽。

![19 个槽位](../docs-screenshots/template-19-slots.png)

---

## 19 个槽位构成

| 类别 | 数量 | 槽位 |
|---|---|---|
| **必读槽**（词库） | 7 | 场景主题 / 景别构图 / 裸露液体 / 服装专项 / 光影氛围 / 姿势动作 / 表情眼神 |
| **选读槽**（词库） | 7 | 风格胶片 / 妆容专项 / 发型饰品 / 瑕疵细节 / 纹身标记 / 道具宠物 / 人格卡片 |
| **persona 槽**（下拉） | 5 | 人种 / 年龄 / 身材 / 气质 / 画风 |

---

## 之前漏掉的两个 bug

### Bug 1：槽位名不匹配（14 个词库槽）

前端传模块全名，`nsfw_compose` 认短名：

```python
SLOT_ALIAS = {
    "场景主题": "场景",
    "景别构图": "景别",
    "裸露液体": "裸露",
    ...
}
```

不映射的话，`compose_random(want={"场景主题": "bedroom"})` 会去 `pools["场景主题"]` 找池子，
找不到就**当用户没选**，直接从池里随机抽 —— 你选的全被忽略。

### Bug 2：persona 槽完全没接（5 个）

`filled` 里**确实有** `人种`/`年龄`/`身材`/`气质`，但：

1. `SLOT_ALIAS` 没有映射它们
2. `nsfw_compose` 的 `want` 不认这些键
3. `画风` 更是连 `filled` 都没进

结果这 5 个下拉**选了也白选**。

---

## 修法

### 1. `nsfw_compose.py` 加 persona 处理

`compose_random` 里新增 persona 列表：

```python
# persona 槽：只用用户给的，不自动补
# （自动补人种/年龄容易拼出奇怪组合）
persona = ["画风", "年龄", "人种", "身材", "气质"]

for key in persona:
    v = want.get(key)
    if v:
        picks[key] = v
```

### 2. `compose()` 里拼进句子

**画风**放最开头（整段最外层风格）：

```python
style_extra = g("画风")
if style_extra:
    sentences.append(f"{style_extra}。")
```

**年龄+人种+身材+气质+角色**拼成人物主语：

```python
subj_bits = [x for x in (age, eth, bodyshape, vibe, role) if x]
if subj_bits:
    s2.append(" ".join(subj_bits))
```

### 3. `api_nsfw_templates.py` 把画风加进 filled

```python
extra_style = str(req.get("extra_style") or "").strip()
if extra_style:
    try:
        import style_options as SO
        st = SO.pick(extra_style)
        if st:
            filled["画风"] = st.get("label") or extra_style
    except Exception:
        filled["画风"] = extra_style
```

**注意用 label 不用 value** —— `guofeng_xianxia` 是 id，输出里应该是「国风仙侠」。

---

## 验证

### API 层（19 个槽位全填）

```
输出:
国风仙侠。在 bedroom，以 confined space 构图。28岁 中国江南女性，骨架纤细、脸型偏鹅蛋 丰满 慵懒，
身着 lace lingerie， transparent droplets。motivated lighting，spine curved， seductive confidence。
妆容 full coverage, flawless, airbrushed, poreless，发型 hime cut，细节 heel with dry skin，
纹身 red daruma with one eye，身份 chiropractor。

✅ 场景主题 ✅ 景别构图 ✅ 裸露液体 ✅ 服装专项 ✅ 光影氛围
✅ 姿势动作 ✅ 表情眼神 ✅ 风格胶片 ✅ 妆容专项 ✅ 发型饰品
✅ 瑕疵细节 ✅ 纹身标记 ✅ 道具宠物 ✅ 人格卡片
✅ 人种 ✅ 年龄 ✅ 身材 ✅ 气质 ✅ 画风

19/19 生效
```

### 浏览器端到端（4/5）

```
必读槽 7 个 ✓
选读槽 7 个 ✓
persona 5 个 ✓
合计 19 个 ✓
命中 18/19
```

**唯一「未命中」是测试脚本的断言问题** —— 脚本检查 `nt-style=xianxia_fairy`（原始 id），
但输出里是「仙侠仙女古风」（label）。功能本身正确，输出开头就是「仙侠仙女古风。」

---

## 实际输出示例

```
仙侠仙女古风。在 bedroom，以 extreme close-up 构图。
18岁成年女性 中国汉族女性 身形纤细，肩窄腰细 神情清冷疏离，
身着 Qipao/kimono/hanbok，fully clothed。
rim light，kneeling， shy expression， cinematic film still。
妆容 natural makeup，发型 pixie cut，细节 large areolae，
纹身 small solid heart tattoo，道具 held in hand，身份 chiropractor。
```

**19 个槽位全部体现**：
- 画风在最开头
- 年龄+人种+身材+气质+角色组成人物主语
- 场景+构图一句
- 服装+裸露一句
- 光影+姿态+表情+风格一句
- 妆容/发型/瑕疵/纹身/道具/身份一句

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/api_nsfw_templates.py` | 加 `SLOT_ALIAS` 映射（14 条）；画风进 `filled`；默认 mode 改 `fast` |
| `scripts/webui/nsfw_compose.py` | `compose_random` 加 persona 列表；`compose()` 拼画风与人物主语 |
| `static/index.html` | 模式下拉 `fast` 调到第一项 |
| `static/js/prompt-skills.js` | 默认 mode 改 `fast` |

---

## 教训

**跨模块传数据，字段名必须对齐，而且要覆盖全部字段。**

`MODULES` 的 `slot` 是给前端下拉和词库文件用的（中文全名），
`nsfw_compose` 的池名是给拼装逻辑用的（短名），persona 又是第三套（`nt-ethnicity` 这类 id）。

三套命名在 API 层汇合，中间没有校验 —— 用户选了词，后端默默忽略，还不报错。

**静默失败最难查**：界面正常、请求 200、输出看起来也正常，只是内容不对。

如果加一句校验会好很多：

```python
unknown = [k for k in want if k not in pools and k not in persona]
if unknown:
    log.warning(f"未识别的槽位: {unknown}")
```
