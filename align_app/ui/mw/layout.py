from __future__ import annotations

from PyQt5 import QtCore, QtWidgets  # type: ignore

from align_app.ui.align_canvas import AlignCanvas


def build_main_ui(mw) -> None:
    """Create splitter, sidebar, toolbars, canvas, status bar, and fs watcher."""
    mw.resize(1400, 900)

    splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, mw)
    mw.setCentralWidget(splitter)

    mw.sidebar = QtWidgets.QTreeWidget()
    mw.sidebar.setHeaderHidden(True)
    mw.sidebar.setMinimumWidth(320)
    splitter.addWidget(mw.sidebar)

    right = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(right)
    layout.setContentsMargins(0, 0, 0, 0)

    mw.toolbar_top = QtWidgets.QToolBar("Top")
    mw.toolbar_bottom = QtWidgets.QToolBar("Bottom")
    for tb in (mw.toolbar_top, mw.toolbar_bottom):
        tb.setIconSize(QtCore.QSize(20, 20))

    layout.addWidget(mw.toolbar_top)
    layout.addWidget(mw.toolbar_bottom)

    mw.canvas = AlignCanvas()
    layout.addWidget(mw.canvas, 1)

    splitter.addWidget(right)
    splitter.setSizes([350, 1050])

    mw.status = QtWidgets.QStatusBar()
    mw.setStatusBar(mw.status)
    mw.project_label = QtWidgets.QLabel("No project")
    mw.status.addWidget(mw.project_label)

    mw.progress = QtWidgets.QProgressBar()
    mw.progress.setVisible(False)
    mw.progress.setFixedWidth(220)
    mw.status.addPermanentWidget(mw.progress)

    mw.watcher = QtCore.QFileSystemWatcher(mw)
    mw.watcher.directoryChanged.connect(mw._fs_changed)
    mw.watcher.fileChanged.connect(mw._fs_changed)
    mw._fs_timer = QtCore.QTimer(mw)
    mw._fs_timer.setSingleShot(True)
    mw._fs_timer.timeout.connect(lambda: mw._fs_refresh())
