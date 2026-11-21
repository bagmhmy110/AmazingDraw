# 国漫出图复用卡片（不再每次都新建）

> 2026-11-15。症状：国漫里每点一次「生成图片」，列表就多一条卡片，
> 而不是把图写进当前那张卡。

---

## 根因：投递时没带 `card_id`

`cu-submit.sh` 有个自动建卡逻辑：

```bash
# ── 6.0 未指定卡片时自动建卡 ───────────
if [ -z "$CARD_ID" ]; then
    CARD_ID=$(... 新建 direct_<时间戳>_<pid>_<随机>.json ...)
    echo "🆕 自动建卡: $CARD_ID"
fi
```

而 `api_guoman.guoman_direct()` 调它时**只传了 prompt / person / scene / theme / narrative**，
没有 `--card`：

```python
args = [
    bash_executable(), str(submit),
    "--raw", "--prompt", prompt,
    "--person", "国漫立绘",
    "--scene", scene,
    "--theme", f"{tone}风",
    "--narrative", f"{tone}调性的{scene}立绘",
]
```

所以每次投递都是「未指定卡片」→ 每次都新建一张。

（这个自动建卡是我之前为了修「CLI 直投的图不出现在 WebUI」加的，
在 CLI 场景是对的 —— 但 WebUI 国漫场景应该复用会话卡片。）

---

## 修复

### 1. 后端：接受并透传 `card_id`

```python
# 复用已有卡片：传了 card_id 就让 cu-submit 回写这张卡，
# 而不是自动新建一张（否则每点一次「生成图片」列表就多一条）
reuse_card = _clean(req.get("card_id"))
if reuse_card:
    args += ["--card", reuse_card]
```

### 2. 前端：会话级卡片绑定

新增三个函数：

```javascript
const STICKY_CARD_KEY = "guoman_active_card";

// 读取上次绑定（跨刷新保留）
function loadStickyCard() {
  state.cardId = localStorage.getItem(STICKY_CARD_KEY) || null;
}

// 绑定/解绑
function setStickyCard(cardId) {
  state.cardId = cardId || null;
  if (cardId) localStorage.setItem(STICKY_CARD_KEY, cardId);
  else localStorage.removeItem(STICKY_CARD_KEY);
  renderCardBadge();
}

// 顶部绑定条
function renderCardBadge() { ... }
```

投递时带上：

```javascript
const payload = { prompt: text, tone: finalTone, scene: finalScene };
if (state.cardId) payload.card_id = state.cardId;   // ← 复用
const r = await apiPost("/direct", payload);
if (r.card_id) setStickyCard(r.card_id);            // ← 首次投递后绑定
```

两处投递（卡片上的「生成图片」和顶部「生成并出图」）都改了。

### 3. UI：绑定状态可见 + 可解绑

参数区顶部新增一条：

```
未绑定： 出图时会新建一张卡片
已绑定： 🔗 出图写入  direct_20261…59db74  [解绑]
```

![绑定条](../docs-screenshots/guoman-card-bind.png)

点「解绑」清空绑定，下次出图重新新建。

---

## 行为

| 场景 | 结果 |
|---|---|
| 首次出图（未绑定） | 新建 1 张卡，并自动绑定它 |
| 再点「生成图片」 | **写回同一张卡**，列表不新增 |
| 换提示词再出图 | 仍写回同一张卡（覆盖上一次的图） |
| 点「解绑」后出图 | 新建一张 |
| 刷新页面 | 绑定保留（localStorage） |

---

## 验证

### API 层（7/7）

```
[1] 首次投递（不带 card_id）
    投递前卡片数: 78  →  投递后: 79
    PASS  新建了 1 张卡

[2] 带同一个 card_id 再投递
    返回 card=direct_20261115_172935_48044_6f05d5c777fc（同一个）
    投递后卡片数: 79 → 79
    PASS  复用同一张卡
    PASS  卡片数未增加

[3] 第三次投递
    PASS  仍未新增
    PASS  返回同一 card_id

[4] 卡片内容
    status=submitted scene=云海 theme=仙侠风
    PASS  卡片存在且状态合理
```

### UI 层（11/11）

```
PASS  绑定条存在
PASS  初始显示「新建卡片」
PASS  初始无 has-card 样式
PASS  首次出图后绑定成功
PASS  绑定条显示卡片 id
PASS  localStorage 存了 card_id
PASS  再次出图不新增卡片（81 → 81）
PASS  仍是同一 card_id
PASS  解绑按钮存在
PASS  解绑后恢复未绑定
PASS  解绑后 localStorage 清空
```

---

## 一个副作用要说明

**同一张卡被覆盖后，旧图不会自动删除。** 归档盘里的 PNG 还在，
但卡片只指向最新那张。想保留每一张就点「解绑」再出图。

如果希望「一张卡只出一张图，之后自动解绑」，可以在渲染完成后清掉绑定 ——
但那样每张新图又需要手动确认，不如现在的可控。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/api_guoman.py` | direct 端点接受 `card_id`，透传 `--card` |
| `static/js/guoman.js` | `loadStickyCard` / `setStickyCard` / `renderCardBadge`；两处投递带 `card_id` |
| `static/index.html` | 参数区顶部加绑定条 |
| `static/css/08-guoman.css` | 绑定条样式 |
