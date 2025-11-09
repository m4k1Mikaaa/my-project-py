from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox, QHBoxLayout, QApplication
)
from app_db.db_management import db_manager, get_db_instance
from .register import RegisterWindow
from .base_dialog import BaseDialog
from .custom_message_box import CustomMessageBox
from app_config import app_config
from datetime import datetime, timedelta

class UserLoginWindow(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("เข้าสู่ระบบผู้ใช้")
        self.setMinimumWidth(350)
        self.db_instance = None # Defer DB instance retrieval

        self.user_data = None

        layout = QVBoxLayout(self)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("ชื่อผู้ใช้")
        layout.addWidget(QLabel("ชื่อผู้ใช้ (Username):"))
        layout.addWidget(self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("รหัสผ่าน")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(QLabel("รหัสผ่าน:"))
        layout.addWidget(self.password_input)

        button_layout = QHBoxLayout()
        
        login_button = QPushButton("เข้าสู่ระบบ")
        login_button.clicked.connect(self.check_login)
        button_layout.addWidget(login_button)

        register_button = QPushButton("สมัครสมาชิก")
        register_button.clicked.connect(self.open_register_window)
        button_layout.addWidget(register_button)

        layout.addLayout(button_layout)
        
        # Adjust size to content and center
        self.adjust_and_center() # This line was missing or misplaced

    def check_login(self):
        username = self.username_input.text()
        password = self.password_input.text()

        if not username or not password:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ข้อมูลไม่ครบ", "กรุณากรอกชื่อผู้ใช้และรหัสผ่าน")
            return
        
        try:
            # Retrieve the currently active DB instance (local or remote)
            self.db_instance = get_db_instance(is_remote=app_config.get('DATABASE', 'enabled', 'False').lower() == 'true')
        except ConnectionError as e:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ข้อผิดพลาดฐานข้อมูล", str(e))
            return
        
        # --- NEW: Use the appropriate verification method based on the mode ---
        is_server_mode = hasattr(self.db_instance.conn, 'get_backend_pid') # Check for PostgreSQL connection
        if is_server_mode:
            verification_result = self.db_instance.verify_user(username, password)
        else:
            # Use the local verification method which includes lockout logic from app_config.ini
            verification_result = self.db_instance.verify_user_local(username, password)

        user, error_message = verification_result if isinstance(verification_result, tuple) else (None, None)

        if user:
            self.user_data = user
            self.accept()
        else:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ล้มเหลว", "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")

    def open_register_window(self):
        register_win = RegisterWindow(self)
        if register_win.exec():
            self.close()
