"""Compatibility aggregator so existing imports keep working:

from align_app.project import ProjectManager, ProjectInfo
"""

from .project_info import ProjectInfo
from .project_manager import ProjectManager

__all__ = ["ProjectInfo", "ProjectManager"]
