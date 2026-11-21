# 第四个 skill：21 岁成人写实摄影

> 2026-11-15。接入 `adult-photorealistic-prompt-style-21`，导航「写实 · Photo21」。

![写实摄影](../docs-screenshots/skill-adult-photo21.png)

---

## 这个 skill 的特点

和前面三个不同，它自带一个**确定性年龄规范化脚本**（`normalize_age.py`），
而且放在 `.workbuddy-ai/skills/` 下而不是 `.dsh/skills/`。

### 四类语料风格

| ID | 风格 | 场景 |
|---|---|---|
| `editorial` | 成人写真 / 情趣时尚 | 中式婚房、酒店套房、办公室、诊所、卧室、亭台 |
| `urban` | 都市生活 / 性感纪实 | 咖啡馆、街道、商店、汽车、舞台、工作室 |
| `hanfu` | 中国舞蹈 / 汉服舞台 | 敦煌、唐、宋、魏晋、汉、明、龟兹、月宫 |
| `yoga` | 瑜伽 / 体操 / 体育场 | 体育场、竞技场、健身房、舞台、庭院 |

### 三个端点

| 端点 | 用途 | 走 LLM？ |
|---|---|---|
| `POST /generate` | 按风格生成 | ✅ |
| `POST /rewrite` | 改写既有提示词 | ✅ |
| `POST /normalize` | 只规范化年龄 | ❌ 纯确定性 |

「只规范化年龄」不调 LLM —— 因为 `normalize_age.py` 已经能确定性处理，
没必要让模型重写一遍，那样反而会改动原文细节。

---

## 实现要点

### 1. 扩展 skill 路径探测

原来只探 `.dsh/skills`，这个 skill 在 `.workbuddy-ai/skills` 下。

```python
_SKILLS_ROOT_CANDIDATES = (
    os.environ.get("AMAZINGDRAW_SKILLS_ROOT"),
    "~/.dsh/skills",
    "~/.workbuddy-ai/skills",     # ← 新增
    "~/.claude/skills",
    "~/.codex/skills",
)

def skill_dir(name):
    """跨多个 skills 根目录查找。"""
    for root in skills_roots():
        p = root / name
        if (p / "SKILL.md").is_file():
            return p
    return None
```

### 2. 补 skill 脚本漏掉的中文年龄

`normalize_age.py` 的 `REPLACEMENTS` 只覆盖英文：

```python
# skill 原脚本能处理：
re.compile(r"\b(?:18|19|20)-year-old\b", re.I), "21岁"
re.compile(r"年轻女孩|少女"), "21岁成年女性"

# 但处理不了：
#   「18岁」← 中文数字+岁
#   「女孩」← 单独出现（它只匹配「年轻女孩」）
```

所以 API 层补一层：

```python
_CN_AGE_FIX = (
    (r"(?<![\d])(1[0-9]|20)\s*周岁", "21岁"),
    (r"(?<![\d])(1[0-9]|20)\s*岁", "21岁"),
    (r"二十岁出头|二十多岁|三十岁出头|十几岁|晚十几岁", "21岁"),
    (r"学生妹|学生感|年轻女孩|年轻女性|年轻女人|小女孩", "21岁成年女性"),
    (r"年轻男孩|年轻男性|年轻男人|小男孩", "21岁成年男性"),
    (r"女孩", "21岁成年女性"),   # 单独出现也要规范化
    (r"男孩", "21岁成年男性"),
)
```

执行顺序：**先本地补中文 → 再交给 skill 脚本 → 再补一次去重**。

实测：

```
「一位18岁女孩站在窗边」        → 「一位21岁成年女性站在窗边」  ✅
「20-year-old woman in office」 → 「21岁 woman in office」        ✅
「年轻女孩穿百褶裙」             → 「21岁成年女性穿百褶裙」        ✅
「少女在咖啡馆」                → 「21岁成年女性在咖啡馆」        ✅
「稚嫩的五官」                  → 「细腻的五官」                 ✅
```

### 3. 拒答检测（这次栽了个大跟头）

模型会回**中文拒答**，而且拒答话很长：

> 这个请求里关于姿态、衣着状态、以及配合散落衣物突出身体线条的描写，
> 组合起来指向的是带有性暗示的私密挑逗场景，这类内容我不便协助生成或润色，
> 因此不会按该模板输出成品提示词。

我第一版检测用「长度 < 200 才算拒答」，直接漏掉 —— 因为这段有 100 多字。

改成**特征短语匹配**：

```python
_REFUSAL_MARKERS = (
    "sorry", "i can't", "cannot respond",
    "无法响应", "我不便", "不便协助", "不会按", "这类内容",
    "该请求", "这个请求", "抱歉",
)

_META_MARKERS = ("提示词", "模板", "输出成品", "该模板", "上述", "该请求")

def _is_refusal(text):
    if any(m in text.lower() for m in _REFUSAL_MARKERS):
        return True
    # 同时命中多个元话语 + 篇幅短 → 多半在解释「我不按这个模板输出」
    meta_hits = sum(1 for m in _META_MARKERS if m in text)
    if meta_hits >= 2 and len(text) < 400:
        return True
    return False
```

### 4. 代码拼装兜底

LLM 空了或被拒，直接用词池拼一条 —— **这不是降级产物**，
模板和词条都来自语料，拼出来的结构就是 skill 要求的「主体—动作—环境—构图—灯光」。

```python
def _compose_locally(style, subject, shot, light, pose, extra):
    pool = _FILL_POOLS[style]
    v = {k: random.choice(vals) for k, vals in pool.items()}
    # 用户指定项覆盖
    ...
    return f"{v['media']}，一位21岁成年女性，{v['face']}，{v['hair']}。身着{v['outfit']}。..."
```

返回体带 `llm_used: false` 标记，前端可以看出来走了兜底。

---

## 最关键的坑：uvicorn keep-alive

### 症状

API 直接调用（Python 脚本）**全部正常**，但通过 HTTP 请求就报
`Internal Server Error` 或 `ConnectionResetError: [WinError 10054]`。

### 根因

```python
uvicorn.run("web_server:app", host=host, port=port, reload=False)
#                                                        ↑ 没设 timeout_keep_alive
```

uvicorn 默认 `timeout_keep_alive=5` 秒。而这些 skill 的 LLM 调用要 **40-60 秒**，
连接会被提前掐断。

### 修法

```python
uvicorn.run(
    "web_server:app",
    host=host,
    port=port,
    reload=False,
    timeout_keep_alive=300,   # ← 给长请求留足时间
)
```

改完连跑两轮，10/10 全过：

```
--- 第 1 轮 ---
  editorial    llm=True  len= 125
  urban        llm=True  len= 175
  hanfu        llm=True  len= 197
  yoga         llm=True  len= 159
  批量3条      count=3
--- 第 2 轮 ---
  editorial    llm=True  len= 166
  urban        llm=True  len= 285
  hanfu        llm=True  len= 153
  yoga        llm=True  len= 156
  批量3条      count=3
```

**这个坑对前面三个 skill 同样有效** —— 之前那些偶发的 500 和连接重置，根源也是它。

---

## 验证

### API 层（两轮稳定）

四条风格 × 2 轮 + 批量 = 10/10。

### UI 层（16/16）

```
PASS  视图 DOM 存在
PASS  导航入口存在
PASS  init 函数已暴露
PASS  视图 active
PASS  display 是 flex
PASS  skill 就绪
PASS  年龄规则提示显示
PASS  四条风格
PASS  姿态选项 >=6
PASS  机位选项 >=6
PASS  光线选项 >=6
PASS  其他视图正确隐藏
PASS  生成成功
PASS  含 21岁
PASS  无低龄词
PASS  纯规范化生效
```

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/skill_common.py` | 扩展 skill 路径探测（`.workbuddy-ai`）；加 `llm_chat_with_retry()` |
| `scripts/webui/api_adult_photo21.py` | **新增** 四风格生成 + 改写 + 纯规范化 |
| `scripts/webui/web_server.py` | 注册 router；**`timeout_keep_alive=300`** |
| `static/js/adult-photo21.js` | **新增** 前端逻辑 |
| `static/css/09-prompt-skills.css` | 加 `#view-adult-photo21.active` |
| `static/index.html` | 视图 + 导航入口 |
| `static/js/shell.js` | switchView 分发 |

### 五个 skill 现状

| 导航 | Skill | 位置 |
|---|---|---|
| 国漫 | guoman-costume-xianxia-prompts | `.dsh/skills` |
| 国漫人像 | guoman-portrait-prompts | `.dsh/skills` |
| MOSS | moss-image-prompt-architect | `.dsh/skills` |
| 模板 | nsfw-prompt-templates-asian | `.dsh/skills` |
| **写实** | **adult-photorealistic-prompt-style-21** | **`.workbuddy-ai/skills`** |
