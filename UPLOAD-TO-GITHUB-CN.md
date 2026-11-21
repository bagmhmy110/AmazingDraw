# 上传到 GitHub 完整步骤

> 本地仓库已经初始化好了：181 个文件、68037 行、10.47 MB。
> 剩下就是**在 GitHub 建仓库 → 关联 → 推送**。

---

## 已完成的部分

我在 `J:\AmazingDraw` 做了这些：

| 操作 | 结果 |
|---|---|
| `git init` | 初始化仓库（分支 `master`） |
| 创建 `.gitignore` | 排除 config.json / 日志 / `__pycache__` |
| 创建 `.gitattributes` | 统一换行符（`.sh` 强制 LF，`.pyd` 二进制） |
| 清理硬编码路径 | `api_upscale.py` 里 `I:\ComfyUI-aki-v2` → `~/ComfyUI` |
| 首次提交 | `40fc9e9` 181 files, 68037 insertions |

### 已排除的敏感/冗余内容

```
config.json              ← 含本机路径（I:\ComfyUI-aki-v2、C:\Users\bagmh\...）
scripts/webui/logs/      ← 2.3 MB 运行日志
__pycache__/             ← 8 个目录的字节码
*.log / *.tmp / *.bak
```

**仓库里保留的是 `config.example.json`** —— 干净的模板，`api_key` 为空。

---

## 第一步：在 GitHub 建仓库

1. 打开 https://github.com/new
2. 填写：

| 字段 | 建议值 |
|---|---|
| **Repository name** | `AmazingDraw`（或你喜欢的名字） |
| **Description** | 可选，比如「AI 抽卡引擎 + WebUI + 提示词 skill 集成」 |
| **Visibility** | ⚠️ **Private**（见下方说明） |
| **Initialize this repository with** | ❌ **全部不勾**（README / .gitignore / license 都不要勾） |

3. 点 **Create repository**

> ⚠️ **为什么建议 Private**
>
> 这个项目包含成人向提示词 skill（NSFW 模板、成人写真等）。
> GitHub 的服务条款对「性化内容」有明确规定，公开仓库可能被举报下架。
> 自己用或小范围分享，Private 最稳。
>
> 如果你确定要公开，务必先看一遍仓库里那些 `FEATURE-*` / `FIX-*` 中文文档，
> 确认内容你能接受公开展示。

---

## 第二步：关联远程仓库

创建完会看到一个空仓库页面，复制那串 HTTPS 地址，然后执行：

```bash
cd /j/AmazingDraw

# 关联（把 URL 换成你自己的）
git remote add origin https://github.com/你的用户名/AmazingDraw.git

# 确认关联成功
git remote -v
```

---

## 第三步：推送

```bash
# 首次推送（-u 记住上游，以后直接 git push）
git push -u origin master
```

### 会遇到认证

GitHub 从 2021 年起**不接受账号密码**，要用 **Personal Access Token**：

1. 打开 https://github.com/settings/tokens
2. **Generate new token** → **Generate new token (classic)**
3. Note 随便填，Expiration 选 90 天或更长
4. 勾选权限：**`repo`**（整个 repo 组）
5. 点 **Generate token**
6. **复制那串 `ghp_xxxxx`**（只显示一次，关掉就看不到了）

推送时：
- Username：你的 GitHub 用户名
- Password：**粘贴那串 token**（不是账号密码）

Windows 会弹窗让你登录，或者走 Git Credential Manager 授权一次，之后就记住了。

---

## 第四步：验证

推完后打开 `https://github.com/你的用户名/AmazingDraw`，应该看到：

- 181 个文件
- README 正常渲染
- 没有 `config.json`、没有 `logs/`
- `docs-screenshots/` 里的 22 张图能正常显示

---

## 后续更新

改完代码后：

```bash
cd /j/AmazingDraw

git status                    # 看改了什么
git add -A                    # 全部暂存
git commit -m "描述这次改了什么"
git push                      # 推到 GitHub
```

---

## 常见问题

### 推送被拒：`remote contains work that you do not have`

建仓库时勾了 README 之类的东西。解决：

```bash
git pull origin master --allow-unrelated-histories
git push -u origin master
```

或者干脆删掉 GitHub 上的仓库重建（**什么都别勾**）。

### 推送太慢 / 超时

国内直连 GitHub 经常卡。方案：

```bash
# 方案 A：改用 SSH（配好 key 后更稳）
git remote set-url origin git@github.com:你的用户名/AmazingDraw.git

# 方案 B：走代理（把 7890 换成你的代理端口）
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890

# 取消代理
git config --global --unset http.proxy
git config --global --unset https.proxy
```

### 大文件被拒：`file exceeds GitHub's file size limit of 100 MB`

这个项目最大的文件是 4.8 MB 的 `data/poetry_db.json`，不会触发。
以后如果加了模型文件，用 [Git LFS](https://git-lfs.com/)：

```bash
git lfs install
git lfs track "*.safetensors"
git add .gitattributes
```

### 想改分支名成 main

GitHub 现在默认 `main`：

```bash
git branch -M main
git push -u origin main
```

---

## 我改动的两个文件

| 文件 | 改动 |
|---|---|
| `.gitignore` | 新建 |
| `.gitattributes` | 新建 |
| `scripts/webui/api_upscale.py` | 两处 `I:\ComfyUI-aki-v2\ComfyUI` → `~/ComfyUI`（fallback 默认值） |

功能完全不受影响 —— 因为 `config.json` 里本来就配了 `comfyui_dir`，那两处 fallback 用不到。
