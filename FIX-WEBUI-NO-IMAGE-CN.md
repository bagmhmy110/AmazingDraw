# WebUI 看不到图 —— 根因与修复

> 2026-11-15 实测。图片一直生成成功，但 WebUI 卡片列表永远是空的。
> 一路挖下去是 **5 个串联的 bug**，修完才能看到。

---

## 症状

- `C:\Users\bagmh\Downloads\card-engine-out\` 里有图
- WebUI 卡片列表只有几条 `status: draft`、`render_image: null` 的空卡
- 队列里所有任务都是 `failed` / `worker_exit_1`

---

## 五个 bug（按发现顺序）

### 1. `cu-deliver.sh` — DONE 文件路径反斜杠转义

```bash
# 坏：
FILE=$(python3 -c "...open('$DONE_FILE')['file']")
# $DONE_FILE = C:\Users\bagmh\...\cu-draw-card-done_xxx.json
# Python 把 \U 当 unicode 转义 → SyntaxError: truncated \UXXXXXXXX escape
```

**修**：改为 argv 传参

```bash
_done_field() {
    python3 -c "import json,sys; print(json.load(open(sys.argv[1], encoding='utf-8'))[sys.argv[2]])" "$DONE_FILE" "$1"
}
FILE=$(_done_field file)
SEED=$(_done_field seed)
ELAPSED=$(_done_field elapsed_min)
```

### 2. `cu-deliver.sh` — Telegram 未配置时 `exit 1` 掐死整条交付链

```bash
# 坏：token 为空直接退出，后面的 WebUI 交付永远跑不到
if [ -z "$BOT_TOKEN" ]; then
    echo "❌ Bot token not found" >&2
    exit 1
fi
```

**修**：降级为跳过该通道

```bash
if [ "${DELIVERY_TELEGRAM:-1}" = "1" ]; then
    if [ -z "$BOT_TOKEN" ]; then
        echo "⚠️ 未配置 telegram_bot_token → 跳过 Telegram 交付，继续 WebUI" >&2
        DELIVERY_TELEGRAM=0
    fi
fi
```

### 3. `cu-deliver.sh` — `signal.SIGALRM` 在 Windows 不存在

归档拷贝用了 `signal.alarm()` 做超时，Windows 没这 API：
`AttributeError: module 'signal' has no attribute 'SIGALRM'`

**修**：跨平台超时封装

```python
def _copy_with_timeout(src_path, dst_path, seconds):
    if hasattr(signal, "SIGALRM") and hasattr(signal, "alarm"):
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(seconds)
        try:
            shutil.copy2(src_path, dst_path)
        finally:
            signal.alarm(0)
        return
    # Windows：线程 + join(timeout)
    import threading
    box = {}
    def _worker():
        try:
            shutil.copy2(src_path, dst_path)
        except BaseException as exc:
            box["error"] = exc
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise _Timeout("archive_cp_timeout")
    if "error" in box:
        raise box["error"]
```

### 4. `card_status_service.py` — 找不到 `card_config` 原生模块

交付最后一步回写卡片状态时：

```
ModuleNotFoundError: No module named 'card_config'
```

`card_config` 是 `card_engine_core/native/card_config.cp312-win_amd64.pyd`。
WebUI 进程内有 sys.path 引导（`api_queue.py` 里那段），但从 gpu-pipeline
子进程直接调用本脚本时没有。

**修**：补同样的 bootstrap

```python
for _p in [SCRIPT_DIR] + list(SCRIPT_DIR.parents):
    _native = _p / "card_engine_core" / "native"
    if _native.is_dir() and (
        list(_native.glob("card_asset_loader*.so"))
        or list(_native.glob("card_asset_loader*.pyd"))
    ):
        if str(_native) not in sys.path:
            sys.path.insert(0, str(_native))
        break
```

### 5. `cu-submit.sh` — CLI 直投不建卡，`card_id` 永远为空 ← **最关键**

这是真正的根因。WebUI 的「闪电直投」走 `api_cards.py`，会自动建卡：

```python
card_id = requested_card_id or new_card_id("direct")
```

但 CLI 的 `cu-submit.sh` 里 `--card` 是可选参数，不传就是空字符串。
交付阶段报：

```
card_id 不能为空或包含首尾空白
```

图生成了、归档了、队列 ACK 了，**但没有任何卡片指向它**，所以 WebUI 永远看不到。

**修**：`cu-submit.sh` 在 `CARD_ID` 为空时自动建一张 direct 卡

```bash
if [ -z "$CARD_ID" ]; then
    CARD_ID=$(CU_PROMPT="$PROMPT" ... python3 - <<'PY'
# 在 ~/.amazingdraw/cards/ 写 direct_<时间戳>_<pid>_<随机>.json
# status=submitted, workflow_mode=direct
PY
)
    echo "🆕 自动建卡: $CARD_ID"
fi
```

---

## 配置项（`~/.amazingdraw/config.json`）

```json
"delivery_telegram": false,   // 没配 bot token，关掉省事
"delivery_webui": true        // 必须 true，否则卡片状态不更新
```

⚠️ `delivery_webui` 若被误设为 `false`，日志会显示 `WebUI=0` 并跳过卡片同步。

---

## 验证方法

```bash
cd /j/AmazingDraw
bash scripts/gpu-pipeline/cu-submit.sh \
  --raw --prompt "测试" --workflow moss50 --width 768 --height 1152
```

成功标志（worker 日志）：

```
🆕 自动建卡: direct_20261115_124045_43224_dc41b04ae512
✅ 卡片完成态同步: 💾 direct_... v2 → C:\Users\bagmh\.amazingdraw\cards\direct_....json
{"ok": true, "status": "rendered", "render_image": "直投模式-神秘情境-灵感直投_5.png", "version": 2}
```

WebUI 里：

```powershell
(Invoke-WebRequest 'http://127.0.0.1:8318/api/cards' -UseBasicParsing).Content | ConvertFrom-Json |
  Where-Object { $_.render_image } | Select card_id, status, render_image
```

图片 URL 直链：`http://127.0.0.1:8318/images/<URL编码的文件名>`

---

## 修改文件清单

| 文件 | 改动 |
|---|---|
| `scripts/gpu-pipeline/cu-deliver.sh` | DONE 读取改 argv、Telegram 降级、SIGALRM 跨平台 |
| `scripts/gpu-pipeline/cu-progress.sh` | 卡片状态读取改 argv |
| `scripts/gpu-pipeline/cu-submit.sh` | **新增自动建卡** |
| `scripts/webui/card_status_service.py` | 补 native sys.path bootstrap |

`card_engine_core/gpu-pipeline/` 下的同名副本已同步。

---

## 顺带说明：CLI vs WebUI 的两条出图路径

| 路径 | 是否建卡 | WebUI 可见 |
|---|---|---|
| WebUI 闪电直投（`/api/direct/submit`） | ✅ 自动 | ✅ |
| WebUI 骰子精选 | ✅ 自动 | ✅ |
| CLI `card_cli.py direct` | ✅（现在会了） | ✅ |
| CLI `cu-submit.sh` | ✅（现在会了） | ✅ |
| `cu-draw-card.py` 直接调用 | ❌ 不建卡 | ❌ |

最后一条：`cu-draw-card.py` 是最底层的渲染器，绕过整个卡片体系。
直接调它出图只会落盘，不会进 WebUI。要进 WebUI 必须走上面四条之一。
