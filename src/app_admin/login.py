from PyQt6.QtWidgets import QVBoxLayout, QLineEdit, QPushButton, QMessageBox, QHBoxLayout
from app.base_dialog import BaseDialog
from app.custom_message_box import CustomMessageBox
from app_config import app_config
from app_db.db_management import get_db_instance
from datetime import datetime, timedelta

class AdminLoginWindow(BaseDialog):
    def __init__(self, main_window_ref, auth_only=False, force_local_auth=False, force_remote_auth=False):
        super().__init__(main_window_ref)
        self.main_window_ref = main_window_ref
        self.setWindowTitle("Admin Login")
        self.force_local_auth = force_local_auth
        self.force_remote_auth = force_remote_auth
        self.auth_only = auth_only
        self.db_instance = None # Will hold the successful DB instance for remote login
        self.user = None # Will hold the successful user data for remote login
        
        self.setMinimumWidth(350)

        layout = QVBoxLayout(self)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        layout.addWidget(self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.password_input)

        # ทำให้สามารถกด Enter เพื่อ Login ได้
        self.username_input.returnPressed.connect(self.check_login)
        self.password_input.returnPressed.connect(self.check_login)

        button_layout = QHBoxLayout()
        login_button = QPushButton("Login")
        login_button.clicked.connect(self.check_login)
        button_layout.addWidget(login_button)

        # Add Test Connection button only for remote login attempts
        should_use_server = self.force_remote_auth or (app_config.get('DATABASE', 'enabled', fallback='False').lower() == 'true' and not self.force_local_auth)
        if should_use_server:
            test_conn_button = QPushButton("ทดสอบการเชื่อมต่อ")
            test_conn_button.clicked.connect(self.test_remote_connection)
            button_layout.addWidget(test_conn_button)

        layout.addLayout(button_layout)

        self.adjust_and_center()

    def test_remote_connection(self):
        """
        Attempts to connect to the remote database using the current config
        and shows a message box with the result.
        """
        try:
            # We use get_db_instance which already has the logic to connect.
            # It will raise ConnectionError on failure.
            # We need to get a fresh instance for testing, not the cached one.
            from app_db.db_management import DBManagement
            test_db = DBManagement()
            test_db._connect_remote()
            test_db.close_connection() # Close immediately as it was just for a test.
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "เชื่อมต่อฐานข้อมูลเซิร์ฟเวอร์สำเร็จ!")
        except Exception as e:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "เชื่อมต่อล้มเหลว", f"ไม่สามารถเชื่อมต่อฐานข้อมูลได้:\n{e}")

    def check_login(self):
        username = self.username_input.text()
        password = self.password_input.text()

        # Determine which authentication method to use
        should_use_server = self.force_remote_auth or (app_config.get('DATABASE', 'enabled', fallback='False').lower() == 'true' and not self.force_local_auth)

        if not should_use_server:
            # --- Local Authentication (using app_config.ini) ---
            is_correct = (username == app_config.get('END_ADMIN', 'ID') and password == app_config.get('END_ADMIN', 'password', fallback=''))
            if is_correct:
                self.accept()
            else:
                CustomMessageBox.show(self, CustomMessageBox.Warning, "ล้มเหลว", "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
        else:
            # --- Server Database Authentication (using 'users' table) ---
            try:
                # Create a NEW, DEDICATED instance for this login attempt.
                from app_db.db_management import DBManagement
                self.db_instance = DBManagement()
                self.db_instance._connect_remote() # This will raise ConnectionError on failure

                verification_result = self.db_instance.verify_user(username, password)
                user, error_message = verification_result if isinstance(verification_result, tuple) else (None, None)

                if user and user.get('role') in ['admin', 'super_admin'] and not error_message:
                    self.user = user
                    self.accept()
                else:
                    # Use the specific error message from verify_user, or a generic one.
                    CustomMessageBox.show(self, CustomMessageBox.Warning, "การล็อกอินล้มเหลว", error_message or "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
            except ConnectionError as e:
                CustomMessageBox.show(self, CustomMessageBox.Critical, "Connection Failed", f"Could not connect to the remote database:\n{e}")
            except Exception as e: # Catch other DB errors like 'table not found'
                CustomMessageBox.show(self, CustomMessageBox.Critical, "Database Error", f"An error occurred while verifying user:\n{e}\n\nPlease ensure the server database has been initialized ('db init-server').")


    def closeEvent(self, event):
        """
        Ensures that if a temporary remote connection was made but the login was
        cancelled (or failed), the connection is properly closed.
        """
        super().closeEvent(event)