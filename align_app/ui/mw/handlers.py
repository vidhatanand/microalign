from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5 import QtCore, QtWidgets  # type: ignore

from align_app.ui.sidebar import build_sidebar, highlight_current_in_sidebar
from align_app.ui.watchers import rebuild_watchers
from align_app.project import ProjectInfo


def welcome_startup(mw) -> None:
    if mw.project.info:
        return
    recents = mw.project.recent_projects()
    if not recents:
        mw.project.new_project_wizard(mw)
        return
    dlg = QtWidgets.QDialog(mw)
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
            mw.project.info = info
            mw.project.remember_project(root)
            mw.project.changed.emit(info)
            dlg.accept()

    listw.itemDoubleClicked.connect(pick_recent)
    btn_new.clicked.connect(lambda: (dlg.accept(), mw.project.new_project_wizard(mw)))
    btn_open.clicked.connect(lambda: (dlg.accept(), mw.project.open_project(mw)))
    btn_cancel.clicked.connect(dlg.reject)

    dlg.exec_()


def sidebar_double_clicked(mw, item: QtWidgets.QTreeWidgetItem, _col: int) -> None:
    path = item.data(0, QtCore.Qt.UserRole)
    if not path:
        return
    p = Path(path)
    if p.is_file():
        if mw.canvas.files:
            try:
                idx = mw.canvas.files.index(p)
            except ValueError:
                idx = None
            if idx is not None:
                mw.canvas.idx = idx
                mw.canvas.update()
                highlight_current_in_sidebar(mw.sidebar, mw.canvas)
    elif p.is_dir():
        mw.canvas.set_paths(base_path=None, src_dir=p, align_out=None, crop_out=None)
        build_sidebar(mw.sidebar, mw.canvas)
        rebuild_watchers(mw.watcher, mw.canvas)
        highlight_current_in_sidebar(mw.sidebar, mw.canvas)


def on_project_changed(mw, info: Optional[ProjectInfo]) -> None:
    if info is None:
        mw.canvas.set_paths(None, None, None, None)
        mw.project_label.setText("No project")
        build_sidebar(mw.sidebar, mw.canvas)
        rebuild_watchers(mw.watcher, mw.canvas)
        highlight_current_in_sidebar(mw.sidebar, mw.canvas)
        return

    mw.canvas.set_paths(
        info.base_image, info.source_dir, info.align_dir, info.crops_dir
    )
    mw.project_label.setText(str(info.root))
    build_sidebar(mw.sidebar, mw.canvas)
    rebuild_watchers(mw.watcher, mw.canvas)
    highlight_current_in_sidebar(mw.sidebar, mw.canvas)


def fs_changed(mw, _path: str) -> None:
    mw._fs_timer.start(250)


def fs_refresh(mw) -> None:
    cur = mw.canvas.current_path()
    mw.canvas.set_paths(
        mw.canvas.base_path,
        mw.canvas.src_dir,
        mw.canvas.align_out,
        mw.canvas.crop_out,
    )
    if cur and cur in mw.canvas.files:
        try:
            mw.canvas.idx = mw.canvas.files.index(cur)
        except ValueError:
            pass
    build_sidebar(mw.sidebar, mw.canvas)
    rebuild_watchers(mw.watcher, mw.canvas)
    highlight_current_in_sidebar(mw.sidebar, mw.canvas)


def on_crop_progress(mw, done: int, total: int) -> None:
    if total <= 0:
        mw.progress.setVisible(False)
        return
    mw.progress.setVisible(True)
    mw.progress.setMaximum(total)
    mw.progress.setValue(done)
    if done >= total:
        QtCore.QTimer.singleShot(600, lambda: mw.progress.setVisible(False))
