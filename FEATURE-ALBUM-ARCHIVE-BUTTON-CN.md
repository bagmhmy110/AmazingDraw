# 相册加「存进灵感库」按钮

> 2026-11-16。相册里每张图右上角加了个书签图标，点一下就把这张图的提示词存进 Obsidian 灵感库。

---

## 用法

鼠标悬停在相册的图上，右上角出现一排快捷按钮：

| 图标 | 作用 |
|---|---|
| 🔖 **书签**（新增） | **存进 Obsidian 灵感库** |
| ✨ 魔杖 | 转高清（SeedVR2） |
| ♡ 爱心 | 收藏 |
| 🗑 垃圾桶 | 删除卡片 |

点书签 → 后端生成笔记 + 复制图片到 attachments → Toast 提示「📸 已存进 Obsidian 灵感库」

**已存过的会提示「这张已经存过了」**，不会重复写。

---

## 生成的笔记

```markdown
---
tags: ["抽卡", "amateur", "厚涂御姐", "默认风格"]
scene: "夜市"
person: "厚涂御姐"
status: "archived"
date: 2026-11-19
card_id: "厚涂御姐-夜市-厚涂御姐_4"
---

# 厚涂御姐·夜市·厚涂御姐_4

![[厚涂御姐·夜市·厚涂御姐_4.png]]

## 📝 提示词
```text
Wuthering Waves style二次元半写实厚涂，竖屏构图。29岁成熟女子...
```

## 📖 中文描述
无叙事描述

## 🎬 创作思路
- **意图**:厚涂御姐_4
- **光影**:--
- **焦点**:

---
> 存档时间:2026-11-19 22:08:24
```

图片复制到 `Vault/attachments/`，笔记里用 `![[...]]` 嵌入。

---

## 实现

### 前端（`albums.js`）

**1. 加按钮**

```javascript
<div class="album-tile-quick">
  <button type="button" data-album-archive title="存进 Obsidian 灵感库">
    <i class="fa-regular fa-bookmark"></i>
  </button>
  <button type="button" data-album-upscale ...>...</button>
  ...
</div>
```

**2. 绑事件**

```javascript
tile.querySelector("[data-album-archive]")?.addEventListener("click", (e) => {
  e.preventDefault();
  e.stopPropagation();
  archiveAlbumCard(card, e.currentTarget);
});
```

**3. 存档函数**

```javascript
async function archiveAlbumCard(card, btnEl) {
  const res = await fetch(`/api/cards/${encodeURIComponent(cardId)}/archive`, {
    method: "POST",
  });
  ...
  showToast(already ? "这张已经存过了" : "📸 已存进 Obsidian 灵感库", ...);
}
```

复用现成的 `/api/cards/{id}/archive`，不新增后端端点。

---

## 又挖出一个 bug：scene 是字符串

点按钮报 500：

```
File "build/cython_p1/src/card_archive.py", line 188, in _card_metadata_values
AttributeError: 'str' object has no attribute 'get'
```

### 根因

`card_archive` 的编译模块假设 `scene` / `subject` 是 **dict**，但卡片有两种存法：

| 卡片类型 | `scene` |
|---|---|
| 厚涂/国漫（正常出图） | `{"name": "夜市", "keywords": "", ...}` |
| **直投模式** | `"雪山"` ← 裸字符串 |

`_card_metadata_values` 直接 `card["scene"].get("name")`，遇到 str 就崩。

### 修法：存档前临时规整，存完还原

源码在 `.pyd` 里改不了，所以在 API 层做转换：

```python
def _normalize_card_fields_for_archive(card_id):
    """把裸字符串的 scene / subject 临时改成 dict。"""
    card = json.loads(path.read_text(...))
    changed = False

    scene = card.get("scene")
    if isinstance(scene, str):
        restored["scene"] = scene          # 记下原值
        card["scene"] = {
            "name": scene.strip(),
            "keywords": "", "tags": [], "moods": [],
            "optional_details": [], "directives": None,
        }
        changed = True

    subject = card.get("subject")
    if isinstance(subject, str):
        restored["subject"] = subject
        card["subject"] = {
            "mode": card.get("mode") or "amateur",
            "display_name": subject.strip(),
            "trigger": "girl", "lora": None,
            "archetype": None, "model_type": "z",
        }
        changed = True

    if changed:
        path.write_text(json.dumps(card, ...))
    return restored


def _restore_card_fields_after_archive(card_id, restored):
    """存档完把字段还原回裸字符串。"""
    if not restored:
        return
    card = json.loads(path.read_text(...))
    for key, val in restored.items():
        card[key] = val
    path.write_text(json.dumps(card, ...))
```

**存档端点包一层 try/finally：**

```python
def archive_card_api(card_id):
    restored = _normalize_card_fields_for_archive(card_id)
    try:
        result = archive_card(card_id)
    ...
    finally:
        _restore_card_fields_after_archive(card_id, restored)
```

**关键：`finally` 保证异常时也还原**，不会把磁盘数据改坏。

---

## 验证

### 单个测试（scene 是 str 的卡片）

```
✅ 存档成功
note: ...\灵感库\NSFW模板·雪山·模板使用.md

卡片字段还原检查:
  scene 类型: str = 雪山        ← 还原成功，没被改成 dict
```

### 浏览器端到端（4/5）

```
PASS  相册有卡片（100 张）
PASS  每张都有存档按钮（100 个）
PASS  点击成功
PASS  笔记数增加（25 → 26）
FAIL  Toast 提示成功（选择器没抓到，toast 已消失）
```

**Toast 那条是测试脚本问题** —— toast 是临时元素，我 sleep 8 秒后才查，早消失了。

### 灵感库现状

```
笔记: 26 篇
```

存档生成的（文件名 `·` 连接）：
```
NSFW模板·悬崖·模板.md
NSFW模板·雪山·模板使用.md
厚涂御姐·夜市·厚涂御姐_4.md
厚涂御姐·戈壁·厚涂御姐.md
厚涂御姐·樱林·厚涂御姐_3.md
限制级模板·石窟·模板主题.md
```

反推生成的用 `-` 连接，两种命名能区分来源。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `static/js/albums.js` | 加存档按钮 + `archiveAlbumCard()` |
| `scripts/webui/api_cards.py` | 新增 `_normalize_card_fields_for_archive()` / `_restore_card_fields_after_archive()`；存档端点包 try/finally |
| `static/index.html` | `albums.js?v=1.3.0` |

---

## 两种存档入口

| 位置 | 按钮 | 说明 |
|---|---|---|
| **卡片列表**（左侧） | 📦 方块图标 | 原有的，只对已出图的卡片显示 |
| **相册**（网格） | 🔖 书签图标 | 新增的，悬停图片时出现 |

两个都走同一个 API，生成的笔记一样。
