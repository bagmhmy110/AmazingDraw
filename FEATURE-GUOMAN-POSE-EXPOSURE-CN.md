# 姿势 + 裸露范围（exposure）

> 2026-11-15。给国漫 skill 加了两个新维度：**姿势**（构图 / 动作）和**裸露范围**（六档）。

![姿势与裸露范围](../docs-screenshots/guoman-pose-exposure.png)

---

## 裸露范围（六档）

档位语义对齐 AmazingDraw 引擎的 `exposure_mode`：

| 值 | 标签 | 含义 | 服装句怎么改 |
|---|---|---|---|
| `none` | 全遮（不漏） | 服装完整，无任何裸露信号 | 原七槽服装，不动 |
| `half_covered` | 擦边（半遮） | 湿身、透视、微露内衣，不露点 | 追加「衣料被水汽浸透…透出底下内衣的边线，却始终没有真正走光」 |
| `upper` | 露上（Topless） | 上身裸露，下身必须遮挡 | 上装褪到腰际 + 胸前无遮挡 + 下身仍被裙装裹住 |
| `lower` | 露下（Bottomless） | 下身裸露，上身必须遮挡 | 下身裙装褪至脚踝 + 上身仍被衣料包覆 |
| `half_nude` | 半裸（局部露点） | 保留服装结构（解开纽扣/滑落肩带），露一侧 | 衣襟解开大半 + 一侧肩带滑落 + 半边露出半边遮着 |
| `both` | 全裸（三点全露） | 上下全露，三点全露 | 去掉「身着X」+ 原衣物堆在脚边 + 三点完全裸露 |

### 设计原则

**裸露只改服装状态与身体叙事，不改人物脸/发/气质。** 换档不会让人物变成另一个人 ——
同一个 seed 下换 exposure，面部、发型、妆容、场景全部保持一致，只有身体部分变化。

每档配两段：
- `COSTUME_OVERRIDE` — 服装句替换
- `BODY_NOTE` — 身体句（追加在服装句后）

```python
"upper": (
    "{costume_head}"
    "上身衣物已褪到腰际，胸前毫无遮挡，乳房自然垂坠，"
    "腰腹以下仍被裙装严实裹住。"
),
```

```python
"upper": (
    "上身裸露的状态下，锁骨与肩线完全暴露，"
    "乳房随呼吸起伏，腰线因为下身衣物的收束显得更细。"
),
```

### 自动避让（防自相矛盾）

三处联动修正，避免写出「全身赤裸 + 轻纱层层飘动」这种病句：

| 档位 | 修正 |
|---|---|
| `both` | 不写「身着X」；动态词清空（衣物已褪，不能写「纱裙飘动」） |
| `upper` | 动态词含「袖/衣/纱/裙/披帛」时清空（上装已褪） |
| `both` / `lower` | 腿部句清空（避免与裸露句重复描述同一部位） |

---

## 姿势

两类型，同一个下拉里用 `[构图]` / `[动作]` 标记区分：

| 类型 | 示例 | 句式 |
|---|---|---|
| **构图** | 以半身特写姿态正面居中占据画面 | 「以X姿态…画面」 |
| **动作** | 侧卧于云石之上，一臂支颐，衣袂顺着身侧铺开 | 自带完整动词 |

每个调性 **13 条**（5 构图 + 8 动作），五调性合计 65 条（去重后 62）。

调性选「🎲 随机」时，姿势下拉合并所有调性的池子（62 条），否则只会剩「随机」一条 ——
这个坑踩过一次，见下方「踩坑记录」。

---

## 用法

### 界面

右侧导航 → 国漫 → 立绘成稿

- **姿势**：下拉选具体姿势，或留「🎲 随机」
- **裸露范围**：六档下拉，选完下方显示该档说明

### CLI

```bash
# 指定姿势 + 露上
python scripts/promptforge.py portrait --tone 仙侠 --scene 云海 \
  --pose "侧卧于云石之上，一臂支颐，衣袂顺着身侧铺开" --exposure upper

# 查可用姿势
python scripts/promptforge.py lookup --poses --tone 仙侠

# 查裸露档位
python scripts/promptforge.py lookup --exposures
```

### API

```bash
curl -X POST http://127.0.0.1:8318/api/guoman/portrait \
  -H 'Content-Type: application/json' \
  -d '{"tone":"仙侠","scene":"云海","exposure":"upper","pose":"侧卧于云石之上，一臂支颐，衣袂顺着身侧铺开"}'
```

`GET /api/guoman/meta` 现在额外返回：
- `exposures` — 六档的 value / label / desc
- `poses` — 每个调性的姿势列表

---

## 验证

### skill 层（CLI 逐档）

六档全部生成成功，服装句正确改写：

| 档位 | 实测服装句片段 |
|---|---|
| `none` | 身着灵蝶仙衣。云纹裙摆，上身为吊带设计…（原样） |
| `half_covered` | …衣料被水汽浸透，薄纱贴在皮肤上勾出轮廓，透出底下内衣的边线，却始终没有真正走光。 |
| `upper` | …上身衣物已褪到腰际，胸前毫无遮挡，乳房自然垂坠，腰腹以下仍被裙装严实裹住。 |
| `lower` | …下身裙装已褪至脚踝，双腿与胯部完全裸露，上身却仍被衣料层层包覆。 |
| `half_nude` | …衣襟已解开大半，一侧肩带滑落臂弯，半边胸脯露在光里，另一半仍被衣料遮着。 |
| `both` | 全身赤裸，未着寸缕。原本的灵蝶仙衣堆落在脚边，纱料还泛着微光。三点完全裸露… |

### UI 层（Chrome headless + CDP，19 项）

```
PASS  姿势下拉存在
PASS  有动作类姿势
PASS  有构图类姿势
PASS  裸露下拉存在
PASS  裸露 6 档
PASS  档位值正确（none/half_covered/upper/lower/half_nude/both）
PASS  默认全遮
PASS  档位提示存在
PASS  切换档位刷新提示
PASS  生成成功（416 字）
PASS  姿势生效
PASS  露上生效
PASS  身体句存在
PASS  无「身着」重复
PASS  切调性刷新姿势池
PASS  全裸档生效
PASS  全裸不说「身着」
PASS  全裸无衣物动态
```

（第 19 项断言写死「13 条」失败 —— 随机模式下合并成 62 条，是预期行为）

---

## 踩坑记录

### 坑 1：服装句重复「身着X」

第一版模板里写了 `"身着{style}。{costume}"`，但 `render_portrait` 外层已经拼好
`f"身着{p['风格款']}。"`，结果输出 `身着灵蝶仙衣。身着灵蝶仙衣。`。

**修**：模板只输出服装正文，不带 `身着` 前缀；`both` 档在渲染层单独处理（去掉前缀）。

### 坑 2：调性「随机」时姿势池为空

调性下拉第一项是 `__random__`（🎲 随机），默认就选它。
`fillPoseOptions()` 用 `state.meta.poses["__random__"]` 去查，查不到 → 池子空 → 只剩「随机」一条。

**修**：调性为 `__random__` 时合并所有调性的姿势并去重。

```javascript
if (tone === "__random__" || !allPoses[tone]) {
  const seen = new Set();
  for (const list of Object.values(allPoses)) {
    for (const p of list || []) {
      if (!seen.has(p)) { seen.add(p); pool.push(p); }
    }
  }
} else {
  pool = allPoses[tone] || [];
}
```

---

## 修改文件

| 文件 | 改动 |
|---|---|
| `scripts/exposure_profile.py` | **新增** 六档裸露定义 + 姿势扩展池 |
| `scripts/promptforge.py` | import EXP；`build_portrait` 接 pose/exposure；`render_portrait` 处理服装句与动态避让；CLI 加 `--pose` / `--exposure`；`lookup` 加 `--poses` / `--exposures` |
| `scripts/webui/api_guoman.py` | portrait 端点透传 pose/exposure；meta 返回 poses/exposures |
| `static/index.html` | 加姿势 / 裸露范围两个下拉 |
| `static/js/guoman.js` | 填充与联动逻辑 |
| `static/css/08-guoman.css` | 无需改动（复用现有 field 样式） |

### 内容边界

全部为成年虚构角色（18+）用途。skill 原有红线不变：
未成年角色零身材描写、服装限校服衬衫朴素裙装。
