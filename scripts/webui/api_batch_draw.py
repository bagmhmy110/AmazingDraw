#!/usr/bin/env python3
"""批量出图：把一组提示词逐条投进 GPU 渲染队列。

各 skill 的「批量生成」只产出提示词文本；这个模块负责把整批提示词
一次性投递出去，省去逐条点「生成图片」。

设计要点：
  - 复用 `/api/guoman/direct` 的投递链路（cu-submit.sh），不另造一套
  - 串行投递并留间隔，避免瞬间打爆队列
  - 单条失败不影响整批，最后汇总成功/失败明细
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

import api_guoman as GM

router = APIRouter()

# 两条投递之间留的间隔（秒）——队列是串行的，太快没意义
SUBMIT_GAP = 0.6

# 单次批量出图的上限，防止误操作把队列塞爆
MAX_BATCH = 60


@router.post("/api/batch-draw")
def batch_draw(req: Dict[str, Any]) -> Dict[str, Any]:
    """批量投递提示词出图。

    请求体：
        prompts    : List[str]  要投递的提示词（必填）
        person     : str        来源 skill 名，参与文件名
        scene      : str        兜底场景（提示词里反推不到时用）
        tone       : str        兜底调性
        theme      : str        兜底风格名
        limit      : int        最多投几条（默认全投，上限 MAX_BATCH）
        skip_dupes : bool       跳过重复提示词（默认 True）

    返回：
        ok, submitted, failed, total, items[{index, ok, card_id, error}]
    """
    raw = req.get("prompts")
    if not isinstance(raw, list) or not raw:
        raise HTTPException(status_code=400, detail="prompts 必须是非空数组")

    prompts: List[str] = []
    seen = set()
    skip_dupes = bool(req.get("skip_dupes", True))
    for p in raw:
        t = str(p or "").strip()
        if not t:
            continue
        if skip_dupes:
            if t in seen:
                continue
            seen.add(t)
        prompts.append(t)

    if not prompts:
        raise HTTPException(status_code=400, detail="没有可投递的提示词")

    limit = int(req.get("limit") or MAX_BATCH)
    limit = max(1, min(limit, MAX_BATCH))
    if len(prompts) > limit:
        prompts = prompts[:limit]

    person = str(req.get("person") or "国漫立绘").strip() or "国漫立绘"
    scene_fb = str(req.get("scene") or "").strip()
    tone_fb = str(req.get("tone") or "").strip()
    theme_fb = str(req.get("theme") or "").strip()

    items: List[Dict[str, Any]] = []
    ok_count = 0

    for idx, prompt in enumerate(prompts, start=1):
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "person": person,
        }
        if scene_fb:
            payload["scene"] = scene_fb
        if tone_fb:
            payload["tone"] = tone_fb
        if theme_fb:
            payload["theme"] = theme_fb

        try:
            r = GM.guoman_direct(payload)
            card_id = r.get("card_id") or r.get("id") or ""
            items.append({
                "index": idx,
                "ok": True,
                "card_id": card_id,
                "prompt_head": prompt[:40],
            })
            ok_count += 1
        except HTTPException as exc:
            items.append({
                "index": idx,
                "ok": False,
                "error": str(exc.detail)[:160],
                "prompt_head": prompt[:40],
            })
        except Exception as exc:  # noqa: BLE001
            items.append({
                "index": idx,
                "ok": False,
                "error": str(exc)[:160],
                "prompt_head": prompt[:40],
            })

        if idx < len(prompts):
            time.sleep(SUBMIT_GAP)

    return {
        "ok": ok_count > 0,
        "total": len(prompts),
        "submitted": ok_count,
        "failed": len(prompts) - ok_count,
        "person": person,
        "items": items,
    }
