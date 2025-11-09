from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox, QFormLayout, QHBoxLayout, QApplication
) # Import QApplication
from PyQt6.QtCore import Qt
from app_db.db_management import db_manager
from validators import is_valid_email, is_valid_phone, is_username_taken, is_email_taken, is_valid_username, is_valid_password, sanitize_input
from .base_dialog import BaseDialog
from .custom_message_box import CustomMessageBox

INPUT_FIELD_MIN_WIDTH = 250

class RegisterWindow(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("สมัครสมาชิก")
        self.db_instance = None # Defer DB instance retrieval
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.username_input = QLineEdit()
        self.username_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        form_layout.addRow("ชื่อผู้ใช้:", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("รหัสผ่าน:", self.password_input)

        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        self.confirm_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("ยืนยันรหัสผ่าน:", self.confirm_password_input)

        self.first_name_input = QLineEdit()
        self.first_name_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        form_layout.addRow("ชื่อ:", self.first_name_input)

        self.last_name_input = QLineEdit()
        self.last_name_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        form_layout.addRow("นามสกุล:", self.last_name_input)

        self.email_input = QLineEdit()
        self.email_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        form_layout.addRow("อีเมล:", self.email_input)

        self.phone_input = QLineEdit()
        self.phone_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        form_layout.addRow("เบอร์โทร:", self.phone_input)

        self.location_input = QLineEdit()
        self.location_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        form_layout.addRow("ที่อยู่:", self.location_input)

        layout.addLayout(form_layout)

        button_layout = QHBoxLayout()
        register_button = QPushButton("สมัครสมาชิก")
        register_button.clicked.connect(self.register_user)
        cancel_button = QPushButton("ยกเลิก")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(register_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        # Adjust size to content and center
        self.adjust_and_center()

    def register_user(self):
        username = self.username_input.text()
        password = self.password_input.text()
        confirm_password = self.confirm_password_input.text()
        first_name = sanitize_input(self.first_name_input.text())
        last_name = sanitize_input(self.last_name_input.text())
        email = self.email_input.text()
        phone = self.phone_input.text()
        location = sanitize_input(self.location_input.text())

        if not all([username, password, confirm_password, first_name, email]):
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ข้อมูลไม่ครบ", "กรุณากรอกข้อมูลที่จำเป็น (ชื่อผู้ใช้, รหัสผ่าน, ชื่อ, อีเมล)")
            return
        
        # --- 1. Validate input formats first ---
        if not is_valid_username(username):
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ชื่อผู้ใช้ไม่ถูกต้อง", "ชื่อผู้ใช้ต้องมี 3-20 ตัวอักษร และประกอบด้วย a-z, A-Z, 0-9, _, - เท่านั้น")
            return
        if not is_valid_password(password):
            CustomMessageBox.show(self, CustomMessageBox.Warning, "รหัสผ่านไม่ปลอดภัย", "รหัสผ่านต้องมีความยาวอย่างน้อย 8 ตัวอักษร และมีทั้งตัวอักษรและตัวเลข")
            return
        if password != confirm_password:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "รหัสผ่านไม่ตรงกัน", "กรุณากรอกรหัสผ่านและยืนยันรหัสผ่านให้ตรงกัน")
            return
        if not is_valid_email(email):
            CustomMessageBox.show(self, CustomMessageBox.Warning, "อีเมลไม่ถูกต้อง", "รูปแบบอีเมลไม่ถูกต้องหรืออีเมลนี้ถูกใช้ไปแล้ว")
            return
        if not is_valid_phone(phone):
            CustomMessageBox.show(self, CustomMessageBox.Warning, "รูปแบบเบอร์โทรไม่ถูกต้อง", "เบอร์โทรศัพท์ต้องประกอบด้วยตัวเลขอย่างน้อย 9 ตัว")
            return

        # --- 2. Connect to DB and check for uniqueness ---
        try:
            self.db_instance = db_manager.get_active_instance()
            if is_username_taken(username, db_instance=self.db_instance):
                CustomMessageBox.show(self, CustomMessageBox.Warning, "ชื่อผู้ใช้ไม่พร้อมใช้งาน", "ชื่อผู้ใช้นี้ถูกใช้ไปแล้ว")
                return
            if is_email_taken(email, db_instance=self.db_instance):
                CustomMessageBox.show(self, CustomMessageBox.Warning, "อีเมลไม่พร้อมใช้งาน", "อีเมลนี้ถูกใช้ไปแล้ว")
                return
        except ConnectionError as e:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ข้อผิดพลาดฐานข้อมูล", str(e))
            return

        # --- 3. Create user ---
        success, message = self.db_instance.create_user(username, password, first_name, last_name, email, phone, location)
        if success:
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "สมัครสมาชิกเรียบร้อยแล้ว\nคุณสามารถเข้าสู่ระบบได้เลย")
            self.accept()
        else:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", f"ไม่สามารถสมัครสมาชิกได้: {message}")
