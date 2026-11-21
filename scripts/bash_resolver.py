#!/usr/bin/env python3
"""bash 解析：Windows 上 ``bash`` 常被解析成 WSL 的 ``C:\\Windows\\System32\\bash.exe``。

引擎的 shell 管线（``gpu-pipeline/*.sh``、``install.sh``）是 POSIX 脚本，
必须交给 Git for Windows 的 Git Bash 执行，否则会报
``WSL ERROR: execvpe(/bin/bash) failed``。

本模块提供 ``bash_executable()``，返回可直接用于 ``subprocess`` 的 bash 路径：

* POSIX：``bash``
* Windows：按优先级探测 Git Bash（``git --exec-path`` 反推 / 常见安装位置 /
  ``AMAZINGDRAW_BASH`` 覆盖）；找不到时回退 ``bash`` 并保持旧行为。

仅依赖标准库。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

_CACHED: Optional[str] = None

# Git for Windows 的典型安装位置（含 32 位与 scoop / 便携版）
_WINDOWS_CANDIDATES = (
    r"C:\Program Files\Git\bin\bash.exe",
    r"C:\Program Files\Git\usr\bin\bash.exe",
    r"C:\Program Files (x86)\Git\bin\bash.exe",
    r"C:\Program Files (x86)\Git\usr\bin\bash.exe",
)


def _from_git_exec_path() -> Optional[str]:
    """用 ``git --exec-path`` 反推 Git 安装根，再定位 bash.exe。"""
    git = shutil.which("git")
    if not git:
        return None
    try:
        out = subprocess.run(
            [git, "--exec-path"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except Exception:
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    # <GitRoot>\mingw64\libexec\git-core  →  <GitRoot>\bin\bash.exe
    exec_path = Path(out.stdout.strip())
    for parent in exec_path.parents:
        for rel in ("bin/bash.exe", "usr/bin/bash.exe"):
            cand = parent / rel
            if cand.is_file():
                return str(cand)
    return None


def _is_wsl_bash(path: str) -> bool:
    """识别 WSL 的 bash（System32 / WindowsApps 下的 bash.exe）。"""
    lowered = path.replace("/", "\\").lower()
    return "\\windows\\system32\\bash" in lowered or "\\windowsapps\\bash" in lowered


def bash_executable() -> str:
    """返回可直接交给 subprocess 的 bash 路径。"""
    global _CACHED
    if _CACHED is not None:
        return _CACHED

    override = os.environ.get("AMAZINGDRAW_BASH")
    if isinstance(override, str) and override.strip():
        _CACHED = override.strip()
        return _CACHED

    if sys.platform != "win32":
        _CACHED = "bash"
        return _CACHED

    for cand in _WINDOWS_CANDIDATES:
        if Path(cand).is_file():
            _CACHED = cand
            return _CACHED

    from_git = _from_git_exec_path()
    if from_git:
        _CACHED = from_git
        return _CACHED

    # PATH 上的 bash 若不是 WSL，也可用
    found = shutil.which("bash")
    if found and not _is_wsl_bash(found):
        _CACHED = found
        return _CACHED

    # 兜底：保持旧行为（可能失败），但至少路径语义一致
    _CACHED = "bash"
    return _CACHED


def bash_argv(*args: str) -> list:
    """构造 ``[bash, *args]``，供 subprocess 直接使用。"""
    return [bash_executable(), *args]


if __name__ == "__main__":
    print(bash_executable())
