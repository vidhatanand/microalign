from __future__ import annotations

from PyQt5 import QtWidgets  # type: ignore


def build_menus(mw) -> None:
    mbar = mw.menuBar()

    m_file = mbar.addMenu("&File")
    act_new = QtWidgets.QAction(
        "New Project…",
        mw,
        triggered=lambda: mw.project.new_project_wizard(mw),
    )
    act_open = QtWidgets.QAction(
        "Open Project…", mw, triggered=lambda: mw.project.open_project(mw)
    )
    act_save = QtWidgets.QAction(
        "Save Project", mw, triggered=lambda: mw.project.save_project(mw)
    )
    act_save_as = QtWidgets.QAction(
        "Save Project As…", mw, triggered=lambda: mw.project.save_project_as(mw)
    )
    act_close = QtWidgets.QAction(
        "Close Project", mw, triggered=lambda: mw.project.close_project()
    )
    act_quit = QtWidgets.QAction("Quit", mw, triggered=lambda: QtWidgets.qApp.quit())
    for a in (act_new, act_open, act_save, act_save_as, act_close):
        m_file.addAction(a)
    m_file.addSeparator()
    m_file.addAction(act_quit)

    m_help = mbar.addMenu("&Help")
    m_help.addAction(QtWidgets.QAction("About", mw, triggered=mw._about))


def about_dialog(mw) -> None:
    QtWidgets.QMessageBox.information(
        mw, "About", "MicroAlign – simple manual alignment utility."
    )
