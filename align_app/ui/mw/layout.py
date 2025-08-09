from __future__ import annotations

from PyQt5 import QtCore, QtWidgets  # type: ignore

from align_app.ui.align_canvas import AlignCanvas
from align_app.ui.theme import ThemeManager  # NEW


def build_main_ui(mw) -> None:
    """Builds the fixed layout (no behavior changes)."""

    # ---- Theme: must exist before building toolbars so widgets inherit palette ----
    mw.themer = ThemeManager(QtWidgets.QApplication.instance())
    mw.themer.apply_saved()

    # ---- Central splitter ----
    splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, mw)
    mw.setCentralWidget(splitter)

    # Left: collapsible sidebar
    mw.sidebar = QtWidgets.QTreeWidget()
    mw.sidebar.setHeaderHidden(True)
    mw.sidebar.setMinimumWidth(320)
    splitter.addWidget(mw.sidebar)

    # Right: toolbars + canvas (two rows)
    right = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(right)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

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

    # ---- Status bar + progress ----
    mw.status = QtWidgets.QStatusBar()
    mw.setStatusBar(mw.status)
    mw.project_label = QtWidgets.QLabel("No project")
    mw.status.addWidget(mw.project_label)

    mw.progress = QtWidgets.QProgressBar()
    mw.progress.setVisible(False)
    mw.progress.setFixedWidth(220)
    mw.status.addPermanentWidget(mw.progress)

    # ---- File/folder watcher ----
    mw.watcher = QtCore.QFileSystemWatcher(mw)
    mw.watcher.directoryChanged.connect(mw._fs_changed)
    mw.watcher.fileChanged.connect(mw._fs_changed)
    mw._fs_timer = QtCore.QTimer(mw)
    mw._fs_timer.setSingleShot(True)
    mw._fs_timer.timeout.connect(lambda: mw._fs_refresh())

    mw.resize(1400, 900)
