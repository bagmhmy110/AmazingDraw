# 厚涂御姐：人种槽位不生效（已修）

> 2026-11-16。你说「厚涂不行」，我逐项排查，找到 `ethnicity` 这一项。

---

## 症状

厚涂页面有「人种」下拉（`ao-ethnicity`，25 项），但选了不生效 ——
输出永远是「精致的东方面容」，不带人种。

---

## 根因：三层都没接

### 1. 前端没传

单次 payload：

```javascript
const payload = {
  style, age, temper, hair, category, outfit, stockings,
  sexy, pose, scene, shot, light,
  body: $("ao-body")?.value || "",
  vibe: $("ao-vibe")?.value || "",
  // ← 没有 ethnicity
  include_cultivation, seed,
};
```

批量 payload 同样没有。

### 2. 后端没读

`api_anime_oneesan.py` 的 `generate()` 里完全没有 `ethnicity`：

```
$ grep -n "ethnicity" api_anime_oneesan.py
129:        # 通用人种/年龄/身材/气质      ← 只有注释
```

meta 里有 `ethnicity_groups`（下拉数据来源），但生成时没用。

### 3. 拼句写死了

```python
body = f"身着{outfit_val}，{stockings}，精致的东方面容。{sexy}。{pose}。"
#                                  ↑ 写死的，人种永远是「东方」
```

---

## 修法

### 后端：拼句接上人种

```python
# 人种：原来「精致的东方面容」是写死的，选了人种也不体现
eth_val = str(req.get("ethnicity") or "").strip()
if eth_val and eth_val not in ("不限", "随机"):
    face = f"精致的东方面容，{eth_val}"
else:
    face = "精致的东方面容"

if stockings:
    body = f"身着{outfit_val}，{stockings}，{face}。{sexy}。{pose}。"
else:
    body = f"身着{outfit_val}，{face}。{sexy}。{pose}。"
```

### 后端：批量透传

```python
for _field in ("age", "temper", "hair", "sexy", "pose", "scene", "light",
               "body", "vibe", "ethnicity"):   # ← 加 ethnicity
    _val = str(req.get(_field) or "").strip()
    if _val and _val not in ("不限", "随机"):
        cmd += [f"--lock-{_field}", _val]
```

### `generate.py`：加 CLI 参数

```python
ap.add_argument("--lock-ethnicity", help="锁定人种描述")
```

```python
lock = {
    ...
    "ethnicity": getattr(args, "lock_ethnicity", None),
}
```

```python
_ethnicity = lock.get("ethnicity") or ""
_extra = "，".join(x for x in (_body_shape, _vibe, _ethnicity) if x)
```

### 前端：两个 payload 都补

```javascript
body: $("ao-body")?.value || "",
vibe: $("ao-vibe")?.value || "",
ethnicity: $("ao-ethnicity")?.value || "",   // ← 新增
```

---

## 验证

### 单次

```
1. ✅ 含「中国汉族女性」
   Wuthering Waves style二次元半写实厚涂，竖屏构图。25岁冷艳成熟女性，
   蜜桃色大卷长发，风情慵懒。身着藕粉迷你竹风旗袍，立领盘扣，短摆露脐，
   收腰，精致的东方面容，中国汉族女性。紧身包臀勾勒丰润腰臀曲线…

2. ✅ 含「中国汉族女性」
```

### 批量

```
1-1. ✅   1-2. ✅
2-1. ✅   2-2. ✅
```

### 厚涂全槽位（每项 3 次）

| 槽位 | 单次 | 批量 |
|---|---|---|
| age | 3/3 | 3/3 |
| temper | 3/3 | 3/3 |
| hair | 3/3 | 3/3 |
| sexy | 3/3 | 3/3 |
| pose | 3/3 | 3/3 |
| scene | 3/3 | 3/3 |
| light | 3/3 | 3/3 |
| body | 3/3 | 3/3 |
| vibe | 3/3 | 3/3 |
| shot | 3/3 | 3/3 |
| **ethnicity** | **3/3** | **3/3** |
| style | 3/3 | 3/3 |

**24/24 全部稳定生效。**

---

## 为什么之前的审计没发现

审计脚本从 `meta.bodies` / `meta.vibes` 取槽位值，但**人种是从 `meta.ethnicity_groups`（一个 dict）取的**，
我的脚本里这个结构处理有误，取出来是 dict 而不是字符串：

```
ethnicity = {'value': '中国北方女性，骨架偏大、脸型偏方', 'label': '中国 · 北方'}
```

传 dict 进去，后端 `.strip()` 失败或得到字符串化的 dict，自然匹配不上。

**教训**：审计脚本要覆盖**所有** meta 字段结构（list / dict / 嵌套 dict）。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/api_anime_oneesan.py` | `generate()` 接 ethnicity；批量透传加 ethnicity |
| `skills/anime-thickpaint-oneesan-prompts/scripts/generate.py` | 加 `--lock-ethnicity`；lock 字典 + 拼句 |
| `~/.dsh/skills/.../generate.py` | 同步 |
| `static/js/anime-oneesan.js` | 单次 + 批量 payload 补 ethnicity |
| `static/index.html` | `anime-oneesan.js?v=1.10.0` |

---

## 审计脚本

新加了厚涂专项脚本，可单独跑：

```bash
cd J:\AmazingDraw
python scripts/audit-anime-slots.py
```

覆盖 12 个槽位 × 2 模式 × 3 次 = 72 次请求。
