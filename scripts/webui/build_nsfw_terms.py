#!/usr/bin/env python3
"""从 NSFW 模板词库里抽取「可入句的词条」，供前端下拉与代码拼装使用。

设计变更（v2）：
  v1 假设「提示词正文用中文」，于是把所有英文词条都过滤掉了
  （见旧版 looks_like_signal）—— 结果留下大量中文说明文字、表格行、
  ❌ 规则条目，拼出来的句子完全不通顺。

  v2 反过来：**真正的词条是英文**（cleavage visible through collar、
  single drop、unbuttoned shirt 这种），中文那些多半是标题、说明、
  规则与表格标签，应当过滤掉。

抽取策略：
  1. 只认「代码块里的逗号分隔词条」+「表格第一列」+「列表项」
  2. 过滤：表格分隔行、标题、说明文字、❌ 规则、中文长句、纯序号
  3. 词条必须是英文短语，长度 2~60 字符，允许少量数字与连字符
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

SKILL_ROOT_CANDIDATES = (
    Path.home() / ".dsh" / "skills" / "nsfw-prompt-templates-asian",
    Path(__file__).resolve().parent.parent.parent
    / "skills"
    / "nsfw-prompt-templates-asian",
)

# 槽位 → 文件名
SLOT_FILES = {
    "场景主题": "01-场景主题.md",
    "景别构图": "02-景别构图.md",
    "裸露液体": "03-裸露液体.md",
    "服装专项": "04-服装专项.md",
    "光影氛围": "05-光影氛围.md",
    "姿势动作": "06-姿势动作.md",
    "表情眼神": "07-表情眼神.md",
    "风格胶片": "08-风格胶片.md",
    "妆容专项": "09-妆容专项.md",
    "发型饰品": "10-发型饰品.md",
    "瑕疵细节": "11-瑕疵细节.md",
    "纹身标记": "12-纹身标记.md",
    "道具宠物": "13-道具宠物.md",
    "人格卡片": "14-人格卡片.md",
}

# 不要的小节（索引、说明、附录规则、黑名单、检查清单）
SKIP_SECTION = re.compile(
    r"索引|目录|快速定位|核心原则|装配顺序|使用说明|说明|前言|免责|搭配禁忌"
    r"|禁止组合|附录|黑名单|禁用|翻车|规则|铁律|公式|检查清单|常见问题"
    r"|正确写法|正确使用|绝对避免|速查|与.*联动$",
)

# 只保留英文词条：允许字母、空格、逗号、连字符、斜杠、数字、括号内英文
_EN_OK = re.compile(r"^[A-Za-z][A-Za-z0-9 ,'\-/()（）%×:+.]*$")

# 中文说明的特征词，命中即丢弃
_CN_EXPLAIN = re.compile(
    r"适用|建议|必须|禁止|不得|应当|配合|参考|见|注|要点|原则|规则|说明"
    r"|每个|选\s*\d|仅|只选|推荐|示例|例如|比如|表示|意味着|对应"
)

# 表格分隔行 / 空占位
_TABLE_SEP = re.compile(r"^[\s|:\-]+$")

# 形如「1. xxx」「① xxx」的编号标题
_NUMBERED_HEAD = re.compile(r"^[\d①-⑳]+[.、)]\s*\S{0,12}$")

# 词条里不该出现的东西
_BAD_CHARS = re.compile(r"[❌✅⚠️→←↑↓★☆◆◇■□●○]|[\U0001F300-\U0001FAFF]")

# 噪音词条：裸露级别标注、章节引用、单字母碎片
# 注意 ICU / POV / CBT / WAM 这类是有效缩写，不能一刀切
_NOISE = re.compile(
    r"^(?:[A-Z]/\s*[A-Z](?:/[A-Z])*"          # A/B/C
    r"|L[1-6](?:\s*[-~]\s*L?[1-6])?"          # L3 / L3-5
    r"|[A-Z]{1,2}$"                            # 单双字母碎片（除已知缩写）
    r")$"
)
# 已知有效缩写，放行
_ALLOW_ABBR = {
    "POV", "OTS", "ICU", "CBT", "WAM", "BDSM", "SM", "AV", "VR", "AR",
    "OL", "JK", "NTR", "3P", "4P", "KO", "ECU", "CU", "MCU", "MS", "WS",
    "ELS", "HDR", "ISO", "RAW", "4K", "8K", "AI",
}


def _skill_refs() -> Path:
    for root in SKILL_ROOT_CANDIDATES:
        if (root / "references").is_dir():
            return root / "references"
    return SKILL_ROOT_CANDIDATES[0] / "references"


def clean(s: str) -> str:
    """去掉 markdown 强调、链接、emoji，压缩空白。"""
    out = s.strip()
    out = re.sub(r"\*\*|__|`", "", out)
    out = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", out)
    out = _BAD_CHARS.sub("", out)
    out = re.sub(r"\s+", " ", out)
    return out.strip(" ·|—-、，。")


def is_term(s: str) -> bool:
    """判断是否是可入句的英文词条。"""
    if not s or len(s) < 2 or len(s) > 60:
        return False
    if s.startswith((">", "#", "|", "-", "=", "```", "❌", "✅")):
        return False
    if _TABLE_SEP.match(s):
        return False
    if _NUMBERED_HEAD.match(s):
        return False
    # 文件名残留（`-服装专项.md — 东亚情色服装词库`）
    if ".md" in s.lower() or "词库" in s:
        return False
    # 噪音：级别标注 / 单字母碎片（已知缩写放行）
    if _NOISE.match(s) and s.upper() not in _ALLOW_ABBR:
        return False
    # 必须基本是英文
    if not _EN_OK.match(s):
        return False
    # 至少要有一个字母
    if not re.search(r"[A-Za-z]", s):
        return False
    # 纯大写缩写但不在白名单里，多半是标注
    if s.isupper() and len(s) <= 2 and s not in _ALLOW_ABBR:
        return False
    # 单词数过多不像词条
    words = s.split()
    if len(words) > 12:
        return False
    return True


def _split_terms(text: str) -> List[str]:
    """把一段文本切成词条列表。

    代码块 / 表格里可能是三种形态，都要能处理：
      1. 反引号包裹的英文词条：`convenience store, konbini, ...`  ← 01/05/13 主力形态
      2. 逗号分隔串：unbuttoned shirt, open blouse, dress unzipped
      3. 表格片段：| **情人旅馆** |  （第一列是中文标签，通常不是词条）
    """
    out: List[str] = []

    # 1) 反引号里的内容 —— 词库最规范的写法（表格第二列基本都是这种）
    for m in re.finditer(r"`([^`]+)`", text):
        for chunk in re.split(r"[,，]", m.group(1)):
            t = clean(chunk)
            if is_term(t):
                out.append(t)

    # 2) 没有反引号的文本，逐行处理（代码块里的裸逗号串走这条）
    remainder = re.sub(r"`[^`]+`", "", text)
    for line in remainder.splitlines():
        s = line.strip()
        if not s:
            continue

        # 表格行：取「第一列之外」的列（第一列多为中文标签）
        if s.startswith("|"):
            if _TABLE_SEP.match(s):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            for cell in cells[1:]:
                t = clean(cell)
                if is_term(t):
                    out.append(t)
            continue

        # 标题 / 引用直接跳过
        if s.startswith(("#", ">", "❌", "✅")):
            continue

        # 列表项
        if s.startswith(("-", "*", "+")):
            body = clean(re.sub(r"^[-*+]\s+", "", s))
            for chunk in re.split(r"[,，]", body):
                t = clean(chunk)
                if is_term(t):
                    out.append(t)
            continue

        # 普通行：按逗号切
        for chunk in re.split(r"[,，]", s):
            t = clean(chunk)
            if is_term(t):
                out.append(t)
    return out


def parse_module(path: Path) -> Dict[str, List[str]]:
    """解析一个模块，返回 {小节名: [词条...]}。"""
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")

    sections: Dict[str, List[str]] = {}
    cur = "通用"
    sections[cur] = []

    in_code = False
    code_buf: List[str] = []

    for raw in text.splitlines():
        s = raw.strip()

        # ── 代码块：里面的逗号分隔串就是词条主体 ──
        if s.startswith("```"):
            if in_code:
                # 结束：把缓冲的词条收进当前小节
                joined = "\n".join(code_buf)
                for t in _split_terms(joined):
                    sections.setdefault(cur, []).append(t)
                code_buf = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_buf.append(raw)
            continue

        if not s:
            continue

        # ── 小节标题 ──
        if s.startswith("#"):
            title = clean(s.lstrip("#").strip())
            title = re.sub(r"^[\d①-⑳]+[.、)]?\s*", "", title)
            if title and not SKIP_SECTION.search(title):
                cur = title[:20]
                sections.setdefault(cur, [])
            continue

        if SKIP_SECTION.search(cur):
            continue

        # ── 表格行：交给 _split_terms（它会优先抓反引号里的英文词条）──
        if s.startswith("|"):
            for t in _split_terms(s):
                sections.setdefault(cur, []).append(t)
            continue

        # ── 列表项 / 普通行：都交给 _split_terms ──
        if re.match(r"^[-*+]\s+", s):
            body = re.sub(r"^[-*+]\s+", "", s)
            for x in _split_terms(body):
                sections.setdefault(cur, []).append(x)
            continue

        if not _CN_EXPLAIN.search(s):
            for x in _split_terms(s):
                sections.setdefault(cur, []).append(x)

    # 去重 + 过滤空小节
    out: Dict[str, List[str]] = {}
    for k, vals in sections.items():
        seen, uniq = set(), []
        for v in vals:
            key = v.lower()
            if v and key not in seen:
                seen.add(key)
                uniq.append(v)
        if uniq:
            out[k] = uniq[:120]
    return out


def build() -> Dict[str, Any]:
    refs = _skill_refs()
    result: Dict[str, Any] = {}
    for slot, fname in SLOT_FILES.items():
        sections = parse_module(refs / fname)
        total = sum(len(v) for v in sections.values())
        result[slot] = {
            "file": fname,
            "sections": sections,
            "total": total,
        }
    return result


if __name__ == "__main__":
    data = build()
    out = Path(__file__).resolve().parent / "nsfw_terms_cache.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    grand = 0
    for slot, info in data.items():
        grand += info["total"]
        print(f"{slot:8} {info['total']:4} 条 / {len(info['sections'])} 小节")
        for sname, arr in list(info["sections"].items())[:2]:
            print(f"    [{sname}] {', '.join(arr[:4])}")
    print(f"\n合计 {grand} 条")
    print(f"写出: {out}")
