# 修：模板 skill 选中的词条不生效

> 2026-11-16。在模板页选了词条，组装出来的提示词里一个都没用上。

![模板槽位修复](../docs-screenshots/template-slot-fixed.png)

---

## 根因：槽位名不匹配

前端传的是**模块名**，`nsfw_compose` 认的是**短名**：

| 前端传（来自 `MODULES`） | `nsfw_compose` 期望 |
|---|---|
| `场景主题` | `场景` |
| `景别构图` | `景别` |
| `裸露液体` | `裸露` / `液体` |
| `服装专项` | `服装` |
| `光影氛围` | `光影` |
| `姿势动作` | `姿态` |
| `表情眼神` | `表情` |
| `风格胶片` | `风格` |
| `妆容专项` | `妆容` |
| `发型饰品` | `发型` |
| `瑕疵细节` | `瑕疵` |
| `纹身标记` | `纹身` |
| `道具宠物` | `道具` |
| `人格卡片` | `身份` |

`compose_random(want=filled)` 收到 `{"场景主题": "love hotel"}` 后，
去 `pools["场景主题"]` 找不到这个池（池名是 `场景`），于是**当作用户没选**，
直接从池里随机抽 —— 你选的全被忽略。

---

## 修法：加映射表

```python
SLOT_ALIAS = {
    "场景主题": "场景",
    "景别构图": "景别",
    "裸露液体": "裸露",      # 原槽混着裸露与液体，优先当裸露
    "服装专项": "服装",
    "光影氛围": "光影",
    "姿势动作": "姿态",
    "表情眼神": "表情",
    "风格胶片": "风格",
    "妆容专项": "妆容",
    "发型饰品": "发型",
    "瑕疵细节": "瑕疵",
    "纹身标记": "纹身",
    "道具宠物": "道具",
    "人格卡片": "身份",
}

want: Dict[str, str] = {}
for k, v in filled.items():
    key = SLOT_ALIAS.get(k, k)
    if key not in want and str(v or "").strip():
        want[key] = str(v).strip()

r = NC.compose_random(seed=seed_i, want=want, fill_missing=True)
```

**先到先得** —— 同一目标槽已有值就不覆盖（比如先填「场景主题」又填「场景」）。

---

## 顺带：默认模式改成极速拼装

三处一起改：

| 位置 | 改动 |
|---|---|
| `index.html` | `<option value="fast">` 调到第一项 |
| `prompt-skills.js` | `$("nt-mode")?.value \|\| "fast"` |
| `api_nsfw_templates.py` | `req.get("mode") or "fast"` |

---

## 验证

### API 层（不传 mode）

```
耗时: 0.04s
实际模式: fast  llm_used: False
输出: 在 love hotel，以 extreme close-up 构图。honey，身着 lace lingerie。
      golden hour light，kneeling，shy expression。细节 one eyelid slightly different...

✅ love hotel
✅ extreme close-up
✅ lace lingerie
✅ golden hour light
✅ kneeling
✅ shy expression
```

**6 个选中的词全部出现。**

### 浏览器端到端（4/4）

```
槽位数: 7
  场景主题: 1857 项，首项=bedroom
  景别构图: 632 项，首项=extreme close-up
  裸露液体: 957 项，首项=fully clothed
  服装专项: 1317 项，首项=Qipao/kimono/hanbok
  光影氛围: 403 项，首项=rim light
  姿势动作: 1437 项，首项=kneeling
  表情眼神: 700 项，首项=shy expression

选中的 7 个词全部出现在输出里（7/7）

PASS  有槽位下拉
PASS  每个槽位有词条
PASS  极速模式有输出
PASS  选中的词全部出现（7/7）

4 passed / 0 failed
```

---

## 两种模式的分工

| 模式 | 行为 | 耗时 |
|---|---|---|
| **极速拼装**（默认） | 英文词条**原样保留**，中文连接词拼接 | 0.04s |
| LLM 润色 | 把英文词条**翻成中文**润色成通顺段落 | 4-6s |

LLM 模式实测会把 `convenience store` 变成「深夜便利店场景」——
语义对得上，但字面不同。这是刻意的润色行为，不是 bug。

**要 100% 忠实于你选的词，用极速模式。**

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/api_nsfw_templates.py` | 加 `SLOT_ALIAS` 映射；默认 mode 改 `fast` |
| `static/index.html` | 模式下拉 `fast` 调到第一项 |
| `static/js/prompt-skills.js` | 默认 mode 改 `fast` |
| `static/index.html` | `prompt-skills.js?v=1.16.0` |

---

## 教训

**跨模块传递数据时，字段名必须对齐。**

`MODULES` 里的 `slot` 是给前端下拉和词库文件用的（中文全名），
`nsfw_compose` 里的池名是给拼装逻辑用的（短名），两套命名没对齐，
中间也没有校验 —— 用户选了词，后端默默忽略，还不报错。

这种「静默失败」最难查：界面正常、请求成功、输出正常，只是内容不对。

**加校验会更好**：如果 `want` 里的 key 在池子里找不到，应该打日志警告。
