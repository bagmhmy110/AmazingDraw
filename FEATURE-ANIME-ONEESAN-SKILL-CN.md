# 新 skill：二次元厚涂御姐

> 2026-11-15。把 `提示词规则_二次元厚涂御姐_agent版(1).md` 做成独立 skill 并接进 WebUI。
> 导航新增「厚涂 · Oneesan」。

![厚涂御姐](../docs-screenshots/anime-oneesan.png)

---

## Skill 结构

```
~/.dsh/skills/anime-thickpaint-oneesan-prompts/
├── SKILL.md                    4.3 KB   调度中心
├── references/
│   └── pools.json            148.4 KB   七大词池（结构化）
└── scripts/
    ├── extract_pools.py        5.4 KB   从原文档抽词池
    └── generate.py             6.8 KB   批量生成
```

---

## 词池规模

| 池 | 数量 |
|---|---|
| 年龄 | 6（25-30 岁） |
| 气质 | 6（成熟御姐 / 冷艳御姐 / 风情成熟女性…） |
| **发型** | **100** |
| **服装** | **650**（7 类） |
| 性感动词 | 10 |
| **姿态** | **100** |
| **场景** | **100** |
| 光影 | 96 |
| 吊带丝袜 | 5 |

### 服装 7 类

| 类别 | 条数 |
|---|---|
| 传统旗袍 | 118 |
| 迷你旗袍 | 100+ |
| 迷你礼裙 | 100+ |
| 迷你包臀裙 | 100+ |
| 长款礼裙 | 100+ |
| 修仙女装（扩展） | 100 |
| 修仙迷你女装（扩展） | 50 |

---

## 固定骨架

```
Wuthering Waves style二次元半写实厚涂，竖屏构图。
{年龄}{气质}，{发型}。
身着{服装}，{细节}，精致的东方面容。{性感动词}。{姿态}。
场景：{场景}。{光影}。
```

### 硬性规则

- 必含 **`精致的东方面容`**
- 禁词 6 个：九宫格 / 渔网 / 青涩 / 大波浪发型 / 机顶直闪 / 皮肤白皙细腻如瓷
- 形容腿时禁「白皙」
- 丝袜只允许「吊带丝袜」一种写法，默认 40% 概率加点

---

## 抽取时踩的坑：场景光影必须配对

原文档里场景和光影是**配对**写的：

```
山间古寺台阶，青石板落松针，山门半掩 | 晨雾晨光
雪后庭院，屋脊积雪未化，檐下冰棱       | 冷白天光
```

我第一版拆成两个独立池随机组合，结果出现：

> 场景：**雪后庭院**，屋脊积雪未化，檐下冰棱。**暖黄咖啡馆**。
> 场景：**江边木质栈道**，夕阳斜照，水波粼粼。**晨光穿透云隙**。

完全错配。

**修法**：抽取时保留 `scene_pairs`，生成时成对取：

```python
if p.get("scene_pairs"):
    pair = rng.choice(p["scene_pairs"])
    scene, light = pair["scene"], pair["light"]
```

修后：

```
雪后庭院 → 冷白天光        ✅
高山瀑布观景台 → 清澈天光   ✅
城市高架桥夜景 → 蓝紫霓虹   ✅
海滨灯塔 → 黄昏余晖         ✅
```

---

## WebUI 页面

13 个下拉，全部来自词池：

| 排 | 下拉 |
|---|---|
| 1 | 年龄 · 气质 · 发型 |
| 2 | 服装类别 · 服装 · 丝袜概率 |
| 3 | 性感动词 · 姿态 |
| 4 | 场景 · 光线 |
| 5 | 人种 · 身材 · 表情气质 |

加一个「启用修仙扩展池」开关。

### 服装类别 → 服装 联动

选「传统旗袍」→ 服装下拉从 651 缩到 101 条（含「随机」项）。

### 丝袜概率档

不加 / 20% / 40%（默认）/ 60% / 80% / 100%

---

## API

| 端点 | 用途 |
|---|---|
| `GET /api/anime-oneesan/meta` | 词池 + 类别 + 丝袜档 |
| `POST /api/anime-oneesan/generate` | 单条（代码拼装，不走 LLM） |
| `POST /api/anime-oneesan/batch` | 批量（调 generate.py） |
| `POST /api/anime-oneesan/polish` | LLM 润色（保留骨架与必含词） |

**单条不走 LLM** —— 词池拼装已经足够，且能保证 100% 符合骨架与禁词规则。

### 请求示例

```json
{
  "age": "26岁",
  "temper": "冷艳御姐",
  "hair": "紫罗兰长发自然披散，微卷垂落",
  "category": "传统旗袍",
  "outfit": "紧身水墨渐变旗袍，单侧高开叉至大腿根部",
  "stockings": 0.6,
  "sexy": "高开叉至大腿根部露出修长双腿，勾勒玲珑曲线",
  "pose": "斜倚宫灯柱，一手撩拨发丝，微微歪头",
  "scene": "竹林禅院青石台阶，细竹摇影，薄雾轻浮",
  "light": "晨雾晨光",
  "include_cultivation": false
}
```

任一项留空则随机。

---

## CLI

```bash
cd ~/.dsh/skills/anime-thickpaint-oneesan-prompts/scripts

# 基础
python generate.py -n 100 -o prompts.txt --json prompts.json --seed 2024

# 限定服装类别
python generate.py -n 50 --category 传统旗袍,迷你旗袍

# 启用修仙池 + 60% 丝袜
python generate.py -n 20 --include-cultivation --with-stockings 0.6

# 完全不加丝袜
python generate.py -n 10 --no-stockings
```

自检输出：

```
[自检] 产出 5 条 / 禁词违规 0 条 / 丝袜 1 条（20%）
[分布] 传统旗袍:1 · 迷你旗袍:1 · 迷你礼裙:1 · 迷你包臀裙:1 · 长款礼裙:1
```

五类自动均衡轮换。

---

## 验证（20/20）

```
PASS  视图存在 / 导航入口存在 / init 函数已暴露
PASS  视图 active / display 是 flex
PASS  skill 就绪 / 规则提示显示
PASS  下拉 13 个
PASS  年龄 6 项 / 发型 101 / 场景 101 / 姿态 101
PASS  服装类别 2 组（主线 + 修仙）
PASS  其他视图隐藏
PASS  服装联动生效（651 → 101）
PASS  生成成功（166 字）
PASS  含 Wuthering Waves
PASS  含 精致的东方面容
PASS  无禁词
PASS  批量 5 条
```

---

## 生成的提示词示例

> Wuthering Waves style二次元半写实厚涂，竖屏构图。**26岁冷艳御姐**，
> **紫罗兰长发自然披散，微卷垂落**。身着**紧身水墨渐变旗袍，单侧高开叉至大腿根部**，
> **修长双腿罩着吊带丝袜**，**精致的东方面容**。
> **高开叉至大腿根部露出修长双腿，勾勒玲珑曲线**。
> **斜倚宫灯柱，一手撩拨发丝，微微歪头**。
> 场景：**竹林禅院青石台阶，细竹摇影，薄雾轻浮**。**晨雾晨光**。

骨架、必含词、禁词、场景光影配对全部符合。

---

## 一个坑：改了 shell.js 要提版本号

新视图加进 `shell.js` 的 `switchView` 分发后，浏览器还是加载旧版 —— 因为
`<script src="js/shell.js?v=1.11.3">` 的版本号没变，缓存命中。

**改任何 JS 都要同步提 `index.html` 里的 `?v=`。**

这次是 `shell.js?v=1.11.3` → `v=1.12.0` 才生效。

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `~/.dsh/skills/anime-thickpaint-oneesan-prompts/` | **新增** skill（SKILL.md + pools.json + 两个脚本） |
| `scripts/webui/api_anime_oneesan.py` | **新增** API |
| `scripts/webui/web_server.py` | 注册 router |
| `static/js/anime-oneesan.js` | **新增** 前端逻辑 |
| `static/index.html` | 视图 + 导航 + JS 引用 |
| `static/js/shell.js` | switchView 分发 |
| `static/css/09-prompt-skills.css` | `.active` 显示规则 |

### 现在一共 6 个 skill 页面

| 导航 | Skill |
|---|---|
| 国漫 | guoman-costume-xianxia-prompts |
| 国漫人像 | guoman-portrait-prompts |
| MOSS | moss-image-prompt-architect |
| 模板 | nsfw-prompt-templates-asian |
| 写实 | adult-photorealistic-prompt-style-21 |
| **厚涂** | **anime-thickpaint-oneesan-prompts** |
