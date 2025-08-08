from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import Qt, QSize, QTimer, QFileSystemWatcher
from PyQt5.QtWidgets import (
    QMainWindow,
    QSplitter,
    QWidget,
    QVBoxLayout,
    QToolBar,
    QAction,
    QFileDialog,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QLabel,
)

from align_app.ui.align_canvas import AlignCanvas
from align_app.utils.img_io import SUPPORTED_LOWER, clamp


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MicroAlign")
        self.resize(1400, 900)

        splitter = QSplitter(Qt.Horizontal, self)
        self.setCentralWidget(splitter)

        # Left: compact sidebar
        self.sidebar = QTreeWidget()
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setMinimumWidth(320)
        splitter.addWidget(self.sidebar)

        # Right: toolbars + canvas
        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(0, 0, 0, 0)

        self.toolbar_paths = QToolBar("Paths")
        self.toolbar_align = QToolBar("Align")
        for tb in (self.toolbar_paths, self.toolbar_align):
            tb.setIconSize(QSize(20, 20))

        layout.addWidget(self.toolbar_paths)
        layout.addWidget(self.toolbar_align)

        self.canvas = AlignCanvas()
        layout.addWidget(self.canvas, 1)

        splitter.addWidget(right)
        splitter.setSizes([350, 1050])

        # Build toolbars
        self._build_paths_toolbar()
        self._build_align_toolbar()

        # Sidebar interactions
        self.sidebar.itemDoubleClicked.connect(self._sidebar_double_clicked)

        # Status label (live)
        self.status_label = QLabel()
        self.status_label.setStyleSheet("QLabel { color: #ddd; padding-left: 8px; }")
        self.toolbar_align.addSeparator()
        self.toolbar_align.addWidget(self.status_label)
        self._start_status_timer()

        # File/folder watcher
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self._fs_changed)
        self.watcher.fileChanged.connect(self._fs_changed)
        self._fs_timer = QTimer(self)
        self._fs_timer.setSingleShot(True)
        self._fs_timer.timeout.connect(lambda: self._fs_refresh())


        # Keep sidebar selection in sync with current image
        self.canvas.currentPathChanged.connect(self._highlight_current_in_sidebar)

        # Initial sidebar build & watchers
        self._rebuild_sidebar()
        self._update_watchers()
        self._highlight_current_in_sidebar()

    # ---------- Toolbars ----------

    def _build_paths_toolbar(self):
        add = self.toolbar_paths.addAction

        act_base = QAction("Base Image…", self, triggered=self._pick_base_image)
        act_src = QAction("Source Dir…", self, triggered=self._pick_src_dir)
        act_align = QAction("Align Out…", self, triggered=self._pick_align_out)
        act_crop = QAction("Crops Out…", self, triggered=self._pick_crop_out)
        act_reload = QAction("Reload", self, triggered=self._reload_all)
        act_del = QAction("Delete Selected", self, triggered=self._delete_selected)

        for a in (act_base, act_src, act_align, act_crop, act_reload):
            add(a)
        self.toolbar_paths.addSeparator()
        add(act_del)

    def _build_align_toolbar(self):
        add = self.toolbar_align.addAction

        # Navigation & Save
        a_prev = QAction(
            "Prev", self, triggered=lambda checked=False: self.canvas.prev_image()
        )
        a_next = QAction(
            "Next", self, triggered=lambda checked=False: self.canvas.next_image()
        )
        a_save = QAction(
            "Save",
            self,
            triggered=lambda checked=False: self.canvas.save_current_aligned(),
        )
        a_savn = QAction(
            "Save+Next",
            self,
            triggered=lambda checked=False: (
                self.canvas.save_current_aligned(),
                self.canvas.next_image(),
            ),
        )
        for a, tip in [
            (a_prev, "Show previous image from Source directory"),
            (a_next, "Show next image from Source directory"),
            (a_save, "Save full-resolution aligned PNG to Align Out"),
            (a_savn, "Save current aligned PNG, then go to next image"),
        ]:
            a.setToolTip(tip)
            add(a)

        self.toolbar_align.addSeparator()

        # Move buttons
        for label, dx, dy in [("←", -1, 0), ("→", +1, 0), ("↑", 0, -1), ("↓", 0, +1)]:
            add(
                QAction(
                    label,
                    self,
                    triggered=(
                        lambda dx=dx, dy=dy: (
                            lambda checked=False: self.canvas.move_dxdy(
                                dx * self.canvas.step, dy * self.canvas.step
                            )
                        )
                    )(),
                )
            )
        self.toolbar_align.addSeparator()

        # Step / Rotate / Zoom
        add(
            QAction(
                "Step−",
                self,
                triggered=lambda checked=False: setattr(
                    self.canvas, "step", max(0.5, self.canvas.step - 1.0)
                ),
            )
        )
        add(
            QAction(
                "Step+",
                self,
                triggered=lambda checked=False: setattr(
                    self.canvas, "step", min(50.0, self.canvas.step + 1.0)
                ),
            )
        )
        self.toolbar_align.addSeparator()
        add(
            QAction(
                "Rot−",
                self,
                triggered=lambda checked=False: self.canvas.rotate_deg(
                    -self.canvas.rot_step
                ),
            )
        )
        add(
            QAction(
                "Rot+",
                self,
                triggered=lambda checked=False: self.canvas.rotate_deg(
                    +self.canvas.rot_step
                ),
            )
        )
        self.toolbar_align.addSeparator()
        add(
            QAction(
                "Zoom−",
                self,
                triggered=lambda checked=False: self.canvas.zoom_factor(
                    1.0 - self.canvas.scale_step
                ),
            )
        )
        add(
            QAction(
                "Zoom+",
                self,
                triggered=lambda checked=False: self.canvas.zoom_factor(
                    1.0 + self.canvas.scale_step
                ),
            )
        )
        add(
            QAction(
                "µZoom−",
                self,
                triggered=lambda checked=False: self.canvas.zoom_factor(
                    1.0 - self.canvas.micro_scale_step
                ),
            )
        )
        add(
            QAction(
                "µZoom+",
                self,
                triggered=lambda checked=False: self.canvas.zoom_factor(
                    1.0 + self.canvas.micro_scale_step
                ),
            )
        )
        self.toolbar_align.addSeparator()

        # View toggles
        add(
            QAction(
                "Reset",
                self,
                triggered=lambda checked=False: self.canvas.reset_current(),
            )
        )
        add(
            QAction(
                "Overlay", self, triggered=lambda checked=False: self._toggle_overlay()
            )
        )
        add(
            QAction(
                "Alpha−",
                self,
                triggered=lambda checked=False: setattr(
                    self.canvas, "alpha", clamp(self.canvas.alpha - 0.05, 0.0, 1.0)
                ),
            )
        )
        add(
            QAction(
                "Alpha+",
                self,
                triggered=lambda checked=False: setattr(
                    self.canvas, "alpha", clamp(self.canvas.alpha + 0.05, 0.0, 1.0)
                ),
            )
        )
        add(QAction("Grid", self, triggered=lambda checked=False: self._toggle_grid()))
        add(
            QAction(
                "Grid−",
                self,
                triggered=lambda checked=False: setattr(
                    self.canvas, "grid_step", max(10, self.canvas.grid_step - 5)
                ),
            )
        )
        add(
            QAction(
                "Grid+",
                self,
                triggered=lambda checked=False: setattr(
                    self.canvas, "grid_step", min(200, self.canvas.grid_step + 5)
                ),
            )
        )
        add(
            QAction(
                "Outline", self, triggered=lambda checked=False: self._toggle_outline()
            )
        )
        self.toolbar_align.addSeparator()

        # Crop (choice dialog lives in MainWindow)
        add(
            QAction(
                "Crop", self, triggered=lambda checked=False: self._choose_crop_target()
            )
        )

        # After any toolbar action, repaint & sync highlight
        self.toolbar_align.actionTriggered.connect(
            lambda _a: (self.canvas.update(), self._highlight_current_in_sidebar())
        )

    # ---------- Status label ----------

    def _start_status_timer(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_status)
        self._timer.start(150)

    def _refresh_status(self):
        step = self.canvas.step
        rstep = self.canvas.rot_step
        zstep = self.canvas.scale_step * 100.0
        mzstep = self.canvas.micro_scale_step * 100.0
        alpha = self.canvas.alpha
        txt = (
            f"Move step: {step:.1f}px   Rot step: {rstep:.2f}°   "
            f"Zoom step: ±{zstep:.2f}% (µ ±{mzstep:.2f}%)   "
            f"Alpha: {alpha:.2f}"
        )
        self.status_label.setText(txt)

    # ---------- Path pickers ----------

    def _pick_base_image(self):
        fn, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Base Image",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.jpe)",
        )
        if fn:
            self.canvas.set_paths(
                base_path=Path(fn), src_dir=None, align_out=None, crop_out=None
            )
            self._rebuild_sidebar()
            self._update_watchers()
            self._highlight_current_in_sidebar()

    def _pick_src_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, "Choose Source Directory", str(Path.home())
        )
        if d:
            self.canvas.set_paths(
                base_path=None, src_dir=Path(d), align_out=None, crop_out=None
            )
            self._rebuild_sidebar()
            self._update_watchers()
            self._highlight_current_in_sidebar()

    def _pick_align_out(self):
        d = QFileDialog.getExistingDirectory(
            self, "Choose Align Out Directory", str(Path.home())
        )
        if d:
            self.canvas.set_paths(
                base_path=None, src_dir=None, align_out=Path(d), crop_out=None
            )
            self._rebuild_sidebar()
            self._update_watchers()
            self._highlight_current_in_sidebar()

    def _pick_crop_out(self):
        d = QFileDialog.getExistingDirectory(
            self, "Choose Crops Out Directory", str(Path.home())
        )
        if d:
            self.canvas.set_paths(
                base_path=None, src_dir=None, align_out=None, crop_out=Path(d)
            )
            self._rebuild_sidebar()
            self._update_watchers()
            self._highlight_current_in_sidebar()

    def _reload_all(self):
        self.canvas.set_paths(
            self.canvas.base_path,
            self.canvas.src_dir,
            self.canvas.align_out,
            self.canvas.crop_out,
        )
        self._rebuild_sidebar()
        self._update_watchers()
        self._highlight_current_in_sidebar()

    # ---------- Sidebar ----------

    def _rebuild_sidebar(self):
        self.sidebar.clear()

        # Base Image
        base_root = QTreeWidgetItem(self.sidebar, ["Base Image"])
        base_root.setExpanded(True)
        if self.canvas.base_path:
            bi = QTreeWidgetItem(base_root, [self.canvas.base_path.name])
            bi.setData(0, Qt.UserRole, str(self.canvas.base_path))
        else:
            QTreeWidgetItem(base_root, ["(none)"])

        # Source Directory
        src_root = QTreeWidgetItem(self.sidebar, ["Source Directory"])
        src_root.setExpanded(True)
        if self.canvas.src_dir:
            head = QTreeWidgetItem(src_root, [str(self.canvas.src_dir)])
            head.setData(0, Qt.UserRole, str(self.canvas.src_dir))
            self._add_dir_tree(head, self.canvas.src_dir)
        else:
            QTreeWidgetItem(src_root, ["(none)"])

        # Align Out
        align_root = QTreeWidgetItem(self.sidebar, ["Align Out"])
        align_root.setExpanded(True)
        if self.canvas.align_out:
            head = QTreeWidgetItem(align_root, [str(self.canvas.align_out)])
            head.setData(0, Qt.UserRole, str(self.canvas.align_out))
            if self.canvas.align_out.exists():
                self._add_dir_tree(head, self.canvas.align_out)
        else:
            QTreeWidgetItem(align_root, ["(none)"])

        # Crops Out
        crop_root = QTreeWidgetItem(self.sidebar, ["Crops Out"])
        crop_root.setExpanded(True)
        if self.canvas.crop_out:
            head = QTreeWidgetItem(crop_root, [str(self.canvas.crop_out)])
            head.setData(0, Qt.UserRole, str(self.canvas.crop_out))
            if self.canvas.crop_out.exists():
                self._add_dir_tree(head, self.canvas.crop_out)
        else:
            QTreeWidgetItem(crop_root, ["(none)"])

        self.sidebar.expandAll()

        if self.canvas.have_base() and self.canvas.have_files():
            self.canvas.idx = min(self.canvas.idx, len(self.canvas.files) - 1)
            self.canvas.update()

        # NEW: select the current file node
        self._highlight_current_in_sidebar()

    def _add_dir_tree(self, parent_item: QTreeWidgetItem, dir_path: Path):
        try:
            entries = sorted(
                dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
            )
        except Exception:
            return
        for p in entries:
            node = QTreeWidgetItem(parent_item, [p.name])
            node.setData(0, Qt.UserRole, str(p))
            if p.is_dir():
                self._add_dir_tree(node, p)

    def _sidebar_double_clicked(self, item: QTreeWidgetItem, _col: int):
        path = item.data(0, Qt.UserRole)
        if not path:
            return
        p = Path(path)
        if p.is_file() and p.suffix.lower() in SUPPORTED_LOWER:
            if self.canvas.files:
                try:
                    idx = self.canvas.files.index(p)
                except ValueError:
                    idx = None
                if idx is not None:
                    self.canvas.idx = idx
                    self.canvas.update()
                    self._highlight_current_in_sidebar()
        elif p.is_dir():
            self.canvas.set_paths(
                base_path=None, src_dir=p, align_out=None, crop_out=None
            )
            self._rebuild_sidebar()
            self._update_watchers()
            self._highlight_current_in_sidebar()

    # ---------- Delete selected ----------

    def _delete_selected(self):
        items = self.sidebar.selectedItems()
        if not items:
            return
        item = items[0]
        path = item.data(0, Qt.UserRole)
        if not path:
            return
        p = Path(path)
        if not p.exists():
            return

        if p.is_dir():
            reply = QMessageBox.question(
                self,
                "Delete Folder?",
                f"Delete the folder and ALL its contents?\n\n{p}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            try:
                shutil.rmtree(p)
            except Exception as e:
                QMessageBox.critical(self, "Delete failed", str(e))
        else:
            reply = QMessageBox.question(
                self,
                "Delete File?",
                f"Delete file?\n\n{p}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            try:
                p.unlink()
            except Exception as e:
                QMessageBox.critical(self, "Delete failed", str(e))

        self._reload_all()

    # ---------- toggles ----------

    def _toggle_overlay(self):
        self.canvas.overlay_mode = not self.canvas.overlay_mode
        self.canvas.update()

    def _toggle_grid(self):
        self.canvas.grid_on = not self.canvas.grid_on
        self.canvas.update()

    def _toggle_outline(self):
        self.canvas.show_outline = not self.canvas.show_outline
        self.canvas.update()

    # ---------- crop choice dialog ----------

    def _choose_crop_target(self):
        if not self.canvas.have_base():
            QMessageBox.information(self, "Crop", "Load a Base image first.")
            return
        if not self.canvas.crop_out:
            QMessageBox.information(self, "Crop", "Pick a Crops Out directory first.")
            return

        box = QMessageBox(self)
        box.setWindowTitle("Crop which images?")
        box.setText(
            "Choose which images to crop with the selected rectangle on the Base image:"
        )
        btn_aligned = box.addButton("Aligned images", QMessageBox.AcceptRole)
        btn_source = box.addButton("Original source images", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Cancel)
        box.exec_()
        clicked = box.clickedButton()
        if clicked == btn_aligned:
            self.canvas.start_crop_mode(use_aligned=True)
        elif clicked == btn_source:
            self.canvas.start_crop_mode(use_aligned=False)
        # Cancel -> do nothing

    # ---------- filesystem watching ----------

    def _collect_dirs_recursive(self, root: Path, limit: int = 2000) -> List[str]:
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

    def _update_watchers(self):
        try:
            olds = self.watcher.directories() + self.watcher.files()
            if olds:
                self.watcher.removePaths(olds)
        except Exception:
            pass

        paths: List[str] = []
        if self.canvas.base_path and self.canvas.base_path.exists():
            paths.append(str(self.canvas.base_path))

        for d in (self.canvas.src_dir, self.canvas.align_out, self.canvas.crop_out):
            if d:
                paths += self._collect_dirs_recursive(d)

        paths = [p for p in paths if Path(p).exists()]
        uniq = []
        seen = set()
        for p in paths:
            if p not in seen:
                uniq.append(p)
                seen.add(p)

        if uniq:
            try:
                self.watcher.addPaths(uniq)
            except Exception:
                tops = []
                for d in (
                    self.canvas.src_dir,
                    self.canvas.align_out,
                    self.canvas.crop_out,
                ):
                    if d and d.exists():
                        tops.append(str(d))
                if tops:
                    try:
                        self.watcher.addPaths(tops)
                    except Exception:
                        pass

    def _fs_changed(self, _path: str):
        self._fs_timer.start(250)

    def _fs_refresh(self):
        cur = self.canvas.current_path()
        self.canvas.set_paths(
            self.canvas.base_path,
            self.canvas.src_dir,
            self.canvas.align_out,
            self.canvas.crop_out,
        )
        if cur and cur in self.canvas.files:
            try:
                self.canvas.idx = self.canvas.files.index(cur)
            except ValueError:
                pass
        self._rebuild_sidebar()
        self._update_watchers()
        self._highlight_current_in_sidebar()

    # ---------- NEW: highlight helper ----------

    def _highlight_current_in_sidebar(self):
        """Select the current moving image in the Source tree."""
        cur = self.canvas.current_path()
        if not cur:
            self.sidebar.clearSelection()
            return

        target = str(cur)

        def find_item_recursive(item: QTreeWidgetItem) -> Optional[QTreeWidgetItem]:
            if item.data(0, Qt.UserRole) == target:
                return item
            for i in range(item.childCount()):
                found = find_item_recursive(item.child(i))
                if found:
                    return found
            return None

        # Prefer the “Source Directory” section
        src_root = None
        for i in range(self.sidebar.topLevelItemCount()):
            root = self.sidebar.topLevelItem(i)
            if root.text(0) == "Source Directory":
                src_root = root
                break

        item_to_select = None
        if src_root:
            item_to_select = find_item_recursive(src_root)
        if not item_to_select:
            # fallback: search whole tree
            for i in range(self.sidebar.topLevelItemCount()):
                root = self.sidebar.topLevelItem(i)
                item_to_select = find_item_recursive(root)
                if item_to_select:
                    break

        if item_to_select:
            self.sidebar.setCurrentItem(item_to_select)
            item_to_select.setSelected(True)
            self.sidebar.scrollToItem(item_to_select)
        else:
            self.sidebar.clearSelection()
