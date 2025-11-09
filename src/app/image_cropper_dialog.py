from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QGraphicsView, 
    QGraphicsScene, QGraphicsRectItem, QGraphicsPixmapItem, QGraphicsItem, QGraphicsPathItem
)
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QPainterPath, QCursor, QWheelEvent
from PyQt6.QtCore import Qt, QRectF, QPointF, QBuffer, QSizeF

class Cropper(QGraphicsRectItem):
    """ A movable and resizable square cropping rectangle with 8 handles. """
    
    # Enum for handles
    TopLeft, Top, TopRight, Right, BottomRight, Bottom, Left, BottomLeft, Center = range(9)

    def __init__(self, rect, parent_dialog, *args):
        super().__init__(rect, *args)
        self.parent_dialog = parent_dialog
        self.setBrush(QBrush(Qt.GlobalColor.transparent))
        pen = QPen(QColor(255, 255, 255, 200), 2, Qt.PenStyle.DashLine)
        self.setPen(pen)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable | 
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges |
                      QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)

        self.handle_size = 12.0
        self.current_handle = self.Center
        self.mouse_press_pos = QPointF()
        self.mouse_press_rect = QRectF()

    def _get_handle_at(self, pos: QPointF) -> int:
        """Returns the handle at the given position."""
        rect = self.rect()
        hs = self.handle_size
        
        if QRectF(rect.topLeft(), QSizeF(hs, hs)).contains(pos): return self.TopLeft
        if QRectF(rect.topRight() - QPointF(hs, 0), QSizeF(hs, hs)).contains(pos): return self.TopRight
        if QRectF(rect.bottomRight() - QPointF(hs, hs), QSizeF(hs, hs)).contains(pos): return self.BottomRight
        if QRectF(rect.bottomLeft() - QPointF(0, hs), QSizeF(hs, hs)).contains(pos): return self.BottomLeft
        
        if abs(pos.x() - rect.left()) < hs / 2: return self.Left
        if abs(pos.x() - rect.right()) < hs / 2: return self.Right
        if abs(pos.y() - rect.top()) < hs / 2: return self.Top
        if abs(pos.y() - rect.bottom()) < hs / 2: return self.Bottom
        
        return self.Center

    def hoverMoveEvent(self, event):
        """Change cursor based on handle position."""
        handle = self._get_handle_at(event.pos())
        if handle in [self.TopLeft, self.BottomRight]:
            self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        elif handle in [self.TopRight, self.BottomLeft]:
            self.setCursor(QCursor(Qt.CursorShape.SizeBDiagCursor))
        elif handle in [self.Top, self.Bottom]:
            self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
        elif handle in [self.Left, self.Right]:
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        """Capture handle and initial state on mouse press."""
        self.current_handle = self._get_handle_at(event.pos())
        self.mouse_press_pos = event.pos()
        self.mouse_press_rect = self.rect()
        if self.current_handle == self.Center:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Resize the rectangle based on the handle being dragged."""
        if self.current_handle == self.Center:
            super().mouseMoveEvent(event)
            return

        self.prepareGeometryChange()
        rect = QRectF(self.mouse_press_rect)
        delta = event.pos() - self.mouse_press_pos

        if self.current_handle == self.TopLeft:
            new_size = max(rect.width() - delta.x(), rect.height() - delta.y())
            rect.setTopLeft(rect.bottomRight() - QPointF(new_size, new_size))
        elif self.current_handle == self.TopRight:
            new_size = max(rect.width() + delta.x(), rect.height() - delta.y())
            rect.setTopRight(rect.bottomLeft() + QPointF(new_size, -new_size))
        elif self.current_handle == self.BottomLeft:
            new_size = max(rect.width() - delta.x(), rect.height() + delta.y())
            rect.setBottomLeft(rect.topRight() + QPointF(-new_size, new_size))
        elif self.current_handle == self.BottomRight:
            new_size = max(rect.width() + delta.x(), rect.height() + delta.y())
            rect.setSize(QSizeF(new_size, new_size))
        elif self.current_handle == self.Top:
            rect.setTop(rect.top() + delta.y())
        elif self.current_handle == self.Bottom:
            rect.setBottom(rect.bottom() + delta.y())
        elif self.current_handle == self.Left:
            rect.setLeft(rect.left() + delta.x())
        elif self.current_handle == self.Right:
            rect.setRight(rect.right() + delta.x())

        # Constrain to image boundaries
        if self.scene():
            scene_rect = self.scene().sceneRect()
            rect = rect.intersected(scene_rect)

        self.setRect(rect)
        self.parent_dialog.update_overlay()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            # Keep the cropper within the scene's bounding rect (the image)
            new_pos = value
            image_rect = self.scene().sceneRect()
            cropper_rect = self.rect()
            # Create the target bounding rect for the cropper
            target_rect = QRectF(new_pos, cropper_rect.size())
            if not image_rect.contains(target_rect):
                # Clamp the new position to keep the cropper inside the image
                new_pos.setX(min(image_rect.right() - cropper_rect.width(), max(new_pos.x(), image_rect.left())))
                new_pos.setY(min(image_rect.bottom() - cropper_rect.height(), max(new_pos.y(), image_rect.top())))
                return new_pos
            self.parent_dialog.update_overlay()
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        """Reset handle on mouse release."""
        self.current_handle = self.Center
        super().mouseReleaseEvent(event)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        # Draw 8 resize handles
        painter.setBrush(QColor(255, 255, 255, 200))
        painter.setPen(Qt.PenStyle.NoPen)
        rect = self.rect()
        hs = self.handle_size
        hsh = hs / 2 # half handle size

        # Corners
        painter.drawRect(QRectF(rect.topLeft(), QSizeF(hs, hs)))
        painter.drawRect(QRectF(rect.topRight() - QPointF(hs, 0), QSizeF(hs, hs)))
        painter.drawRect(QRectF(rect.bottomRight() - QPointF(hs, hs), QSizeF(hs, hs)))
        painter.drawRect(QRectF(rect.bottomLeft() - QPointF(0, hs), QSizeF(hs, hs)))
        
        # Mid-points
        painter.drawRect(QRectF(rect.left(), rect.center().y() - hsh, hs, hs))
        painter.drawRect(QRectF(rect.right() - hs, rect.center().y() - hsh, hs, hs))
        painter.drawRect(QRectF(rect.center().x() - hsh, rect.top(), hs, hs))
        painter.drawRect(QRectF(rect.center().x() - hsh, rect.bottom() - hs, hs, hs))

class ImageCropperDialog(QDialog):
    def __init__(self, image_source, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ตัดรูปภาพ (Crop Image)")
        self.setMinimumSize(600, 500)
        self.zoom_factor = 1.0

        self.pixmap = QPixmap()
        if isinstance(image_source, str): # It's a path
            self.pixmap.load(image_source)
        elif isinstance(image_source, bytes): # It's data
            self.pixmap.loadFromData(image_source)

        if self.pixmap.isNull():
            self.reject()
            return

        self.scene = QGraphicsScene(self)
        self.pixmap_item = QGraphicsPixmapItem(self.pixmap)
        self.scene.addItem(self.pixmap_item)

        # --- Create overlay with a hole using QPainterPath ---
        self.overlay = QGraphicsPathItem()
        self.overlay.setBrush(QColor(0, 0, 0, 150))
        self.overlay.setPen(QPen(Qt.PenStyle.NoPen))
        self.scene.addItem(self.overlay)
        # --- End overlay ---

        # Add cropper item
        initial_size = min(self.pixmap.width(), self.pixmap.height()) * 0.8
        self.cropper = Cropper(QRectF(0, 0, initial_size, initial_size), self)
        self.cropper.setPos((self.pixmap.width() - initial_size) / 2, (self.pixmap.height() - initial_size) / 2)
        self.cropper.setZValue(1) # Ensure cropper is on top of overlay
        self.scene.addItem(self.cropper)

        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Layout
        layout = QVBoxLayout(self)
        layout.addWidget(self.view)

        button_layout = QHBoxLayout()
        ok_button = QPushButton("ตกลง")
        ok_button.clicked.connect(self.accept)
        cancel_button = QPushButton("ยกเลิก")
        cancel_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)

        self.cropped_pixmap = None

        self.update_overlay() # Initial update

    def update_overlay(self):
        """Updates the overlay path to create a hole for the cropper."""
        path = QPainterPath()
        # Add the outer rectangle (the full image area)
        path.addRect(self.scene.sceneRect())
        # Add the inner rectangle (the cropper area)
        path.addRect(self.cropper.sceneBoundingRect())
        self.overlay.setPath(path)

    def showEvent(self, event):
        super().showEvent(event)
        self.view.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def accept(self):
        # Get the cropping rectangle relative to the image
        crop_rect = self.cropper.sceneBoundingRect()

        # Ensure the crop rect is within the image bounds
        image_rect = self.pixmap_item.boundingRect()
        crop_rect = crop_rect.intersected(image_rect)

        if crop_rect.isValid():
            self.cropped_pixmap = self.pixmap.copy(crop_rect.toRect())
        
        super().accept()

    def get_cropped_pixmap(self) -> QPixmap | None:
        return self.cropped_pixmap

    @staticmethod
    def crop(image_path, parent=None) -> QPixmap | None:
        dialog = ImageCropperDialog(image_path, parent)
        if dialog.exec():
            return dialog.get_cropped_pixmap()
        return None

    @staticmethod
    def crop_from_data(image_data: bytes, parent=None) -> QPixmap | None:
        dialog = ImageCropperDialog(image_data, parent)
        if dialog.exec():
            return dialog.get_cropped_pixmap()
        return None