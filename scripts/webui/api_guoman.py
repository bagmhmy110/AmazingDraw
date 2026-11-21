#!/usr/bin/env python3
"""国漫服装装配 + 仙侠立绘 API。

把 `guoman-costume-xianxia-prompts` skill 的 promptforge 引擎接进 WebUI：

  GET  /api/guoman/meta        调性 / 场景 / 风格款 / 露腿分级 / 渲染风格选项
  GET  /api/guoman/combos      七槽词库（线 D 服装装配用）
  POST /api/guoman/portrait    生成一条立绘提示词（线 C）
  POST /api/guoman/combo       生成一条服装提示词（线 D）
  POST /api/guoman/batch       批量生成（带去重与禁词自检）
  POST /api/guoman/direct      生成并直接投递到 GPU 队列

设计契约：
  * skill 目录可用 AMAZINGDRAW_GUOMAN_SKILL 覆盖；找不到时所有接口返回
    503 + 可读原因，不影响 WebUI 其他功能。
  * 引擎在子进程里跑（skill 自带 sys.path 假设），每次调用隔离，
    避免污染 WebUI 进程。
  * 生成结果原样返回，不做二次改写 —— promptforge 已内置禁词与去重。
"""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from bash_resolver import bash_executable
import shot_options as SH
import style_options as SO
from web_server import SCRIPT_DIR

router = APIRouter(tags=["guoman"])

# 前端「随机」哨兵值。收到它就由服务端抽一个具体值再传给 promptforge。
RANDOM_TOKEN = "__random__"


def _random_seed() -> int:
    """每次调用返回一个新种子，保证批量不复用同一套随机序列。"""
    import random as _random

    return _random.randint(1, 2**31 - 1)


_DEFAULT_TONES = ["仙侠", "宫廷", "战斗", "暗黑", "新中式"]
_DEFAULT_SCENES = [
    "庭院", "云海", "樱林", "废墟", "暗室",
    "亭台", "雪山", "夜市", "宫殿", "竹林",
]

# skill 根目录探测顺序：环境变量 → 仓库内置 → ~/.dsh/skills → 其他常见位置
_REPO_GUOMAN_SKILL = (
    Path(__file__).resolve().parent.parent.parent / "skills" / "guoman-costume-xianxia-prompts"
)
_SKILL_DIR_CANDIDATES = (
    os.environ.get("AMAZINGDRAW_GUOMAN_SKILL"),
    str(_REPO_GUOMAN_SKILL),
    str(Path(os.path.expanduser("~")) / ".dsh" / "skills" / "guoman-costume-xianxia-prompts"),
    str(Path(os.path.expanduser("~")) / ".claude" / "skills" / "guoman-costume-xianxia-prompts"),
)


def _skill_dir() -> Optional[Path]:
    for cand in _SKILL_DIR_CANDIDATES:
        if not cand:
            continue
        p = Path(cand)
        if (p / "scripts" / "promptforge.py").is_file():
            return p
    return None


def _require_skill() -> Path:
    p = _skill_dir()
    if p is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "未找到 guoman-costume-xianxia-prompts skill。"
                "请安装到 ~/.dsh/skills/ 或设置环境变量 AMAZINGDRAW_GUOMAN_SKILL。"
            ),
        )
    return p


def _python() -> str:
    return sys.executable or "python3"


def _run_forge(args: List[str], timeout: float = 120.0) -> subprocess.CompletedProcess:
    """在 skill 目录里跑 promptforge.py，强制 UTF-8。"""
    skill = _require_skill()
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        return subprocess.run(
            [_python(), str(skill / "scripts" / "promptforge.py"), *args],
            cwd=str(skill),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail=f"promptforge 超时（{timeout}s）") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"无法执行 promptforge: {exc}") from exc


def _clean(text: Optional[str]) -> str:
    return (text or "").strip()


def _split_pick(raw: str) -> Dict[str, Optional[str]]:
    """解析 promptforge 的输出。

    `--pick` 模式结构：
        【选中元素】
          key: value
          ...
        【完整提示词】
        <正文>

    非 pick 模式：整个 stdout 就是正文。
    """
    text = _clean(raw)
    marker = "【完整提示词】"
    pick_marker = "【选中元素】"

    if pick_marker in text and marker in text:
        head, _, body = text.partition(marker)
        breakdown = head.replace(pick_marker, "", 1).strip()
        return {"prompt": body.strip(), "breakdown": breakdown or None}

    # 只出现拆解没有正文（异常兜底）
    if pick_marker in text:
        breakdown = text.replace(pick_marker, "", 1).strip()
        return {"prompt": "", "breakdown": breakdown}

    return {"prompt": text, "breakdown": None}


# ── 选项元数据 ────────────────────────────────────────────────────────────


def _resolve_random(value: Optional[str], pool: List[str]) -> Optional[str]:
    """把前端「随机」哨兵解析成具体值；普通值原样返回。"""
    raw = _clean(value)
    if raw in ("", RANDOM_TOKEN, "random", "随机"):
        return random.choice(pool) if pool else None
    return raw


def _tone_pool() -> List[str]:
    meta_scenes = _scene_pool()
    del meta_scenes  # 只为触发 skill 探测，保持接口一致
    return list(_DEFAULT_TONES)


def _scene_pool() -> List[str]:
    """尽量从 skill 的 tone_profile 取真实场景池，失败回退内置列表。"""
    skill = _skill_dir()
    if skill is None:
        return list(_DEFAULT_SCENES)
    try:
        res = subprocess.run(
            [_python(), "-c",
             "import sys,json; sys.path.insert(0,'scripts'); import tone_profile as TP;"
             "print(json.dumps(sorted(TP.SCENE_BASE.keys()), ensure_ascii=False))"],
            cwd=str(skill),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout.strip().splitlines()[-1])
            if isinstance(data, list) and data:
                return data
    except Exception:
        pass
    return list(_DEFAULT_SCENES)


@router.get("/api/guoman/meta")
def guoman_meta() -> Dict[str, Any]:
    """返回下拉框需要的全部选项。缺 skill 时也返回静态元数据 + available=false。"""
    skill = _skill_dir()
    meta: Dict[str, Any] = {
        "available": skill is not None,
        "skill_dir": str(skill) if skill else None,
        "tones": ["仙侠", "宫廷", "战斗", "暗黑", "新中式"],
        "leg_levels": [
            {"value": "none", "label": "不露腿", "desc": "完全不提腿，适合宫廷正装"},
            {"value": "mild", "label": "含蓄", "desc": "只给裙裾下的腿部线条（默认）"},
            {"value": "bold", "label": "大胆", "desc": "裙摆高开叉露出修长双腿"},
        ],
        "tone_desc": {
            "仙侠": "月白·冰蓝·霜蓝·浅紫 / 纱丝绫 / 清冷飘逸疏离",
            "宫廷": "朱红·绛红·孔雀蓝·金 / 锦缎绒 / 雍容矜贵威仪",
            "战斗": "墨黑·赤红·深蓝·青灰 / 皮革金属紧实织物 / 凌厉飒爽警觉",
            "暗黑": "紫黑·酒红·墨绿·暗银 / 薄纱丝绒幻彩 / 神秘冷艳压迫",
            "新中式": "月白·青灰·淡金·香槟 / 真丝缎面混纺 / 现代利落松弛",
        },
        "scenes": [],
        "style_variants": [],
        "render_styles": [],
        "poses": {},
        **SH.meta(),
        "exposures": [
            {"value": "none", "label": "全遮（不漏）", "desc": "服装完整，无任何裸露信号"},
            {"value": "half_covered", "label": "擦边（半遮）", "desc": "湿身、透视、微露内衣，不露点"},
            {"value": "upper", "label": "露上（Topless）", "desc": "上身裸露，下身必须遮挡"},
            {"value": "lower", "label": "露下（Bottomless）", "desc": "下身裸露，上身必须遮挡"},
            {"value": "half_nude", "label": "半裸（局部露点）", "desc": "保留服装结构（解开纽扣/滑落肩带），露一侧"},
            {"value": "both", "label": "全裸（三点全露）", "desc": "上下全露，三点全露"},
        ],
    }
    if skill is None:
        return meta

    # 从 tone_profile.py 直接取池子，避免前端硬编码
    probe = r"""
import json, sys
sys.path.insert(0, 'scripts')
import tone_profile as TP
import exposure_profile as EXP
out = {
  'scenes': sorted(TP.SCENE_BASE.keys()) if hasattr(TP, 'SCENE_BASE') else [],
  'style_variants': sorted(getattr(TP, 'STYLE_VARIANT', {}).keys()) if hasattr(TP, 'STYLE_VARIANT') else [],
  'tones': list(getattr(TP, 'COSTUME_POOL', {}).keys()),
  'slots': {},
  'poses': {},
  'exposures': [
      {'value': lv, 'label': EXP.EXPOSURE_LABELS[lv], 'desc': EXP.EXPOSURE_DESC[lv]}
      for lv in EXP.EXPOSURE_LEVELS
  ],
}
for slot in ('配色','材质','纹样','袖型','裙装结构','腰部','肩部'):
    pool = getattr(TP, 'COSTUME_POOL', {}).get('仙侠', {})
    if isinstance(pool, dict) and slot in pool:
        out['slots'][slot] = sorted(pool[slot])
# 每个调性的姿势池（构图 + 动作）
for tone in out['tones']:
    try:
        out['poses'][tone] = EXP.pose_options(tone)
    except Exception:
        out['poses'][tone] = []
print(json.dumps(out, ensure_ascii=False))
"""
    try:
        res = subprocess.run(
            [_python(), "-c", probe],
            cwd=str(skill),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout.strip().splitlines()[-1])
            meta["scenes"] = data.get("scenes") or []
            meta["style_variants"] = data.get("style_variants") or []
            if data.get("tones"):
                meta["tones"] = data["tones"]
            meta["slots"] = data.get("slots") or {}
            meta["poses"] = data.get("poses") or {}
            if data.get("exposures"):
                meta["exposures"] = data["exposures"]
    except Exception as exc:  # 元数据探测失败不该阻断生成
        meta["meta_error"] = str(exc)

    # 调性下拉末尾追加 12 种画风（与原调性并列，同一套七槽词库）
    tones = list(meta.get("tones") or _DEFAULT_TONES)
    style_labels = [s["label"] for s in SO.EXTRA_STYLES]
    meta["tones"] = tones + [t for t in style_labels if t not in tones]

    # 渲染风格（含扩展 profile）
    try:
        res2 = subprocess.run(
            [_python(), "-c",
             "import sys,json; sys.path.insert(0,'scripts'); import render_profile as RP;"
             "print(json.dumps(list(RP.RENDER), ensure_ascii=False))"],
            cwd=str(skill),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        if res2.returncode == 0 and res2.stdout.strip():
            base = json.loads(res2.stdout.strip().splitlines()[-1])
            meta["render_styles"] = list(base) + ["hk80s", "real", "sweet", "gauze"]
    except Exception:
        meta["render_styles"] = ["clean", "hk80s", "real", "sweet", "gauze"]

    return meta


@router.get("/api/guoman/combos")
def guoman_combos(tone: str = "仙侠") -> Dict[str, Any]:
    """返回某调性下七槽可选词，供线 D 锁定槽位。"""
    skill = _require_skill()
    probe = f"""
import json, sys
sys.path.insert(0, 'scripts')
import tone_profile as TP
pool = TP.COSTUME_POOL.get({tone!r}, {{}})
out = {{k: sorted(v) for k, v in pool.items() if isinstance(v, (list, set, tuple))}}
print(json.dumps(out, ensure_ascii=False))
"""
    try:
        res = subprocess.run(
            [_python(), "-c", probe],
            cwd=str(skill),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="读取词库超时") from exc
    if res.returncode != 0:
        raise HTTPException(status_code=500, detail=_clean(res.stderr) or "读取词库失败")
    try:
        data = json.loads(_clean(res.stdout).splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise HTTPException(status_code=500, detail="词库返回格式异常") from exc
    return {"tone": tone, "slots": data}


# ── 生成 ──────────────────────────────────────────────────────────────────


# 槽位 key → promptforge 命令行标志
_SLOT_FLAGS = {
    "color": "--color",
    "fabric": "--fabric",
    "pattern": "--pattern",
    "sleeve": "--sleeve",
    "skirt": "--skirt",
    "waist": "--waist",
    "shoulder": "--shoulder",
}


def _slot_args(req: Dict[str, Any]) -> List[str]:
    """把请求里的服装槽位转成 promptforge 的锁词参数。

    支持两种写法：
      * {"slots": {"color": "月白与银灰", ...}}   ← 前端新版
      * {"color": "月白与银灰", ...}              ← 扁平写法（兼容旧调用）
    """
    raw = req.get("slots")
    slots: Dict[str, Any] = raw if isinstance(raw, dict) else req
    out: List[str] = []
    for key, flag in _SLOT_FLAGS.items():
        val = _clean(slots.get(key))
        if val and val != RANDOM_TOKEN:
            out += [flag, val]
    return out


@router.post("/api/guoman/portrait")
def guoman_portrait(req: Dict[str, Any]) -> Dict[str, Any]:
    """立绘成稿：生成一条完整提示词。

    tone/scene 传 __random__ 时由服务端抽；
    slots 里的槽位会锁定，未锁的按调性随机。
    """
    args = ["portrait"]
    tone = _resolve_random(req.get("tone"), _DEFAULT_TONES) or "仙侠"

    # 调性下拉里可能选的是画风（12 种之一）：
    # 这时用基础调性「仙侠」跑词库，生成后再套该画风的开头/结尾。
    style_pick = SO.pick(tone)
    base_tone = tone
    if style_pick:
        base_tone = "仙侠"

    scene = _resolve_random(req.get("scene"), _scene_pool())
    args += ["--tone", base_tone]
    if scene:
        args += ["--scene", scene]
    if req.get("leg"):
        args += ["--leg", _clean(req["leg"])]
    if req.get("pose"):
        args += ["--pose", _clean(req["pose"])]
    if req.get("exposure"):
        args += ["--exposure", _clean(req["exposure"])]
    if req.get("style"):
        args += ["--style", _clean(req["style"])]
    if req.get("render"):
        args += ["--render", _clean(req["render"])]
    # 服装槽位锁词（并入立绘）
    args += _slot_args(req)
    if req.get("seed") not in (None, ""):
        args += ["--seed", str(int(req["seed"]))]
    if req.get("pick"):
        args.append("--pick")

    res = _run_forge(args)
    if res.returncode != 0:
        raise HTTPException(status_code=400, detail=_clean(res.stderr) or "生成失败")

    parsed = _split_pick(res.stdout)
    if not parsed["prompt"]:
        raise HTTPException(status_code=500, detail="生成结果解析失败（无正文）")
    # 画风：调性里选的画风优先，其次 extra_style（兼容旧调用）
    style_val = (style_pick["value"] if style_pick
                 else str(req.get("extra_style") or ""))
    _prompt = SO.apply(parsed["prompt"], style_val)

    # 机位构图（追加到末尾）
    shot_val = _clean(req.get("shot"))
    if shot_val:
        _prompt = SH.apply(_prompt, shot_val)

    return {
        "ok": True,
        "tone": tone,
        "scene": scene,
        "prompt": _prompt,
        "breakdown": parsed["breakdown"],
        "raw": _clean(res.stdout),
    }


@router.post("/api/guoman/combo")
def guoman_combo(req: Dict[str, Any]) -> Dict[str, Any]:
    """纯服装提示词（保留的兼容端点，界面已并入立绘）。

    tone 传 __random__ 时服务端抽；slots 可锁定任意槽位。
    """
    args = ["combo"]
    tone = _resolve_random(req.get("tone"), _DEFAULT_TONES)
    if tone:
        args += ["--tone", tone]
    args += _slot_args(req)
    if req.get("seed") not in (None, ""):
        args += ["--seed", str(int(req["seed"]))]
    if req.get("pick"):
        args.append("--pick")

    res = _run_forge(args)
    if res.returncode != 0:
        raise HTTPException(status_code=400, detail=_clean(res.stderr) or "生成失败")

    parsed = _split_pick(res.stdout)
    if not parsed["prompt"]:
        raise HTTPException(status_code=500, detail="生成结果解析失败（无正文）")
    return {
        "ok": True,
        "tone": tone,
        "prompt": parsed["prompt"],
        "breakdown": parsed["breakdown"],
        "raw": _clean(res.stdout),
    }


@router.post("/api/guoman/batch")
def guoman_batch(req: Dict[str, Any]) -> Dict[str, Any]:
    """批量生成。脚本内置禁词校验、完整句去重、三元组去重、五调性均衡。"""
    n = int(req.get("n") or 20)
    if n < 1 or n > 2000:
        raise HTTPException(status_code=400, detail="条数需在 1~2000 之间")

    skill = _require_skill()
    tones = _clean(req.get("tones")) or "仙侠,宫廷,战斗,暗黑,新中式"
    scenes = _clean(req.get("scenes")) or "庭院,云海,樱林,废墟,暗室,亭台,雪山,夜市,宫殿,竹林"
    leg = _clean(req.get("leg")) or "mild"
    render = _clean(req.get("render")) or "clean"
    exposure = _clean(req.get("exposure")) or "none"
    pose = _clean(req.get("pose"))
    seed = req.get("seed")
    # 不传 / 空 / "random" 一律随机 —— 固定种子会让每次批量出一模一样的提示词
    if seed in (None, "", "random", "rand", "auto"):
        seed = _random_seed()
    else:
        try:
            seed = int(seed)
        except (TypeError, ValueError):
            seed = _random_seed()

    with tempfile.TemporaryDirectory(prefix="guoman-batch-") as tmp:
        out_txt = Path(tmp) / "prompts.txt"
        out_json = Path(tmp) / "prompts.json"
        args = [
            "batch", "-n", str(n),
            "-o", str(out_txt), "--json", str(out_json),
            "--seed", str(seed),
            "--tones", tones, "--scenes", scenes,
            "--leg", leg, "--render", render,
            "--exposure", exposure,
        ]
        if pose:
            args += ["--pose", pose]
        # 七槽锁词：前端传 slots 对象，这里展开成 --color/--fabric/...
        slots = req.get("slots") or {}
        if isinstance(slots, dict):
            for key in ("color", "fabric", "pattern", "sleeve", "skirt", "waist", "shoulder"):
                val = _clean(slots.get(key))
                if val:
                    args += [f"--{key}", val]
        res = _run_forge(args, timeout=max(120.0, n * 1.5))
        if res.returncode != 0:
            raise HTTPException(status_code=400, detail=_clean(res.stderr) or "批量生成失败")

        items: List[Dict[str, Any]] = []
        if out_json.is_file():
            try:
                data = json.loads(out_json.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for i, row in enumerate(data, 1):
                        if isinstance(row, dict):
                            items.append({
                                "index": i,
                                "prompt": row.get("prompt") or row.get("text") or "",
                                "tone": row.get("tone"),
                                "scene": row.get("scene"),
                            })
                        else:
                            items.append({"index": i, "prompt": str(row)})
                elif isinstance(data, dict):
                    rows = data.get("items") or data.get("prompts") or []
                    for i, row in enumerate(rows, 1):
                        if isinstance(row, dict):
                            items.append({"index": i, "prompt": row.get("prompt") or row.get("text") or "", "tone": row.get("tone"), "scene": row.get("scene")})
                        else:
                            items.append({"index": i, "prompt": str(row)})
            except Exception:
                items = []
        if not items and out_txt.is_file():
            lines = [ln.strip() for ln in out_txt.read_text(encoding="utf-8").splitlines() if ln.strip()]
            items = [{"index": i, "prompt": ln} for i, ln in enumerate(lines, 1)]

        # 机位构图：promptforge 的 batch 不认 --shot，这里在代码层补
        shot_val = _clean(req.get("shot"))
        if shot_val:
            for it in items:
                t = it.get("prompt") or ""
                if t:
                    it["prompt"] = SH.apply(t, shot_val)

        return {
            "ok": True,
            "count": len(items),
            "items": items,
            "stdout": _clean(res.stdout)[:2000],
        }


def _normalize_scene(raw: str, pool: List[str]) -> str:
    """把反推出的场景描述归一化成标准场景 key。

    正文里是「香火未绝的青石铺地的道观前庭」，标准 key 是「道观」。
    按「key 出现在描述里」匹配，取最长匹配（避免「雪山」误配「雪寺」）。
    """
    s = (raw or "").strip()
    if not s:
        return ""
    if s in pool:
        return s
    hits = [k for k in pool if k in s]
    if hits:
        return max(hits, key=len)
    return s


def _infer_from_prompt(text: str) -> Dict[str, str]:
    """从提示词正文反推调性与场景。

    提示词里已经写死了真实场景（如「场景落在青石铺地的道观前庭」），
    比调用方传进来的元数据可靠 —— 前端下拉框可能已被改动。
    """
    out = {"tone": "", "scene": ""}
    m_tone = re.search(r"^一位东方(.+?)风格的", text or "")
    if m_tone:
        out["tone"] = m_tone.group(1).strip()
    m_scene = re.search(r"(?:场景落在|背景为)([^，。]+)", text or "")
    if m_scene:
        s = m_scene.group(1).strip()
        # 去掉形容词前缀（「如梦似幻的」「香火未绝的」…），取最后一个「的」之后
        idx = s.rfind("的")
        if 0 < idx < len(s) - 1:
            s = s[idx + 1:]
        out["scene"] = s
    return out


@router.post("/api/guoman/direct")
def guoman_direct(req: Dict[str, Any]) -> Dict[str, Any]:
    """投递提示词到 GPU 队列（走 cu-submit.sh）。

    两种用法：
      * 传 prompt  → 直接投递这条现成提示词（前端「生成图片」按钮用这个）
      * 不传 prompt → 先生成立绘再投递（旧行为，保持兼容）

    场景/调性**以提示词正文为准** —— 正文是出图的唯一依据，
    请求里的元数据只是兜底（正文里反推不出来时才用）。
    """
    given_prompt = _clean(req.get("prompt"))
    if given_prompt:
        prompt = given_prompt
        breakdown = None
        inferred = _infer_from_prompt(prompt)
        scene_pool = _scene_pool()
        # 正文优先；反推不到才用请求值 / 随机
        req_tone = _clean(req.get("tone"))
        req_scene = _clean(req.get("scene"))
        tone = (
            inferred["tone"]
            or (req_tone if req_tone and req_tone != RANDOM_TOKEN else "")
            or _resolve_random(req_tone, _DEFAULT_TONES)
            or "仙侠"
        )
        scene = (
            _normalize_scene(inferred["scene"], scene_pool)
            or (req_scene if req_scene and req_scene != RANDOM_TOKEN else "")
            or _resolve_random(req_scene, scene_pool)
            or "云海"
        )
    else:
        portrait = guoman_portrait(req)
        prompt = portrait.get("prompt") or ""
        breakdown = portrait.get("breakdown")
        tone = portrait.get("tone") or "仙侠"
        scene = portrait.get("scene") or "云海"

    if not prompt:
        raise HTTPException(status_code=400, detail="提示词为空，无法投递")

    # 卡片/文件名用的「人物名」= 来源 skill 名。
    # 前端各 skill 页面会传 person（如「国漫人像」「MOSS」「写实摄影」），
    # 没传时回退到「国漫立绘」以兼容旧调用。
    person = _clean(req.get("person")) or "国漫立绘"

    # theme 承载「风格」，参与文件名 <person>-<scene>-<theme>.png
    # 规则：
    #   - 显式传了 theme 就用它
    #   - 否则用 <tone>风
    #   - 若 person 已包含 tone（如 person=写实摄影 / tone=写实摄影），
    #     说明风格名和 skill 名重合，此时用「人像」这类中性词，避免叠字
    #   - 绝不能是空字符串 —— cu-submit.sh 会兜底成「灵感直投」
    explicit_theme = _clean(req.get("theme"))
    if explicit_theme:
        theme_suffix = explicit_theme
    elif tone and tone in person:
        theme_suffix = "人像"
    else:
        theme_suffix = f"{tone}风"

    submit = SCRIPT_DIR.parent / "gpu-pipeline" / "cu-submit.sh"
    args = [
        bash_executable(), str(submit),
        "--raw", "--prompt", prompt,
        "--person", person,
        "--scene", scene,
        "--theme", theme_suffix,
        "--narrative", f"{tone}调性的{scene}立绘",
    ]
    # 复用已有卡片：传了 card_id 就让 cu-submit 回写这张卡，
    # 而不是自动新建一张（否则每点一次「生成图片」列表就多一条）
    reuse_card = _clean(req.get("card_id"))
    if reuse_card:
        args += ["--card", reuse_card]
    if req.get("workflow"):
        args += ["--workflow", _clean(req["workflow"])]
    if req.get("width"):
        args += ["--width", str(int(req["width"]))]
    if req.get("height"):
        args += ["--height", str(int(req["height"]))]

    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        res = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="投递超时") from exc

    ack: Dict[str, Any] = {}
    for line in reversed(_clean(res.stdout).splitlines()):
        try:
            cand = json.loads(line)
            if isinstance(cand, dict):
                ack = cand
                break
        except (ValueError, TypeError):
            continue

    if res.returncode != 0 or not ack.get("accepted"):
        raise HTTPException(
            status_code=400,
            detail=ack.get("error") or _clean(res.stderr) or "投递失败",
        )

    return {
        "ok": True,
        "prompt": prompt,
        "breakdown": breakdown,
        "job_id": ack.get("job_id"),
        "card_id": ack.get("card_id"),
        "state": ack.get("state"),
        "ack": ack,
    }
