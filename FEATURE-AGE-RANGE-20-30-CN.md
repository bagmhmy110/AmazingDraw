# 厚涂御姐：年龄范围改为 20-30 岁

> 2026-11-16。原来只有 25-30 岁，扩到 20-30。

![年龄 20-30](../docs-screenshots/age-20-30.png)

---

## 改动

**年龄池从 6 项扩到 11 项**：

```
改前：25岁 26岁 27岁 28岁 29岁 30岁
改后：20岁 21岁 22岁 23岁 24岁 25岁 26岁 27岁 28岁 29岁 30岁
```

下拉里显示 12 项（11 个年龄 + 「随机」）。

---

## 一个坑：改错了文件

第一次只改了 `C:\Users\bagmh\.dsh\skills\...\pools.json`，
结果 WebUI 里还是 25-30。

原因：上次把「仓库内置 skills」加进了探测候选，且**优先级高于用户目录**：

```python
_SKILLS_ROOT_CANDIDATES = (
    os.environ.get("AMAZINGDRAW_SKILLS_ROOT"),
    str(_REPO_SKILLS),                                  # ← J:\AmazingDraw\skills
    str(Path.home() / ".dsh" / "skills"),               # ← 用户目录（排在后面）
    ...
)
```

所以 WebUI 实际读的是 `J:\AmazingDraw\skills\...\pools.json`。

**两份都要改**，否则改了半天不生效。

---

## 修法

### 1. 直接改 pools.json（两份）

```python
for f in [
    Path(r"J:\AmazingDraw\skills\anime-thickpaint-oneesan-prompts\references\pools.json"),
    Path(r"C:\Users\bagmh\.dsh\skills\anime-thickpaint-oneesan-prompts\references\pools.json"),
]:
    d = json.loads(f.read_text(encoding="utf-8"))
    d["ages"] = [{"value": f"{n}岁", "label": f"{n}岁"} for n in range(20, 31)]
    if "stats" in d:
        d["stats"]["ages"] = len(d["ages"])
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
```

### 2. 改抽取脚本，以后重建也保持 20-30

`extract_pools.py` 原来是从源文档用正则抓年龄：

```python
ages = re.findall(r"`(\d+岁)`", text)     # 源文档只写了 25-30
```

改成固定生成：

```python
# 年龄：固定 20-30 岁（原文档只写到 25-30，这里扩到 20 起）
# 全部为成年角色，硬边界不低于 20 岁
ages = [f"{n}岁" for n in range(20, 31)]
```

顺带修了 `build()` 里漏掉的 `--src` 参数支持 —— 之前 `build()` 还直接读全局 `SRC`，
没有走传入的 `src`，导致源文档不在默认位置时脚本跑不起来。

---

## 验证

### meta 接口

```
选项: ['20岁','21岁','22岁','23岁','24岁','25岁','26岁','27岁','28岁','29岁','30岁']
数量: 11
```

### 批量 20 条年龄分布

```
分布: {20:4, 21:1, 22:2, 23:3, 24:1, 25:2, 26:1, 27:2, 28:1, 30:3}
范围: 20 - 30
含 20-24 岁: 11 条
```

### 浏览器实测

```
下拉 12 项（11 年龄 + 随机）
选项: 随机 / 20岁 / 21岁 / ... / 30岁

选 20 岁生成：
  Wuthering Waves style二次元半写实厚涂，竖屏构图。20岁冷艳成熟女性，暖棕低马尾...

批量 10 条年龄：
  [20, 27, 24, 23, 20, 29, 22, 29, 20, 23]     ← 覆盖 20-29
```

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `skills/anime-thickpaint-oneesan-prompts/references/pools.json` | 年龄池 6 → 11 项 |
| `~/.dsh/skills/anime-thickpaint-oneesan-prompts/references/pools.json` | 同上（两份同步） |
| `skills/anime-thickpaint-oneesan-prompts/scripts/extract_pools.py` | 年龄固定生成 20-30；修 `build()` 的 src 参数 |
| `~/.dsh/skills/.../scripts/extract_pools.py` | 同上 |

---

## 提醒

**skill 文件有两份**，改的时候两边都要动：

| 位置 | 用途 |
|---|---|
| `J:\AmazingDraw\skills\` | 仓库内置，**WebUI 优先读这个** |
| `C:\Users\bagmh\.dsh\skills\` | 用户目录，agent 用这个 |

或者设环境变量 `AMAZINGDRAW_SKILLS_ROOT` 指定一个，避免混淆。

---

## 硬边界

年龄下限 **20 岁**，全部为成年角色。这个不会因为扩范围而放松 ——
`extract_pools.py` 里的注释也写明了「硬边界不低于 20 岁」。
