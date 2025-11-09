from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QFormLayout, QMessageBox, QApplication, QWidget, QGridLayout
) # Import QApplication
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtCore import Qt, QBuffer 
from app_user.profile import UserProfileWindow
from .image_cropper_dialog import ImageCropperDialog
from .image_viewer import ImageViewerDialog
from app_payment.payment_history_dialog import PaymentHistoryDialog
import qtawesome as qta
from app_db.db_management import get_db_instance
from .base_dialog import BaseDialog
from .custom_message_box import CustomMessageBox
from theme import PALETTES
from .utils import set_image_on_label
from validators import is_valid_image_data

class UserProfileViewWindow(BaseDialog):
    def __init__(self, user_data, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.user_data = user_data
        # Get the correct database instance from the main window
        self.db_instance = self.main_window._get_db_instance_for_refresh() if self.main_window else get_db_instance()
        self.setWindowTitle("ข้อมูลส่วนตัว")
        self.setMinimumWidth(500)

        main_layout = QVBoxLayout(self)

        avatar_container = QWidget()
        avatar_layout = QVBoxLayout(avatar_container) # เปลี่ยนเป็น QVBoxLayout
        avatar_layout.setContentsMargins(0,0,0,0)

        self.avatar_label = QLabel("No Avatar")
        self.avatar_label.setFixedSize(192, 192) # ขยายขนาด Avatar
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setProperty("class", "avatar-label")
        self.avatar_label.setToolTip("ดับเบิลคลิกเพื่อดูภาพขนาดเต็ม")
        self.avatar_label.mouseDoubleClickEvent = self.view_full_image
        avatar_layout.addWidget(self.avatar_label)
        
        change_avatar_button = QPushButton("เปลี่ยนรูปโปรไฟล์")
        change_avatar_button.clicked.connect(self.change_avatar)
        
        main_layout.addWidget(avatar_container, 0, Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(change_avatar_button, 0, Qt.AlignmentFlag.AlignCenter)

        form_layout = QFormLayout()
        form_layout.setContentsMargins(20, 20, 20, 10)
        self.username_label = QLabel()
        self.fullname_label = QLabel()
        self.email_label = QLabel()
        self.phone_label = QLabel()
        self.location_label = QLabel()

        # เปิดใช้งาน Word Wrap เพื่อป้องกันข้อความตกขอบ
        for label in [self.username_label, self.fullname_label, self.email_label, self.phone_label, self.location_label]:
            label.setWordWrap(True)

        form_layout.addRow("<b>ชื่อผู้ใช้:</b>", self.username_label)
        form_layout.addRow("<b>ชื่อ-สกุล:</b>", self.fullname_label)
        form_layout.addRow("<b>อีเมล:</b>", self.email_label)
        form_layout.addRow("<b>เบอร์โทร:</b>", self.phone_label)
        form_layout.addRow("<b>ที่อยู่:</b>", self.location_label)

        main_layout.addLayout(form_layout)
        button_layout = QHBoxLayout()

        edit_button = QPushButton("แก้ไขข้อมูล")
        edit_button.clicked.connect(self.open_edit_window)
        close_button = QPushButton("ปิด")
        close_button.clicked.connect(self.accept)
        
        button_layout.addStretch()
        button_layout.addWidget(edit_button)
        button_layout.addWidget(close_button)

        main_layout.addLayout(button_layout)

        self.load_user_data()
        self.update_icons()
        
        # Adjust size to content and center
        self.adjust_and_center()

    def load_user_data(self):
        self.username_label.setText(self.user_data.get('username', '-'))
        full_name = f"{self.user_data.get('first_name', '')} {self.user_data.get('last_name', '')}".strip()
        self.fullname_label.setText(full_name or '-')
        self.email_label.setText(self.user_data.get('email', '-'))
        self.phone_label.setText(self.user_data.get('phone', '-'))
        self.location_label.setText(self.user_data.get('location', '-'))

        avatar_data = self.user_data.get('avatar_path')
        set_image_on_label(self.avatar_label, avatar_data, "No Avatar")

    def open_edit_window(self):
        edit_win = UserProfileWindow(user_data=self.user_data, parent=self)
        if edit_win.exec():
            # Refresh user data by ID after editing
            self.user_data = self.db_instance.get_user_by_id(self.user_data['id'])
            self.load_user_data()
            self.main_window.update_user_status_from_child(self.user_data)

    def change_avatar(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "เลือกรูปโปรไฟล์", "", "Image Files (*.png *.jpg *.jpeg)")
        if not file_name:
            return
        
        # เปิดหน้าต่างสำหรับ Crop รูปภาพ
        cropped_pixmap = ImageCropperDialog.crop(file_name, self)

        if cropped_pixmap:
            buffer = QBuffer()
            buffer.open(QBuffer.OpenModeFlag.WriteOnly)
            cropped_pixmap.save(buffer, "PNG")
            avatar_data = buffer.data().data()

            # --- NEW: Validate image data after cropping ---
            if not is_valid_image_data(avatar_data):
                CustomMessageBox.show(self, CustomMessageBox.Warning, "ไฟล์ไม่ถูกต้อง", "ไฟล์ผลลัพธ์จากการตัดรูปไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง")
                return

            # --- FIX: Use the correct unified update method ---
            self.db_instance.update_user(self.user_data['id'], avatar_path=avatar_data)
            self.user_data['avatar_path'] = avatar_data
            self.load_user_data()
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "เปลี่ยนรูปโปรไฟล์เรียบร้อยแล้ว")

    def view_full_image(self, event=None):
        if self.user_data.get('avatar_path'):
            # Set the main window as the parent to ensure correct lifecycle management
            # and prevent crashes when this dialog is closed.
            dialog = ImageViewerDialog(self.user_data['avatar_path'], self.main_window)
            dialog.exec()

    def update_icons(self):
        """A placeholder method to be called when the theme changes. Currently no icons to update."""
        pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        avatar_data = self.user_data.get('avatar_path')
        set_image_on_label(self.avatar_label, avatar_data, "No Avatar")

    def showEvent(self, event):
        super().showEvent(event)
        avatar_data = self.user_data.get('avatar_path')
        set_image_on_label(self.avatar_label, avatar_data, "No Avatar")
