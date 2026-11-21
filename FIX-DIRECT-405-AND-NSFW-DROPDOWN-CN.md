# 两个修复：投递 405 + 模板插槽改下拉

> 2026-11-15。

![模板下拉](../docs-screenshots/nsfw-dropdowns.png)

---

## 一、写实 skill 投递失败（Method Not Allowed）

### 根因：路径被拼了两次

`adult-photo21.js` 里的 `apiPost()` 会自动加上本 skill 的 API 前缀：

```javascript
const API = "/api/adult-photo21";

async function apiPost(path, body) {
  const r = await fetch(API + path, {...});   // ← 自动拼前缀
}
```

而投递时我传了**完整路径**：

```javascript
const r = await apiPost("/api/guoman/direct", payload);
//                      ↑ 已经带了 /api
```

结果实际请求变成：

```
POST /api/adult-photo21/api/guoman/direct
     ^^^^^^^^^^^^^^^^^^ 前缀     ^^^^^^^^^^^ 又拼了一次
```

这个路径不存在，FastAPI 返回 **405 Method Not Allowed**。

### 修法：投递单独走一个不拼前缀的函数

```javascript
/**
 * 出图投递：走主引擎的 /api/guoman/direct。
 * 注意不能用 apiPost() —— 它会自动拼上本 skill 的 API 前缀，
 * 结果变成 /api/adult-photo21/api/guoman/direct → 405 Method Not Allowed。
 */
async function postDirect(payload) {
  const r = await fetch("/api/guoman/direct", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  ...
}
```

### 为什么另外三个 skill 没这个问题

`prompt-skills.js` 的 `apiPost()` 接受**完整路径**（没有前缀拼接）：

```javascript
async function apiPost(url, body) {
  const r = await fetch(url, {...});   // 直接用传入的 url
}
```

所以那三处的 `/api/guoman/direct`、`/api/moss-architect/generate` 都是对的。

**教训：同一个函数名在不同文件里语义不同。** 改代码前先看那个文件里的 `apiPost` 到底怎么实现的。

### 验证

```
/api/guoman/direct → HTTP 200
{ "ok": true, "job_id": "job-443d1caf...", "card_id": "direct_20261115_205225..." }
```

---

## 二、模板 skill 插槽改下拉

### 原来

必读槽是**纯文本输入框**，要用户自己翻词库手打。词库 1600 多条，手打基本不可行。

### 现在

每个槽位一个**分组下拉**，选项直接来自词库：

```
场景主题  模块 01 · 178 条  [（不填·由模型自选） ▼]
景别构图  模块 02 · 69 条   [（不填·由模型自选） ▼]
裸露液体  模块 03 · 87 条   [（不填·由模型自选） ▼]
...
```

选读槽也配了下拉 —— **勾选后才启用**：

```
☑ 风格胶片  25 种胶片模拟…  [（不指定·由模型自选） ▼]
☐ 妆容专项  底妆/眼妆/唇妆…  [（不指定·由模型自选） ▼]  ← 灰色禁用
```

---

### 词条从哪来

词库是 markdown，结构混杂（表格、列表、章节标题、索引表、规则说明）。
不能直接扔给前端，需要先抽成结构化 JSON。

**`scripts/webui/build_nsfw_terms.py`** —— 一次性构建脚本：

```bash
python scripts/webui/build_nsfw_terms.py
# → 写出 nsfw_terms_cache.json
```

输出结构：

```json
{
  "景别构图": {
    "file": "02-景别构图.md",
    "total": 69,
    "sections": {
      "标准景别": ["大特写 ECU", "近景 CU", "中近景 MCU", "中景 MS", "中全景 MLS"],
      "基础视角": ["平视", "仰视", "俯视", "鸟瞰", "蛙眼", "斜角", "过肩"],
      "手机 / 便携": ["自拍", "偷拍", "日常"]
    }
  }
}
```

### 抽取难点：过滤伪词条

词库里混着大量**不是词条**的东西。踩了四轮才过滤干净：

| 轮次 | 混进来的东西 | 过滤规则 |
|---|---|---|
| 1 | `子类型` `类别` `信号词` | 表头黑名单 |
| 2 | `十一` `十二` `联动` | 中文数字序号 + 黑名单 |
| 3 | `kneeling, head bowed` 英文信号词 | 全英文一律跳过 |
| 4 | `🎬 电影感布光` `📐 光影选择原则` | 去 emoji 前缀后匹配章节标签 |
| 5 | `1. 风格标签` `附录A` `中文名` | 编号标题 + 黑名单扩充 |

最终过滤逻辑：

```python
def is_term(s):
    if s in JUNK_TERMS: return False              # 表头
    stripped = strip_emoji(s)
    if _SECTION_LABEL.match(stripped): return False   # 章节标签
    if _NUMBERED_HEAD.match(stripped): return False   # 「1. 风格标签」
    if re.search(r"(原则|规则|说明|速查|公式)$", stripped): return False
    if _CN_NUM.match(stripped): return False          # 「十一」
    if re.match(r"^[^\u4e00-\u9fffA-Za-z]+$", s): return False  # 纯 emoji
    if looks_like_signal(s): return False             # 全英文
    return True
```

### 最终产出

| 槽位 | 词条数 | 小节数 |
|---|---|---|
| 场景主题 | 178 | 26 |
| 景别构图 | 69 | 9 |
| 裸露液体 | 87 | 16 |
| 服装专项 | 54 | 12 |
| 光影氛围 | 39 | 2 |
| 姿势动作 | 16 | 3 |
| 表情眼神 | 99 | 17 |
| 风格胶片 | 18 | 3 |
| 妆容专项 | 93 | 10 |
| 发型饰品 | 104 | 14 |
| 瑕疵细节 | 32 | 2 |
| 纹身标记 | 449 | 45 |
| 道具宠物 | 212 | 45 |
| 人格卡片 | 4 | 1 |
| **合计** | **~1454** | |

---

### 后端

新增 `GET /api/nsfw-templates/terms`：

```python
@router.get("/api/nsfw-templates/terms")
def terms(slot: str = ""):
    """返回某槽位（或全部）的可选词条，按小节分组。"""
    data = _load_terms()
    if slot:
        ...
    return {"slots": {...}}
```

`/meta` 也直接带上 `terms` 字段，前端一次请求就够：

```python
out["terms"] = {
    k: {"sections": v.get("sections") or {}, "total": v.get("total", 0)}
    for k, v in _load_terms().items()
}
```

### 前端

必读槽渲染成 `<optgroup>` 分组下拉：

```javascript
const groups = Object.keys(sections).map((sec) => {
  const opts = sections[sec]
    .map((t) => `<option value="${esc(t)}">${esc(t)}</option>`)
    .join("");
  return opts ? `<optgroup label="${esc(sec)}">${opts}</optgroup>` : "";
}).join("");

return `
  <label class="skill-field">
    <span class="skill-label">${slot}<em>模块 ${id} · ${total} 条</em></span>
    <select data-nt-slot="${slot}">
      <option value="">（不填 · 由模型自选）</option>
      ${groups}
    </select>
  </label>`;
```

选读槽：勾选才启用下拉

```javascript
optHost.querySelectorAll("[data-nt-opt]").forEach((cb) => {
  cb.addEventListener("change", () => {
    const sel = optHost.querySelector(`[data-nt-opt-term="${cb.value}"]`);
    if (sel) {
      sel.disabled = !cb.checked;
      if (!cb.checked) sel.value = "";
    }
  });
});
```

组装时把选读槽选中的词条也带上：

```javascript
document.querySelectorAll("[data-nt-opt]:checked").forEach((cb) => {
  const slot = cb.value;
  const sel = document.querySelector(`[data-nt-opt-term="${slot}"]`);
  const term = sel ? (sel.value || "").trim() : "";
  optional.push(slot);
  if (term) slots[slot] = term;   // ← 具体词条
});
```

---

## 验证（11/11）

```
PASS  必读槽全部变成 select
PASS  没有残留 input
PASS  下拉有 optgroup 分组（27 个）
PASS  下拉有词条（179 项）
PASS  词条是真实内容
PASS  选读槽也有下拉（7 个）
PASS  选读下拉默认禁用
PASS  勾选后启用
PASS  选读下拉有词条（25 项）
PASS  下拉组装成功
PASS  投递不再 405（HTTP 200）
```

组装结果示例：

> 深夜便利店场景中，采用**近景 CU** 构图，人物呈**半裸**状态，整体笼罩在**钨丝灯**的光影氛围中。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `static/js/adult-photo21.js` | 新增 `postDirect()`，投递不再走带前缀的 `apiPost` |
| `scripts/webui/build_nsfw_terms.py` | **新增** 词库抽词条脚本 |
| `scripts/webui/nsfw_terms_cache.json` | **新增** 生成的词条缓存（1454 条） |
| `scripts/webui/api_nsfw_templates.py` | 新增 `/terms` 端点；`/meta` 带 `terms`；补 `import json, Path` |
| `static/js/prompt-skills.js` | 必读槽改下拉；选读槽加词条下拉 |
| `static/css/09-prompt-skills.css` | `.skill-opt-slot` 样式 |

### 重新生成词条缓存

词库有更新时跑一次：

```bash
python scripts/webui/build_nsfw_terms.py
```

然后重启 WebUI（缓存是模块级 memo，重启才会重新读）。
