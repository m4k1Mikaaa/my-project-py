from PyQt6.QtWidgets import QVBoxLayout, QApplication, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from PyQt6.QtGui import QPixmap, QPainter, QCursor
from PyQt6.QtCore import Qt, QEvent
from .base_dialog import BaseDialog

class ImageViewerDialog(BaseDialog):
    def __init__(self, image_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Full Image")

        # 1. เก็บ Pixmap ต้นฉบับและตั้งค่าการซูม
        self.pixmap = QPixmap()
        self.pixmap.loadFromData(image_data)
        self.zoom_factor = 1.0

        # 2. สร้าง Scene และ View สำหรับแสดงผล
        self.scene = QGraphicsScene(self)
        self.pixmap_item = QGraphicsPixmapItem(self.pixmap)
        self.scene.addItem(self.pixmap_item)

        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag) # ทำให้ลากรูปได้
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        
        # ปิดการทำงานของ Scrollbar ทั้งหมด เพราะใช้การลากและซูมแทน
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff) 
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # ติดตั้ง Event Filter เพื่อดักจับ Wheel Event ที่ View โดยตรง
        self.view.viewport().installEventFilter(self)

        # 3. ตั้งค่า Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

        # 4. กำหนดขนาดเริ่มต้นให้พอดีกับรูป แต่ไม่เกิน 90% ของจอ
        # ใช้หน้าจอปัจจุบันที่ parent อยู่ หรือหน้าจอที่เมาส์อยู่ถ้าไม่มี parent
        if parent and parent.screen():
            current_screen = parent.screen()
        else:
            current_screen = QApplication.screenAt(QCursor.pos())

        available_geom = current_screen.availableGeometry()
        max_size = available_geom.size() * 0.9 # Use 90% of the available screen space
        initial_size = self.pixmap.size().scaled(max_size, Qt.AspectRatioMode.KeepAspectRatio)
        self.resize(initial_size)

        # 5. จัดหน้าต่างให้อยู่กลาง "หน้าจอ" เสมอ โดยไม่สนใจตำแหน่งของ parent
        screen_center = current_screen.geometry().center()
        self.move(screen_center - self.frameGeometry().center())

    def eventFilter(self, source, event):
        """
        ดักจับ Event ที่เกิดขึ้นบน View ที่เราติดตามอยู่
        """
        if source is self.view.viewport() and event.type() == QEvent.Type.Wheel:
            # คำนวณค่าการซูม
            zoom_in_factor = 1.15
            zoom_out_factor = 1 / zoom_in_factor

            if event.angleDelta().y() > 0:
                zoom_factor = zoom_in_factor
            else:
                zoom_factor = zoom_out_factor

            # ตรวจสอบขีดจำกัดการซูม
            new_zoom = self.zoom_factor * zoom_factor
            if 0.1 < new_zoom < 10.0:
                self.zoom_factor = new_zoom
                self.view.scale(zoom_factor, zoom_factor)
            
            # Accept the event to prevent any further processing (like scrolling)
            event.accept()
            return True # คืนค่า True เพื่อบอกว่าเราจัดการ Event นี้แล้ว ไม่ต้องส่งต่อ
        
        return super().eventFilter(source, event)

    def resizeEvent(self, event):
        """
        เมื่อมีการขยายหน้าต่าง ให้รูปภาพขยายตาม
        """
        super().resizeEvent(event)
        # ใช้ fitInView เพื่อให้รูปภาพปรับขนาดพอดีกับ Viewport
        self.view.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def showEvent(self, event):
        """
        เมื่อหน้าต่างแสดงผลครั้งแรก ให้ปรับขนาดรูปให้พอดี
        """
        super().showEvent(event)
        # ต้องเรียก fitInView หลังจากที่หน้าต่างแสดงผลแล้ว
        # เพื่อให้ได้ขนาดที่ถูกต้อง
        self.view.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
