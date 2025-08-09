from __future__ import annotations

import shutil
from pathlib import Path
from PyQt5 import QtWidgets  # type: ignore

from .project_info import ProjectInfo


class ProjectWizard(QtWidgets.QWizard):
    """Self-contained 'New Project' wizard that returns a ProjectInfo on accept()."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Project")

        # Page 1: where + name
        p1 = QtWidgets.QWizardPage()
        p1.setTitle("Project Location")
        p1.setSubTitle("Choose a folder and name for your project.")
        p1_lay = QtWidgets.QGridLayout(p1)
        self.edt_root = QtWidgets.QLineEdit()
        btn_browse_root = QtWidgets.QPushButton("Browse…")
        self.edt_name = QtWidgets.QLineEdit()
        p1_lay.addWidget(QtWidgets.QLabel("Create in:"), 0, 0)
        p1_lay.addWidget(self.edt_root, 0, 1)
        p1_lay.addWidget(btn_browse_root, 0, 2)
        p1_lay.addWidget(QtWidgets.QLabel("Project name:"), 1, 0)
        p1_lay.addWidget(self.edt_name, 1, 1, 1, 2)

        def pick_root():
            d = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose Folder")
            if d:
                self.edt_root.setText(d)

        btn_browse_root.clicked.connect(pick_root)
        self.addPage(p1)

        # Page 2: source folder
        p2 = QtWidgets.QWizardPage()
        p2.setTitle("Source Images")
        p2.setSubTitle(
            "Pick the folder containing your source images (copied into the project)."
        )
        p2_lay = QtWidgets.QGridLayout(p2)
        self.edt_src = QtWidgets.QLineEdit()
        btn_src = QtWidgets.QPushButton("Browse…")
        p2_lay.addWidget(QtWidgets.QLabel("Source folder:"), 0, 0)
        p2_lay.addWidget(self.edt_src, 0, 1)
        p2_lay.addWidget(btn_src, 0, 2)

        def pick_src():
            d = QtWidgets.QFileDialog.getExistingDirectory(
                self, "Choose Source Directory"
            )
            if d:
                self.edt_src.setText(d)

        btn_src.clicked.connect(pick_src)
        self.addPage(p2)

        # Page 3: base image
        p3 = QtWidgets.QWizardPage()
        p3.setTitle("Base Image")
        p3.setSubTitle("Choose the base/reference image.")
        p3_lay = QtWidgets.QGridLayout(p3)
        self.edt_base = QtWidgets.QLineEdit()
        btn_base = QtWidgets.QPushButton("Browse…")
        p3_lay.addWidget(QtWidgets.QLabel("Base image:"), 0, 0)
        p3_lay.addWidget(self.edt_base, 0, 1)
        p3_lay.addWidget(btn_base, 0, 2)

        def pick_base():
            fn, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Choose Base Image",
                self.edt_src.text() or "",
                "Images (*.png *.jpg *.jpeg *.jpe)",
            )
            if fn:
                self.edt_base.setText(fn)

        btn_base.clicked.connect(pick_base)
        self.addPage(p3)

    # Returns a ProjectInfo and creates the folder layout when accepted; else None
    def build(self) -> ProjectInfo | None:
        if self.exec_() != QtWidgets.QDialog.Accepted:
            return None

        root_parent = Path(self.edt_root.text().strip())
        name = self.edt_name.text().strip()
        src = Path(self.edt_src.text().strip())
        base_fn = Path(self.edt_base.text().strip())

        if (
            not root_parent.exists()
            or not name
            or not src.exists()
            or not base_fn.exists()
        ):
            QtWidgets.QMessageBox.warning(
                self, "Incomplete", "Please fill all fields with valid paths."
            )
            return None

        root = root_parent / name
        if root.exists() and any(root.iterdir()):
            QtWidgets.QMessageBox.warning(
                self, "Folder Exists", "Please choose an empty/new project folder."
            )
            return None

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

        return ProjectInfo(
            root=root,
            base_dir=base_dir,
            source_dir=source_dir,
            align_dir=align_dir,
            crops_dir=crops_dir,
            base_image=base_dir / base_fn.name,
        )
