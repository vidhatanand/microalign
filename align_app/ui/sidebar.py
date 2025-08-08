"""Sidebar utilities: build and highlight."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PyQt5 import QtCore, QtWidgets  # pylint: disable=no-name-in-module

from align_app.utils.img_io import SUPPORTED_LOWER


def _add_dir_tree(parent_item: QtWidgets.QTreeWidgetItem, dir_path: Path) -> None:
    try:
        entries = sorted(
            dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
        )
    except Exception:
        return
    for p in entries:
        node = QtWidgets.QTreeWidgetItem(parent_item, [p.name])
        node.setData(0, QtCore.Qt.UserRole, str(p))
        if p.is_dir():
            _add_dir_tree(node, p)


def build_sidebar(tree: QtWidgets.QTreeWidget, canvas) -> None:
    """Rebuild the entire sidebar tree from canvas paths/state."""
    tree.clear()

    # Base Image
    base_root = QtWidgets.QTreeWidgetItem(tree, ["Base Image"])
    base_root.setExpanded(True)
    if canvas.base_path:
        bi = QtWidgets.QTreeWidgetItem(base_root, [canvas.base_path.name])
        bi.setData(0, QtCore.Qt.UserRole, str(canvas.base_path))
    else:
        QtWidgets.QTreeWidgetItem(base_root, ["(none)"])

    # Source Directory
    src_root = QtWidgets.QTreeWidgetItem(tree, ["Source Directory"])
    src_root.setExpanded(True)
    if canvas.src_dir:
        head = QtWidgets.QTreeWidgetItem(src_root, [str(canvas.src_dir)])
        head.setData(0, QtCore.Qt.UserRole, str(canvas.src_dir))
        _add_dir_tree(head, canvas.src_dir)
    else:
        QtWidgets.QTreeWidgetItem(src_root, ["(none)"])

    # Align Out
    align_root = QtWidgets.QTreeWidgetItem(tree, ["Align Out"])
    align_root.setExpanded(True)
    if canvas.align_out:
        head = QtWidgets.QTreeWidgetItem(align_root, [str(canvas.align_out)])
        head.setData(0, QtCore.Qt.UserRole, str(canvas.align_out))
        if canvas.align_out.exists():
            _add_dir_tree(head, canvas.align_out)
    else:
        QtWidgets.QTreeWidgetItem(align_root, ["(none)"])

    # Crops Out
    crop_root = QtWidgets.QTreeWidgetItem(tree, ["Crops Out"])
    crop_root.setExpanded(True)
    if canvas.crop_out:
        head = QtWidgets.QTreeWidgetItem(crop_root, [str(canvas.crop_out)])
        head.setData(0, QtCore.Qt.UserRole, str(canvas.crop_out))
        if canvas.crop_out.exists():
            _add_dir_tree(head, canvas.crop_out)
    else:
        QtWidgets.QTreeWidgetItem(crop_root, ["(none)"])

    tree.expandAll()

    if canvas.have_base() and canvas.have_files():
        canvas.idx = min(canvas.idx, len(canvas.files) - 1)
        canvas.update()


def highlight_current_in_sidebar(tree: QtWidgets.QTreeWidget, canvas) -> None:
    """Select the current moving image in the Source tree."""
    cur = canvas.current_path()
    if not cur:
        tree.clearSelection()
        return

    target = str(cur)

    def find_item_recursive(
        item: QtWidgets.QTreeWidgetItem,
    ) -> Optional[QtWidgets.QTreeWidgetItem]:
        if item.data(0, QtCore.Qt.UserRole) == target:
            return item
        for i in range(item.childCount()):
            found = find_item_recursive(item.child(i))
            if found:
                return found
        return None

    # Prefer the “Source Directory” section
    src_root = None
    for i in range(tree.topLevelItemCount()):
        root = tree.topLevelItem(i)
        if root.text(0) == "Source Directory":
            src_root = root
            break

    item_to_select = None
    if src_root:
        item_to_select = find_item_recursive(src_root)
    if not item_to_select:
        # fallback: search whole tree
        for i in range(tree.topLevelItemCount()):
            root = tree.topLevelItem(i)
            item_to_select = find_item_recursive(root)
            if item_to_select:
                break

    if item_to_select:
        tree.setCurrentItem(item_to_select)
        item_to_select.setSelected(True)
        tree.scrollToItem(item_to_select)
    else:
        tree.clearSelection()
