# 批量出图：批量生成提示词后一键全部投递

> 2026-11-16。以前批量生成 20 条提示词后，要逐条点「生成图片」20 次。
> 现在结果区顶部有个「批量出图」按钮，一次投完整批。

![批量出图](../docs-screenshots/batch-draw.png)

---

## 用起来

批量生成后会看到一条工具条：

```
共 5 条   出图上限 [2]   [🖼 批量出图]        已投递 2 条，去队列看进度
```

- **出图上限** —— 想投几条投几条，默认 10，上限 60
- **自动去重** —— 重复的提示词只投一次
- 投完状态变绿：「已投递 N 条，去队列看进度」
- 有失败会变黄：「已投递 N 条，M 条失败」

---

## 覆盖的 skill

| Skill | 批量入口 | 说明 |
|---|---|---|
| 厚涂御姐 | `ao-batch` | ✅ 纯代码，最快 |
| 国漫 · 立绘 | `guoman` 批量模式 | ✅ 纯代码 |
| 国漫人像 | `gp-batch` | 走 LLM |
| MOSS | `ma-batch` | 走 LLM |
| 模板 | 组装多条 | 走 LLM |
| 写实摄影 | `ap-generate` count>1 | 走 LLM |

**只要批量结果超过 1 条，工具条就自动出现。**

---

## 后端

### 新端点 `POST /api/batch-draw`

```json
{
  "prompts": ["提示词1", "提示词2", "..."],
  "person": "厚涂御姐",
  "scene": "",
  "tone": "",
  "theme": "厚涂御姐",
  "limit": 10,
  "skip_dupes": true
}
```

返回：

```json
{
  "ok": true,
  "total": 5,
  "submitted": 2,
  "failed": 0,
  "person": "厚涂御姐",
  "items": [
    { "index": 1, "ok": true, "card_id": "direct_...", "prompt_head": "..." },
    { "index": 2, "ok": true, "card_id": "direct_...", "prompt_head": "..." }
  ]
}
```

### 实现要点

**复用现成投递链路** —— 不另造一套，直接调 `api_guoman.guoman_direct()`：

```python
for idx, prompt in enumerate(prompts, start=1):
    try:
        r = GM.guoman_direct({"prompt": prompt, "person": person, ...})
        items.append({"index": idx, "ok": True, "card_id": r.get("card_id")})
    except Exception as exc:
        items.append({"index": idx, "ok": False, "error": str(exc)[:160]})
    if idx < len(prompts):
        time.sleep(SUBMIT_GAP)      # 0.6s 间隔
```

**串行 + 间隔** —— 队列本来就是串行的，瞬间投 60 条没意义，
反而可能让 `cu-submit.sh` 抢锁失败。留 0.6 秒间隔最稳。

**单条失败不影响整批** —— 每条独立 try/except，最后汇总成功/失败明细。

**去重** —— 默认开启，同样的提示词只投一次（批量生成偶尔会撞）。

**上限保护** —— `MAX_BATCH = 60`，防止误把 500 条塞进队列。

---

## 前端

### 共享模块 `static/js/batch-draw.js`

```javascript
window.BatchDraw = { attach, promptsFromCards };
```

**attach(hostEl, getPrompts, opts)** —— 在结果区顶部插入工具条。
重复调用会先删旧的，避免批量多次后叠一堆。

**promptsFromCards(hostEl)** —— 从 DOM 里收集提示词。

**关键**：收集的是 `[data-prompt-editable]` 的 `innerText`，
所以**你手动改过的提示词也会被投递**，用的是改后的版本。

### 接到各 skill 的渲染函数

```javascript
// 厚涂
if (items.length > 1) {
  window.BatchDraw?.attach(
    host,
    () => window.BatchDraw.promptsFromCards(host),
    { person: "厚涂御姐", theme: "厚涂御姐" }
  );
}
```

四个渲染函数各加这么一段，`person` 决定卡片显示名和文件名前缀。

---

## 验证

```
PASS  BatchDraw 已加载
PASS  厚涂有批量出图按钮条
PASS  按钮条显示条数（5 条）
PASS  有批量出图按钮
PASS  能收集到 5 条提示词
PASS  投递后有状态反馈

6 passed / 0 failed
```

队列确认：

```
投递前: local_queue: []
投递后: local_queue: [{ job_id: "job-2f347ce8280f43f3...", ... }]
```

真的进了队列。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/api_batch_draw.py` | **新增** 批量投递端点 |
| `scripts/webui/web_server.py` | 注册 router |
| `static/js/batch-draw.js` | **新增** 工具条与投递逻辑 |
| `static/js/prompt-skills.js` | 批量结果加工具条 + 传 person |
| `static/js/anime-oneesan.js` | 同上 |
| `static/js/adult-photo21.js` | 同上 |
| `static/js/guoman.js` | 同上 |
| `static/css/09-prompt-skills.css` | 工具条样式 |
| `static/index.html` | 引入 batch-draw.js |

---

## 注意

批量出图会**真的往 GPU 队列投任务**，每条要跑 40-90 秒。

投之前先看「出图上限」—— 别一激动把 60 条全投了，GPU 得跑一个多小时。

想看进度去「配置」页的渲染队列，或者等卡片自动刷新。
