# 国漫立绘：去掉眉眼 / 眼眸 / 唇色描写

> 2026-11-15。国漫 · 服装装配与仙侠立绘 skill，提示词不再描述眉眼、眼眸、唇色。

---

## 改动

### 1. 面部句只剩「面容 + 肤质」

**`render_face()`（clean 版）** 原来拼 4 个组件：

```python
# 改前
face, skin, brow, eye, lip = p["面部"], p["肤质"], p["眉眼"], p["眼眸"], p["唇色"]
mods = [skin, brow, eye]
body = f"{tail}，{lip_ph}"
```

```python
# 改后
face, skin = p["面部"], p["肤质"]
return rng.choice([
    f"女子拥有{face}，{skin}",
    f"她有一张{face}，{skin}",
    ...
])
```

**`render_face_ccd()`** 同理。

### 2. 新增 `FACE_WORD_BLOCK` + `strip_face_words()`

```python
FACE_WORD_BLOCK = ("眉眼", "眼眸", "唇色", "唇形", "唇峰", "唇珠",
                   "嘴唇", "唇上", "唇线", "唇釉", "眼影", "眼线",
                   "眼妆", "眼窝", "眼尾", "卧蚕", "眉毛", "眉形", "眉峰")

def strip_face_words(text: str) -> str:
    """把描述眉眼/眼眸/唇的片段从逗号分隔的串里剔掉。"""
    parts = [p.strip() for p in re.split(r"[，、]", text) if p.strip()]
    keep = [p for p in parts if not any(w in p for w in FACE_WORD_BLOCK)]
    return "，".join(keep).strip("，、 ")
```

### 3. 挂到 `scrub()` —— 一处覆盖全部渲染路径

```python
def scrub(text: str) -> str:
    ...
    out = re.sub(r"[，、]{2,}", "，", out).strip("，、 ")
    # 所有渲染路径最终都过这里，统一剔掉
    return strip_face_words(out)
```

---

## 关键：残留来源不止面部句

改完面部句后还有残留，逐层排查才发现有三个来源：

| 来源 | 例子 | 修法 |
|---|---|---|
| **面部句** | `眉眼细长而上挑，眼眸泛着冷蓝微光，唇上淡雅粉红色` | 直接不拼这些组件 |
| **妆容句** | `底妆清透有光泽，眼尾压了一点深色，唇色裸棕` | `strip_face_words(p['妆容'])` |
| **姿态/动作句** | `嘴唇微张，像正要说什么` / `唇线绷着，不笑` | 最终 `scrub()` 统一过滤 |

第三个最隐蔽 —— 它藏在动作描写里，不是"面部描述"。

**所以最终方案是挂在 `scrub()` 上**，所有渲染路径（clean / ccd / real / sweet / hk80s / gauze）都过这里，一处改动全覆盖。

---

## 验证

### 六种渲染模式 × 12 seed

```
OK   clean   0/12 残留
OK   ccd     0/12 残留
OK   real    0/12 残留
OK   sweet   0/12 残留
OK   hk80s   0/12 残留
OK   gauze   0/12 残留
```

### WebUI API 端到端 × 5 seed

```
OK  seed0 len=356 残留=[]
OK  seed1 len=366 残留=[]
OK  seed2 len=377 残留=[]
OK  seed3 len=386 残留=[]
OK  seed4 len=362 残留=[]

违规 0/5
```

---

## 改前 vs 改后

**改前（clean）：**
> …她眼神清冷而专注地直视镜头，唇角微扬带着淡然知性的气质。**五官是精致秀雅的东方面容，眉眼细长而上挑，眼眸泛着冷蓝微光，唇上淡雅粉红色，肤若凝脂，肌肤细腻透亮。**深黑色长发…

**改后（clean）：**
> …她眼神清冷而专注地直视镜头，唇角微扬带着淡然知性的气质。**她有一张精致秀雅的东方面容，肤若凝脂，肌肤细腻透亮。**深黑色长发…

**改前（real）：**
> 骨相上，骨相立体，颧骨位置漂亮，下颌线清晰流畅，皮肤状态极好，透着一层薄薄的柔光，**唇形饱满，唇峰清晰，唇色深，眉毛浓密，眉形修得干净利落，眼睛狭长，眼尾微微上挑**，鼻子挺拔，鼻翼窄…

**改后（real）：**
> 骨相上，骨相立体，颧骨位置漂亮，下颌线清晰流畅，皮肤状态极好，透着一层薄薄的柔光，鼻背高，鼻尖微翘，侧面线条很漂亮。

---

## 保留了什么

- **眼神**：「她眼神清冷而专注地直视镜头」—— 这是氛围描写，不是眼型/眼妆描写，保留
- **唇角微扬**：属于表情/气质，不是唇色，保留
- **面部轮廓**：脸型、骨相、肤质、鼻形 —— 全部保留
- **发色发式、头饰、耳饰、颈饰、服装、场景、光影** —— 完全不动

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/promptforge.py` | `render_face()` / `render_face_ccd()` 去掉眉眼/眼眸/唇色组件；新增 `FACE_WORD_BLOCK` + `strip_face_words()`；`scrub()` 末尾统一过滤；`render_real()` / `render_sweet()` 的 `feat` 列表只留鼻形；妆容句套 `strip_face_words` |

### 影响范围

只影响 **portrait（立绘成稿）** 系列渲染。
`combo`（纯服装）和 `batch` 里服装模式不受影响 —— 它们本来就不写脸。
