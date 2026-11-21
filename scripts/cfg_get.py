#!/usr/bin/env python3
"""从运行期 config.json 取单个键，供 shell 脚本调用。

Windows 上 ``config.json`` 路径含反斜杠，直接拼进 ``python3 -c "...open('C:\\Users\\...')"``
会被当成转义序列而报 ``truncated \\UXXXXXXXX escape``。本工具改为 argv 传参，
彻底绕开转义问题。

用法::

    python3 cfg_get.py <config.json> <key> [default]

* 值经 ``os.path.expanduser`` 展开（``~`` / ``~/...``）。
* 缺失或读取失败时输出 ``default``（未给则空行），退出码 0，方便 shell 兜底。
"""

from __future__ import annotations

import json
import os
import sys


def main(argv: list) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    path, key = argv[0], argv[1]
    default = argv[2] if len(argv) > 2 else ""

    value = None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            value = data.get(key)
    except Exception:
        value = None

    if value is None or value == "":
        print(default)
        return 0

    if isinstance(value, bool):
        print("1" if value else "0")
        return 0

    print(os.path.expanduser(str(value)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
