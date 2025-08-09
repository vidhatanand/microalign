"""Main window: menu bar, two toolbars (rows), sidebar, status bar + progress, project integration."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5 import QtCore, QtWidgets  # type: ignore

from align_app.ui.align_canvas import AlignCanvas
from align_app.ui.sidebar import build_sidebar, highlight_current_in_sidebar
from align_app.ui.watchers import rebuild_watchers
from align_app.ui.top_toolbar import build_top_toolbar
from align_app.ui.context_toolbar import build_context_toolbar
from align_app.project import ProjectManager, ProjectInfo


class MainWindow(QtWidgets.QMainWindow):
    """Main application window wiring canvas, toolbars, sidebar, and project manager."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MicroAlign")
        self.resize(1400, 900)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        self.setCentralWidget(splitter)

        # Left: collapsible sidebar
        self.sidebar = QtWidgets.QTreeWidget()
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setMinimumWidth(320)
        splitter.addWidget(self.sidebar)

        # Right: toolbars + canvas (two rows)
        right = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(right)
        layout.setContentsMargins(0, 0, 0, 0)

        self.toolbar_top = QtWidgets.QToolBar("Top")
        self.toolbar_bottom = QtWidgets.QToolBar("Bottom")
        for tb in (self.toolbar_top, self.toolbar_bottom):
            tb.setIconSize(QtCore.QSize(20, 20))

        layout.addWidget(self.toolbar_top)
        layout.addWidget(self.toolbar_bottom)

        self.canvas = AlignCanvas()
        layout.addWidget(self.canvas, 1)

        splitter.addWidget(right)
        splitter.setSizes([350, 1050])

        # Project manager
        self.project = ProjectManager(self)
        self.project.changed.connect(self._on_project_changed)

        # Build menu + toolbars
        self._build_menus()
        build_top_toolbar(self)
        build_context_toolbar(self)

        # Sidebar interactions
        self.sidebar.itemDoubleClicked.connect(self._sidebar_double_clicked)

        # Status bar + progress + project path (left side)
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)
        self.project_label = QtWidgets.QLabel("No project")
        self.status.addWidget(self.project_label)  # left side of status bar

        self.progress = QtWidgets.QProgressBar()
        self.progress.setVisible(False)
        self.progress.setFixedWidth(220)
        self.status.addPermanentWidget(self.progress)

        # File/folder watcher
        self.watcher = QtCore.QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self._fs_changed)
        self.watcher.fileChanged.connect(self._fs_changed)
        self._fs_timer = QtCore.QTimer(self)
        self._fs_timer.setSingleShot(True)
        self._fs_timer.timeout.connect(lambda: self._fs_refresh())

        # Canvas signals
        self.canvas.currentPathChanged.connect(
            lambda _p: highlight_current_in_sidebar(self.sidebar, self.canvas)
        )
        self.canvas.cropProgress.connect(self._on_crop_progress)

        # Initial sidebar + watchers
        build_sidebar(self.sidebar, self.canvas)
        rebuild_watchers(self.watcher, self.canvas)
        highlight_current_in_sidebar(self.sidebar, self.canvas)

        # Welcome splash on first run
        QtCore.QTimer.singleShot(200, self._welcome_startup)

    # ---------- Menus ----------

    def _build_menus(self) -> None:
        mbar = self.menuBar()

        # File menu
        m_file = mbar.addMenu("&File")
        act_new = QtWidgets.QAction(
            "New Project…",
            self,
            triggered=lambda: self.project.new_project_wizard(self),
        )
        act_open = QtWidgets.QAction(
            "Open Project…", self, triggered=lambda: self.project.open_project(self)
        )
        act_save = QtWidgets.QAction(
            "Save Project", self, triggered=lambda: self.project.save_project(self)
        )
        act_save_as = QtWidgets.QAction(
            "Save Project As…",
            self,
            triggered=lambda: self.project.save_project_as(self),
        )
        act_close = QtWidgets.QAction(
            "Close Project", self, triggered=lambda: self.project.close_project()
        )
        act_quit = QtWidgets.QAction(
            "Quit", self, triggered=lambda: QtWidgets.qApp.quit()
        )
        for a in (act_new, act_open, act_save, act_save_as, act_close):
            m_file.addAction(a)
        m_file.addSeparator()
        m_file.addAction(act_quit)

        # Help menu
        m_help = mbar.addMenu("&Help")
        m_help.addAction(QtWidgets.QAction("About", self, triggered=self._about))

    def _about(self) -> None:
        QtWidgets.QMessageBox.information(
            self, "About", "MicroAlign – simple manual alignment utility."
        )

    # ---------- welcome ----------

    def _welcome_startup(self) -> None:
        if self.project.info:
            return
        recents = self.project.recent_projects()
        if not recents:
            self.project.new_project_wizard(self)
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Welcome to MicroAlign")
        lay = QtWidgets.QVBoxLayout(dlg)
        lbl = QtWidgets.QLabel("Open a recent project or start a new one:")
        lay.addWidget(lbl)

        listw = QtWidgets.QListWidget()
        for r in recents:
            listw.addItem(r)
        lay.addWidget(listw)

        btns = QtWidgets.QDialogButtonBox()
        btn_new = btns.addButton("New Project", QtWidgets.QDialogButtonBox.AcceptRole)
        btn_open = btns.addButton("Open…", QtWidgets.QDialogButtonBox.ActionRole)
        btn_cancel = btns.addButton("Cancel", QtWidgets.QDialogButtonBox.RejectRole)
        lay.addWidget(btns)

        def pick_recent(item):
            root = Path(item.text())
            manifest = root / "project.json"
            if manifest.exists():
                info = ProjectInfo.from_json(manifest)
                self.project.info = info
                self.project.remember_project(root)
                self.project.changed.emit(info)
                dlg.accept()

        listw.itemDoubleClicked.connect(pick_recent)
        btn_new.clicked.connect(
            lambda: (dlg.accept(), self.project.new_project_wizard(self))
        )
        btn_open.clicked.connect(
            lambda: (dlg.accept(), self.project.open_project(self))
        )
        btn_cancel.clicked.connect(dlg.reject)

        dlg.exec_()

    # ---------- sidebar ----------

    def _toggle_sidebar(self, visible: bool) -> None:
        self.sidebar.setVisible(bool(visible))
        if visible:
            self.centralWidget().setSizes([350, self.width() - 350])
        else:
            self.centralWidget().setSizes([0, self.width()])

    def _sidebar_double_clicked(
        self, item: QtWidgets.QTreeWidgetItem, _col: int
    ) -> None:
        path = item.data(0, QtCore.Qt.UserRole)
        if not path:
            return
        p = Path(path)
        if p.is_file():
            if self.canvas.files:
                try:
                    idx = self.canvas.files.index(p)
                except ValueError:
                    idx = None
                if idx is not None:
                    self.canvas.idx = idx
                    self.canvas.update()
                    highlight_current_in_sidebar(self.sidebar, self.canvas)
        elif p.is_dir():
            self.canvas.set_paths(
                base_path=None, src_dir=p, align_out=None, crop_out=None
            )
            build_sidebar(self.sidebar, self.canvas)
            rebuild_watchers(self.watcher, self.canvas)
            highlight_current_in_sidebar(self.sidebar, self.canvas)

    # ---------- project state changed ----------

    def _on_project_changed(self, info: Optional[ProjectInfo]) -> None:
        if info is None:
            self.canvas.set_paths(None, None, None, None)
            self.project_label.setText("No project")
            build_sidebar(self.sidebar, self.canvas)
            rebuild_watchers(self.watcher, self.canvas)
            highlight_current_in_sidebar(self.sidebar, self.canvas)
            return

        self.canvas.set_paths(
            info.base_image, info.source_dir, info.align_dir, info.crops_dir
        )
        self.project_label.setText(str(info.root))
        build_sidebar(self.sidebar, self.canvas)
        rebuild_watchers(self.watcher, self.canvas)
        highlight_current_in_sidebar(self.sidebar, self.canvas)

    # ---------- filesystem watching ----------

    def _fs_changed(self, _path: str) -> None:
        self._fs_timer.start(250)

    def _fs_refresh(self) -> None:
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
        build_sidebar(self.sidebar, self.canvas)
        rebuild_watchers(self.watcher, self.canvas)
        highlight_current_in_sidebar(self.sidebar, self.canvas)

    # ---------- crop progress ----------

    def _on_crop_progress(self, done: int, total: int) -> None:
        if total <= 0:
            self.progress.setVisible(False)
            return
        self.progress.setVisible(True)
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        if done >= total:
            QtCore.QTimer.singleShot(600, lambda: self.progress.setVisible(False))
