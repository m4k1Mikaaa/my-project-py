from PyQt6.QtWidgets import (
    QVBoxLayout, QLabel, QLineEdit, QPushButton, QFormLayout, QHBoxLayout, QApplication, QFileDialog
) # Import QApplication
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QBuffer
from app.base_dialog import BaseDialog
from app_db.db_management import get_db_instance
from validators import is_valid_email, is_valid_phone, is_email_taken, is_username_taken, is_valid_username, is_valid_password, is_valid_image_data
from app.image_cropper_dialog import ImageCropperDialog
from app.custom_message_box import CustomMessageBox

INPUT_FIELD_MIN_WIDTH = 280

class UserProfileWindow(BaseDialog):
    def __init__(self, user_data, parent=None, is_admin_edit=False, db_instance=None):
        super().__init__(parent)
        self.user_data = user_data
        self.new_avatar_data = None # เก็บข้อมูลรูปใหม่
        self.is_admin_edit = is_admin_edit
        self.setMinimumWidth(450)
        # Use the passed db_instance, otherwise get the currently active one.
        self.db_instance = db_instance if db_instance else get_db_instance()

        if self.user_data:
            self.setWindowTitle("แก้ไขข้อมูลส่วนตัว")
        else:
            self.setWindowTitle("เพิ่มผู้ใช้ใหม่")

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # --- Avatar Section ---
        avatar_layout = QHBoxLayout()
        self.avatar_label = QLabel("No Avatar")
        self.avatar_label.setFixedSize(128, 128) # ขยายขนาด Avatar
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self.user_data:
            self.avatar_label.setStyleSheet("border: 1px solid #ccc; border-radius: 64px;") # วงกลมสำหรับแก้ไข
        else:
            self.avatar_label.setStyleSheet("border: 1px solid #ccc; border-radius: 4px;") # สี่เหลี่ยมสำหรับเพิ่มใหม่
        change_avatar_button = QPushButton("เปลี่ยนรูป")
        change_avatar_button.clicked.connect(self.change_avatar)
        avatar_layout.addWidget(self.avatar_label)
        avatar_layout.addWidget(change_avatar_button)
        avatar_layout.addStretch()
        form_layout.addRow(avatar_layout)

        self.username_input = QLineEdit()
        # ทำให้ Username แก้ไขได้เฉพาะตอนเพิ่มผู้ใช้ใหม่
        self.username_input.setReadOnly(bool(self.user_data))
        form_layout.addRow("ชื่อผู้ใช้:", self.username_input)

        self.email_input = QLineEdit()
        form_layout.addRow("อีเมล:", self.email_input)

        self.first_name_input = QLineEdit()
        form_layout.addRow("ชื่อ:", self.first_name_input)

        self.last_name_input = QLineEdit()
        form_layout.addRow("นามสกุล:", self.last_name_input)

        self.phone_input = QLineEdit()
        form_layout.addRow("เบอร์โทร:", self.phone_input)

        self.location_input = QLineEdit()
        form_layout.addRow("ที่อยู่:", self.location_input)

        # --- Password Change Section ---
        self.old_password_input = QLineEdit()
        self.old_password_input.setPlaceholderText("กรอกรหัสผ่านปัจจุบันเพื่อเปลี่ยนรหัสผ่าน")
        self.old_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.old_password_label = QLabel("รหัสผ่านปัจจุบัน:")
        form_layout.addRow(self.old_password_label, self.old_password_input)

        # --- FIX: Hide old password field if it's an admin edit OR if it's a new user creation ---
        # A normal user editing their own profile will have self.is_admin_edit=False and self.user_data=True
        if self.is_admin_edit or not self.user_data:
            self.old_password_label.hide()
            self.old_password_input.hide()

        self.new_password_input = QLineEdit()
        self.new_password_input.setPlaceholderText("เว้นว่างไว้หากไม่ต้องการเปลี่ยน")
        self.new_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("รหัสผ่านใหม่:", self.new_password_input)

        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setPlaceholderText("ยืนยันรหัสผ่านใหม่")
        self.confirm_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("ยืนยันรหัสผ่านใหม่:", self.confirm_password_input)
        # --- End Password Change Section ---

        layout.addLayout(form_layout)

        button_layout = QHBoxLayout()
        save_button = QPushButton("บันทึก")
        save_button.clicked.connect(self.save_profile)
        cancel_button = QPushButton("ยกเลิก")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)

        # โหลดข้อมูลเฉพาะเมื่อเป็นการแก้ไข
        if self.user_data:
            self.load_user_data()
        self.adjust_and_center()

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
            self.new_avatar_data = buffer.data().data()

            # --- NEW: Validate image data after cropping ---
            if not is_valid_image_data(self.new_avatar_data):
                CustomMessageBox.show(self, CustomMessageBox.Warning, "ไฟล์ไม่ถูกต้อง", "ไฟล์ผลลัพธ์จากการตัดรูปไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง")
                return

            self.avatar_label.setPixmap(cropped_pixmap.scaled(self.avatar_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def load_user_data(self):
        self.username_input.setText(self.user_data['username'])
        self.email_input.setText(self.user_data['email'] or "")
        self.first_name_input.setText(self.user_data['first_name'] or "")
        self.last_name_input.setText(self.user_data['last_name'] or "")
        self.phone_input.setText(self.user_data['phone'] or "")
        self.location_input.setText(self.user_data['location'] or "")

        avatar_data = self.user_data.get('avatar_path')
        if avatar_data:
            pixmap = QPixmap()
            pixmap.loadFromData(avatar_data)
            self.avatar_label.setPixmap(pixmap.scaled(self.avatar_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.avatar_label.setText("No Avatar")

    def save_profile(self):
        email = self.email_input.text()
        first_name = self.first_name_input.text()
        last_name = self.last_name_input.text()
        phone = self.phone_input.text()
        location = self.location_input.text()
        old_password = self.old_password_input.text()
        new_password = self.new_password_input.text()
        confirm_password = self.confirm_password_input.text()
        username = self.username_input.text()

        if not first_name or not email:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ข้อมูลไม่ครบ", "กรุณากรอกชื่อและอีเมล")
            return

        # --- Password Change Validation ---
        password_to_save = None
        if new_password:
            # 1. Check old password only if it's a user editing their own profile
            if not self.is_admin_edit and self.user_data:
                if not self.db_instance.verify_user(self.user_data.get('username'), old_password):
                    CustomMessageBox.show(self, CustomMessageBox.Warning, "รหัสผ่านไม่ถูกต้อง", "รหัสผ่านปัจจุบันไม่ถูกต้อง")
                    return
            # 2. Always check if new passwords match
            if new_password != confirm_password:
                CustomMessageBox.show(self, CustomMessageBox.Warning, "รหัสผ่านใหม่ไม่ตรงกัน", "กรุณากรอกรหัสผ่านใหม่และยืนยันให้ตรงกัน")
                return
            if not is_valid_password(new_password):
                CustomMessageBox.show(self, CustomMessageBox.Warning, "รหัสผ่านใหม่ไม่ปลอดภัย", "รหัสผ่านต้องมีความยาวอย่างน้อย 8 ตัวอักษร และมีทั้งตัวอักษรและตัวเลข")
                return
            password_to_save = new_password
        # --- End Validation ---

        # --- 1. Validate input formats first (Client-side) ---
        if not is_valid_username(username):
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ชื่อผู้ใช้ไม่ถูกต้อง", "ชื่อผู้ใช้ต้องมี 3-20 ตัวอักษร และประกอบด้วย a-z, A-Z, 0-9, _, - เท่านั้น")
            return
        if not is_valid_email(email):
            CustomMessageBox.show(self, CustomMessageBox.Warning, "รูปแบบอีเมลไม่ถูกต้อง", "กรุณาตรวจสอบรูปแบบอีเมลของคุณ")
            return
        if not is_valid_phone(phone):
            CustomMessageBox.show(self, CustomMessageBox.Warning, "รูปแบบเบอร์โทรไม่ถูกต้อง", "กรุณาตรวจสอบรูปแบบเบอร์โทรศัพท์ของคุณ")
            return

        # --- 2. Check for uniqueness in DB ---
        user_id_to_exclude = self.user_data['id'] if self.user_data else None
        if is_username_taken(username, db_instance=self.db_instance, user_id=user_id_to_exclude):
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ชื่อผู้ใช้ไม่พร้อมใช้งาน", "ชื่อผู้ใช้นี้ถูกใช้ไปแล้ว")
            return
        if is_email_taken(email, self.db_instance, user_id=user_id_to_exclude):
            CustomMessageBox.show(self, CustomMessageBox.Warning, "อีเมลไม่พร้อมใช้งาน", "อีเมลนี้ถูกใช้โดยผู้ใช้อื่นแล้ว")
            return


        try:
            if self.user_data: # --- Editing existing user ---
                # --- FIX: Use the single, correct update_user method ---
                self.db_instance.update_user(
                    user_id=self.user_data['id'],
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    phone=phone,
                    location=location,
                    password=password_to_save,
                    avatar_path=self.new_avatar_data
                )

                CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "บันทึกข้อมูลส่วนตัวเรียบร้อยแล้ว")
                self.accept()
            else: # --- Adding new user ---
                if not username or not new_password:
                    CustomMessageBox.show(self, CustomMessageBox.Warning, "ข้อมูลไม่ครบ", "กรุณากรอกชื่อผู้ใช้และรหัสผ่านสำหรับผู้ใช้ใหม่")
                    return
                if new_password != confirm_password:
                    CustomMessageBox.show(self, CustomMessageBox.Warning, "รหัสผ่านใหม่ไม่ตรงกัน", "กรุณากรอกรหัสผ่านใหม่และยืนยันให้ตรงกัน")
                    return
                if not is_valid_password(new_password):
                    CustomMessageBox.show(self, CustomMessageBox.Warning, "รหัสผ่านไม่ปลอดภัย", "รหัสผ่านต้องมีความยาวอย่างน้อย 8 ตัวอักษร และมีทั้งตัวอักษรและตัวเลข")
                    return
                if is_username_taken(username, db_instance=self.db_instance, user_id=user_id_to_exclude):
                    CustomMessageBox.show(self, CustomMessageBox.Warning, "ชื่อผู้ใช้ไม่พร้อมใช้งาน", "ชื่อผู้ใช้นี้ถูกใช้ไปแล้ว")
                    return
                
                success, message = self.db_instance.create_user(username, new_password, first_name, last_name, email, phone, location, self.new_avatar_data)
                if success:
                    CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "เพิ่มผู้ใช้ใหม่เรียบร้อยแล้ว")
                    self.accept()
                else:
                    CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", f"ไม่สามารถเพิ่มผู้ใช้ได้: {message}")
        except Exception as e:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", f"ไม่สามารถบันทึกข้อมูลได้: {e}")