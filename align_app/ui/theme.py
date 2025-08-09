from __future__ import annotations

from PyQt5 import QtCore, QtGui, QtWidgets  # type: ignore


def _dark_palette() -> QtGui.QPalette:
    p = QtGui.QPalette()
    bg0 = QtGui.QColor("#1a1d21")
    bg1 = QtGui.QColor("#1f2328")
    bg2 = QtGui.QColor("#111418")
    base = QtGui.QColor("#171a1f")
    text = QtGui.QColor("#e6e6e6")
    dim = QtGui.QColor("#aab1bb")
    acc = QtGui.QColor("#3b82f6")
    link = QtGui.QColor("#8ab4f8")
    p.setColor(QtGui.QPalette.Window, bg0)
    p.setColor(QtGui.QPalette.WindowText, text)
    p.setColor(QtGui.QPalette.Base, base)
    p.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#1e2228"))
    p.setColor(QtGui.QPalette.ToolTipBase, bg1)
    p.setColor(QtGui.QPalette.ToolTipText, text)
    p.setColor(QtGui.QPalette.Text, text)
    p.setColor(QtGui.QPalette.Button, bg1)
    p.setColor(QtGui.QPalette.ButtonText, text)
    p.setColor(QtGui.QPalette.BrightText, QtGui.QColor("#ff5555"))
    p.setColor(QtGui.QPalette.Link, link)
    p.setColor(QtGui.QPalette.Highlight, acc)
    p.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#ffffff"))
    p.setColor(QtGui.QPalette.PlaceholderText, dim)
    return p


def _light_palette() -> QtGui.QPalette:
    p = QtGui.QPalette()
    bg0 = QtGui.QColor("#f7f8fa")
    bg1 = QtGui.QColor("#ffffff")
    base = QtGui.QColor("#ffffff")
    text = QtGui.QColor("#1b1f24")
    dim = QtGui.QColor("#6b7178")
    acc = QtGui.QColor("#2563eb")
    link = QtGui.QColor("#1d4ed8")
    p.setColor(QtGui.QPalette.Window, bg0)
    p.setColor(QtGui.QPalette.WindowText, text)
    p.setColor(QtGui.QPalette.Base, base)
    p.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#f0f2f5"))
    p.setColor(QtGui.QPalette.ToolTipBase, bg1)
    p.setColor(QtGui.QPalette.ToolTipText, text)
    p.setColor(QtGui.QPalette.Text, text)
    p.setColor(QtGui.QPalette.Button, bg1)
    p.setColor(QtGui.QPalette.ButtonText, text)
    p.setColor(QtGui.QPalette.BrightText, QtGui.QColor("#b00020"))
    p.setColor(QtGui.QPalette.Link, link)
    p.setColor(QtGui.QPalette.Highlight, acc)
    p.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#ffffff"))
    p.setColor(QtGui.QPalette.PlaceholderText, dim)
    return p


_STYLE_COMMON = """
* { outline: 0; }
QToolBar { spacing: 6px; }
QToolButton { padding: 6px 10px; border-radius: 6px; }
QToolButton:checked { font-weight: 600; }
QSlider::groove:horizontal { height: 6px; border-radius: 3px; }
QSlider::handle:horizontal { width: 14px; border-radius: 7px; margin: -5px 0; }
QStatusBar::item { border: 0; }
QProgressBar { border: 0; border-radius: 6px; text-align: center; height: 12px; }
QCheckBox, QRadioButton { spacing: 8px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { padding: 4px 6px; border-radius: 6px; }
QTreeWidget { alternate-background-color: palette(alternate-base); }
QRubberBand { border: 1px solid palette(highlight); }
"""

_STYLE_DARK = (
    _STYLE_COMMON
    + """
QWidget { background: #1a1d21; color: #e6e6e6; font-size: 11pt; }
QToolBar { background: #1f2328; border: 1px solid #2a2f36; }
QToolButton:hover { background: #2a2f36; }
QToolButton:checked { background: #3b82f6; color: white; }
QSlider::groove:horizontal { background: #2a2f36; }
QSlider::handle:horizontal { background: #3b82f6; }
QTreeWidget::item:selected { background: #2b3441; color: #ffffff; }
QProgressBar { background: #2a2f36; }
QProgressBar::chunk { background: #3b82f6; border-radius: 6px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #111418; border: 1px solid #2a2f36; }
QStatusBar { background: #1f2328; border-top: 1px solid #2a2f36; }
QRubberBand { background: rgba(59,130,246,0.2); }
"""
)

_STYLE_LIGHT = (
    _STYLE_COMMON
    + """
QWidget { background: #f7f8fa; color: #1b1f24; font-size: 11pt; }
QToolBar { background: #ffffff; border: 1px solid #e6e8eb; }
QToolButton:hover { background: #eef2f6; }
QToolButton:checked { background: #2563eb; color: white; }
QSlider::groove:horizontal { background: #e6e8eb; }
QSlider::handle:horizontal { background: #2563eb; }
QTreeWidget::item:selected { background: #dbe7ff; color: #0b1220; }
QProgressBar { background: #e6e8eb; }
QProgressBar::chunk { background: #2563eb; border-radius: 6px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #ffffff; border: 1px solid #d7dbe0; }
QStatusBar { background: #ffffff; border-top: 1px solid #e6e8eb; }
QRubberBand { background: rgba(37,99,235,0.18); }
"""
)


class ThemeManager(QtCore.QObject):
    themeChanged = QtCore.pyqtSignal(str)

    def __init__(self, app: QtWidgets.QApplication):
        super().__init__()
        self._app = app
        self._mode = "dark"
        self._settings = QtCore.QSettings("MicroAlign", "UI")

        # Choose first actually-installed family (do NOT touch “Inter” if missing)
        prefer = [
            "Inter",
            "SF Pro Text",
            "Segoe UI",
            "Roboto",
            "Helvetica Neue",
            "Arial",
        ]
        available = set(QtGui.QFontDatabase().families())
        chosen = None
        for fam in prefer:
            if fam in available:
                chosen = QtGui.QFont(fam, 11)
                break
        self._font = chosen or QtGui.QFont()

    @property
    def mode(self) -> str:
        return self._mode

    def apply_saved(self) -> None:
        mode = str(self._settings.value("theme", "dark"))
        self.apply(mode)

    def apply(self, mode: str) -> None:
        mode = "dark" if str(mode).lower().startswith("d") else "light"
        self._mode = mode

        if mode == "dark":
            self._app.setPalette(_dark_palette())
            self._app.setStyleSheet(_STYLE_DARK)
        else:
            self._app.setPalette(_light_palette())
            self._app.setStyleSheet(_STYLE_LIGHT)

        if self._font:
            self._app.setFont(self._font)

        self._settings.setValue("theme", mode)
        self.themeChanged.emit(mode)

    def toggle(self) -> None:
        self.apply("light" if self._mode == "dark" else "dark")
