# 同一张图出现两条卡（SUBMITTED + RENDERED）

> 2026-11-15。症状：出图后列表里出现两条卡指向同一张图 ——
> 一条 `SUBMITTED`（旧，无图），一条 `RENDERED`（新，有图）。

---

## 根因：`delivery_webui=false` 导致图没回写，变成「孤儿 PNG」

### 时间线证据

```
17:30:27  direct_..._173027.json 创建   status=submitted
17:30:47  国漫立绘-藏书阁-仙侠风.json 创建   status=rendered
17:30:48  交付日志：📤 Delivery Options: Telegram=0, WebUI=0
          → "ℹ️ WebUI 本地卡片更新已被配置关闭，跳过卡片状态更新"
```

两条卡就是**同一张图的两个「身份」**：

| 卡 | 来源 | 状态 |
|---|---|---|
| `direct_..._173027` | `cu-submit.sh` 建的**真实卡** | `submitted`（永远停在这） |
| `国漫立绘-藏书阁-仙侠风` | 列表扫描**孤儿 PNG** 合成的虚拟卡 | `rendered` |

### 为什么会有孤儿 PNG

`cu-deliver.sh` 里的卡片回写受 `delivery_webui` 开关控制：

```bash
if [ "${DELIVERY_WEBUI:-1}" = "1" ]; then
    ... card_status_service complete ...   # 回写 render_image
else
    echo "ℹ️  WebUI 本地卡片更新已被配置关闭，跳过卡片状态更新"
fi
```

而 `~/.amazingdraw/config.json` 里 `delivery_webui` 被设成了 `false`
（之前排查 Telegram 时误改的）。于是：

1. 图正常出、正常归档到 `ZDpaotu/`
2. 但**没有任何卡片指向它** → 成为孤儿 PNG
3. `api_cards.list_cards()` 扫描归档目录，发现有中文名 PNG 没被认领
4. 就**合成一张虚拟卡**（`card_id` = 文件名去掉 `.png`），状态 `rendered`
5. 原来那张真实卡永远停在 `submitted`

---

## 修复

### 1. 配置改回

```json
"delivery_telegram": false,
"delivery_webui": true
```

### 2. 交付脚本加兜底

即使 `delivery_webui=false`，只要任务关联了卡片就仍然回写 ——
否则必然产生重复卡：

```bash
elif [ -n "${CARD_ID:-}" ]; then
    # delivery_webui=false 时若不回写，图会变成「孤儿 PNG」，
    # 列表扫描时又合成一条虚拟卡 → 同一张图出现两条卡。
    STATUS_RESULT=$(python3 "$STATUS_SERVICE" complete \
        --card "$CARD_ID" --job-id "$JOB_ID" --image "$FILE")
    echo "✅ 卡片完成态同步（delivery_webui 关闭，仍回写卡片）: $STATUS_RESULT"
else
    echo "ℹ️  WebUI 本地卡片更新已被配置关闭，且该任务无关联卡片，跳过"
fi
```

### 3. 清理已产生的重复卡

21 组配对（按 scene 匹配 文件名卡 ↔ stuck 真实卡）：

```python
# 1) 把图片回写到真实卡
complete_render_job(real_id, job_id=f"backfill-{...}", render_image=image)
# 2) 删掉重复的文件名卡
(CARDS_DIR / f"{fc_id}.json").unlink()
```

结果：

```
修复 21 组，失败 0，删除重复卡 21 张
剩余 4 张孤立卡 → 再删 1 张完全重复的，保留 3 张（图片未被任何真实卡持有）
```

---

## 验证

### 修复前后对比

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 国漫卡总数 | 56 | **35** |
| `submitted` | 21 | **0** |
| `rendered` | 35 | **35** |
| 重复卡 | 21 组 | **0** |

### 端到端复现

```
投递前国漫卡: 34
投递 card=direct_20261115_174806_41876_1d25fa9e170e
✅ 出图回写: 国漫立绘-断崖边缘-战斗风.png  status=rendered
投递后国漫卡: 35  (增加 1 张)
✅ 只增 1 张 = 正常
```

出图后卡片直接变成 `rendered` 并带上 `render_image`，**不再产生第二条卡**。

---

## 教训

1. **`delivery_webui=false` 不只是「不推送」，它会切断卡片回写。**
   这个开关名字看起来像「推送通知」，实际控制的是「写回卡片状态」，
   关掉就会产生孤儿 PNG + 虚拟卡。

2. **列表的「孤儿 PNG 合成虚拟卡」是双刃剑。**
   它能在卡片丢失时救回图（好事），但也会把「没回写的图」变成重复条目。
   只要回写正常，它就不会触发。

3. **排查时先看交付日志的 `Delivery Options: Telegram=X, WebUI=Y`。**
   那一行直接告诉你卡片会不会被回写。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `~/.amazingdraw/config.json` | `delivery_webui` 改回 `true` |
| `scripts/gpu-pipeline/cu-deliver.sh` | 加 `elif [ -n "$CARD_ID" ]` 兜底回写 |
| （数据修复） | 21 组重复卡合并 + 22 张文件名卡删除 |
