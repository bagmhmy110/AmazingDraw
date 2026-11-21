# 当前工作流配置（2026-11-15 定版）

只保留你指定的五套。项目自带的 3 套（Moody Moss / Krea2 Turbo / ZIB+ZIT）和我之前加的测试流 `MyKrea2_Test` 已全部移除。

---

## 五套工作流

| ID | 名称 | 步数 | 底模 | 类型 |
|---|---|---|---|---|
| `moss50` | MOSS Image 50步加速 | 50 | `moss/moss_image_sft_int8_convrot` | 文生图 |
| `moss25` | MOSS Image 25步 | 25 | `moss/moss_image_sft_int8_convrot` | 文生图 |
| `krea4` | Krea2 4步极速 | 5 | `krea2/krea2_turbo_int8_convrot` | 文生图 |
| `qwen_edit` | Qwen Image 2.1 编辑 | 30 | `Qwen/qwen_image_2.1_int8_convrot` | **图生图** |
| `seedvr2` | SeedVR2 放大 | 1 | `seedvr2_7b_int8_convrot` | **图生图** |

**默认：`moss50`**

### 别名

```
moss / moss50 / moss-50  → moss50
moss25 / moss-25         → moss25
krea / krea4 / krea2     → krea4
qwen / qwen_edit / edit  → qwen_edit
seedvr2 / sr / upscale   → seedvr2
```

---

## 文件位置

| 内容 | 路径 |
|---|---|
| 工作流 JSON | `I:\ComfyUI-aki-v2\ComfyUI\workflows\{moss50,moss25,krea4,qwen_edit,seedvr2}.json` |
| 运行期配置 | `C:\Users\bagmh\.amazingdraw\config.json` |
| 出图目录 | `C:\Users\bagmh\Downloads\card-engine-out` |

---

## 用法

```bash
cd /j/AmazingDraw

# 用默认（moss50）
J:/Python312/python.exe scripts/gpu-pipeline/cu-draw-card.py \
  --prompt "你的提示词" --width 768 --height 1152

# 指定工作流
J:/Python312/python.exe scripts/gpu-pipeline/cu-draw-card.py \
  --mode krea4 --prompt "..." --width 768 --height 1024

# 走队列（带失败重试/自愈）
bash scripts/gpu-pipeline/cu-submit.sh --raw --prompt "..." --workflow krea4
```

---

## 已实测出图

| 工作流 | 状态 | 输出 |
|---|---|---|
| `moss50` | ✅ | `Moss50_00001_.png`（784×1184） |
| `moss25` | ✅ | `Moss25_00001_.png` |
| `krea4` | ✅ | `Krea4_00002_.png`（800×1056，质量好） |
| `qwen_edit` | ⚠️ 需输入图 | 见下 |
| `seedvr2` | ⚠️ 需输入图 | 见下 |

---

## 图生图两套的注意点

这两套不是文生图，**必须先有输入图**。

### `qwen_edit`

- 提示词节点是 `PrimitiveStringMultiline@501`，输入键是 **`value`** 不是 `text`（配置里已用 `prompt_input_key: value`）
- 正向实际走 `TextEncodeQwenImage21@497`，它从 `501` 取 prompt
- 输入图两个：`LoadImage@475`（`pasted/image (7).png`）和 `LoadImage@725`（`QW21-...png`）—— **这两个文件当前都不存在**
- 用法：把图放进 `I:\ComfyUI-aki-v2\ComfyUI\input\`，然后改 JSON 里的 `image` 字段

### `seedvr2`

- 无提示词节点（`prompt_nodes: []`），放大流不需要 prompt
- 输入图：`LoadImageOutput@152`，当前指向 `Moss-20261024232309_00001_.png [output]` —— **这个文件存在**
- 所以 seedvr2 现在就能直接跑，放大 `output` 目录里的那张图
- 要换图：改 `152.inputs.image` 为 `你的文件名.png [output]`（output 目录）或改用 `LoadImage`（input 目录）

---

## 引擎改动（为了这五套）

原版引擎有三处硬编码会卡住这些工作流，已修：

| 位置 | 问题 | 修法 |
|---|---|---|
| `cu-draw-card.py` prompt 注入 | 硬编码 `inputs["text"]` | 新增 `prompt_input_key` 配置项（`qwen_edit` 用 `value`） |
| `cu-draw-card.py` negative 注入 | 硬编码 `inputs["text"]` | 新增 `negative_input_key` |
| `cu-draw-card.py` 画幅注入 | 只认 `width`/`height` | 新增 `size_node_kind: "resolution"`，支持 `ResolutionSelector`（按宽高比挑档位 + 算 megapixels） |
| `cu-draw-card.py` LoRA 注入 | 只认 `LORA_1` 单槽 | 新增 `lora_input_key: "lora_slots"`，支持新版 `Power Lora Loader` 的 `lora_1..lora_N` 槽位 |

`krea4` 用了最后一项：`Power Lora Loader@380` 有 50 个明星 LoRA 槽位（全 `on:false`），引擎会找第一个空槽写入。

---

## 新增配置字段说明

| 字段 | 取值 | 说明 |
|---|---|---|
| `prompt_input_key` | `text` / `value` | prompt 节点的输入键名，默认 `text` |
| `negative_input_key` | `text` / `value` | 负向词节点的输入键名，默认 `text` |
| `size_node_kind` | `latent` / `resolution` | `latent`=直接写 width/height；`resolution`=改 ResolutionSelector 的 aspect_ratio+megapixels |
| `lora_input_key` | `lora_name` / `lora_slots` / `LORA_1` | `lora_name`=LoraLoader 类；`lora_slots`=新版 PowerLoraLoader（`lora_1..N`）；`LORA_1`=旧版 |
| `requires_input_image` | `true` | 标记图生图，仅文档用途 |

---

## 备份

替换前的配置备份在 `C:\Users\bagmh\.amazingdraw\config.json.bak-replace-*` 和 `.bak-before-mywf`。
