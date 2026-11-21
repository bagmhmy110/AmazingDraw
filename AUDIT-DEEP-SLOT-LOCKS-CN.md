# 深度槽位审计：130/132 稳定，0 失效

> 2026-11-16。每项跑 **3 次**（不是 1 次），排除「碰巧通过」。
> 又挖出 **2 个真 bug**。

---

## 最终结果

| Skill | 单次 | 批量 |
|---|---|---|
| 国漫立绘 | **11/11** | **11/11** |
| 国漫人像 | 10/11 | **11/11** |
| MOSS | 8/9 | **9/9** |
| 模板 | **19/19** | **19/19** |
| 写实摄影 | **5/5** | **5/5** |
| 厚涂御姐 | **11/11** | **11/11** |

**总计 132 项：稳定 130 / 不稳定 2 / 失效 0**

剩下 2 项是 LLM 单次输出的偶发波动（同一项手工跑 5 次全中），不是代码问题。

---

## 为什么单次审计不够

上一轮跑 1 次得到 130/132，看起来还行。
这轮每项跑 3 次，暴露出 **5 项不稳定 + 1 项失效** —— 单次测试时它们碰巧通过了。

**有随机逻辑的代码，必须跑多次。**

---

## 新挖出的 2 个真 bug

### Bug 1：写实批量 `pose`/`light` 只有 1/3 生效

**症状**：批量 2 条时，只有第 1 条带用户选的姿态/光线，第 2 条完全没有。

**根因**：`_build_fill_prompt` 在 `count > 1` 时给 LLM 的指令是：

```python
p += f"\n写 {count} 条，换姿态/服装/地点，每条一行，格式 `1. 正文`。"
```

**「换姿态」直接让 LLM 忽略用户锁定的 pose。**

**修法**：只允许在**没锁**的维度上变化

```python
locked_names = [
    n for n, v in (("姿态", pose), ("光线", light), ("镜头", shot), ("地点", subject)) if v
]
free_names = [
    n for n, v in (("姿态", pose), ("服装", ""), ("地点", subject),
                   ("光线", light), ("镜头", shot)) if not v
]
vary = "、".join(free_names) if free_names else "细节措辞"
p += f"\n写 {count} 条，只在这几个维度上做差异：{vary}。"
if locked_names:
    p += f"\n用户指定的 {'、'.join(locked_names)} 每一条都必须原样体现，不能变化。"
p += "\n每条一行，格式 `1. 正文`。"
```

**验证**：从 0/3 和 1/3 → **6/6 全中**。

### Bug 2：`_compose_locally` 只有调用没有定义

`api_adult_photo21.py` 里两处调用：

```python
if not llm_ok:
    parts = [_compose_locally(fill_style, subject, shot, light, pose, extra) for _ in range(count)]

# 一条都没解析出来（LLM 给了拒答或格式乱）→ 代码拼装兜底
if not items:
    parts = [_compose_locally(fill_style, subject, shot, light, pose, extra) for _ in range(count)]
```

但全项目搜不到 `def _compose_locally` —— **LLM 一旦拒答就 `NameError`**。

**修法**：补上定义

```python
def _compose_locally(
    style: str, subject: str, shot: str, light: str, pose: str, extra: str,
) -> str:
    """纯代码拼一条（LLM 失败或拒答时的兜底）。"""
    import random as _rnd

    pool = _FILL_POOLS.get(style, _FILL_POOLS["editorial"])
    v = {k: _rnd.choice(vals) for k, vals in pool.items()}

    # 用户指定项覆盖（这是锁词能生效的关键）
    if pose:
        v["pose"] = pose
    if light:
        v["light"] = light
    if shot:
        v["tail"] = f"{shot}，{v['tail']}"
    if subject:
        v["env"] = f"{subject}，{v['env']}"

    text = _FILL_TEMPLATE.format(**v)
    if extra:
        text = text.rstrip("。") + f"，{extra}。"
    return text
```

**验证**：

```
一位21岁成年中国女性，五官精致优雅，深棕卷发垂肩。身着黑色贴身连衣裙，深V领口。
妩媚回眸，直视镜头。梳妆台上摆着口红、镜子和首饰盒。背景是木质床头和半掩的窗帘。
屋里自然光，很平，正面平视，35mm，全身，一双修长的长腿从裙摆下延伸到画面边缘。

✅ 含回眸  ✅ 含自然光  ✅ 含35mm
```

---

## 排除的 4 个「假失效」

深度审计报了 6 项，其中 4 项是**断言口径问题**：

| 项 | 审计报的 | 实际 | 原因 |
|---|---|---|---|
| 国漫人像 `light` | 1/3 | 3/3 | LLM 用「薄雾」「清晨晨雾」变体 |
| 国漫人像 `outfit_cat` | 1/3 | 9/9 | probe 用了桶内某一件，实际随机抽别的旗袍 |
| MOSS `vibe` | 2/3 | 3/3 | LLM 改写为「神情疏离」「倦怠的疏离」 |
| 写实 `pose` | 0/3 | 真 bug | 见上面 Bug 1 |

### `outfit_cat` 的断言怎么修

**错误做法**：用桶内第一件当 probe

```python
bucket = outfits.get("传统旗袍") or []
s = bucket[0]   # 「浅青立领紧身旗袍，领口盘扣，高开叉至大腿根部」
pr = frags_of(s.get("value"))
# 实际随机抽到「暗金滚边墨绿旗袍」→ 匹配失败
```

**正确做法**：用类别关键词

```python
CAT_KW = {
    "传统旗袍": ["旗袍"], "迷你旗袍": ["旗袍"],
    "迷你礼裙": ["礼裙"], "迷你包臀裙": ["包臀"],
    "长款礼裙": ["礼裙"],
}
pr = CAT_KW.get(val) or [val]
```

---

## 审计方法论

### 三档判定

| 状态 | 含义 | 处理 |
|---|---|---|
| **stable** | 3/3 全中 | ✅ 通过 |
| **unstable** | 1-2/3 中 | ⚠️ 手工复查 |
| **fail** | 0/3 全不中 | ❌ 真 bug |

### 为什么要跑 3 次

```
写实批量 pose：
  第1轮 ['1/2']  ← 第1条有，第2条没有
  第2轮 ['1/2']
  第3轮 ['1/2']
```

单跑一次看到 `1/2`，可能以为是断言太严（批量时部分命中算过）。
跑 3 次发现**每次都是同样的 1/2** → 稳定复现 → 真 bug。

### 断言要贴合实际输出

LLM 输出会：
- 重排语序（「妩媚回眸，直视镜头」→「眼神妩媚直视镜头…侧身回眸撩人」）
- 拆开长串
- 数字转中文（18岁 → 十八岁）
- 用同义词（清冷疏离 → 疏离 / 倦怠的疏离）
- 换变体（晨雾晨光 → 薄雾 / 清晨晨雾）

**写死完整字符串匹配，会误报大量「无效」。**

---

## 审计脚本

两个脚本都在仓库：

```bash
cd J:\AmazingDraw

# 快速版（每项 1 次，约 10 分钟）
python scripts/audit-all-slots.py

# 深度版（每项 3 次，约 40 分钟，能发现不稳定项）
python scripts/deep-audit-slots.py
```

结果存 `docs-screenshots/deep_audit.json`。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/api_adult_photo21.py` | **补 `_compose_locally` 定义**；批量提示词改成只变未锁维度 |
| `scripts/audit-all-slots.py` | `outfit_cat` 用类别关键词判断 |
| `scripts/deep-audit-slots.py` | 同上 + 每项跑 3 次 + 宽松断言 |

---

## 累计修掉的 bug（两轮合计）

| # | Bug | 影响 |
|---|---|---|
| 1 | 国漫立绘批量 `shot` 不生效 | 选了没用 |
| 2 | 国漫立绘 `肩部` 被 `render_costume` 忽略 | 选了没用 |
| 3 | 国漫立绘 `腰部` 被腰饰挤掉 | 5 次中 2 次 |
| 4 | 国漫立绘 `leg=none` 报 400 | 直接报错 |
| 5 | 国漫人像批量完全不读选项 | 13 个参数全丢 |
| 6 | 国漫人像 `outfit_cat` 不生效 | 选了没用 |
| 7 | 厚涂批量完全不读槽位 | 9 个参数全丢 |
| 8 | 厚涂 `body`/`vibe` 前端有下拉没接线 | 三层都没通 |
| 9 | 厚涂批量 `shot` 不生效 | 选了没用 |
| 10 | MOSS 批量 `extra_style` 不生效 | 画风丢失 |
| 11 | MOSS 批量 `subject` 被当标签忽略 | 题材不体现 |
| **12** | **写实批量 `pose`/`light` 只有 1/3 生效** | **「换姿态」指令冲掉锁词** |
| **13** | **`_compose_locally` 未定义** | **LLM 拒答时 NameError** |
