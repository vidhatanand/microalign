"""Filesystem watcher utilities."""

from __future__ import annotations

from pathlib import Path
from typing import List

from PyQt5 import QtCore  # pylint: disable=no-name-in-module


def collect_dirs_recursive(root: Path, limit: int = 2000) -> List[str]:
    out: List[str] = []
    try:
        if root.exists() and root.is_dir():
            out.append(str(root))
            for p in root.rglob("*"):
                if p.is_dir():
                    out.append(str(p))
                    if len(out) >= limit:
                        break
    except Exception:
        pass
    return out


def rebuild_watchers(watcher: QtCore.QFileSystemWatcher, canvas) -> None:
    """Re-add watchers for base/src/align/crop directories."""
    try:
        olds = watcher.directories() + watcher.files()
        if olds:
            watcher.removePaths(olds)
    except Exception:
        pass

    paths: List[str] = []
    if canvas.base_path and canvas.base_path.exists():
        paths.append(str(canvas.base_path))

    for d in (canvas.src_dir, canvas.align_out, canvas.crop_out):
        if d:
            paths += collect_dirs_recursive(d)

    paths = [p for p in paths if Path(p).exists()]
    uniq = []
    seen = set()
    for p in paths:
        if p not in seen:
            uniq.append(p)
            seen.add(p)

    if uniq:
        try:
            watcher.addPaths(uniq)
        except Exception:
            tops = []
            for d in (canvas.src_dir, canvas.align_out, canvas.crop_out):
                if d and d.exists():
                    tops.append(str(d))
            if tops:
                try:
                    watcher.addPaths(tops)
                except Exception:
                    pass
