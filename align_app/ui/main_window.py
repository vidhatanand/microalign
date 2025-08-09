"""Main window wrapper that composes small helper modules.

Public API remains: from align_app.ui.main_window import MainWindow
"""

from __future__ import annotations

from typing import Optional

from PyQt5 import QtCore, QtWidgets  # type: ignore

from align_app.ui.sidebar import build_sidebar, highlight_current_in_sidebar
from align_app.ui.watchers import rebuild_watchers
from align_app.ui.top_toolbar import build_top_toolbar
from align_app.ui.context_toolbar import build_context_toolbar
from align_app.project import ProjectManager, ProjectInfo
from align_app.similarity.manager import SimilarityManager

from align_app.ui.mw.layout import build_main_ui
from align_app.ui.mw.menus import build_menus, about_dialog
from align_app.ui.mw.handlers import (
    sidebar_double_clicked,
    on_project_changed,
    fs_changed,
    fs_refresh,
    on_crop_progress,
    welcome_startup,
)


class MainWindow(QtWidgets.QMainWindow):
    """Main app window wiring canvas, toolbars, sidebar, and project manager."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MicroAlign")

        build_main_ui(self)

        self.project = ProjectManager(self)
        self.project.changed.connect(self._on_project_changed)
        build_menus(self)

        build_top_toolbar(self)
        build_context_toolbar(self)

        self.sidebar.itemDoubleClicked.connect(self._sidebar_double_clicked)

        self.canvas.currentPathChanged.connect(
            lambda _p: highlight_current_in_sidebar(self.sidebar, self.canvas)
        )
        self.canvas.cropProgress.connect(self._on_crop_progress)

        build_sidebar(self.sidebar, self.canvas)
        rebuild_watchers(self.watcher, self.canvas)
        highlight_current_in_sidebar(self.sidebar, self.canvas)

        self.similarity = SimilarityManager(self)
        self.similarity.sidebar_rebuilt()

        QtCore.QTimer.singleShot(200, lambda: welcome_startup(self))

    # ----------------- Routed handlers -----------------

    def _about(self) -> None:
        about_dialog(self)

    def _toggle_sidebar(self, visible: bool) -> None:
        self.sidebar.setVisible(bool(visible))
        if visible:
            self.centralWidget().setSizes([350, self.width() - 350])
        else:
            self.centralWidget().setSizes([0, self.width()])

    def _sidebar_double_clicked(
        self, item: QtWidgets.QTreeWidgetItem, col: int
    ) -> None:
        sidebar_double_clicked(self, item, col)

    def _on_project_changed(self, info: Optional[ProjectInfo]) -> None:
        on_project_changed(self, info)
        if hasattr(self, "similarity"):
            self.similarity.sidebar_rebuilt()

    def _fs_changed(self, path: str) -> None:
        fs_changed(self, path)

    def _fs_refresh(self) -> None:
        fs_refresh(self)
        if hasattr(self, "similarity"):
            self.similarity.sidebar_rebuilt()

    def _on_crop_progress(self, done: int, total: int) -> None:
        on_crop_progress(self, done, total)
