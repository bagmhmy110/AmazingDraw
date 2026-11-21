# 直投图片和提示词对不上 —— 根因与修复

> 2026-11-15。症状：国漫生成的图，卡片显示的场景和画面内容不一致
> （如卡片写「道观」，图里是「戈壁」）。

---

## 排查结论：提示词本身是对的，错的是元数据

先逐一排除：

| 检查 | 结果 |
|---|---|
| 卡片里存的 prompt | ✅ 完整，和生成时一致 |
| ComfyUI 实际收到的 prompt | ✅ 和卡片里的一字不差 |
| 图片内容 vs prompt 描述 | ✅ **高度吻合**（银白发、凤凰发饰、火焰额饰、雪白淡金裙、露肩、高开叉、赤红戈壁、落日全对） |
| 卡片 `scene` 字段 | ❌ **写的是「道观」，实际画面是「戈壁」** |

所以不是「图跑偏了」，是**卡片的场景/调性元数据错位**，导致：
- 文件名错（`国漫立绘-道观-仙侠风.png` 里是戈壁）
- 归档命名错
- 你按卡片名去找图会对不上

---

## 根因：投递时用的是「当前下拉框」而非「这条提示词的真实场景」

### 问题代码（前端）

```javascript
// 单卡片的「生成图片」按钮，只带了 prompt
<button data-render="${esc(prompt)}">生成图片</button>

// doRenderPrompt 里回退读当前下拉框
const r = await apiPost("/direct", {
  prompt: text,
  tone: tone || $("guoman-tone")?.value || "仙侠",   // ← 下拉框可能已被改动
  scene: scene || $("guoman-scene")?.value || "",   // ← 同上
});
```

**场景 A**：生成时选「道观」→ 提示词里写死「道观前庭」→ 你去看别的、把下拉框改成「戈壁」→ 回头点这张卡的「生成图片」→ 卡片 scene 变成「戈壁」，但图还是道观。

**场景 B**：调性选「🎲 随机」→ 生成时抽到「仙侠」→ 投递时 `_resolve_random` **又抽一次** → 可能抽到「暗黑」，元数据直接错位。

### 关键认知

**提示词正文是出图的唯一依据。** 里面已经写死了真实场景：

```
…场景落在香火未绝的青石铺地的道观前庭，香炉青烟直上…
```

任何元数据都应该**从正文反推**，而不是相信调用方传来的值。

---

## 修复

### 1. 后端：正文反推 + 归一化

```python
def _normalize_scene(raw: str, pool: List[str]) -> str:
    """把反推出的场景描述归一化成标准场景 key。

    正文里是「香火未绝的青石铺地的道观前庭」，标准 key 是「道观」。
    按「key 出现在描述里」匹配，取最长匹配（避免「雪山」误配「雪寺」）。
    """
    s = (raw or "").strip()
    if not s:
        return ""
    if s in pool:
        return s
    hits = [k for k in pool if k in s]
    if hits:
        return max(hits, key=len)
    return s


def _infer_from_prompt(text: str) -> Dict[str, str]:
    """从提示词正文反推调性与场景。"""
    out = {"tone": "", "scene": ""}
    m_tone = re.search(r"^一位东方(.+?)风格的", text or "")
    if m_tone:
        out["tone"] = m_tone.group(1).strip()
    m_scene = re.search(r"(?:场景落在|背景为)([^，。]+)", text or "")
    if m_scene:
        s = m_scene.group(1).strip()
        # 去掉形容词前缀（「如梦似幻的」「香火未绝的」…）
        idx = s.rfind("的")
        if 0 < idx < len(s) - 1:
            s = s[idx + 1:]
        out["scene"] = s
    return out
```

投递端点改为**正文优先**：

```python
if given_prompt:
    prompt = given_prompt
    inferred = _infer_from_prompt(prompt)
    scene_pool = _scene_pool()
    # 正文优先；反推不到才用请求值 / 随机
    tone = (
        inferred["tone"]
        or (req_tone if req_tone and req_tone != RANDOM_TOKEN else "")
        or _resolve_random(req_tone, _DEFAULT_TONES)
        or "仙侠"
    )
    scene = (
        _normalize_scene(inferred["scene"], scene_pool)
        or (req_scene if req_scene and req_scene != RANDOM_TOKEN else "")
        or _resolve_random(req_scene, scene_pool)
        or "云海"
    )
```

### 2. 前端：按钮带上真实元数据

生成时把服务端返回的实际 tone/scene 存进按钮：

```javascript
const usedTone = result.tone || "";
const usedScene = result.scene || "";

<button data-render="${esc(prompt)}"
        data-tone="${esc(usedTone)}"
        data-scene="${esc(usedScene)}">生成图片</button>
```

`doRenderPrompt` 三级回退：

```javascript
// 优先级：按钮携带的元数据 > 从正文反推 > 当前下拉框
const inferred = inferFromPrompt(text);
const finalTone = (tone && tone.trim()) || inferred.tone || $("guoman-tone")?.value || "仙侠";
let finalScene = (scene && scene.trim()) || inferred.scene || $("guoman-scene")?.value || "";
```

### 3. 「生成并出图」不再二次抽签

原来是 `POST /direct`（服务端内部生成+投递），调性选随机时服务端会抽两次。
改成**先 `/portrait` 拿结果，再用结果里的 tone/scene 投递**：

```javascript
const gen = await apiPost("/portrait", collectPortraitPayload());
const r = await apiPost("/direct", {
  prompt: gen.prompt,
  tone: gen.tone || "",
  scene: gen.scene || "",
});
```

---

## 验证

### 反推与归一化（5/5）

```
生成 scene=道观  prompt 场景=香火未绝的青石铺地的道观前庭
投递（故意传 scene=戈壁）
  卡片 scene=道观
PASS  场景以正文为准，不被传入值污染

传 __random__ 时
  生成 scene=宫殿  卡片 scene=宫殿
PASS  __random__ 时用正文场景

PASS  反推 仙侠/云海     （「仙山云海」→ 云海）
PASS  反推 暗黑/废墟     （「石质废墟」→ 废墟）
PASS  反推 宫廷/道观     （「道观前庭」→ 道观）
```

### 归一化效果

| 正文描述 | 归一化后 |
|---|---|
| 如梦似幻的仙山云海 | `云海` |
| 沉在暗调里的石质废墟 | `废墟` |
| 香火未绝的青石铺地的道观前庭 | `道观` |
| 宫殿大殿 | `宫殿` |

---

## 教训

1. **不要把「界面当前状态」当作「这条数据的属性」。** 提示词生成后就是不变的事实，
   下拉框是可变的界面状态。二者必须解耦。

2. **随机参数不能抽两次。** 生成抽一次，投递必须复用那一次的结果，否则元数据和内容必然错位。

3. **正文是唯一真相源。** 元数据能从正文反推就反推，调用方传的值只作兜底。

4. **图片内容本身可能一直是对的**，只是标签错了。排查时先对比「prompt vs 图」，
   再对比「元数据 vs prompt」，能快速定位是渲染问题还是标签问题。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/api_guoman.py` | 新增 `_infer_from_prompt()` / `_normalize_scene()`；direct 端点正文优先 |
| `static/js/guoman.js` | 按钮带 tone/scene；新增 `inferFromPrompt()`；`doGenerateDirect` 不再二次抽签 |
