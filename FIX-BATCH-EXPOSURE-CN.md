# 批量生产不支持裸露范围 / 姿势

> 2026-11-15。症状：批量模式里选了「裸露范围」，生成出来的提示词完全没体现。

![批量模式](../docs-screenshots/guoman-batch-exposure.png)

---

## 根因：`cmd_batch` 没把参数传给 `build_portrait`

`promptforge.py` 的 `cmd_batch()` 里：

```python
p = build_portrait(d, rng, tone, scene, leg, render=args.render)
```

只传了 `tone / scene / leg / render`，**`pose` 和 `exposure` 完全没传**。
而且 `batch` 子命令的 argparse 里也根本没有这两个参数：

```python
p4.add_argument("--leg", default="mild", choices=["mild", "bold"])
p4.add_argument("--render", default="clean", ...)
# ← 没有 --exposure，没有 --pose
```

所以批量走的永远是默认 `exposure="none"`（全遮）。

---

## 修复

### 1. skill：batch 子命令加参数

```python
p4.add_argument("--exposure", default="none", choices=list(EXP.EXPOSURE_LEVELS),
                help="裸露范围：none 全遮 / half_covered 擦边 / upper 露上 / "
                     "lower 露下 / half_nude 半裸 / both 全裸")
p4.add_argument("--pose", default=None,
                help="指定姿势（动作或构图），留空按调性随机")
```

### 2. skill：`cmd_batch` 透传

```python
# 裸露范围与姿势透传给 build_portrait（批量里同样生效）
p = build_portrait(d, rng, tone, scene, leg, render=args.render,
                   pose=getattr(args, "pose", None),
                   exposure=getattr(args, "exposure", "none"))
```

### 3. 后端：batch 端点接受并透传

```python
exposure = _clean(req.get("exposure")) or "none"
pose = _clean(req.get("pose"))
args = [
    "batch", "-n", str(n), ...,
    "--leg", leg, "--render", render,
    "--exposure", exposure,
]
if pose:
    args += ["--pose", pose]
```

### 4. 前端：payload 带上 + 下拉不再隐藏

```javascript
// collectBatchPayload 里补两个字段
const exposure = $("guoman-exposure")?.value?.trim();
if (exposure) payload.exposure = exposure;
const pose = $("guoman-pose")?.value?.trim();
if (pose) payload.pose = pose;
```

`setMode` 原来在批量模式下隐藏了「露腿分级」，现在改为始终可见
（这三个参数在批量里都生效，藏起来反而让人以为不能用）：

```javascript
// 露腿分级 / 姿势 / 裸露范围 在批量下同样生效，保持可见
if (legField) legField.classList.remove("is-hidden");
```

---

## 验证

### CLI

```bash
python scripts/promptforge.py batch -n 3 --seed 42 \
  --tones 仙侠 --scenes 云海 --exposure upper
```

三条全部含「上身衣物已褪到腰际，胸前毫无遮挡，乳房自然垂坠」。

### API（11/11）

```
[1] 批量 + 各裸露档位
  PASS  none          无裸露信号  (3 条, 违规 0)
  PASS  half_covered  含「衣料被水汽浸透」  (3/3)
  PASS  upper         含「上身衣物已褪到腰际」  (3/3)
  PASS  lower         含「下身裙装已褪至脚踝」  (3/3)
  PASS  half_nude     含「衣襟已解开大半」  (3/3)
  PASS  both          含「全身赤裸」  (3/3)

[2] 批量 + 指定姿势
  PASS  指定姿势全部生效  (2/2)

[3] 批量 + 姿势 + 裸露组合
  PASS  姿势生效
  PASS  裸露生效
  PASS  两者共存

[4] 不传参数时默认全遮
  PASS  默认无裸露  (2 条, 违规 0)
```

### UI（7/7）

```
PASS  批量模式露出露腿分级
PASS  批量模式露出姿势
PASS  批量模式露出裸露范围
PASS  批量生成了 3 条
PASS  每条都含露上描述  (3/3)
PASS  每条都用指定姿势  (3/3)
PASS  状态显示成功
```

---

## 教训

**新增参数要检查所有调用路径。** 之前给 `portrait` 加了 `--exposure` / `--pose`，
但 `batch` 是独立的子命令和独立函数，漏了。

`build_portrait` 的签名有默认值（`exposure="none"`），所以漏传不会报错 ——
只是静默地用默认值。这类「有默认值所以不报错」的漏传最难发现。

排查方法：grep 所有 `build_portrait(` 调用点，逐个核对参数。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/promptforge.py`（skill） | batch 加 `--exposure` / `--pose`；`cmd_batch` 透传 |
| `scripts/webui/api_guoman.py` | batch 端点接受并透传 |
| `static/js/guoman.js` | `collectBatchPayload` 带两个字段；批量模式不隐藏三个下拉 |
