from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

from PyQt5 import QtCore, QtGui, QtWidgets  # type: ignore

from align_app.utils.img_io import bgr_to_qimage
from align_app.similarity.engine import compute_similarity_for_params

# pylint: disable=protected-access

ParamsSig = Tuple[
    float,
    float,
    float,
    float,
    Tuple[
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
    ],
]


class _FuncRunnable(QtCore.QRunnable):
    """Tiny QRunnable wrapper that runs a provided callable in the pool."""

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self) -> None:  # noqa: D401
        self._fn()


class SimilarityManager(QtCore.QObject):
    """Wires similarity + thumbnails in a self-contained way."""

    resultReady = QtCore.pyqtSignal(object, object)  # (Path, Dict[str,float])

    def __init__(self, mw):
        super().__init__(mw)
        self.mw = mw
        self.canvas = mw.canvas
        self.tree = mw.sidebar
        self._sim_label = QtWidgets.QLabel("Similarity: —")
        self._sim_label.setMinimumWidth(260)
        self.mw.status.addPermanentWidget(self._sim_label)

        self._pool = QtCore.QThreadPool.globalInstance()
        self._pool.setMaxThreadCount(max(1, self._pool.maxThreadCount() - 1))

        self._sim_cache: Dict[Path, Dict[str, float]] = {}
        self._thumb_cache: Dict[Path, QtGui.QIcon] = {}
        self._last_sig: Optional[ParamsSig] = None

        self._param_timer = QtCore.QTimer(self)
        self._param_timer.setInterval(180)
        self._param_timer.timeout.connect(self._maybe_recompute_current)
        self._param_timer.start()

        self.canvas.currentPathChanged.connect(lambda _p: self._on_current_changed())
        self.canvas.modeChanged.connect(lambda _b: self._schedule_current())

        self.resultReady.connect(self._on_result_ready)

        QtCore.QTimer.singleShot(0, self.sidebar_rebuilt)

    # ---------- Public hooks ----------

    def sidebar_rebuilt(self) -> None:
        self._decorate_sidebar()
        self._schedule_all_background()

    # ---------- Internal helpers ----------

    def _params_signature(self, path: Optional[Path]) -> Optional[ParamsSig]:
        if not path or not self.canvas.have_files():
            return None
        p = self.canvas.params.get(path, {})
        tx = float(p.get("tx", 0.0))
        ty = float(p.get("ty", 0.0))
        th = float(p.get("theta", 0.0))
        sc = float(p.get("scale", 1.0))
        quad = p.get("persp")
        if isinstance(quad, list) and len(quad) == 4:
            flat = tuple(float(v) for pt in quad for v in pt)
        else:
            flat = (
                0.0,
                0.0,
                self.canvas.pw - 1.0,
                0.0,
                self.canvas.pw - 1.0,
                self.canvas.ph - 1.0,
                0.0,
                self.canvas.ph - 1.0,
            )
        return (tx, ty, th, sc, flat)

    def _maybe_recompute_current(self) -> None:
        sig = self._params_signature(self.canvas.current_path())
        if sig is None:
            return
        if sig != self._last_sig:
            self._last_sig = sig
            self._schedule_current()

    def _schedule_current(self) -> None:
        path = self.canvas.current_path()
        if not path:
            self._sim_label.setText("Similarity: —")
            return
        self._schedule_similarity(path)

    def _on_current_changed(self) -> None:
        self._last_sig = None
        cp = self.canvas.current_path()
        if cp and cp in self._sim_cache:
            self._update_status(cp, self._sim_cache[cp])

    def _schedule_all_background(self) -> None:
        for p in getattr(self.canvas, "files", []):
            if isinstance(p, Path):
                self._schedule_similarity(p, _background=True)

    def _schedule_similarity(self, path: Path, _background: bool = False) -> None:
        try:
            base_prev = self.canvas.base_prev
            if base_prev is None:
                return
            mov_prev = self.canvas._get_preview(path)
            params = self.canvas.params.get(path, {}).copy()
            pw, ph = self.canvas.pw, self.canvas.ph
        except Exception:
            return

        def _work():
            try:
                res = compute_similarity_for_params(base_prev, mov_prev, params, pw, ph)
            except Exception:
                res = {
                    "score": 0.0,
                    "ssim": 0.0,
                    "corr": 0.0,
                    "hist": 0.0,
                    "orb": 0.0,
                    "psnr": 0.0,
                }
            self.resultReady.emit(path, res)

        job = _FuncRunnable(_work)
        self._pool.start(job)

    def _on_result_ready(self, path: Path, res: Dict[str, float]) -> None:
        self._sim_cache[path] = res
        if path == self.canvas.current_path():
            self._update_status(path, res)
        self._update_tree_item_score(path)

    def _update_status(self, _path: Path, res: Dict[str, float]) -> None:
        pct = int(round(res.get("score", 0.0) * 100))
        self._sim_label.setText(
            f"Similarity: {pct}%  (SSIM {res.get('ssim',0):.2f} | "
            f"Corr {res.get('corr',0):.2f} | ORB {res.get('orb',0):.2f})"
        )

    # ---------- Sidebar decoration ----------

    def _decorate_sidebar(self) -> None:
        tree = self.tree
        if tree is None:
            return

        src_root = None
        for i in range(tree.topLevelItemCount()):
            root = tree.topLevelItem(i)
            if root and root.text(0) == "Source Directory":
                src_root = root
                break
        if not src_root:
            return

        def dfs(node: QtWidgets.QTreeWidgetItem) -> None:
            path_s = node.data(0, QtCore.Qt.UserRole)
            if path_s:
                p = Path(path_s)
                if p.is_file():
                    node.setIcon(0, self._thumbnail_icon_for(p))
                    self._set_item_text_with_score(node, p)
            for j in range(node.childCount()):
                dfs(node.child(j))

        for i in range(src_root.childCount()):
            dfs(src_root.child(i))

    def _thumbnail_icon_for(self, path: Path) -> QtGui.QIcon:
        ico = self._thumb_cache.get(path)
        if ico:
            return ico
        try:
            prev = self.canvas._get_preview(path)
            qimg = bgr_to_qimage(prev)
            pix = QtGui.QPixmap.fromImage(qimg).scaled(
                48, 48, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
            )
            ico = QtGui.QIcon(pix)
            self._thumb_cache[path] = ico
            return ico
        except Exception:
            return QtGui.QIcon()

    def _set_item_text_with_score(
        self, item: QtWidgets.QTreeWidgetItem, path: Path
    ) -> None:
        base_text = path.name
        res = self._sim_cache.get(path)
        if res is not None:
            pct = int(round(res.get("score", 0.0) * 100))
            item.setText(0, f"{base_text}   [{pct}%]")
        else:
            item.setText(0, f"{base_text}   […]")

    def _update_tree_item_score(self, path: Path) -> None:
        tree = self.tree
        if tree is None:
            return
        for i in range(tree.topLevelItemCount()):
            root = tree.topLevelItem(i)
            if not root:
                continue
            found = self._find_item_recursive(root, str(path))
            if found:
                self._set_item_text_with_score(found, path)
                return

    def _find_item_recursive(
        self, item: QtWidgets.QTreeWidgetItem, target: str
    ) -> Optional[QtWidgets.QTreeWidgetItem]:
        if item.data(0, QtCore.Qt.UserRole) == target:
            return item
        for i in range(item.childCount()):
            got = self._find_item_recursive(item.child(i), target)
            if got:
                return got
        return None
