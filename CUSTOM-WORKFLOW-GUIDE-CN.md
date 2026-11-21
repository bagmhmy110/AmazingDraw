# 接入自己的工作流（AmazingDraw）

> 一句话：**把 ComfyUI 的 UI JSON 放进 `{ComfyUI}/workflows/`，然后在 `~/.amazingdraw/config.json` 的 `workflows` 里加一段元数据，告诉引擎哪个节点是 prompt / 种子 / 画幅。**

不需要改任何 Python 代码。转换器（UI → API）是通用的，靠节点 ID 定位。

---

## 三步走

### 第 1 步：保存工作流

在 ComfyUI 里调好图，`Save`（Ctrl+S），存到：

```
I:\ComfyUI-aki-v2\ComfyUI\workflows\你的名字.json
```

**硬性要求：**

- 必须有 **`SaveImage` 节点**（不是 `PreviewImage`）。引擎靠它找输出文件。
- UI 格式（有 `nodes[]` + `links[]`）或 API 格式都行，引擎自动识别。
- 节点不要用 `mode=4`（静音）包住关键节点，否则转换后会缺。

### 第 2 步：找出 4 类关键节点的 ID

打开 JSON，找这几种节点，记下 `id`：

| 字段 | 节点类型 | 作用 |
|---|---|---|
| `prompt_nodes` | `CLIPTextEncode` | 正向提示词注入点 |
| `negative_nodes` | `CLIPTextEncode` | 负向提示词（没有就留空数组） |
| `seed_nodes` | `KSampler` / `KSamplerAdvanced` / `Seed (rgthree)` | 种子注入 |
| `size_nodes` | `EmptyLatentImage` / `EmptySD3LatentImage` | 画幅注入 |

**怎么确认哪个 CLIPTextEncode 是正向？** 看 `links` 数组，找到连到 `KSamplerAdvanced` 的 `positive` 槽位的那个。

命令行快速查（PowerShell，UTF-8）：

```powershell
$env:PYTHONUTF8="1"
& "J:\Python312\python.exe" -c @"
import json
f = r'I:\ComfyUI-aki-v2\ComfyUI\workflows\你的名字.json'
d = json.load(open(f, encoding='utf-8'))
for n in d['nodes']:
    if not isinstance(n, dict): continue
    t = n.get('type','')
    if t in ('CLIPTextEncode','KSampler','KSamplerAdvanced','EmptyLatentImage','SaveImage','Seed (rgthree)','LoraLoaderModelOnly','UNETLoader','CLIPLoader','VAELoader'):
        print(f\"id={n.get('id'):>4} mode={n.get('mode',0)} {t:24s} {str(n.get('widgets_values'))[:70]}\")
"@
```

### 第 3 步：写进配置

编辑 `C:\Users\bagmh\.amazingdraw\config.json`，在 `workflows` 里加一段：

```json
"workflows": {
  "my_flow": {
    "name": "我的工作流 · 显示名",
    "workflow_path": "workflows/你的名字.json",
    "filename_prefix": "MyFlow",
    "prompt_nodes": ["627"],
    "negative_nodes": [],
    "negative_text": "",
    "lora_nodes": ["854"],
    "seed_nodes": ["851"],
    "size_nodes": ["698"],
    "seed_type": "standard",
    "deforum_fix": false,
    "link_key": "links",
    "node_key": "nodes",
    "prompt_style": "photorealistic_portrait",
    "description": "备注",
    "lora_subdir": "girls_like_krea2",
    "lora_input_key": "lora_name",
    "node_input_overrides": {},
    "default_steps": 8,
    "default_width": 768,
    "default_height": 1152,
    "resolution_presets": {
      "vertical":   {"width": 768,  "height": 1152},
      "horizontal": {"width": 1152, "height": 768},
      "square":     {"width": 1024, "height": 1024}
    }
  }
}
```

**字段说明：**

| 字段 | 必填 | 说明 |
|---|---|---|
| `workflow_path` | ✅ | 相对 `{comfyui_dir}` 或绝对路径；也支持 `{comfyui_dir}` 占位符 |
| `filename_prefix` | ✅ | 引擎会改写 SaveImage 的 prefix，靠它找输出文件。**别和别的流撞名** |
| `prompt_nodes` | ✅ | 数组，可多个 |
| `seed_nodes` | ✅ | `KSamplerAdvanced` 的 `seed` 是 `noise_seed`；`Seed (rgthree)` 的 `seed_type` 要写 `rgthree` |
| `size_nodes` | ✅ | 留空数组时引擎会自动找带 `width`+`height` 输入的节点 |
| `lora_nodes` | 可选 | 要挂明星 LoRA 才需要 |
| `lora_input_key` | 可选 | `LORA_1`（PowerLoraLoader）或 `lora_name`（LoraLoader / LoraLoaderModelOnly） |
| `lora_subdir` | 可选 | LoRA 相对 `models/loras/` 的子目录 |
| `negative_text` | 可选 | 会写进 `negative_nodes` 的 text |
| `node_input_overrides` | 可选 | `{"节点ID": {"cfg": 2.5}}`，强制覆盖任意输入 |
| `static_loras` | 可选 | `{"节点ID": "路径.safetensors"}`，固定挂载不随机 |

### 第 4 步：验证

```bash
cd /j/AmazingDraw
# 先看能不能解析（会校验节点 ID 是否存在）
J:/Python312/python.exe scripts/gpu-pipeline/cu-draw-card.py \
  --mode my_flow \
  --prompt "test prompt" \
  --width 768 --height 1152
```

报 `引用了不存在的节点: prompt_nodes -> 5` 就是 ID 写错了，回去查。

---

## 切换默认工作流

⚠️ **`card_cli.py workflow --set` 只认内置的 `zi` / `krea` / `moss`**，自定义流会报「未知工作流」。

自定义流要直接改配置：

```powershell
$env:PYTHONUTF8="1"
& "J:\Python312\python.exe" -c @"
import json
p = r'C:\Users\bagmh\.amazingdraw\config.json'
c = json.load(open(p, encoding='utf-8'))
c['default_workflow'] = 'my_flow'
json.dump(c, open(p,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
"@
```

单次指定：`cu-draw-card.py --mode my_flow ...` 或 `card_cli.py direct --workflow my_flow ...`

---

## 你这台机器的现状（2026-11-15 实测）

### 已有的模型（ComfyUI 实际可见）

| 家族 | 目录 | 文件 |
|---|---|---|
| Krea2 | `models/diffusion_models/krea2/` | 15 个，含 `krea2_turbo_fp8_scaled`、`Krea2-Moody-Mix-premium_int8_convrot`、`Krea2-大师pornmasterKrea2_v2_fp8` |
| MOSS | `models/diffusion_models/moss/` | `moss_image_sft_bf16`、`moss_image_sft_int8_convrot` |
| Qwen Image | `models/diffusion_models/Qwen/` | 5 个，含 `qwen_image_2.1_int8_convrot` |
| Flux2-Klein | `models/diffusion_models/flux-2-klein/` | 4 个 |
| H3 / LTX2.3 | 各自子目录 | 视频模型 |

### 你的工作流为什么都跑不了

**所有指向 `zimage\` 或 `z_image\` 子目录的工作流都是坏的** —— 那个目录已经不存在了，模型被重新组织到 `krea2/` `moss/` 等子目录。

| 工作流 | 缺的模型 |
|---|---|
| `Moody Zimage Simple Workflow - V6` | `zimage\mood-porn-v10.safetensors` |
| `Moody Zimage - V5` / `Moody Anime2Real V1` / `Moody ZIB+ZIT V4` | `z_image\moodyPornMix_v10DPO.safetensors` |
| `Z+RefineV1.3` | `darkBeastMar2126Latest_dbzit9DIMRclaw.safetensors` |
| `黑兽V9` | `z_image\darkBeastFeb2226Latest_...` |
| `Lora 强度测试 6Steps` / `lora测试` | `Krea-2\pornmasterKrea2_v31Turbo.safetensors` |
| `【Work-Fisher】ANIMA` / `easonAnimaSpeedUp` | `anima_baseV10.safetensors` |

**修法有两种：**

1. **改工作流里的模型名**（推荐）—— 在 ComfyUI 里重新选一次模型，保存。最干净。
2. **改配置覆盖** —— 用 `node_input_overrides`：
   ```json
   "node_input_overrides": {
     "46": {"unet_name": "krea2\\krea2_turbo_fp8_scaled.safetensors"}
   }
   ```

### 已经跑通的示例

`my_krea2` —— 基于 `Krea2_Turbo_fp8_8步_CFG1` 改的，模型换成磁盘上真实存在的 `krea2/krea2_turbo_fp8_scaled.safetensors`，节点 ID 修正为 `627/851/698/854`。

已出两张图：`C:\Users\bagmh\Downloads\card-engine-out\MyKrea2_0000{1,2}_.png`，768×1152，3 分钟/张。

---

## 几个坑

- **`zimage\` vs `z_image\`** —— ComfyUI 用反斜杠表示子目录，JSON 里必须写 `krea2\\xxx.safetensors`（转义）。写单斜杠在某些节点上会失败。
- **`SaveImage` 必须 mode=0** —— mode=4（静音）的 SaveImage 不会产出文件，引擎会超时。
- **多个 SaveImage** —— 引擎会改写**所有** SaveImage 的 `filename_prefix`，可能一次出多张。
- **`filename_prefix` 不要重复** —— 两个工作流用同一个前缀，搜救会拿错图。
- **冷却 30s** —— 每张图之间引擎会 sleep 30 秒，批量跑别以为卡死了。
- **首次出图慢** —— 模型要加载进显存，第一次 3 分钟正常，之后会快。
- **`Power Lora Loader (rgthree)`** —— 空槽天然直通，不用管；但要挂 LoRA 时 `lora_input_key` 必须写 `LORA_1`。
