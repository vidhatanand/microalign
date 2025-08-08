from __future__ import annotations

from PyQt5 import QtCore, QtWidgets  # pylint: disable=no-name-in-module


def _lbl(tb: QtWidgets.QToolBar, text: str) -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text)
    # Match toolbar button font size
    lbl.setFont(tb.font())
    return lbl


def build_top_toolbar(mw) -> None:
    """Construct the top toolbar on the given MainWindow instance."""
    tb = mw.toolbar_top
    tb.clear()
    add = tb.addAction
    style = mw.style()

    # ---- Sidebar toggle (collapsible)
    act_sidebar = QtWidgets.QAction(
        style.standardIcon(QtWidgets.QStyle.SP_DirOpenIcon), "Sidebar", mw
    )
    act_sidebar.setCheckable(True)
    act_sidebar.setChecked(True)
    act_sidebar.toggled.connect(mw._toggle_sidebar)
    add(act_sidebar)

    tb.addSeparator()

    # ---- Paths ----
    act_base = QtWidgets.QAction("Base…", mw, triggered=mw._pick_base_image)
    act_src = QtWidgets.QAction("Source Dir…", mw, triggered=mw._pick_src_dir)
    act_align = QtWidgets.QAction("Align Out…", mw, triggered=mw._pick_align_out)
    act_crop_dir = QtWidgets.QAction("Crops Out…", mw, triggered=mw._pick_crop_out)
    act_reload = QtWidgets.QAction("Reload", mw, triggered=mw._reload_all)

    for a in (act_base, act_src, act_align, act_crop_dir, act_reload):
        add(a)

    tb.addSeparator()
    add(QtWidgets.QAction("Overlay", mw, triggered=mw.toggle_overlay))
    add(QtWidgets.QAction("Outline", mw, triggered=mw.toggle_outline))

    # ---- Collective view zoom (top-left anchored) ----
    tb.addSeparator()
    tb.addWidget(_lbl(tb, "View Zoom:"))

    btn_minus = QtWidgets.QToolButton()
    btn_minus.setText("−")
    btn_minus.clicked.connect(lambda: mw._bump_view_zoom(-0.1))
    tb.addWidget(btn_minus)

    mw.zoom_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    mw.zoom_slider.setMinimum(25)  # 0.25x
    mw.zoom_slider.setMaximum(500)  # 5.0x
    mw.zoom_slider.setValue(100)  # 1.0x
    mw.zoom_slider.setFixedWidth(180)
    mw.zoom_slider.valueChanged.connect(mw._on_zoom_slider)
    tb.addWidget(mw.zoom_slider)

    btn_plus = QtWidgets.QToolButton()
    btn_plus.setText("+")
    btn_plus.clicked.connect(lambda: mw._bump_view_zoom(+0.1))
    tb.addWidget(btn_plus)

    btn_reset = QtWidgets.QToolButton()
    btn_reset.setText("Reset")
    btn_reset.clicked.connect(mw._reset_view_zoom)
    tb.addWidget(btn_reset)

    # Hand (pan) toggle – pans BOTH panels when zoomed
    mw.act_hand = QtWidgets.QAction("🖐", mw, checkable=True)
    mw.act_hand.setToolTip("Pan view")
    mw.act_hand.toggled.connect(mw._toggle_hand_pan)
    tb.addAction(mw.act_hand)

    # ---- Alpha (overlay blend) ----
    tb.addSeparator()
    tb.addWidget(_lbl(tb, "Alpha:"))
    mw.alpha_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    mw.alpha_slider.setMinimum(0)
    mw.alpha_slider.setMaximum(100)
    mw.alpha_slider.setValue(int(round(mw.canvas.alpha * 100)))
    mw.alpha_slider.setFixedWidth(120)
    mw.alpha_slider.valueChanged.connect(
        lambda v: (setattr(mw.canvas, "alpha", v / 100.0), mw.canvas.update())
    )
    tb.addWidget(mw.alpha_slider)

    # ---- Navigation group (Prev/Next/Save/Save+Next) ----
    tb.addSeparator()
    tb.addWidget(_lbl(tb, "Navigate:"))
    add(QtWidgets.QAction("Prev", mw, triggered=lambda: mw.canvas.prev_image()))
    add(QtWidgets.QAction("Next", mw, triggered=lambda: mw.canvas.next_image()))
    add(
        QtWidgets.QAction(
            "Save", mw, triggered=lambda: mw.canvas.save_current_aligned()
        )
    )
    add(
        QtWidgets.QAction(
            "Save+Next",
            mw,
            triggered=lambda: (
                mw.canvas.save_current_aligned(),
                mw.canvas.next_image(),
            ),
        )
    )

    # ---- Undo / Redo / Reset current image ----
    tb.addSeparator()
    act_undo = QtWidgets.QAction(
        style.standardIcon(QtWidgets.QStyle.SP_ArrowBack), "Undo", mw
    )
    act_undo.triggered.connect(mw.canvas.undo)
    tb.addAction(act_undo)

    act_redo = QtWidgets.QAction(
        style.standardIcon(QtWidgets.QStyle.SP_ArrowForward), "Redo", mw
    )
    act_redo.triggered.connect(mw.canvas.redo)
    tb.addAction(act_redo)

    act_reset = QtWidgets.QAction(
        style.standardIcon(QtWidgets.QStyle.SP_BrowserReload), "Reset Image", mw
    )
    act_reset.triggered.connect(mw.canvas.reset_current)
    tb.addAction(act_reset)
