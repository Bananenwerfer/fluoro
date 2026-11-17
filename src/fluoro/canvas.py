"""Image view with ROI overlay, brush/eraser painting, mouse-wheel zoom and space+drag panning."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView
from scipy import ndimage as ndi

FILL_RGBA = (0, 190, 255, 45)       # light fill, white-light view only
EDGE_RGBA = (255, 225, 0, 255)      # outline, both views


def to_qimage(a: np.ndarray) -> QImage:
    a = np.ascontiguousarray(a, dtype=np.uint8)
    h, w = a.shape[:2]
    if a.ndim == 2:
        return QImage(a.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
    if a.shape[2] == 3:
        return QImage(a.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
    return QImage(a.data, w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()


def overlay_rgba(mask: np.ndarray, fill: bool) -> np.ndarray:
    """Outline (about 0.2 % of the longer image side wide) plus optional fill."""
    rgba = np.zeros(mask.shape + (4,), np.uint8)
    if fill:
        rgba[mask] = FILL_RGBA
    w = max(1, round(max(mask.shape) / 500))
    inner = ndi.binary_erosion(mask, structure=np.ones((2 * w + 1, 2 * w + 1), bool), border_value=0)
    rgba[mask & ~inner] = EDGE_RGBA
    return rgba


def paint_disc(mask: np.ndarray, x: float, y: float, radius: float, value: bool) -> None:
    h, w = mask.shape
    x0, x1 = max(0, int(x - radius)), min(w, int(x + radius) + 1)
    y0, y1 = max(0, int(y - radius)), min(h, int(y + radius) + 1)
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.ogrid[y0:y1, x0:x1]
    mask[y0:y1, x0:x1][(xx - x) ** 2 + (yy - y) ** 2 <= radius ** 2] = value


class ImageCanvas(QGraphicsView):
    edited = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self._image, self._overlay = QGraphicsPixmapItem(), QGraphicsPixmapItem()
        self.scene().addItem(self._image)
        self.scene().addItem(self._overlay)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.mask = None
        self.tool, self.radius, self.editable, self.fill = "brush", 20, True, True
        self._painting = self._panning = False

    def set_image(self, rgb: np.ndarray, fit: bool = True) -> None:
        self._image.setPixmap(QPixmap.fromImage(to_qimage(rgb)))
        self.scene().setSceneRect(self._image.boundingRect())
        if fit:
            self.fit()

    def set_mask(self, mask) -> None:
        self.mask = mask
        self.refresh_overlay()

    def refresh_overlay(self) -> None:
        if self.mask is None:
            self._overlay.setPixmap(QPixmap())
            return
        self._overlay.setPixmap(QPixmap.fromImage(to_qimage(overlay_rgba(self.mask, self.fill))))

    def fit(self) -> None:
        self.fitInView(self._image, Qt.AspectRatioMode.KeepAspectRatio)

    def paint_at(self, x: float, y: float) -> bool:
        """x, y in image pixels (scene coordinates). Returns False if painting is not possible."""
        if self.mask is None or not self.editable:
            return False
        paint_disc(self.mask, x - 0.5, y - 0.5, self.radius, self.tool == "brush")
        self.refresh_overlay()
        return True

    def wheelEvent(self, e):
        f = 1.25 if e.angleDelta().y() > 0 else 0.8
        self.scale(f, f)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._panning = True
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._panning = False
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            return
        super().keyReleaseEvent(e)

    def mousePressEvent(self, e):
        if self._panning or e.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(e)
        p = self.mapToScene(e.position().toPoint())
        self._painting = self.paint_at(p.x(), p.y())

    def mouseMoveEvent(self, e):
        if self._painting:
            p = self.mapToScene(e.position().toPoint())
            self.paint_at(p.x(), p.y())
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._painting:
            self._painting = False
            self.edited.emit()
            return
        super().mouseReleaseEvent(e)
