from __future__ import annotations

from PyQt5 import QtCore, QtWidgets  # type: ignore

from align_app.utils.img_io import clamp


def _lbl(tb: QtWidgets.QToolBar, text: str) -> QtWidgets.QLabel:
    l = QtWidgets.QLabel(text)
    l.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
    l.setFont(tb.font())
    return l


def build_top_toolbar(mw) -> None:
    tb = mw.toolbar_top
    tb.clear()

    style = mw.style()

    # ---- Sidebar toggle (<< / >>) – FIRST on the toolbar ----
    mw.side_btn = QtWidgets.QToolButton()
    mw.side_btn.setCheckable(True)
    mw.side_btn.setChecked(True)
    mw.side_btn.setText("<<")
    mw.side_btn.setToolTip("Hide sidebar")

    def _toggle_side(v: bool) -> None:
        mw._toggle_sidebar(bool(v))
        mw.side_btn.setText("<<" if v else ">>")
        mw.side_btn.setToolTip("Hide sidebar" if v else "Show sidebar")

    mw.side_btn.toggled.connect(_toggle_side)
    tb.addWidget(mw.side_btn)

    tb.addSeparator()

    # ---- Navigation & Save group ----
    nav_widget = QtWidgets.QWidget()
    nav_layout = QtWidgets.QHBoxLayout(nav_widget)
    nav_layout.setContentsMargins(0, 0, 0, 0)
    nav_layout.setSpacing(4)

    prev_btn = QtWidgets.QToolButton()
    prev_btn.setText("Prev")
    prev_btn.clicked.connect(lambda: mw.canvas.prev_image())
    next_btn = QtWidgets.QToolButton()
    next_btn.setText("Next")
    next_btn.clicked.connect(lambda: mw.canvas.next_image())

    save_btn = QtWidgets.QToolButton()
    save_btn.setText("Save")
    save_btn.clicked.connect(lambda: mw.canvas.save_current_aligned())
    save_next_btn = QtWidgets.QToolButton()
    save_next_btn.setText("Save+Next")

    def _save_next():
        mw.canvas.save_current_aligned()
        mw.canvas.next_image()

    save_next_btn.clicked.connect(_save_next)

    for b in (prev_btn, next_btn, save_btn, save_next_btn):
        b.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        nav_layout.addWidget(b)

    tb.addWidget(nav_widget)

    tb.addSeparator()

    # ---- View Zoom + Hand Pan ----
    tb.addWidget(_lbl(tb, "View Zoom:"))
    mw.view_zoom_minus = QtWidgets.QToolButton()
    mw.view_zoom_minus.setText("−")
    mw.view_zoom_minus.clicked.connect(lambda: _bump_view_zoom(mw, -0.1))
    tb.addWidget(mw.view_zoom_minus)

    mw.zoom_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    mw.zoom_slider.setMinimum(25)  # 0.25x
    mw.zoom_slider.setMaximum(500)  # 5.0x
    mw.zoom_slider.setValue(int(round(mw.canvas.view_zoom * 100)))
    mw.zoom_slider.setFixedWidth(200)
    mw.zoom_slider.valueChanged.connect(lambda v: _on_zoom_slider(mw, v))
    tb.addWidget(mw.zoom_slider)

    mw.view_zoom_plus = QtWidgets.QToolButton()
    mw.view_zoom_plus.setText("+")
    mw.view_zoom_plus.clicked.connect(lambda: _bump_view_zoom(mw, +0.1))
    tb.addWidget(mw.view_zoom_plus)

    mw.view_zoom_reset = QtWidgets.QToolButton()
    mw.view_zoom_reset.setText("Reset")
    mw.view_zoom_reset.clicked.connect(lambda: _reset_view_zoom(mw))
    tb.addWidget(mw.view_zoom_reset)

    mw.hand_pan_btn = QtWidgets.QToolButton()
    mw.hand_pan_btn.setCheckable(True)
    mw.hand_pan_btn.setText("Pan")
    mw.hand_pan_btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
    # AlignCanvas API:
    mw.hand_pan_btn.toggled.connect(lambda v: mw.canvas.set_hand_pan_mode(bool(v)))
    tb.addWidget(mw.hand_pan_btn)

    tb.addSeparator()

    # ---- Undo / Redo / Reset current image / Reset view ----
    undo_btn = QtWidgets.QToolButton()
    undo_btn.setIcon(style.standardIcon(QtWidgets.QStyle.SP_ArrowBack))
    undo_btn.setText("Undo")
    undo_btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
    undo_btn.clicked.connect(mw.canvas.undo)

    redo_btn = QtWidgets.QToolButton()
    redo_btn.setIcon(style.standardIcon(QtWidgets.QStyle.SP_ArrowForward))
    redo_btn.setText("Redo")
    redo_btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
    redo_btn.clicked.connect(mw.canvas.redo)

    reset_btn = QtWidgets.QToolButton()
    reset_btn.setText("Reset Image")
    # AlignCanvas API:
    reset_btn.clicked.connect(mw.canvas.reset_current_image)

    reset_view_btn = QtWidgets.QToolButton()
    reset_view_btn.setText("Reset View")
    reset_view_btn.clicked.connect(lambda: _reset_view_zoom(mw))

    for w in (undo_btn, redo_btn, reset_btn, reset_view_btn):
        tb.addWidget(w)


def _on_zoom_slider(mw, value: int) -> None:
    mw.canvas.view_zoom = value / 100.0
    mw.canvas.update()


def _bump_view_zoom(mw, delta: float) -> None:
    v = clamp(mw.canvas.view_zoom + delta, 0.25, 5.0)
    mw.zoom_slider.blockSignals(True)
    mw.zoom_slider.setValue(int(round(v * 100)))
    mw.zoom_slider.blockSignals(False)
    mw.canvas.view_zoom = v
    mw.canvas.update()


def _reset_view_zoom(mw) -> None:
    mw.zoom_slider.blockSignals(True)
    mw.zoom_slider.setValue(100)
    mw.zoom_slider.blockSignals(False)
    mw.canvas.view_zoom = 1.0
    # AlignCanvas uses QPointF
    from PyQt5 import QtCore as _QtCore  # type: ignore

    mw.canvas.view_pan = _QtCore.QPointF(0.0, 0.0)
    mw.canvas.update()
