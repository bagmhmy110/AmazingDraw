# 国漫 Skill 接入 WebUI

> 2026-11-15。把 `guoman-costume-xianxia-prompts` 的 promptforge 引擎接进 AmazingDraw WebUI，
> 右侧导航栏多了一个「国漫」入口。

![国漫立绘](../docs-screenshots/guoman-ui.png)

---

## 用起来

右侧竖排导航 → **国漫**（Guoman）

两种模式：

| 模式 | 产出 |
|---|---|
| **立绘成稿** | 完整人像提示词（人 + 衣），**可锁定服装槽位** |
| **批量生产** | 一次 N 条，带去重与禁词自检 |

![国漫界面](../docs-screenshots/guoman-merged.png)

> 早期版本有独立的「服装装配」模式（线 D，只要衣服不要人）。
> 现在已并入立绘成稿的「服装槽位」折叠区 —— 需要纯服装提示词时，
> 直接调 API `POST /api/guoman/combo` 仍然可用。

### 立绘成稿

- **调性**：🎲 随机 / 仙侠 / 宫廷 / 战斗 / 暗黑 / 新中式（切换时下方会显示该调性的配色材质气质）
- **场景**：🎲 随机 / 20 个（云海、亭台、夜市、宫殿、废墟、庭院、悬崖、戈壁、暗室、桃花源、樱林、水榭、石窟、竹林、花船、藏书阁、道观、镜湖、雪寺、雪山）
- **露腿分级**：不露腿 / 含蓄 / 大胆
- **种子**：留空随机
- **服装槽位**（折叠，默认收起）：配色 / 材质 / 纹样 / 袖型 / 裙装 / 腰部 / 肩部

选「🎲 随机」时，服务端在每次请求里重新抽一个具体值，提示词下方会说明抽取范围
（如「从 5 个调性里随机：仙侠 / 宫廷 / 战斗 / 暗黑 / 新中式」）。

**服装槽位**留「随机」的槽由引擎按调性抽取；锁定后该槽不再随机，直接写进提示词。
折叠标题上会显示「已锁 N 槽」角标，旁边有「全部清空」按钮。

点「生成提示词」→ 出完整提示词 + 可折叠的「选中元素拆解」（22 项，方便微调）。

生成后**卡片右上角有「⚡ 生成图片」按钮** —— 点它就把这条提示词直接投递到 GPU 队列，
投递成功后按钮变成「已投递」，出图自动进 WebUI 卡片列表。

![生成图片按钮](../docs-screenshots/guoman-render-btn.png)

顶部工具栏的「生成并出图」是「生成 + 投递」一步到位；卡片上的按钮则是
「先看提示词满意了再出图」，两种都有。

### 批量生产

- **条数**：1~500
- **调性池** / **场景池**：逗号分隔
- 脚本内置：禁词校验、完整句去重、`(风格款×场景×姿态)` 三元组去重、五调性均衡
- **每条结果都有自己的「⚡ 生成图片」按钮**，带该条的调性/场景元数据，可以只挑满意的几条出图

---

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/guoman/meta` | 调性 / 场景 / 七槽 / 渲染风格选项 |
| GET | `/api/guoman/combos?tone=仙侠` | 某调性的七槽可选词 |
| POST | `/api/guoman/portrait` | 生成立绘，**支持 `slots` 锁服装槽位** |
| POST | `/api/guoman/combo` | 纯服装提示词（保留的兼容端点） |
| POST | `/api/guoman/batch` | 批量生成 |
| POST | `/api/guoman/direct` | 投递到 GPU 队列（传 prompt 直投 / 不传则先生成） |

### 请求示例

```bash
# 基础：只要人物
curl -X POST http://127.0.0.1:8318/api/guoman/portrait \
  -H 'Content-Type: application/json' \
  -d '{"tone":"仙侠","scene":"云海","leg":"mild","seed":42,"pick":true}'

# 锁服装槽位：配色和袖型固定，其余随机
curl -X POST http://127.0.0.1:8318/api/guoman/portrait \
  -H 'Content-Type: application/json' \
  -d '{"tone":"仙侠","scene":"云海","slots":{"color":"月白与银灰","sleeve":"凤凰羽袖"}}'
```

响应：

```json
{
  "ok": true,
  "tone": "仙侠",
  "scene": "云海",
  "prompt": "一位东方仙侠风格的绝美女子以倚栏姿态半坐于画面右侧，...",
  "breakdown": "  风格标签: 东方仙侠风格\n  人物修饰: 绝美女子\n  ...",
  "raw": "..."
}
```

`slots` 的 key：`color` / `fabric` / `pattern` / `sleeve` / `skirt` / `waist` / `shoulder`。
也可用扁平写法 `{"color":"月白与银灰"}`（向后兼容）。

### 直接出图

```bash
# 方式一：生成并投递（一步到位）
curl -X POST http://127.0.0.1:8318/api/guoman/direct \
  -H 'Content-Type: application/json' \
  -d '{"tone":"暗黑","scene":"废墟","leg":"bold","workflow":"moss50"}'

# 方式二：投递一条现成提示词（卡片「生成图片」按钮走这条）
curl -X POST http://127.0.0.1:8318/api/guoman/direct \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"一位东方仙侠风格的绝美女子……","tone":"仙侠","scene":"云海"}'
```

响应里带 `job_id` / `card_id`，出图后卡片会自动出现在 WebUI。

### 随机值

`tone` / `scene` 传 `__random__` 时由服务端抽具体值（每次请求重新抽）：

```bash
curl -X POST http://127.0.0.1:8318/api/guoman/portrait \
  -H 'Content-Type: application/json' \
  -d '{"tone":"__random__","scene":"__random__","pick":true}'
```

响应里会回填实际用到的 `tone` / `scene`。

---

## 实现要点

### skill 目录探测

```python
_SKILL_DIR_CANDIDATES = (
    os.environ.get("AMAZINGDRAW_GUOMAN_SKILL"),
    "~/.dsh/skills/guoman-costume-xianxia-prompts",
    "~/.claude/skills/guoman-costume-xianxia-prompts",
)
```

找不到时所有接口返回 **503 + 可读原因**，不影响 WebUI 其他功能。界面顶部会显示「skill 未安装」徽章。

### 子进程隔离

promptforge.py 有自己的 `sys.path` 假设（依赖 `scripts/` 下的同级模块），
所以在子进程里跑，`cwd` 设为 skill 根目录，避免污染 WebUI 进程。

### `--pick` 输出解析

promptforge 的 `--pick` 模式结构是：

```
【选中元素】
  风格标签: ...
  ...
【完整提示词】
<正文>
```

解析函数：

```python
def _split_pick(raw):
    if "【选中元素】" in raw and "【完整提示词】" in raw:
        head, _, body = raw.partition("【完整提示词】")
        return {"prompt": body.strip(),
                "breakdown": head.replace("【选中元素】", "", 1).strip() or None}
    return {"prompt": raw.strip(), "breakdown": None}
```

第一版我按「第一段是正文」解析，结果把拆解当成了提示词。这个坑记下来。

### 编码

skill 脚本输出中文，子进程必须强制 UTF-8：

```python
env["PYTHONUTF8"] = "1"
env["PYTHONIOENCODING"] = "utf-8"
```

否则 Windows 下 `subprocess` 默认按 GBK 解码，直接 `UnicodeDecodeError`。

---

## 验证

### API 层（27 项断言）

```
[1] meta          4/4   available / 5 调性 / 20 场景 / 七槽
[2] combos        5/5   五个调性都能查到七槽词
[3] portrait      5/5   五调性 × 场景生成成功（374~420 字）
[4] pick 解析     5/5   正文非空 / 不含拆解标记 / 拆解含槽位标签
[5] combo         2/2   生成成功 / 含服装结构
[6] 锁槽位        1/1   指定配色生效
[7] batch         5/5   10 条 / 无重复 / 多调性均衡
```

### UI 层（Chrome headless + CDP，34 项断言）

基础视图 20 项：

```
PASS  视图 DOM 存在
PASS  导航按钮存在
PASS  三个模式按钮
PASS  七槽下拉存在
PASS  initGuoman 已暴露
PASS  切视图后 active
PASS  skill 徽章就绪
PASS  调性选项 5 个（+随机 = 6）
PASS  场景选项 20 个（+随机 = 21）
PASS  调性提示非空
PASS  立绘生成成功（402 字）
PASS  拆解区存在（533 字）
PASS  状态显示成功
PASS  服装模式显示七槽
PASS  服装模式隐藏出图按钮
PASS  七槽下拉已填充（10~18 词/槽）
PASS  服装生成成功（163 字）
PASS  批量生成 5 条
PASS  批量有标签
PASS  调性切换刷新词库
```

随机 + 生成图片按钮 14 项：
合并服装装配 17 项（本次）：

```
PASS  模式按钮只剩 2 个（立绘成稿 / 批量生产）
PASS  模式为 portrait + batch
PASS  服装槽位折叠区存在
PASS  立绘模式下槽位区可见
PASS  批量模式下批量区可见
PASS  七槽下拉齐全
PASS  折叠标题含说明（「服装槽位（可选 · 锁定后该槽不再随机）」）
PASS  配色选项含「月白与银灰」
PASS  袖型选项含「凤凰羽袖」
PASS  角标显示「已锁 2 槽」
PASS  生成成功（408 字）
PASS  提示词含锁定配色
PASS  提示词含锁定袖型
PASS  清空按钮生效
PASS  清空后角标消失
PASS  批量模式隐藏槽位区
PASS  批量模式显示批量参数
```

```
PASS  调性有随机选项（__random__ / 🎲 随机）
PASS  调性随机文案含🎲
PASS  场景有随机选项
PASS  场景随机文案含🎲
PASS  随机提示说明文案（「从 5 个调性里随机：…」）
PASS  随机生成全部成功（3 次连抽到 仙侠/暗黑/宫廷 三种调性）
PASS  卡片有生成图片按钮
PASS  按钮文案正确
PASS  按钮携带完整提示词（414 字）
PASS  投递成功（状态「已投递 · job job-107b7af9」）
PASS  按钮变为「已投递」
PASS  批量每条都有生成图片（4/4）
PASS  批量按钮带调性
PASS  批量按钮带场景
```

**51/51 通过。**（34 项基础 + 17 项合并验证）

---

## 修改文件

| 文件 | 说明 |
|---|---|
| `scripts/webui/api_guoman.py` | **新增** 后端 API（6 个端点，支持 `__random__`） |
| `scripts/webui/web_server.py` | 注册 guoman_router |
| `static/index.html` | 加 `view-guoman` 视图 + 导航按钮 + 引入 CSS/JS |
| `static/js/guoman.js` | **新增** 前端逻辑（随机选项、卡片内生成图片） |
| `static/css/08-guoman.css` | **新增** 样式（含 primary 按钮） |
| `static/js/shell.js` | `switchView` 支持 guoman |

---

## 已知限制

- **批量上限 500**：脚本本身支持更多，但 WebUI 一次渲染太多列表会卡，要更多建议走 CLI。
- **渲染风格（`--render`）没做进 UI**：扩展 profile（hk80s / real / sweet / gauze）只在 API 层支持，界面暂时固定 `clean`。要加的话在 `guoman-params` 里补个下拉。
- **`--style` 指定风格款没做进 UI**：`meta.style_variants` 目前返回空（tone_profile 里没暴露这个字典），所以下拉没填。要支持得先在 skill 侧暴露 `STYLE_VARIANT`。

---

## Skill 侧改动

界面合并要求 portrait 子命令支持服装槽位锁词，原版只有 combo 有。
已给 skill 的 promptforge.py 补上：

```python
# portrait 新增七个参数
p3.add_argument("--color", help="指定配色，如 墨黑与暗金")
p3.add_argument("--fabric", help="指定材质")
p3.add_argument("--pattern", help="指定纹样")
p3.add_argument("--sleeve", help="指定袖型")
p3.add_argument("--skirt", help="指定裙装结构")
p3.add_argument("--waist", help="指定腰部")
p3.add_argument("--shoulder", help="指定肩部")
```

```python
# cmd_portrait 里转成 want 传给 build_portrait
want = {}
for slot, attr in (("配色", "color"), ("材质", "fabric"), ("纹样", "pattern"),
                   ("袖型", "sleeve"), ("裙装结构", "skirt"),
                   ("腰部", "waist"), ("肩部", "shoulder")):
    val = getattr(args, attr, None)
    if val:
        want[slot] = val
p = build_portrait(d, rng, args.tone, scene, args.leg, args.style,
                   want=want, render=args.render)
```

uild_portrait 本来就支持 want 参数（ssemble() 里优先取锁定值），
只是 cmd_portrait 没往下传。

CLI 现在也能直接锁：

```bash
python scripts/promptforge.py portrait --tone 仙侠 --scene 云海 \
  --color 月白与银灰 --sleeve 凤凰羽袖
```