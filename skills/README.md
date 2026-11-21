# Skills

AmazingDraw 集成的六个提示词 skill。每个 skill 都是独立的目录，包含 `SKILL.md`（调度中心）+ `references/`（词库）+ `scripts/`（可选脚本）。

---

## 目录

| 目录 | 页面 | 说明 |
|---|---|---|
| `guoman-costume-xianxia-prompts/` | 国漫 | 七槽服装装配 + 古风仙侠立绘 |
| `guoman-portrait-prompts/` | 国漫人像 | 四条风格线（二次元厚涂 / 古风仙侠 / 写实CCD / 高定服装） |
| `moss-image-prompt-architect/` | MOSS | MOSS-Image 架构师（Caption / Layout） |
| `nsfw-prompt-templates-asian/` | 模板 | 14 模块按序组装 |
| `adult-photorealistic-prompt-style-21/` | 写实 | 四类语料（情趣时尚 / 都市纪实 / 汉服舞台 / 瑜伽体操） |
| `anime-thickpaint-oneesan-prompts/` | 厚涂 | Wuthering Waves 二次元半写实厚涂 · 七大词池 |

---

## 安装

WebUI 默认从这几个位置找 skill：

```
~/.dsh/skills/
~/.workbuddy-ai/skills/
~/.claude/skills/
~/.codex/skills/
```

**方式一：复制到用户目录**

```bash
mkdir -p ~/.dsh/skills
cp -r skills/* ~/.dsh/skills/
```

Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.dsh\skills"
Copy-Item "skills\*" "$env:USERPROFILE\.dsh\skills\" -Recurse -Force
```

**方式二：直接用仓库内的路径**

设环境变量指向仓库：

```bash
export AMAZINGDRAW_SKILLS_ROOT=/path/to/AmazingDraw/skills
```

Windows：

```powershell
$env:AMAZINGDRAW_SKILLS_ROOT = "J:\AmazingDraw\skills"
```

> 注意：`AMAZINGDRAW_SKILLS_ROOT` 只影响 `skill_dir()` 的探测顺序，
> 部分老路径（如 `AMAZINGDRAW_GUOMAN_SKILL`）是单独的变量。

---

## 边界

全部 skill 都用于**成年虚构角色（18+）**的图像生成。

- 未成年角色（< 18 岁）**零身材描写**，服装限校服、衬衫、朴素裙装 —— 这是硬边界
- 不用于现实具体人物的性化图像
- 除上述两条，词库全部内容按原样使用，不做删改与软化

---

## 各 skill 的词池规模

| skill | 词条数 |
|---|---|
| 国漫（服装装配） | 1100+ 七槽组合词 + 31 仙侠范例 |
| 国漫人像 | 1800+ 选词 + 1200 服装词 |
| MOSS | 纯指令型（无词库，靠 LLM） |
| 模板 | 1454 条（14 模块） |
| 写实 | 四类语料（纯指令型） |
| 厚涂 | 650 服装 + 100 发型 + 100 姿态 + 100 场景 |

---

## 单独用 CLI

每个带脚本的 skill 都能脱离 WebUI 直接用：

### 国漫（服装装配）

```bash
cd guoman-costume-xianxia-prompts/scripts
python promptforge.py portrait --tone 仙侠 --scene 云海 --seed 42
python promptforge.py lookup --poses --tone 仙侠
python promptforge.py lookup --exposures
python promptforge.py batch -n 50 -o prompts.txt --json prompts.json
```

### 国漫人像

```bash
cd guoman-portrait-prompts/scripts
python generate.py -n 100 -o prompts.txt --json prompts.json --seed 2024
```

### 厚涂御姐

```bash
cd anime-thickpaint-oneesan-prompts/scripts
python generate.py -n 100 -o prompts.txt --json prompts.json --seed 2024
python generate.py -n 20 --style guoman3d          # 指定风格
python generate.py -n 20 --include-cultivation     # 启用修仙池
python generate.py -n 20 --with-stockings 0.6      # 60% 丝袜概率
python generate.py -n 20 --category 传统旗袍,迷你旗袍
```

### 词池重建（厚涂）

`pools.json` 已随仓库提供，一般不用重跑。需要更新时：

```bash
cd anime-thickpaint-oneesan-prompts/scripts
python extract_pools.py                            # 读 ../source-rules.md
python extract_pools.py --src 别的文档.md -o 输出.json
```

---

## 依赖

- Python 3.9+（推荐 3.12）
- 纯标准库，无第三方依赖

MOSS 与写实两个 skill 是纯指令型，没有脚本，靠 LLM 执行 `SKILL.md` 里的规则。
