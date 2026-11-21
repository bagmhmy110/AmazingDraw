# WebUI 出图延迟 —— 根因与修复

> 2026-11-15。症状：ComfyUI 里图早就出来了，WebUI 要等很久才显示。

---

## 根因：引擎在**错误的目录**里死等 60 秒

配置里 `output_dir` 和 ComfyUI 实际落盘目录**不是同一个**：

```
output_dir     : C:\Users\bagmh\Downloads\card-engine-out    ← 引擎去这里找
comfyui output : I:\ComfyUI-aki-v2\ComfyUI\output            ← ComfyUI 写这里
```

`wait_for_result()` 只看 `output_dir`，找不到就一直等。代码里有个「搜救」兜底，
但要**满 60 秒**才触发：

```python
if seen_outputs_without_file and (time.time() - outputs_seen_at) > 60:
    comfy_output = os.path.join(COMFYUI_DIR, "output")
    # 才开始去真正的地方找
```

所以每张图都白等 60 秒，然后搜救找到图，再拷回来。

### 实测日志（修复前）

```
✅ PID: 7b93b38e-...
  ⏳ 60s...
⚠️ 主输出目录 60s 未出现文件，触发搜救，搜索 ComfyUI 本地目录...
✅ [搜救] Moss50_00022_.png
```

`⏳ 60s...` 那行就是纯浪费。

---

## 另外两个拖慢点

### 轮询间隔 10 秒

```python
time.sleep(10)   # 出图后最多要等 10 秒才被发现
```

本地 `/history/{pid}` 接口调用成本近乎为零，10 秒纯属浪费。

### 交付前 30 秒「冷却」

```python
wait_for_result(...)
print("\n⏸️  冷却 30s...")
time.sleep(30)      # ← 出完图先睡 30 秒，然后才交付
return
```

这个冷却在**交付之前**，纯粹推迟 WebUI 看到图的时间。队列串行本来就由
`cu-queue` 管，这里再睡没有任何意义。

---

## 修复

### 1. 同时盯两个目录（`cu-draw-card.py`）

```python
comfy_output_dir = os.path.join(COMFYUI_DIR, "output")
search_dirs = [output_dir]
if os.path.abspath(comfy_output_dir) != os.path.abspath(output_dir):
    search_dirs.append(comfy_output_dir)
```

检测出图时两个目录都查，谁先有就用谁：

```python
found_path = None
for base in search_dirs:
    cand = os.path.join(base, name)
    if os.path.exists(cand):
        found_path = cand
        break
```

### 2. 轮询 10s → 1s（可配）

```python
poll_interval = float(os.environ.get("CU_WAIT_POLL") or 1.0)
...
time.sleep(poll_interval)
```

### 3. 搜救延迟 60s → 3s（可配）

```python
rescue_after = float(os.environ.get("CU_RESCUE_AFTER") or 3.0)
if seen_outputs_without_file and (time.time() - outputs_seen_at) > rescue_after:
```

### 4. 删掉交付前 30 秒冷却

```python
wait_for_result(pid, output_dir, prefix, done_file=done_file)
# 冷却放在交付之后无意义：交付（含卡片回写）应立刻进行，
# 让 WebUI 尽快看到成品。队列串行由 cu-queue 负责。
return
```

### 5. DONE marker 目录改为跟随 `done_file`

原来硬编码 `os.makedirs("/tmp/cu-card")`，Windows 上会落到 `C:\tmp\cu-card`，
与配置的 `tmp_dir` 不一致：

```python
os.makedirs(os.path.dirname(done_file) or ".", exist_ok=True)
```

---

## 效果

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 提交返回 | 1.6 s | **1.8 s** |
| 出图 → 发现 | 60 s 白等 | **< 1 s** |
| 出图 → 交付 | +30 s 冷却 | **0 s** |
| **提交 → WebUI 可见** | **90 s+** | **23 s** |

修复后日志（`⏳ 60s` 和搜救都没了，直接命中）：

```
✅ PID: 24ff861c-...
✅ Moss50_00024_.png
📁 I:\ComfyUI-aki-v2\ComfyUI\output\Moss50_00024_.png
⏱️ 0min
✅ DONE marker found → start deliver
✅ 卡片完成态同步: v2 → ...json
DELIVER_RC=0
```

23 秒基本就是模型推理时间本身（MOSS 50 步），已经到硬件下限。

---

## 可调环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `CU_WAIT_POLL` | `1.0` | 轮询 ComfyUI history 的间隔（秒） |
| `CU_RESCUE_AFTER` | `3.0` | 主目录无文件后多久触发前缀搜救（秒） |

想更激进可以设 `CU_WAIT_POLL=0.5`。

---

## 顺带说明：`output_dir` 到底该配什么

现在 `output_dir` 是 `C:\Users\bagmh\Downloads\card-engine-out`，
而 ComfyUI 写 `I:\ComfyUI-aki-v2\ComfyUI\output`。

**两个都保留是合理的**：
- `comfyui_dir/output` 是 ComfyUI 自己的工作目录（995 个历史文件）
- `output_dir` 是引擎侧「新图落点」，搜救会把新图拷过去

但如果想省掉拷贝，把 `output_dir` 直接设成 ComfyUI 的 output 也行 ——
`search_dirs` 会自动去重，不会重复查。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/gpu-pipeline/cu-draw-card.py` | 双目录检测、轮询 1s、搜救 3s、删冷却、done 目录修正 |

`card_engine_core/gpu-pipeline/` 副本已同步。
