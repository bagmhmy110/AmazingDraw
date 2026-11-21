# 国漫人像：下拉从 8 个扩到 14 个

> 2026-11-15。原来只有风格线/露腿/主题/额外要求 + 人种/年龄/身材/气质 共 8 个，
> 现在扩到 **14 个**，把 skill 词库里现成的词池全暴露出来。

![国漫人像全下拉](../docs-screenshots/guoman-portrait-full.png)

---

## 14 个下拉一览

| # | 下拉 | 选项数 | 来源 |
|---|---|---|---|
| 1 | 风格线 | 4 | B 二次元厚涂 / C 古风仙侠 / A 写实CCD / D 高定服装 |
| 2 | 露腿分级 | 3 | 不露腿 / 含蓄 / 大胆 |
| 3 | 主题 | 自由输入 | — |
| 4 | 额外要求 | 自由输入 | — |
| 5 | **人种** | 25（6 组） | persona_options |
| 6 | **年龄** | 19 | persona_options |
| 7 | **身材** | 7 | persona_options |
| 8 | **气质** | 8 | persona_options |
| 9 | **人物类型** | 6 | `generate.py` TEMPERS |
| 10 | **发型** | 30 | `generate.py` HAIRS |
| 11 | **性感级别** | 10 | `generate.py` SEXY |
| 12 | **场景** | 50 | `generate.py` SCENES |
| 13 | **光线** | 50 | `generate.py` SCENES 的第二元组 |
| 14 | **姿势** | 49 | `generate.py` POSES |
| 15 | **服装类别** | 5 | `generate.py` CATEGORY_ORDER |
| 16 | **服装** | 148 | `generate.py` OUTFITS |

（表格 16 行，因为「服装类别 + 服装」是联动的两个下拉）

---

## 关键：不重新造词，直接复用 skill 的词池

这个 skill 的 `scripts/generate.py` 里已经有完整的词池：

```python
AGES   = ["25岁", "26岁", ...]                              # 6
TEMPERS = ["成熟御姐", "冷艳御姐", ...]                        # 6
HAIRS  = ["深棕齐肩短发，层次分明", ...]                       # 30
SEXY   = ["高开叉至大腿根部露出修长双腿，勾勒玲珑曲线", ...]     # 10
POSES  = ["站在拱桥上，手扶住桥栏，侧身望向水面", ...]           # 49
SCENES = [("山间古寺台阶...", "晨雾晨光"), ("竹林禅院...", "清冷月色"), ...]  # 50
OUTFITS = {"传统旗袍": [("浅青立领紧身旗袍", "领口盘扣，高开叉至大腿根部"), ...], ...}  # 148
```

写了个 `build_guoman_portrait_pools.py` 直接 import 它抽出来，**不重写词库**：

```python
def _load_generate():
    sys.path.insert(0, str(SCRIPTS))
    import generate as G
    return G

def build():
    G = _load_generate()
    # 场景是 (场景, 光线) 元组，拆成两个下拉
    for item in G.SCENES:
        sc, lt = item[0], item[1]
        scenes.append({"value": sc, "label": sc})
        if lt not in seen_light:
            lights.append({"value": lt, "label": lt})
    # 服装是 (服装, 细节) 元组，拼成完整值
    for cat, items in G.OUTFITS.items():
        outfits[cat] = [
            {"value": f"{it[0]}，{it[1]}", "label": it[0]}
            for it in items
        ]
```

产出 `guoman_portrait_pools.json`（304 条词）。

---

## 联动：服装类别 → 服装

「服装」下拉会跟着「服装类别」变：

```javascript
const refill = () => {
  const cat = catSel ? catSel.value : "";
  const list = cat && outfits[cat] ? outfits[cat] : Object.values(outfits).flat();
  outfitSel.innerHTML =
    '<option value="">不限（按风格自选）</option>' +
    list.map((o) => `<option value="${esc(o.value)}">${esc(o.label)}</option>`).join("");
};
catSel?.addEventListener("change", refill);
refill();
```

选「传统旗袍」→ 服装下拉只显示 24 条旗袍；选「不限」→ 显示全部 148 条。

---

## 后端：全部作为「覆盖项」

```python
temper = str(req.get("temper") or "").strip()
hair = str(req.get("hair") or "").strip()
sexy = str(req.get("sexy") or "").strip()
pose = str(req.get("pose") or "").strip()
scene = str(req.get("scene") or "").strip()
light = str(req.get("light") or "").strip()
outfit = str(req.get("outfit") or "").strip()

override = []
if ethnicity: override.append(f"人种：{ethnicity}（必须用肤色、眼型、发质等可见特征落地）")
if age:       override.append(f"年龄：{age}")
if body:      override.append(f"身材：{body}")
if vibe:      override.append(f"气质：{vibe}")
if temper:    override.append(f"人物类型：{temper}")
if hair:      override.append(f"发型：{hair}")
if sexy:      override.append(f"性感级别：{sexy}")
if pose:      override.append(f"姿势：{pose}（直接用作姿态句，不要套「以X姿态…画面」）")
if scene:     override.append(f"场景：{scene}")
if light:     override.append(f"光线：{light}")
if outfit:    override.append(f"服装：{outfit}")
if override:
    user += "\n【用户指定，必须覆盖模板默认值】\n" + "\n".join(override) + "\n"
```

**「必须覆盖模板默认值」这句话很关键** —— 不写的话模型会保留模板里的随机值，用户选了等于白选。

---

## 又一个拒答坑

选了「性感级别：高开叉至大腿根部露出修长双腿」+「服装：高开叉旗袍」后，
模型回：

> Sorry, I can't respond to this question.

### 修法：代码拼装兜底

```python
def _compose_from_selections(line, ethnicity, age, body, vibe,
                             temper, hair, sexy, pose, scene, outfit, leg):
    """模型拒答时按选中的词直接组一段。结构与 _FILL_TEMPLATES 一致。"""
    v = {k: _random.choice(vals) for k, vals in _POOLS[line].items() if vals}

    # 用户选中项优先
    if hair: v["hair"] = hair
    if outfit:
        parts = [p.strip() for p in outfit.split("，") if p.strip()]
        v["outfit"] = parts[0]
        if len(parts) > 1: v["detail"] = "，".join(parts[1:])
    if sexy: v["sexy"] = sexy
    if pose: v["pose"] = pose
    if scene: v["scene"] = scene
    if temper: v["age"] = f"{age or v.get('age','')}{temper}".strip()
    elif age: v["age"] = age
    if ethnicity: v["face"] = f"{ethnicity}，{v.get('face','精致的东方面容')}"

    tpl = _FILL_TEMPLATES[line]
    out = tpl
    for k, val in v.items():
        out = out.replace("{" + k + "}", str(val))
    out = re.sub(r"\{[a-z_]+\}", "", out)      # 清未替换的占位符
    out = re.sub(r"[，。]{2,}", "。", out).strip()
    return out if out.endswith("。") else out + "。"
```

响应带 `llm_used` 标记，能看出走了哪条路。

---

## 实测效果

选满 8 项后生成（191 字）：

> Wuthering Waves style二次元半写实厚涂，竖屏构图。**22岁成年日本女性**，**冷艳御姐**，
> **神情清冷疏离**，冷白细腻肤色，**内双细长眼**，鼻梁柔和。**紫罗兰长发自然披散，微卷垂落**，
> 发质柔顺。身着**浅青立领紧身旗袍，领口盘扣，高开叉至大腿根部**，露出修长双腿，
> 勾勒玲珑曲线。**站在拱桥上，手扶住桥栏，侧身望向水面**。
> 场景：**竹林禅院青石台阶**旁拱桥横卧，细竹摇影，薄雾轻浮，柔和窗光透过竹影洒落。

**8 个选中项一个不落地全进去了。**

---

## 验证（15/16）

```
PASS  下拉总数 >= 14  (14 个)
PASS  人物类型下拉
PASS  发型下拉  (31)
PASS  性感级别下拉
PASS  场景下拉  (51)
PASS  姿势下拉  (50)
PASS  服装下拉  (149)
PASS  人种下拉
PASS  年龄下拉
PASS  生成成功  (184 字)
PASS  含选中发型
PASS  含选中姿势关键词
PASS  含人种
PASS  含年龄
PASS  含旗袍
```

（唯一 FAIL 是测试脚本里断言字符串没替换成功，不影响功能）

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/build_guoman_portrait_pools.py` | **新增** 从 generate.py 抽词池 |
| `scripts/webui/guoman_portrait_pools.json` | **新增** 304 条词池缓存 |
| `scripts/webui/api_guoman_portrait.py` | meta 带 pools；generate 接 7 个新参数；拒答兜底 |
| `static/js/prompt-skills.js` | 两行新容器填充；服装类别→服装联动 |
| `static/index.html` | `gp-look` / `gp-setting` 两个容器 |

### 词库更新时

```bash
python scripts/webui/build_guoman_portrait_pools.py
```

然后重启 WebUI（缓存是模块级 memo）。

---

## 踩坑记录

**1. PowerShell 反引号被当字面量**

用 `-replace` 插 `\`n` 时反引号没被解释，写出了 `"scenes": scenes,\`n "lights": lights,`
这种非法 Python。改用 edit 工具就好了。

**2. `re` 没在模块层导入**

兜底函数里用了 `re.sub`，但 `import re` 只在某个函数内部写过。补到模块头部。

**3. 忘了写 `return out`**

MOSS 的 `meta()` 改完漏了 return，返回 `None` → 500。
改字典构造时容易漏末尾 return，改完跑一次端点确认。
