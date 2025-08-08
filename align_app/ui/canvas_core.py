"""Compatibility shim: the old CanvasCore is now the mixin-based CanvasWidget.

Keeping this to satisfy any legacy imports.
"""

from __future__ import annotations

from .canvas_widget import CanvasWidget as CanvasCore  # re-export alias
