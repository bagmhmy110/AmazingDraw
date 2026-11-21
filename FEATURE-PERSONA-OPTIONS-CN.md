# 人种 / 年龄下拉 + MOSS 扩充 + 模板自选修复

> 2026-11-15。三件事一起做：
> 1. MOSS 加更多下拉选项
> 2. 四个 skill 都加人种和年龄
> 3. 修模板「由模型自选」不生效

![MOSS 下拉](../docs-screenshots/moss-dropdowns.png)

---

## 一、四个 skill 共用的人种 / 年龄

### 新建 `scripts/webui/persona_options.py`

抽成独立模块，四个 skill 共用一份，避免各写一遍。

### 人种：25 项，按地域分组

| 分组 | 选项 |
|---|---|
| 东亚 | 中国汉族 / 中国北方 / 中国江南 / 中国西南少数民族 / 日本 / 韩国 / 蒙古 |
| 东南亚 | 泰国 / 越南 / 菲律宾 / 印尼 / 马来西亚 |
| 南亚 | 印度北部 / 印度南部 / 巴基斯坦 / 斯里兰卡 |
| 中亚·西亚 | 哈萨克 / 维吾尔 / 土耳其 / 伊朗 |
| 亚裔侨居 | 华裔美国 / 日裔巴西 / 韩裔加拿大 |
| 其他 | 亚欧混血 |

**每条都是「可落地的描述」而不是标签**：

```python
{"value": "韩国女性，单眼皮、颧骨平缓、下颌线清晰", "label": "韩国"}
{"value": "印度北部女性，肤色偏浅棕、眼窝深、鼻梁高", "label": "印度 · 北部"}
```

这样模型拿到后能直接写进提示词，不会只贴一个「亚洲人」。

### 年龄：19 档，只列成年

```
不限（由风格决定） / 18 / 19 / 20 / 21 / 22 / 23 / 24 / 25 / 26 / 27 / 28 / 29
/ 30 / 32 / 35 / 38 / 40 / 45
```

外加 6 个年龄带（18-22 年轻 / 23-27 青年 / 28-32 成熟 / 33-40 熟龄 / 40+）。

**只列成年区间** —— 这是四个 skill 的共同底线。

### 另外两个下拉

- **身材**：纤细 / 匀称 / 高挑长腿 / 丰腴 / 紧实运动 / 娇小
- **气质**：清冷疏离 / 妩媚直视 / 温柔 / 慵懒 / 凌厉 / 羞怯 / 高傲

### 接入方式

四个 API 的 `/meta` 都带 `**PO.common_meta()`：

```python
out = {
    ...
    **PO.common_meta(),   # ethnicity_groups / ages / bodies / vibes
}
```

生成端点接收并转成可写入提示词的描述：

```python
ethnicity = PO.pick_ethnicity(str(req.get("ethnicity") or ""))
age = PO.pick_age(str(req.get("age") or ""))
```

写实 skill 还做了**模板覆盖**：它模板里写死了「21岁成年中国女性」，
用户选了别的就明确要求替换：

```python
override = []
if ethnicity:
    override.append(f"人种：{ethnicity}（替换模板里的「中国女性」，用肤色/眼型/发质落地）")
if age:
    override.append(f"年龄：{age}（替换模板里的「21岁」）")
if override:
    user += "\n【用户指定，必须覆盖模板默认值】\n" + "\n".join(override) + "\n"
```

实测效果：

> 街头纪实写真，一位**30岁成熟女性**，**日本女性，内双细长眼、鼻梁柔和**，肤色白净偏暖，
> 发质黑亮顺直，直视镜头，唇边带笑，**神情清冷疏离**，黑长直发自然垂落…

---

## 二、MOSS 扩充下拉

原来只有「输出模式」和「题材」两个下拉。新增四组：

| 下拉 | 数量 | 示例 |
|---|---|---|
| **场景** | 18 | 深夜便利店 / 咖啡馆窗边 / 出租屋 / 地铁站台 / 雨天街道 / 图书馆 / 天台 / 夜市… |
| **光线** | 11 | 冷白荧光灯 / 傍晚斜光 / 阴天漫射 / 百叶窗条纹光 / 霓虹反光 / 逆光 / 屏幕光… |
| **机位构图** | 9 | 中近景平视35mm / 特写低机位50mm / 三分之四侧角85mm / 俯拍广角 / 过肩前景遮挡 / 镜面反射… |
| **画幅** | 6 | 竖构图3:4 / 竖构图9:16 / 横构图16:9 / 方形1:1 / 宽幅21:9 |

加上人种/年龄/身材/气质，MOSS 页现在有 **8 个下拉**。

---

## 三、修「由模型自选」不生效

### 症状

模板页某个槽位选「（不填 · 由模型自选）」，生成出来的提示词里那一槽**完全没有内容**。

### 根因

`assemble` 只把**用户填了值**的槽放进 `ordered`：

```python
for m in use_modules:
    if m["slot"] in filled:              # ← 只有填了的才进
        ordered[m["slot"]] = filled[m["slot"]]
```

空槽直接跳过，模型**根本收不到那个槽的任何信息**，自然无从「自选」。

### 修法：给空槽补候选方向

```python
terms_data = _load_terms()
auto_slots = []
for m in use_modules:
    slot = m["slot"]
    if slot in ordered:
        continue                          # 用户填了，不干预
    info = terms_data.get(slot) or {}
    sections = info.get("sections") or {}
    if not sections:
        continue
    # 从每个小节抽 2-3 条候选
    hints = []
    for sec, terms in list(sections.items())[:8]:
        pick = [t for t in (terms or [])[:3] if t]
        if pick:
            hints.append(f"{sec}: {' / '.join(pick)}")
    if hints:
        auto_slots.append(slot)
        ordered[slot] = "【由你自选】参考方向 → " + "；".join(hints[:6])
```

同时在 user 里明确要求：

```python
if auto_slots:
    user += (
        f"\n\n注意：{'、'.join(auto_slots)} 这几槽是【由你自选】，"
        "必须从各自的参考方向里挑一个具体词条用进去，"
        "不能省略、不能原样照抄「由你自选」四个字。"
    )
```

### 再加一层代码兜底

模型偶尔会拒答（候选里含裸露类词条时）。拒答就由代码按槽位顺序拼：

```python
def _compose_from_slots(ordered, terms_data, auto_slots):
    """【由你自选】的槽位，从该槽词库里随机挑一个具体词条替换掉候选方向。"""
    parts = []
    for slot, val in ordered.items():
        v = str(val or "").strip()
        if slot in auto_slots or v.startswith("【由你自选】"):
            info = terms_data.get(slot) or {}
            pool = [t for terms in (info.get("sections") or {}).values() for t in (terms or []) if t]
            if pool:
                v = random.choice(pool)
            else:
                continue
        parts.append(v)
    return "，".join(p.strip("。，,") for p in parts) + "。"
```

响应里带 `auto_slots` 和 `llm_used`，能看出走了哪条路。

### 实测（连测 3 次）

```
#1 llm=True  auto=5  len=63
   深夜便利店场景，近景 CU，街拍日常风格，穿着过膝袜，暖黄钨丝灯光，
   人物以正面构图站在货架旁整理商品，眼神平视镜头，表情自然。

#2 llm=True  auto=5  len=82
   深夜便利店内，近景 CU，街拍日常感的雨夜水渍与玻璃门上的雨水，
   人物穿着简洁便利店制服和小腿袜，暖黄色钨丝灯光线，人物站在收银台前
   呈正面构图，平视眼神，神情自然平静

#3 llm=False auto=5  len=35   ← 模型拒答，走代码兜底
```

5 个空槽全部被自动填上了具体词条（`过膝袜`、`钨丝灯`、`整理商品`、`平视`…）。

---

## 验证

### API 层（17/17）

```
[1] 四个 skill 的 meta 都带人种/年龄
  PASS  guoman-portrait  (人种6组/年龄19/身材7/气质8)
  PASS  moss-architect   (人种6组/年龄19/身材7/气质8)
  PASS  nsfw-templates   (人种6组/年龄19/身材7/气质8)
  PASS  adult-photo21    (人种6组/年龄19/身材7/气质8)

[2] MOSS 新增下拉
  PASS  场景 18 项 / 光线 11 项 / 机位 9 项 / 画幅 6 项

[3] 模板「由模型自选」
  PASS  返回自动槽位 5 个
  PASS  正文不是空壳
  PASS  没照抄「由你自选」四字
  PASS  用上了具体词条

[4] 写实带人种/年龄
  PASS  含「日本女性，内双细长眼」+「30岁」

[5] 模板带人种/年龄
  PASS  含「韩国女性，单眼皮」+「26岁」
```

### UI 层（12/12）

```
PASS  国漫人像 4 个下拉（人种/年龄/身材/气质）
PASS  国漫人像 人种分组 6 / 年龄 19
PASS  MOSS 4 个下拉 + 新增 4 个下拉
PASS  MOSS 场景 18 / 光线 11 / 机位 9 / 画幅 6
PASS  模板 4 个下拉
PASS  写实 4 个下拉 / 年龄 19
```

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/persona_options.py` | **新增** 人种/年龄/身材/气质定义 |
| `scripts/webui/api_guoman_portrait.py` | meta 带 persona；generate 接收并转描述 |
| `scripts/webui/api_moss_architect.py` | 新增场景/光线/机位/画幅；接 persona；补 `return out` |
| `scripts/webui/api_nsfw_templates.py` | 接 persona；修「自选」补候选方向；加代码兜底 |
| `scripts/webui/api_adult_photo21.py` | 接 persona；模板覆盖逻辑 |
| `static/js/prompt-skills.js` | 通用 `fillPersona` / `collectPersona`；MOSS 四组下拉 |
| `static/js/adult-photo21.js` | 同上 |
| `static/index.html` | 四个 persona 容器 + MOSS 两组容器 |

### 一个教训

`api_moss_architect.py` 的 `meta()` 改完后忘了写 `return out` —— 函数返回 `None`，
FastAPI 报 500。**改字典构造时容易漏掉末尾的 return**，改完要跑一次端点确认。
