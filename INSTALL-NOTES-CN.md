# AmazingDraw 安装记录（本机）

- 安装日期：2026-11-15
- 发行版：v0.1.21（`AmazingDraw-windows-cp312.zip`）
- 安装目录：`J:\AmazingDraw`
- Python：`J:\Python312\python.exe`（3.12.10，独立安装，未进系统 PATH 以免污染）
- 数据目录：`C:\Users\bagmh\.amazingdraw`
- 运行期配置：`C:\Users\bagmh\.amazingdraw\config.json`
- ComfyUI：`I:\ComfyUI-aki-v2\ComfyUI`（端口 8188）
- WebUI：`http://127.0.0.1:8318`

---

## 启动 / 停止

```bash
# 必须用 Git Bash
bash /j/AmazingDraw/scripts/webui/webui-start.sh start|stop|status|restart
bash /j/AmazingDraw/scripts/gpu-pipeline/comfyui-start.sh status
```

CLI：

```bash
cd /j/AmazingDraw
J:/Python312/python.exe scripts/card-engine/card_cli.py -h
```

---

## 已修的平台 bug（上游 Windows 未实机测试）

| # | 文件 | 问题 | 修法 |
|---|---|---|---|
| 1 | `gpu-pipeline/cu-queue.py` | `import fcntl` 在 Windows 直接 ModuleNotFoundError，整个队列系统不可用 | 新增 `_win_fcntl.py`（msvcrt.locking 实现 flock），try/except 回退 |
| 2 | `webui/webui-start.sh` | 裸 `bash` 被解析成 WSL 的 `C:\Windows\System32\bash.exe` → `execvpe(/bin/bash) failed` | 新增 `scripts/bash_resolver.py`，按 `git --exec-path` / 常见路径定位 Git Bash |
| 3 | `webui/webui-start.sh` | `python3` 在 Git Bash 里是 `#!/bin/bash` 包装脚本，`detached_spawn.py`（原生进程）无法 exec → WinError 193，日志空、启动超时 | 启动前用 `sys.executable` 解析成真实 `.exe` 路径 |
| 4 | `webui/webui-start.sh` | `collect_pids` 依赖 `pgrep`，Git for Windows 没有 | 回退 `ps -W` + `netstat -ano` 按端口反查 |
| 5 | `webui/webui-start.sh` | Git Bash 的 `kill` 管不了 Windows 原生 PID，`stop` 报成功但进程还在 | 改用 `taskkill //PID //F`，`pid_alive` 用 `tasklist` |
| 6 | `webui/webui-start.sh` | 配置路径内联进 `python -c`，反斜杠被当转义 → `truncated \UXXXXXXXX escape` | 改 argv 传参 + `encoding='utf-8'` |
| 7 | `gpu-pipeline/*.sh`（5 个） | 同样的反斜杠转义问题，共 12 处 | 新增 `scripts/cfg_get.py`（argv 传参），统一 `_cfg` 函数 |
| 8 | `gpu-pipeline/cu-worker.sh` | heredoc 里内插 `$RUNTIME_FILE` / `$META_FILE`，反斜杠崩 | 改环境变量传入 + heredoc 加引号 |
| 9 | `gpu-pipeline/cu-queue.py` | spawn worker 时直接 exec `.sh` → WinError 193 | 显式经 `bash_executable()` 启动 |
| 10 | `card-engine/card_cli_commands.py` 等 5 处 | `subprocess.run(..., text=True)` 无 encoding，Windows 按 GBK 解码 UTF-8 输出必崩 | 全部加 `encoding="utf-8", errors="replace"` |
| 11 | `card_cli_commands.py` | `result.stderr[:500]` 在 stderr 为 None 时 TypeError | 加 `or ""` 兜底 |
| 12 | 环境 | 控制台 GBK 输出 emoji 崩溃 | 设用户级 `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8` |

修改文件清单：

- 新增：`scripts/bash_resolver.py`、`scripts/cfg_get.py`、`scripts/gpu-pipeline/_win_fcntl.py`
- 修改：`scripts/gpu-pipeline/{cu-queue,cu-control,cu-worker,cu-submit,cu-deliver,cu-progress,comfyui-start}`
- 修改：`scripts/webui/{webui-start.sh,api_cards.py,api_queue.py}`
- 修改：`scripts/card-engine/card_cli_commands.py`
- 同步：`card_engine_core/` 下同名副本已一并更新

---

## 验证结果

| 项 | 状态 |
|---|---|
| WebUI 8318 | ✅ HTTP 200，start/stop/restart/status 全通 |
| CLI card_cli | ✅ `-h` / `workflow` / `search` / `progress` / `queue` 正常 |
| 词库加载 | ✅ 8 个场景库 + 角色库 + 明星库 + 桥段库 |
| ComfyUI 连接 | ✅ 8188 可达，节点齐全 |
| 队列系统 | ✅ `queue_store.ok = true`，GPU 锁正常 |
| 出图链路 | ✅ 已跑到 ComfyUI 提交（`prompt_outputs_failed_validation`） |
| 实际出图 | ❌ 缺模型（见下） |
| LLM 端点 | ❌ 8317 未起 |

---

## 待办：出图前必须补齐

### 1. 缺扩散主模型（三套工作流全缺）

| 工作流 | 需要的文件 | 放到 |
|---|---|---|
| `moss`（默认） | `Moody-Moss-Mix-V4.1_00001__clean-fp8.safetensors` | `models/diffusion_models/` |
| `krea` | `Moody-Krea-Mix-fp8.safetensors` | `models/diffusion_models/` |
| `zi` | `MoodyWildMix-zib-base.safetensors` + `MoodyRealMix-zit-write.safetensors` | `models/diffusion_models/` |

文本编码器与 VAE 都已就位（`qwen3.5_9b_int8_convrot` / `qwen3vl_4b_fp8_scaled` / `qwen_3_4b` / `flux2-vae` / `qwen_image_vae` / `ae`）。

### 2. LoRA 目录与文件名不匹配

工作流写死 `moss\MOSS-XG-EPOC10.safetensors`，本机是 `loras/Moss_image/Moss-8stepslora_latest.safetensors` 等。
明星 LoRA：本机 `loras/krea2 人物/girlslike_krea2_张嘉倪.safetensors`（50+ 人齐全），
引擎期望 `loras/girls_like_krea2/`。

### 3. LLM 端点（填槽 / 连抽需要）

默认 `http://127.0.0.1:8317/v1`，当前未启动。可：
- 起一个 OpenAI 兼容网关到 8317，或
- 改 `~/.amazingdraw/config.json` 的 `llm.base_url`

注意：直投（direct）不需要 LLM；只有「填槽 / 连抽」的导演决策需要。

### 4. 尺度开关（默认收着）

```json
"restrict_roles": true,
"exposure_limit": ["half_covered", "half_nude"]
```
