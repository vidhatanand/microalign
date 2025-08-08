from __future__ import annotations

from typing import Optional

from PyQt5 import QtCore, QtWidgets  # pylint: disable=no-name-in-module

from .canvas_model import CanvasModelMixin
from .canvas_view import CanvasViewMixin
from .canvas_interact import CanvasInteractMixin
from .canvas_crop_impl import CanvasCropMixin


class CanvasWidget(
    QtWidgets.QWidget,
    CanvasModelMixin,
    CanvasViewMixin,
    CanvasInteractMixin,
    CanvasCropMixin,
):
    """Composed canvas widget using mixins for model/view/interact/crop."""

    gap = 8  # panel gap

    # Signals for external UI
    currentPathChanged = QtCore.pyqtSignal(object)  # Path or None
    cropProgress = QtCore.pyqtSignal(int, int)  # done, total
    modeChanged = QtCore.pyqtSignal(bool)  # True if perspective
    activeCornerChanged = QtCore.pyqtSignal(int)  # 0..3

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        QtWidgets.QWidget.__init__(self, parent)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setMouseTracking(True)

        # init mixins
        self._init_model()
        self._init_view()
        self._init_interact()
        self._init_crop()

    # ---- signal helpers used by mixins ----
    def _emit_crop_progress(self, done: int, total: int) -> None:
        self.cropProgress.emit(done, total)

    def _on_mode_changed(self, is_persp: bool) -> None:
        self.modeChanged.emit(bool(is_persp))

    def _on_active_corner_changed(self, idx: int) -> None:
        self.activeCornerChanged.emit(int(idx))

    # ---- wrappers to emit current-path changes ----
    def set_paths(self, *args, **kwargs) -> None:  # type: ignore[override]
        CanvasModelMixin.set_paths(self, *args, **kwargs)
        self.currentPathChanged.emit(self.current_path())

    def next_image(self) -> None:  # type: ignore[override]
        CanvasModelMixin.next_image(self)
        self.currentPathChanged.emit(self.current_path())

    def prev_image(self) -> None:  # type: ignore[override]
        CanvasModelMixin.prev_image(self)
        self.currentPathChanged.emit(self.current_path())
