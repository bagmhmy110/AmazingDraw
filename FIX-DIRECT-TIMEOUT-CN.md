# 直投 30 秒超时 —— 根因与修复

> 2026-11-15。症状：WebUI 点直投，30 秒后报
> `Direct submit failed: Command [...cu-submit.sh...] timed out after 30 seconds`

---

## 根因：两次 LLM 调用串行阻塞提交

WebUI 直投的调用链上有**两次独立的 LLM 推理**，都是同步阻塞：

```
WebUI /api/direct/submit
  ├─ extract_card_info_via_llm()        ← LLM 调用 ①  实测 6.9s
  └─ cu-submit.sh
       └─ parse_prompt_meta.py          ← LLM 调用 ②  实测 9.5s
            （3 次重试 + 连接超时，最坏可达 30s+）
```

加上 enqueue / resume / spawn 的固定开销，实测 **28.3 秒**，正好压在 30 秒超时线上。

`subprocess.run(..., timeout=30)` 一超时，整个请求就失败了 —— 而此时
**任务其实已经入队**，只是 WebUI 拿不到 ACK。

---

## 实测耗时分解

| 步骤 | 耗时 |
|---|---|
| `python3 -c pass`（冷启动基线） | 83 ms |
| `amazingdraw_paths get` | 108 ms |
| `cu-queue clean-stale` | 144 ms |
| `cu-queue status` | 144 ms |
| `cu-queue avg-eta` | 121 ms |
| **`parse_prompt_meta`（含 LLM）** | **9513 ms** |
| **完整 `cu-submit.sh`** | **17002 ms** |
| **WebUI 直投全链路** | **28300 ms** |

LLM 单次调用（`hy4free` @ 127.0.0.1:7863）实测 **6.9 秒**。端点是在线的，
不是超时，是真实推理时间。

---

## 三处修复

### 1. `cu-submit.sh` — 默认跳过 LLM 元数据补全

```bash
# 直投/连抽是同步提交路径，LLM 元数据补全（单次 6~10s，带重试更久）
# 会把调用方顶穿超时。默认跳过；需要精细元数据时显式 CU_SKIP_LLM=0。
export CU_SKIP_LLM="${CU_SKIP_LLM:-1}"
```

`parse_prompt_meta.py` 相应支持：

```python
skip_llm = os.environ.get('CU_SKIP_LLM', '').strip() in {'1', 'true', 'yes'}
if missing_any and prompt:
    if not skip_llm and independent_llm_enabled("metadata"):
        ...  # LLM 路径
    else:
        inferred = offline_prompt_metadata(prompt)   # 离线启发式
```

离线启发式够用 —— 它只是给卡片取显示名，不影响出图。

### 2. `parse_prompt_meta.py` — 单次调用限时 25s

```python
response_text = chat_completion(
    messages, max_tokens=1024, timeout=25, feature="metadata"
)
```

防止按 `retry_limit: 3` 叠成分钟级。

### 3. `api_cards.py` — 提交超时改为可配置 120s

```python
try:
    _submit_timeout = float(load_system_config().get("direct_submit_timeout") or 120)
except Exception:
    _submit_timeout = 120.0
res = subprocess.run(cmd, ..., timeout=_submit_timeout)
```

### 4. `api_cards.py` — WebUI 侧也跳过 LLM

```python
# 直投是同步提交，HTTP 调用方有超时预算。
# 这里只为卡片取个显示名，用离线启发式足够；
# 要 LLM 精修时设 direct_llm_metadata=true。
try:
    if not load_system_config().get("direct_llm_metadata"):
        return fallback_data
except Exception:
    return fallback_data
```

---

## 效果

| 场景 | 修复前 | 修复后 |
|---|---|---|
| `cu-submit.sh` 单次提交 | 17.0 s | **1.8 s** |
| WebUI 直投全链路 | 28.3 s（超时） | **1.6 s** |

---

## 新增配置项

```json
"direct_submit_timeout": 120,    // 提交子进程超时（秒）
"direct_llm_metadata": false     // 直投时是否用 LLM 精修卡片显示名
```

要恢复「直投也用 LLM 起名」：把 `direct_llm_metadata` 设 `true`。
代价是每次直投多 ~7 秒，但仍在 120s 预算内。

要恢复「`cu-submit.sh` 也做 LLM 元数据」：调用前 `export CU_SKIP_LLM=0`。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/gpu-pipeline/cu-submit.sh` | 导出 `CU_SKIP_LLM=1` |
| `scripts/gpu-pipeline/parse_prompt_meta.py` | 支持 `CU_SKIP_LLM`；单次 LLM 限时 25s |
| `scripts/webui/api_cards.py` | 提交超时可配置；`direct_llm_metadata` 开关 |

`card_engine_core/gpu-pipeline/` 副本已同步。

---

## 排查这类问题的通用手法

同步提交路径上**任何 LLM 调用都是超时风险**。判断方法：

```bash
# 单独测每个 python3 子步骤
start=$(date +%s%N); python3 <step>; end=$(date +%s%N)
echo "$(( (end-start)/1000000 )) ms"
```

本例中 `parse_prompt_meta` 一个就占了 17 秒里的 9.5 秒 —— 一眼就能看出问题。
