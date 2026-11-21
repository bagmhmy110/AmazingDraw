#!/usr/bin/env python3
"""将提示词中的年龄和低龄化表述统一为21岁成年人。

用法：
  python normalize_age.py input.txt
  python normalize_age.py input1.txt input2.txt --outdir normalized
  python normalize_age.py input.txt --check

脚本不会覆盖输入文件。不指定--outdir时，将转换后的文本输出到标准输出。
指定--check时，只检查转换后是否还残留低龄化词语；如果有残留则返回非零状态码。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


# 先替换较长的词组，再替换较短的词组。
REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\blate twenties or early thirties\b", re.I), "21岁成年人"),
    (re.compile(r"\blate teens or early twenties\b", re.I), "21岁成年人"),
    (re.compile(r"\b(?:early|mid|late)[ -]teens\b", re.I), "21岁成年人"),
    (re.compile(r"\b(?:early|mid|late)[ -]twenties\b", re.I), "21岁成年人"),
    (re.compile(r"\b(?:early|mid|late)[ -]thirties\b", re.I), "21岁成年人"),
    (re.compile(r"\b(?:18|19|20)-year-old\b", re.I), "21岁"),
    (re.compile(r"\byoung adult woman\b", re.I), "21岁成年女性"),
    (re.compile(r"\byoung adult man\b", re.I), "21岁成年男性"),
    (re.compile(r"\byoung adult\b", re.I), "21岁成年人"),
    (re.compile(r"\byoung girl\b", re.I), "21岁成年女性"),
    (re.compile(r"\byoung woman\b", re.I), "21岁成年女性"),
    (re.compile(r"\byoung man\b", re.I), "21岁成年男性"),
    (re.compile(r"\bsmall boy\b", re.I), "21岁成年男性"),
    (re.compile(r"\blittle boy\b", re.I), "21岁成年男性"),
    (re.compile(r"\bsmall girl\b", re.I), "21岁成年女性"),
    (re.compile(r"\blittle girl\b", re.I), "21岁成年女性"),
    (re.compile(r"pure, innocent refined features", re.I), "精致优雅的五官"),
    (re.compile(r"稚嫩|幼态|学生感"), "细腻"),
    (re.compile(r"年轻女孩|少女"), "21岁成年女性"),
    (re.compile(r"年轻女性|年轻女人"), "21岁成年女性"),
    (re.compile(r"年轻男性|年轻男人|少年"), "21岁成年男性"),
]

RESIDUALS = [
    re.compile(r"\b(?:minor|child|children|childlike|childish|teen|teenage|schoolgirl|school-age)\w*\b", re.I),
    re.compile(r"\b(?:underage|under-aged)\b", re.I),
    re.compile(r"未成年|未满十八|儿童|小孩|中学生|学生妹|童颜性化"),
]


def normalize(text: str) -> str:
    """按规则转换年龄词，并避免出现重复年龄短语。"""
    for pattern, replacement in REPLACEMENTS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"\b21岁\s+21岁\b", "21岁", text)
    text = re.sub(r"\b21岁\s+(21岁成年女性|21岁成年男性|21岁成年人)\b", r"\1", text)
    text = re.sub(r"21岁成年女性\s*，?\s*21岁", "21岁成年女性", text)
    text = re.sub(r"21岁成年男性\s*，?\s*21岁", "21岁成年男性", text)
    return text


def residual_terms(text: str) -> list[str]:
    """返回转换后仍然存在的低龄化词语。"""
    found: list[str] = []
    for pattern in RESIDUALS:
        found.extend(match.group(0) for match in pattern.finditer(text))
    return sorted(set(found), key=str.casefold)


def output_path(outdir: Path, source: Path) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir / f"{source.stem}_21岁{source.suffix}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="输入的提示词文件")
    parser.add_argument("--outdir", type=Path, help="写入转换副本的目录")
    parser.add_argument("--check", action="store_true", help="只检查低龄化词语残留")
    args = parser.parse_args()

    exit_code = 0
    for source in args.inputs:
        text = source.read_text(encoding="utf-8", errors="replace")
        transformed = normalize(text)
        residual = residual_terms(transformed)
        if residual:
            print(f"{source}: 仍有低龄化词语：{', '.join(residual)}", file=sys.stderr)
            exit_code = 2
        if args.check:
            continue
        if args.outdir:
            target = output_path(args.outdir, source)
            target.write_text(transformed, encoding="utf-8")
            print(target)
        else:
            if len(args.inputs) > 1:
                print(f"\n===== {source.name} =====")
            sys.stdout.write(transformed)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
