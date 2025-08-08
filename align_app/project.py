from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any

from PyQt5 import QtCore, QtWidgets  # type: ignore

CONFIG_PATH = Path.home() / ".microalign_recent.json"


@dataclass
class ProjectInfo:
    root: Path
    base_dir: Path
    source_dir: Path
    align_dir: Path
    crops_dir: Path
    base_image: Optional[Path]

    def to_json(self) -> Dict[str, Any]:
        return {
            "base_dir": str(self.base_dir.relative_to(self.root)),
            "source_dir": str(self.source_dir.relative_to(self.root)),
            "align_dir": str(self.align_dir.relative_to(self.root)),
            "crops_dir": str(self.crops_dir.relative_to(self.root)),
            "base_image": (
                str(self.base_image.relative_to(self.base_dir))
                if self.base_image
                else None
            ),
        }

    @staticmethod
    def from_json(path: Path) -> "ProjectInfo":
        data = json.loads(path.read_text())
        root = path.parent
        base_dir = root / data["base_dir"]
        source_dir = root / data["source_dir"]
        align_dir = root / data["align_dir"]
        crops_dir = root / data["crops_dir"]
        base_img = (base_dir / data["base_image"]) if data.get("base_image") else None
        return ProjectInfo(root, base_dir, source_dir, align_dir, crops_dir, base_img)


class ProjectManager(QtCore.QObject):
    changed = QtCore.pyqtSignal(object)  # emits ProjectInfo or None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.info: Optional[ProjectInfo] = None

    # ---------- recents ----------
    def _load_recents(self) -> List[str]:
        try:
            if CONFIG_PATH.exists():
                data = json.loads(CONFIG_PATH.read_text())
                recents = [
                    p
                    for p in data.get("recents", [])
                    if (Path(p) / "project.json").exists()
                ]
                return recents[:12]
        except Exception:
            pass
        return []

    def _save_recents(self, recents: List[str]) -> None:
        try:
            CONFIG_PATH.write_text(json.dumps({"recents": recents[:12]}, indent=2))
        except Exception:
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
        new_root = Path(new_dir)
        if new_root.resolve() == self.info.root.resolve():
            # same place: just rewrite manifest
            self._write_manifest(self.info)
            QtWidgets.QMessageBox.information(
                parent, "Saved", "Saved project (same location)."
            )
            return

        def safe_copy(src: Path, dst: Path) -> None:
            try:
                if src.resolve() == dst.resolve():
                    return
            except Exception:
                if str(src) == str(dst):
                    return
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))
            elif src.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
                for p in src.rglob("*"):
                    if p.is_file():
                        rel = p.relative_to(src)
                        target = dst / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(p), str(target))

        (new_root / "base").mkdir(parents=True, exist_ok=True)
        (new_root / "source").mkdir(parents=True, exist_ok=True)
        (new_root / "aligned").mkdir(parents=True, exist_ok=True)
        (new_root / "crops").mkdir(parents=True, exist_ok=True)

        if self.info.base_image:
            safe_copy(
                self.info.base_image, new_root / "base" / self.info.base_image.name
            )
        safe_copy(self.info.source_dir, new_root / "source")
        safe_copy(self.info.align_dir, new_root / "aligned")
        safe_copy(self.info.crops_dir, new_root / "crops")

        new_info = ProjectInfo(
            root=new_root,
            base_dir=new_root / "base",
            source_dir=new_root / "source",
            align_dir=new_root / "aligned",
            crops_dir=new_root / "crops",
            base_image=(
                (new_root / "base" / self.info.base_image.name)
                if self.info.base_image
                else None
            ),
        )
        self._write_manifest(new_info)
        self.info = new_info
        self.remember_project(new_root)
        self.changed.emit(new_info)
        QtWidgets.QMessageBox.information(
            parent, "Saved", f"Saved project as -> {new_root}"
        )

    # ---------- wizard ----------
    def new_project_wizard(self, parent: QtWidgets.QWidget) -> None:
        wiz = QtWidgets.QWizard(parent)
        wiz.setWindowTitle("New Project")

        # Page 1: where + name
        p1 = QtWidgets.QWizardPage()
        p1.setTitle("Project Location")
        p1.setSubTitle("Choose a folder and name for your project.")
        p1_lay = QtWidgets.QGridLayout(p1)
        edt_root = QtWidgets.QLineEdit()
        btn_browse_root = QtWidgets.QPushButton("Browse…")
        edt_name = QtWidgets.QLineEdit()
        p1_lay.addWidget(QtWidgets.QLabel("Create in:"), 0, 0)
        p1_lay.addWidget(edt_root, 0, 1)
        p1_lay.addWidget(btn_browse_root, 0, 2)
        p1_lay.addWidget(QtWidgets.QLabel("Project name:"), 1, 0)
        p1_lay.addWidget(edt_name, 1, 1, 1, 2)

        def pick_root():
            d = QtWidgets.QFileDialog.getExistingDirectory(parent, "Choose Folder")
            if d:
                edt_root.setText(d)

        btn_browse_root.clicked.connect(pick_root)
        wiz.addPage(p1)

        # Page 2: source folder
        p2 = QtWidgets.QWizardPage()
        p2.setTitle("Source Images")
        p2.setSubTitle(
            "Pick the folder containing all your source images (will be copied into the project)."
        )
        p2_lay = QtWidgets.QGridLayout(p2)
        edt_src = QtWidgets.QLineEdit()
        btn_src = QtWidgets.QPushButton("Browse…")
        p2_lay.addWidget(QtWidgets.QLabel("Source folder:"), 0, 0)
        p2_lay.addWidget(edt_src, 0, 1)
        p2_lay.addWidget(btn_src, 0, 2)

        def pick_src():
            d = QtWidgets.QFileDialog.getExistingDirectory(
                parent, "Choose Source Directory"
            )
            if d:
                edt_src.setText(d)

        btn_src.clicked.connect(pick_src)
        wiz.addPage(p2)

        # Page 3: base image
        p3 = QtWidgets.QWizardPage()
        p3.setTitle("Base Image")
        p3.setSubTitle("Choose the base/reference image.")
        p3_lay = QtWidgets.QGridLayout(p3)
        edt_base = QtWidgets.QLineEdit()
        btn_base = QtWidgets.QPushButton("Browse…")
        p3_lay.addWidget(QtWidgets.QLabel("Base image:"), 0, 0)
        p3_lay.addWidget(edt_base, 0, 1)
        p3_lay.addWidget(btn_base, 0, 2)

        def pick_base():
            fn, _ = QtWidgets.QFileDialog.getOpenFileName(
                parent,
                "Choose Base Image",
                edt_src.text() or "",
                "Images (*.png *.jpg *.jpeg *.jpe)",
            )
            if fn:
                edt_base.setText(fn)

        btn_base.clicked.connect(pick_base)
        wiz.addPage(p3)

        # validate on finish
        if wiz.exec_() != QtWidgets.QDialog.Accepted:
            return

        root_parent = Path(edt_root.text().strip())
        name = edt_name.text().strip()
        src = Path(edt_src.text().strip())
        base_fn = Path(edt_base.text().strip())

        if (
            not root_parent.exists()
            or not name
            or not src.exists()
            or not base_fn.exists()
        ):
            QtWidgets.QMessageBox.warning(
                parent, "Incomplete", "Please fill all fields with valid paths."
            )
            return

        root = root_parent / name
        if root.exists() and any(root.iterdir()):
            QtWidgets.QMessageBox.warning(
                parent, "Folder Exists", "Please choose an empty/new project folder."
            )
            return

        # Create structure
        base_dir = root / "base"
        source_dir = root / "source"
        align_dir = root / "aligned"
        crops_dir = root / "crops"
        for d in (base_dir, source_dir, align_dir, crops_dir):
            d.mkdir(parents=True, exist_ok=True)

        # Copy base + sources
        shutil.copy2(str(base_fn), str(base_dir / base_fn.name))
        for p in src.rglob("*"):
            if p.is_file():
                rel = p.relative_to(src)
                dest_p = source_dir / rel
                dest_p.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(p), str(dest_p))

        info = ProjectInfo(
            root=root,
            base_dir=base_dir,
            source_dir=source_dir,
            align_dir=align_dir,
            crops_dir=crops_dir,
            base_image=base_dir / base_fn.name,
        )
        self._write_manifest(info)
        self.info = info
        self.remember_project(root)
        self.changed.emit(info)
        QtWidgets.QMessageBox.information(
            parent, "Project Created", f"Project created at {root}"
        )
