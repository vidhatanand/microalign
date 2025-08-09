from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from PyQt5 import QtCore, QtWidgets  # type: ignore

from .project_info import ProjectInfo
from .project_wizard import ProjectWizard

CONFIG_PATH = Path.home() / ".microalign_recent.json"


class ProjectManager(QtCore.QObject):
    changed = QtCore.pyqtSignal(object)  # emits ProjectInfo or None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.info: Optional[ProjectInfo] = None

    # ---------- recents ----------
    def _load_recents(self) -> List[str]:
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text())
                recents = [
                    p
                    for p in data.get("recents", [])
                    if (Path(p) / "project.json").exists()
                ]
                return recents[:12]
            except (OSError, json.JSONDecodeError):
                return []
        return []

    def _save_recents(self, recents: List[str]) -> None:
        try:
            CONFIG_PATH.write_text(json.dumps({"recents": recents[:12]}, indent=2))
        except OSError:
            pass

    def remember_project(self, root: Path) -> None:
        recents = self._load_recents()
        s = str(root)
        if s in recents:
            recents.remove(s)
        recents.insert(0, s)
        self._save_recents(recents)

    def recent_projects(self) -> List[str]:
        return self._load_recents()

    # ---------- helpers ----------
    def _write_manifest(self, info: ProjectInfo) -> None:
        (info.root / "project.json").write_text(json.dumps(info.to_json(), indent=2))

    # ---------- actions ----------
    def close_project(self) -> None:
        self.info = None
        self.changed.emit(None)

    def open_project(self, parent: QtWidgets.QWidget) -> None:
        d = QtWidgets.QFileDialog.getExistingDirectory(
            parent, "Open MicroAlign Project"
        )
        if not d:
            return
        root = Path(d)
        manifest = root / "project.json"
        if not manifest.exists():
            QtWidgets.QMessageBox.warning(
                parent, "Not a project", "No project.json found here."
            )
            return
        info = ProjectInfo.from_json(manifest)
        self.info = info
        self.remember_project(root)
        self.changed.emit(info)

    def save_project(self, parent: QtWidgets.QWidget) -> None:
        if not self.info:
            return
        self._write_manifest(self.info)
        self.remember_project(self.info.root)
        QtWidgets.QMessageBox.information(
            parent, "Saved", f"Saved project -> {self.info.root}"
        )

    def save_project_as(self, parent: QtWidgets.QWidget) -> None:
        if not self.info:
            return
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(
            parent, "Save Project As (choose empty directory)"
        )
        if not new_dir:
            return
        # Defer the heavy lifting to the wizard implementation so logic stays in one place
        wiz = ProjectWizard(parent)
        # Pre-fill with current locations
        wiz.edt_root.setText(str(Path(new_dir).parent))
        wiz.edt_name.setText(Path(new_dir).name)
        wiz.edt_src.setText(str(self.info.source_dir))
        wiz.edt_base.setText(str(self.info.base_image or ""))
        info = wiz.build()
        if info is None:
            return
        self._write_manifest(info)
        self.info = info
        self.remember_project(info.root)
        self.changed.emit(info)
        QtWidgets.QMessageBox.information(
            parent, "Saved", f"Saved project as -> {info.root}"
        )

    def new_project_wizard(self, parent: QtWidgets.QWidget) -> None:
        info = ProjectWizard(parent).build()
        if info is None:
            return
        self._write_manifest(info)
        self.info = info
        self.remember_project(info.root)
        self.changed.emit(info)
        QtWidgets.QMessageBox.information(
            parent, "Project Created", f"Project created at {info.root}"
        )
