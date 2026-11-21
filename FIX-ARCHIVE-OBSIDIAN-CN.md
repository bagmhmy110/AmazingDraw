# 灵感库怎么增加 + 存档报错修复

> 2026-11-16。三种加笔记的方式，以及修掉「存档到 Obsidian」的 500 错误。

---

## 三种加笔记的方式

### 方式一：卡片存档（推荐）

**WebUI 里点按钮**：卡片列表每条右边有个**方块图标**（📦 存档按钮），点一下就把这张卡存进灵感库。

只对已出图的卡片可用（`status` 为 `rendered` / `delivered` / `success`）。

**API 调用**：

```bash
curl -X POST "http://127.0.0.1:8318/api/cards/厚涂御姐-夜市-厚涂御姐_4/archive"
```

**CLI**：

```bash
python scripts/card-engine/card_cli.py archive --card <card_id>
```

**生成的笔记长这样**：

```markdown
---
tags: ["抽卡", "amateur", "厚涂御姐", "默认风格"]
scene: "夜市"
person: "厚涂御姐"
style: "默认风格"
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
- **身体叙事**:
- **光影**:--
- **焦点**:

---
> 存档时间:2026-11-19 22:08:24
```

图片会复制到 `Vault/attachments/` 下。

### 方式二：从归档盘批量反推

适合一次性把历史图都收进灵感库。扫归档盘 PNG，挖出里面存的 ComfyUI 工作流 JSON，
取 `CLIPTextEncode` 的 `text` 字段就是当时的提示词。

之前跑过一次，收了 20 篇。

### 方式三：手写

在 Obsidian 里往「灵感库」新建 `.md`，**必须有 `## 提示词` + 代码块**：

```markdown
## 提示词

```
英文提示词正文
```
```

精选靠这个标题定位，没有就跳过。

---

## 存档报 500 的修复

### 报错

```
File "build/cython_p1/src/card_archive.py", line 444, in _temporary_copy
OSError: [Errno 9] Bad file descriptor
```

### 排查过程

**第一步：Pillow 缺失**

先报的是：

```
File "build/cython_p1/src/card_archive.py", line 90, in extract_prompt_from_png
ModuleNotFoundError: No module named 'PIL'
```

`card_archive` 的 `.pyd` 里也调 `PIL`。装掉：

```bash
python -m pip install Pillow
```

**第二步：`_temporary_copy` 的 Bad file descriptor**

装完 Pillow 后冒出这个。逐层排除：

| 测试 | 结果 |
|---|---|
| 目标图是否被占用 | ✅ 没占用 |
| 临时目录可写 | ✅ 可以 |
| 灵感库目录可写 | ✅ 可以 |
| `shutil.copy2` 写入灵感库 | ✅ 成功 |
| `tempfile.mkstemp` 在灵感库建文件 | ✅ 成功 |
| **`_temporary_copy` 内部实现** | ❌ Bad file descriptor |

**环境和权限都没问题，是 `_temporary_copy` 自己的实现有 bug** ——
它用底层 fd 操作，在 Windows 上踩了坑。

源码不在仓库里（只有 `.pyd`），改不了。

### 修法：monkey-patch 替换掉

在 `api_cards.py` 导入 `card_archive` 后立刻 patch：

```python
def _patch_card_archive_tempcopy() -> None:
    """修 card_archive._temporary_copy 在 Windows 上的 Bad file descriptor。"""
    try:
        import os as _os
        import shutil as _shutil
        import tempfile as _tempfile
        from pathlib import Path as _Path
        import card_archive as _CA

        def _temporary_copy(source, directory):
            src = _Path(source)
            dirp = _Path(directory)
            dirp.mkdir(parents=True, exist_ok=True)
            suffix = src.suffix or ".png"
            fd, tmp_name = _tempfile.mkstemp(
                dir=str(dirp), prefix=".archive-image-", suffix=".tmp"
            )
            _os.close(fd)
            tmp = _Path(tmp_name)
            try:
                _shutil.copy2(src, tmp)
            except Exception:
                try:
                    tmp.unlink()
                except Exception:
                    pass
                raise
            return tmp

        _CA._temporary_copy = _temporary_copy
    except Exception:
        pass


_patch_card_archive_tempcopy()
```

**语义一致**：把 source 复制成 directory 下的临时文件，返回临时文件路径。

**patch 失败不阻断导入** —— 存档时会走原实现并报错，但其他功能正常。

### 验证

```
✅ 存档成功
note: C:\Users\bagmh\Documents\Obsidian Vault\灵感库\厚涂御姐·樱林·厚涂御姐_3.md
image: C:\Users\bagmh\Documents\Obsidian Vault\attachments\厚涂御姐·樱林·厚涂御姐_3.png
```

API 和 WebUI 按钮都通了。

---

## 灵感库当前状态

```
灵感库笔记: 22 篇
附件图片:   2 张
```

- 20 篇是从归档盘反推的（文件名用 `-` 连接）
- 2 篇是卡片存档生成的（文件名用 `·` 连接）

两种命名风格能区分来源。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/webui/api_cards.py` | 新增 `_patch_card_archive_tempcopy()`，导入后立即执行 |
| 环境 | `pip install Pillow`（13.0.0） |

---

## 注意

**Pillow 现在装上了**，之前修的「参数面板不显示提示词」也有它一份功劳
（那个是改成内置 PNG 解析 + Pillow 兜底）。

装 Pillow 后，`extract_prompt_from_png` 的兜底路径也能用了。
