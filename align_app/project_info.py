from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional


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
