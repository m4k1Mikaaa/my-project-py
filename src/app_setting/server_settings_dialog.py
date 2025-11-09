from PyQt6.QtWidgets import (
    QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QTabWidget, QWidget, QFrame,
    QCheckBox, QComboBox, QHBoxLayout, QGroupBox, QLabel, QApplication, QSizePolicy, QListWidget,
    QSpinBox, QFileDialog
)
from PyQt6.QtCore import Qt, QSize, pyqtSlot, QTimer, QEvent, QBuffer, pyqtSignal
from PyQt6.QtGui import QPixmap, QCursor
import bcrypt
import cv2
import qtawesome as qta
from app.base_dialog import BaseDialog
from app_db.db_management import db_manager, db_signals
from app_config import app_config, AppConfig
from app.custom_message_box import CustomMessageBox
from app.utils import get_icon, resource_path
from theme import theme
from app_payment.scb_api_handler import SCBApiHandler
from app_payment.slipok_api_handler import SlipOKApiHandler
from app_payment.ktb_api_handler import KTBApiHandler
from validators import is_valid_password, is_valid_email, is_valid_phone, is_username_taken, is_email_taken, sanitize_input, is_valid_image_data
from app.image_cropper_dialog import ImageCropperDialog
import os
import importlib.metadata

INPUT_FIELD_MIN_WIDTH = 300

class SystemSettingsDialog(BaseDialog):
    """
    A dedicated dialog for managing server-side settings stored in the database.
    This dialog is only accessible in remote admin mode and requires a valid DB connection.
    """
    def __init__(self, main_window_ref, parent=None, db_instance=None, current_user=None):
        super().__init__(parent)
        self.db_instance = db_instance
        self.main_window_ref = main_window_ref
        self.current_user = current_user
        self.new_avatar_data = None
        # Initialize API handlers, passing the db_instance directly as the config_source.
        self.scb_handler = SCBApiHandler(config_source=self.db_instance)
        self.ktb_handler = KTBApiHandler(config_source=self.db_instance)
        self.slipok_handler = SlipOKApiHandler(debug=True, config_source=self.db_instance)

        # --- Dynamic Sizing ---
        # Get screen geometry to set a maximum height
        if parent and parent.screen():
            screen = parent.screen()
        else:
            screen = QApplication.primaryScreen()
        available_geom = screen.availableGeometry()

        self.setMaximumHeight(int(available_geom.height() * 0.9))
        self.setMinimumHeight(int(available_geom.height() * 0.8)) # เพิ่มความสูงพื้นฐาน
        self.setMinimumWidth(850)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self._create_super_admin_tab(), "บัญชี Super Admin")
        self.tab_widget.addTab(self._create_payment_tab(), "การชำระเงิน")
        self.tab_widget.addTab(self._create_smtp_tab(), "การส่งอีเมล (SMTP)")
        self.tab_widget.addTab(self._create_workflow_tab(), "การทำงานของระบบ")
        self.tab_widget.addTab(self._create_about_tab(), "ข้อมูลโปรแกรม")
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        main_layout.addWidget(self.tab_widget)

        # --- ปุ่มบันทึกและยกเลิก ---
        button_container = QWidget()
        self.bottom_button_layout = QHBoxLayout(button_container)
        self.bottom_button_layout.setSpacing(10)

        self.save_button = QPushButton("บันทึก") # Text will be updated dynamically
        self.save_button.clicked.connect(self._save_current_tab_settings)

        close_button = QPushButton("ปิดหน้าต่าง")
        close_button.clicked.connect(self.accept)

        self.bottom_button_layout.addStretch()
        self.bottom_button_layout.addWidget(self.save_button)
        self.bottom_button_layout.addWidget(close_button)
        self.bottom_button_layout.addStretch()
        main_layout.addWidget(button_container)

        # Set window title to indicate mode
        self.setWindowTitle("ตั้งค่าระบบ (Server)")

        self._on_tab_changed(0) # Initial setup for the first tab

    def update_icons(self):
        """
        A placeholder method to be called when the theme changes.
        This ensures compatibility with the theme-switching mechanism.
        Currently, this dialog does not have theme-dependent icons to update.
        """
        pass
    
    def _create_super_admin_tab(self):
        """Creates the tab for managing the Super Admin (user ID 1) account."""
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        main_layout.setSpacing(20)

        admin_group = QGroupBox("แก้ไขบัญชี Super Admin (ID: 1)")
        admin_layout = QFormLayout(admin_group)
        admin_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Fetch current super admin username
        # --- Avatar Section ---
        avatar_layout = QHBoxLayout()
        self.super_admin_avatar_label = QLabel("No Avatar")
        self.super_admin_avatar_label.setFixedSize(128, 128)
        self.super_admin_avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.super_admin_avatar_label.setStyleSheet("border: 1px solid #ccc; border-radius: 8px;")
        
        self.change_avatar_button = QPushButton("เปลี่ยนรูป")
        self.change_avatar_button.clicked.connect(self._change_super_admin_avatar)
        avatar_layout.addWidget(self.super_admin_avatar_label)
        avatar_layout.addWidget(self.change_avatar_button)
        avatar_layout.addStretch()
        admin_layout.addRow(avatar_layout)

        super_admin_data = self.db_instance.get_user_by_id(1)
        current_username = super_admin_data['username'] if super_admin_data else "N/A"

        self.super_admin_username_input = QLineEdit(current_username)
        self.super_admin_username_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        admin_layout.addRow("ชื่อผู้ใช้ (สำหรับ Login):", self.super_admin_username_input)

        self.super_admin_email_input = QLineEdit(super_admin_data.get('email', '') if super_admin_data else "")
        self.super_admin_email_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        admin_layout.addRow("อีเมล:", self.super_admin_email_input)

        self.super_admin_first_name_input = QLineEdit(super_admin_data.get('first_name', '') if super_admin_data else "")
        self.super_admin_first_name_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        admin_layout.addRow("ชื่อ:", self.super_admin_first_name_input)

        self.super_admin_last_name_input = QLineEdit(super_admin_data.get('last_name', '') if super_admin_data else "")
        self.super_admin_last_name_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        admin_layout.addRow("นามสกุล:", self.super_admin_last_name_input)

        self.super_admin_phone_input = QLineEdit(super_admin_data.get('phone', '') if super_admin_data else "")
        self.super_admin_phone_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        admin_layout.addRow("เบอร์โทร:", self.super_admin_phone_input)

        self.super_admin_location_input = QLineEdit(super_admin_data.get('location', '') if super_admin_data else "")
        self.super_admin_location_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        admin_layout.addRow("ที่อยู่:", self.super_admin_location_input)

        self.super_admin_old_password_input = QLineEdit()
        self.super_admin_old_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.super_admin_old_password_input.setPlaceholderText("กรอกรหัสผ่านปัจจุบันเพื่อเปลี่ยนรหัสผ่าน")
        admin_layout.addRow("รหัสผ่านปัจจุบัน:", self.super_admin_old_password_input)

        self.super_admin_password_input = QLineEdit()
        self.super_admin_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.super_admin_password_input.setPlaceholderText("เว้นว่างไว้หากไม่ต้องการเปลี่ยนรหัสผ่าน")
        admin_layout.addRow("รหัสผ่านใหม่:", self.super_admin_password_input)

        self.super_admin_confirm_password_input = QLineEdit()
        self.super_admin_confirm_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.super_admin_confirm_password_input.setPlaceholderText("ยืนยันรหัสผ่านใหม่")
        admin_layout.addRow("ยืนยันรหัสผ่าน:", self.super_admin_confirm_password_input)
        main_layout.addWidget(admin_group)

        # --- Permission Check ---
        is_super_admin_logged_in = self.current_user and self.current_user.get('id') == 1
        admin_group.setEnabled(is_super_admin_logged_in)
        if not is_super_admin_logged_in:
            admin_group.setToolTip("คุณต้องล็อกอินด้วยบัญชี Super Admin (ID: 1) เพื่อแก้ไขส่วนนี้")

        # Load avatar
        if super_admin_data:
            avatar_data = super_admin_data.get('avatar_path')
            if avatar_data:
                pixmap = QPixmap()
                pixmap.loadFromData(avatar_data)
                self.super_admin_avatar_label.setPixmap(pixmap.scaled(self.super_admin_avatar_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))


        main_layout.addStretch()
        # Return the created widget so it can be wrapped in a scroll area by the caller.
        return widget

    def _create_workflow_tab(self):
        """Creates the tab for managing system workflow settings."""
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        main_layout.setSpacing(20)

        workflow_group = QGroupBox("การทำงานของระบบ")
        form_layout = QFormLayout(workflow_group)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.auto_confirm_return_checkbox = QCheckBox("ยืนยันการรับคืนสินค้าอัตโนมัติ")
        self.auto_confirm_return_checkbox.setToolTip("เมื่อเปิดใช้งาน, สินค้าที่ถูกส่งคืนจะเปลี่ยนสถานะเป็น 'พร้อมให้เช่า' ทันที\nโดยไม่ต้องให้ผู้ดูแลระบบกดยืนยันการรับคืนด้วยตนเอง")
        is_auto_confirm = self._get_setting('WORKFLOW', 'auto_confirm_return', fallback='False').lower() == 'true'
        self.auto_confirm_return_checkbox.setChecked(is_auto_confirm)
        form_layout.addRow(self.auto_confirm_return_checkbox)

        main_layout.addWidget(workflow_group)
        main_layout.addStretch()
        return widget

    def _create_payment_tab(self):
        """Populates the content of the Payment Settings tab."""
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        main_layout.setContentsMargins(0, 5, 0, 0)

        # --- Primary Gateway Selection ---
        gateway_group = QGroupBox("ช่องทางการชำระเงินหลัก")
        gateway_layout = QFormLayout(gateway_group)
        gateway_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.gateway_map = {
            "Auto (ตามลำดับ)": "auto",
            "SlipOK / Slip2Go": "slipok",
            "SCB API": "scb",
            "KTB API": "ktb",
            "PromptPay (พื้นฐาน)": "promptpay"
        }
        self.reverse_gateway_map = {v: k for k, v in self.gateway_map.items()}

        self.payment_gateway_combo = QComboBox()
        self.payment_gateway_combo.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        self.payment_gateway_combo.addItems(self.gateway_map.keys())
        current_gateway = self._get_setting('PAYMENT', 'primary_gateway', fallback='auto')
        self.payment_gateway_combo.setCurrentText(self.reverse_gateway_map.get(current_gateway, "Auto (ตามลำดับ)"))
        gateway_layout.addRow("เลือกช่องทาง:", self.payment_gateway_combo)

        inactive_layout = QVBoxLayout()
        inactive_layout.addWidget(QLabel("<b>ช่องทางที่ปิดใช้งาน</b>"))
        self.inactive_gateways_list = QListWidget()
        inactive_layout.addWidget(self.inactive_gateways_list)

        main_layout.addWidget(gateway_group)

        # --- Sub-Tab Widget for different providers ---
        payment_providers_tab = QTabWidget()
        payment_providers_tab.addTab(self._create_auto_priority_tab(), "Auto")
        payment_providers_tab.addTab(self._create_scb_tab(), "SCB API")
        payment_providers_tab.addTab(self._create_ktb_tab(), "KTB API")
        payment_providers_tab.addTab(self._create_slipok_tab(), "SlipOK / Slip2Go")
        payment_providers_tab.addTab(self._create_promptpay_tab(), "PromptPay (พื้นฐาน)")

        main_layout.addWidget(payment_providers_tab, 1) # Give it stretch factor
        return widget

    def _create_auto_priority_tab(self):
        """Creates the tab for ordering payment gateways for 'Auto' mode."""
        widget = QWidget()
        main_layout = QVBoxLayout(widget)

        # --- Gateway Priority Group ---
        priority_group = QGroupBox("จัดลำดับช่องทางการชำระเงิน (สำหรับโหมด Auto)")
        priority_layout = QHBoxLayout(priority_group)

        # --- Active Gateways List (Left) ---
        active_layout = QVBoxLayout()
        active_layout.addWidget(QLabel("<b>ช่องทางที่เปิดใช้งาน (เรียงตามลำดับจากบนลงล่าง)</b>"))
        self.active_gateways_list = QListWidget()
        self.active_gateways_list.setDragDropMode(QListWidget.DragDropMode.InternalMove) # Allow reordering
        active_layout.addWidget(self.active_gateways_list)

        # --- Middle Buttons (Left/Right Arrows) ---
        middle_buttons_layout = QVBoxLayout()
        middle_buttons_layout.addStretch()
        self.move_to_inactive_button = QPushButton(qta.icon('fa5s.arrow-right', color='white'), "")
        self.move_to_inactive_button.setToolTip("ปิดใช้งานช่องทางที่เลือก")
        self.move_to_inactive_button.clicked.connect(self._move_to_inactive)
        self.move_to_active_button = QPushButton(qta.icon('fa5s.arrow-left', color='white'), "")
        self.move_to_active_button.setToolTip("เปิดใช้งานช่องทางที่เลือก")
        self.move_to_active_button.clicked.connect(self._move_to_active)
        middle_buttons_layout.addWidget(self.move_to_inactive_button)
        middle_buttons_layout.addWidget(self.move_to_active_button)
        middle_buttons_layout.addStretch()

        # --- Inactive Gateways List (Right) ---
        inactive_layout = QVBoxLayout()
        inactive_layout.addWidget(QLabel("<b>ช่องทางที่ปิดใช้งาน</b>"))
        self.inactive_gateways_list = QListWidget()
        inactive_layout.addWidget(self.inactive_gateways_list)

        priority_layout.addLayout(active_layout, 2)
        priority_layout.addLayout(middle_buttons_layout, 0)
        priority_layout.addLayout(inactive_layout, 1)

        # --- Populate Lists ---
        self.all_gateways = {"slipok": "SlipOK / Slip2Go", "scb": "SCB API", "ktb": "KTB API", "promptpay": "PromptPay (พื้นฐาน)"}
        priority_str = self._get_setting('PAYMENT', 'gateway_priority', fallback='slipok,scb,ktb,promptpay')
        active_keys = [key.strip() for key in priority_str.split(',') if key.strip()]
        
        for key in active_keys:
            if key in self.all_gateways:
                self.active_gateways_list.addItem(self.all_gateways[key])
        
        for key, name in self.all_gateways.items():
            if key not in active_keys:
                self.inactive_gateways_list.addItem(name)
        
        main_layout.addWidget(priority_group)
        main_layout.addStretch()
        return widget
        
    def _move_item_in_list(self, list_widget, direction):
        current_row = list_widget.currentRow()
        if current_row == -1: return

        new_row = current_row + direction
        if 0 <= new_row < list_widget.count():
            item = list_widget.takeItem(current_row)
            list_widget.insertItem(new_row, item)
            list_widget.setCurrentRow(new_row)

    def _move_to_inactive(self):
        selected_items = self.active_gateways_list.selectedItems()
        if not selected_items: return
        for item in selected_items:
            row = self.active_gateways_list.row(item)
            self.inactive_gateways_list.addItem(self.active_gateways_list.takeItem(row))

    def _move_to_active(self):
        selected_items = self.inactive_gateways_list.selectedItems()
        if not selected_items: return
        for item in selected_items:
            row = self.inactive_gateways_list.row(item)
            self.active_gateways_list.addItem(self.inactive_gateways_list.takeItem(row))

    def _get_key_from_name(self, name):
        for key, value in self.all_gateways.items():
            if value == name:
                return key
        return None

    def _create_promptpay_tab(self):
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        # --- PromptPay Group ---
        promptpay_group = QGroupBox("ตั้งค่า PromptPay")
        promptpay_layout = QVBoxLayout(promptpay_group)
        promptpay_desc = QLabel("ใช้สำหรับสร้าง QR Code แบบ PromptPay ทั่วไป ไม่สามารถตรวจสอบสถานะการชำระเงินอัตโนมัติได้")
        promptpay_desc.setWordWrap(True) 
        promptpay_desc.setStyleSheet("margin-bottom: 2px; color: #6c757d;")
        promptpay_layout.addWidget(promptpay_desc)
        promptpay_form_layout = QFormLayout()
        promptpay_form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.promptpay_phone_input = QLineEdit()
        self.promptpay_phone_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        self.promptpay_phone_input.setText(self._get_setting('PROMPTPAY', 'phone_number', fallback=''))
        promptpay_form_layout.addRow("เบอร์โทรศัพท์ PromptPay:", self.promptpay_phone_input)
        promptpay_layout.addLayout(promptpay_form_layout)
        main_layout.addWidget(promptpay_group)
        return widget

    def _create_scb_tab(self):
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        # --- SCB API Group ---
        scb_group = QGroupBox("ตั้งค่า SCB API")
        scb_layout = QFormLayout(scb_group)
        scb_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        # --- NEW: Add warning label ---
        scb_warning_label = QLabel("<b>(ยังไม่พร้อมใช้งานจริง)</b> ฟังก์ชันนี้ยังอยู่ในขั้นทดลองและยังไม่มีการทดสอบเต็มรูปแบบ")
        scb_warning_label.setStyleSheet("color: #f39c12; font-size: 9pt;")
        scb_warning_label.setWordWrap(True)
        scb_layout.addRow(scb_warning_label)

        self.scb_sandbox_checkbox = QCheckBox("เปิดใช้งานโหมด Sandbox (สำหรับทดสอบ)")
        sandbox_setting = self._get_setting('SCB_API', 'sandbox_enabled', fallback='True')
        is_sandbox = str(sandbox_setting).lower() == 'true'
        self.scb_sandbox_checkbox.setChecked(is_sandbox)
        scb_layout.addRow(self.scb_sandbox_checkbox)

        self.scb_biller_name_input = QLineEdit(self._get_setting('SCB_API', 'biller_name', fallback=''))
        self.scb_biller_name_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        scb_layout.addRow("SCB Biller Name:", self.scb_biller_name_input)
        self.scb_biller_id_input = QLineEdit(self._get_setting('SCB_API', 'biller_id', fallback=''))
        self.scb_biller_id_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        scb_layout.addRow("SCB Biller ID:", self.scb_biller_id_input)
        self.scb_api_key_input = QLineEdit(self._get_setting('SCB_API', 'api_key', fallback=''))
        self.scb_api_key_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        scb_layout.addRow("SCB API Key:", self.scb_api_key_input)
        self.scb_api_secret_input = QLineEdit(self._get_setting('SCB_API', 'api_secret', fallback=''))
        self.scb_api_secret_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        self.scb_api_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        scb_layout.addRow("SCB API Secret:", self.scb_api_secret_input)
        self.scb_app_name_input = QLineEdit(self._get_setting('SCB_API', 'app_name', fallback=''))
        self.scb_app_name_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        scb_layout.addRow("SCB App Name:", self.scb_app_name_input)
        self.scb_callback_url_input = QLineEdit(self._get_setting('SCB_API', 'callback_url', fallback=''))
        self.scb_callback_url_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        scb_layout.addRow("SCB Callback URL:", self.scb_callback_url_input)

        # --- Test Connection Button for SCB ---
        scb_test_button_layout = QHBoxLayout()
        scb_test_button = QPushButton("ทดสอบการเชื่อมต่อ SCB")
        scb_test_button.clicked.connect(self.test_scb_connection)
        scb_test_button_layout.addStretch()
        scb_test_button_layout.addWidget(scb_test_button)
        # Add the button layout to the main form layout as a new row
        scb_layout.addRow(scb_test_button_layout)

        main_layout.addWidget(scb_group)
        return widget

    def _create_ktb_tab(self):
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        # --- Krungthai API Group ---
        ktb_group = QGroupBox("ตั้งค่า Krungthai API")
        ktb_layout = QFormLayout(ktb_group)
        ktb_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        # --- NEW: Add warning label ---
        ktb_warning_label = QLabel("<b>(ยังไม่พร้อมใช้งานจริง)</b> ฟังก์ชันนี้ยังอยู่ในขั้นทดลองและยังไม่มีการทดสอบเต็มรูปแบบ")
        ktb_warning_label.setStyleSheet("color: #f39c12; font-size: 9pt;")
        ktb_warning_label.setWordWrap(True)
        ktb_layout.addRow(ktb_warning_label)

        self.ktb_sandbox_checkbox = QCheckBox("เปิดใช้งานโหมด Sandbox (สำหรับทดสอบ)")
        ktb_sandbox_setting = self._get_setting('KTB_API', 'sandbox_enabled', fallback='True')
        is_ktb_sandbox = str(ktb_sandbox_setting).lower() == 'true'
        self.ktb_sandbox_checkbox.setChecked(is_ktb_sandbox)
        ktb_layout.addRow(self.ktb_sandbox_checkbox)

        self.ktb_api_key_input = QLineEdit(self._get_setting('KTB_API', 'api_key', fallback=''))
        self.ktb_api_key_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        ktb_layout.addRow("KTB API Key (Client ID):", self.ktb_api_key_input)

        self.ktb_api_secret_input = QLineEdit(self._get_setting('KTB_API', 'api_secret', fallback=''))
        self.ktb_api_secret_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        self.ktb_api_secret_input.setEchoMode(QLineEdit.EchoMode.Password) # KTB uses client_secret
        ktb_layout.addRow("KTB API Secret (Client Secret):", self.ktb_api_secret_input)

        # --- Test Connection Button for KTB ---
        ktb_test_button_layout = QHBoxLayout()
        ktb_test_button = QPushButton("ทดสอบการเชื่อมต่อ KTB")
        ktb_test_button.clicked.connect(self.test_ktb_connection)
        ktb_test_button_layout.addStretch()
        ktb_test_button_layout.addWidget(ktb_test_button)
        ktb_layout.addRow(ktb_test_button_layout)

        main_layout.addWidget(ktb_group)
        return widget

    def _create_slipok_tab(self):
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        main_layout.setSpacing(20)
        # --- Slip Verification API Group ---
        slip_verify_group = QGroupBox("API ตรวจสอบสลิป")
        slip_verify_layout = QFormLayout(slip_verify_group)
        slip_verify_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.slip_api_url_input = QLineEdit(self._get_setting('SLIP_VERIFICATION', 'api_url', fallback=''))
        self.slip_api_url_input.setPlaceholderText("เช่น .../verify-slip/image หรือ .../verify-slip/qr-image/info")
        self.slip_api_url_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        slip_verify_layout.addRow("API URL (อัปโหลดรูป):", self.slip_api_url_input)

        self.slip_qr_api_url_input = QLineEdit(self._get_setting('SLIP_VERIFICATION', 'qr_api_url', fallback=''))
        self.slip_qr_api_url_input.setPlaceholderText("เช่น https://connect.slip2go.com/api/verify-slip/qr-code/info")
        self.slip_qr_api_url_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        slip_verify_layout.addRow("API URL (สแกน QR):", self.slip_qr_api_url_input)

        self.slip_api_token_input = QLineEdit(self._get_setting('SLIP_VERIFICATION', 'api_token', fallback=''))
        self.slip_api_token_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        self.slip_api_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        slip_verify_layout.addRow("API Token:", self.slip_api_token_input)

        # --- Check Duplicate Checkbox ---
        self.slip_check_duplicate_checkbox = QCheckBox("ตรวจสอบสลิปซ้ำ (แนะนำให้เปิด)")
        check_duplicate = self._get_setting('SLIP_VERIFICATION', 'check_duplicate', fallback='True')
        is_check_duplicate_enabled = str(check_duplicate).lower() == 'true'
        self.slip_check_duplicate_checkbox.setChecked(is_check_duplicate_enabled)
        slip_verify_layout.addRow(self.slip_check_duplicate_checkbox)

        # --- Test Buttons for SlipOK ---
        slipok_test_button_layout = QHBoxLayout()
        slipok_test_qr_button = QPushButton("ทดสอบ API (สแกน QR)")
        slipok_test_qr_button.clicked.connect(self.test_slipok_qr_connection)
        slipok_test_image_button = QPushButton("ทดสอบ API (อัปโหลดรูป)")
        slipok_test_image_button.clicked.connect(self.test_slipok_image_connection)
        slipok_test_button_layout.addStretch()
        slipok_test_button_layout.addWidget(slipok_test_qr_button)
        slipok_test_button_layout.addWidget(slipok_test_image_button)
        slip_verify_layout.addRow(slipok_test_button_layout)

        # --- Receiver Conditions for SlipOK ---
        from PyQt6.QtWidgets import QTextEdit
        self.slip_receiver_conditions_input = QTextEdit(self._get_setting('SLIP_VERIFICATION', 'receiver_conditions', fallback=''))
        self.slip_receiver_conditions_input.setPlaceholderText('ใส่เงื่อนไขบัญชีผู้รับในรูปแบบ JSON Array\nเช่น [{"accountNumber": "1234567890"}, {"accountNameTH": "บริษัท มิกะ"}]')
        self.slip_receiver_conditions_input.setMinimumHeight(80)
        self.slip_receiver_conditions_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        slip_verify_layout.addRow("เงื่อนไขบัญชีผู้รับ (JSON):", self.slip_receiver_conditions_input)

        main_layout.addWidget(slip_verify_group)

        # --- SlipOK QR Generation Group ---
        slipok_qr_group = QGroupBox("SlipOK QR Generation")
        slipok_qr_layout = QFormLayout(slipok_qr_group)
        slipok_qr_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.slipok_qr_gen_enabled_checkbox = QCheckBox("เปิดใช้งานการสร้าง QR ผ่าน SlipOK API")
        slipok_qr_enabled_setting = self._get_setting('SLIPOK_QR_GEN', 'enabled', fallback='False')
        is_slipok_qr_enabled = str(slipok_qr_enabled_setting).lower() == 'true'
        self.slipok_qr_gen_enabled_checkbox.setChecked(is_slipok_qr_enabled)
        slipok_qr_layout.addRow(self.slipok_qr_gen_enabled_checkbox)

        self.slipok_merchant_id_input = QLineEdit(self._get_setting('SLIPOK_QR_GEN', 'merchant_id', fallback=''))
        self.slipok_merchant_id_input.setPlaceholderText("Merchant ID จากระบบ SlipOK/Slip2Go")
        self.slipok_merchant_id_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        slipok_qr_layout.addRow("Merchant ID:", self.slipok_merchant_id_input)

        self.slipok_qr_gen_url_input = QLineEdit(self._get_setting('SLIPOK_QR_GEN', 'api_url', fallback=''))
        self.slipok_qr_gen_url_input.setPlaceholderText("เช่น https://connect.slip2go.com/api/qr-payment/generate-qr-code")
        self.slipok_qr_gen_url_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        slipok_qr_layout.addRow("API URL (สร้าง QR):", self.slipok_qr_gen_url_input)

        # --- NEW: Add the missing api_token field for QR generation ---
        self.slipok_qr_gen_api_token_input = QLineEdit(self._get_setting('SLIPOK_QR_GEN', 'api_token', fallback=''))
        self.slipok_qr_gen_api_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.slipok_qr_gen_api_token_input.setPlaceholderText("ใช้ Token เดียวกับส่วนตรวจสอบสลิปได้")
        slipok_qr_layout.addRow("API Token (สร้าง QR):", self.slipok_qr_gen_api_token_input)

        main_layout.addWidget(slipok_qr_group)
        return widget

    def _create_smtp_tab(self):
        """Populates the content of the SMTP settings tab."""
        widget = QWidget()
        main_layout = QVBoxLayout(widget)

        # --- SMTP Settings ---
        smtp_group = QGroupBox("การส่งอีเมล (SMTP)")
        smtp_layout = QVBoxLayout(smtp_group)
        desc_label = QLabel("ตั้งค่าเซิร์ฟเวอร์สำหรับส่งอีเมล (SMTP) เพื่อใช้ในการส่งใบเสร็จหรือการแจ้งเตือนต่างๆ\nสำหรับ Gmail, กรุณาใช้ 'App Password' 16 หลัก ไม่ใช่รหัสผ่านของบัญชี")
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("margin-bottom: 2px; color: #6c757d;")
        smtp_layout.addWidget(desc_label)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.smtp_enable_checkbox = QCheckBox("เปิดใช้งานการส่งอีเมล")
        smtp_enabled_setting = self._get_setting('SMTP', 'enabled', fallback='True')
        is_enabled = str(smtp_enabled_setting).lower() == 'true'
        self.smtp_enable_checkbox.setChecked(is_enabled)
        form_layout.addRow(self.smtp_enable_checkbox)

        self.smtp_host_input = QLineEdit(self._get_setting('SMTP', 'host', fallback='smtp.gmail.com'))
        form_layout.addRow("SMTP Host:", self.smtp_host_input)

        self.smtp_port_input = QLineEdit(self._get_setting('SMTP', 'port', fallback='587'))
        form_layout.addRow("SMTP Port:", self.smtp_port_input)

        self.smtp_user_input = QLineEdit(self._get_setting('SMTP', 'user', fallback=''))
        form_layout.addRow("อีเมลผู้ส่ง (User):", self.smtp_user_input)

        self.smtp_password_input = QLineEdit(self._get_setting('SMTP', 'password', fallback=''))
        self.smtp_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.smtp_password_input.setPlaceholderText("กรอก App Password 16 หลักที่นี่")
        form_layout.addRow("รหัสผ่าน (App Password):", self.smtp_password_input)

        smtp_layout.addLayout(form_layout)
        main_layout.addWidget(smtp_group)

        # --- Test SMTP Button ---
        smtp_test_button_layout = QHBoxLayout()
        smtp_test_button = QPushButton("ทดสอบการส่งอีเมล")
        smtp_test_button.clicked.connect(self.test_smtp_connection)
        smtp_test_button_layout.addStretch()
        smtp_test_button_layout.addWidget(smtp_test_button) # Add to its own layout
        smtp_layout.addLayout(smtp_test_button_layout) # Add to the group's layout
        main_layout.addStretch(1) # Add stretch to the main layout of the tab
        return widget

    def test_scb_connection(self):
        """Attempts to authenticate with SCB API using the credentials from the form."""
        api_key = self.scb_api_key_input.text().strip()
        api_secret = self.scb_api_secret_input.text().strip()

        if not api_key or not api_secret:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ข้อมูลไม่ครบ", "กรุณากรอก SCB API Key และ API Secret ก่อนทำการทดสอบ")
            return

        class TempConfig:
            def get(self, section, key, fallback=None):
                if section == 'SCB_API':
                    return {
                        'api_key': api_key,
                        'api_secret': api_secret,
                        'sandbox_enabled': str(self.scb_sandbox_checkbox.isChecked()),
                        'biller_id': self.scb_biller_id_input.text()
                    }.get(key, fallback)
                return fallback

        # Pass the temporary config directly to the handler
        handler = SCBApiHandler(debug=True, config_source=TempConfig())
        result_message = handler.test_authentication() # This now returns a detailed message
        
        # Show different message box based on success or failure
        if "Successful" in result_message:
            CustomMessageBox.show(self, CustomMessageBox.Information, "ผลการทดสอบ SCB", result_message)
        else:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ผลการทดสอบ SCB", result_message)

    def test_ktb_connection(self):
        """Attempts to authenticate with KTB API using the credentials from the form."""
        api_key = self.ktb_api_key_input.text().strip()
        api_secret = self.ktb_api_secret_input.text().strip()

        if not api_key or not api_secret:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ข้อมูลไม่ครบ", "กรุณากรอก KTB API Key และ API Secret ก่อนทำการทดสอบ")
            return

        class TempConfig:
            def get(self, section, key, fallback=None):
                if section == 'KTB_API':
                    return {
                        'api_key': api_key,
                        'api_secret': api_secret,
                        'sandbox_enabled': str(self.ktb_sandbox_checkbox.isChecked())
                    }.get(key, fallback)
                return fallback

        handler = KTBApiHandler(config_source=TempConfig())
        result_message = handler.test_authentication()
        CustomMessageBox.show(self, CustomMessageBox.Information, "ผลการทดสอบ KTB", result_message)

    def test_slipok_qr_connection(self):
        """Attempts to authenticate with SlipOK API using the credentials from the form."""
        api_token = self.slip_api_token_input.text().strip()
        qr_api_url = self.slip_qr_api_url_input.text().strip()

        if not api_token or not qr_api_url:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ข้อมูลไม่ครบ", "กรุณากรอก API Token และ API URL (สแกน QR) ก่อนทำการทดสอบ")
            return

        # Create a temporary config-like object from the form data
        # This ensures we test with the values currently in the input fields, not what's saved in the DB.
        class TempConfig:
            def get(self, section, key, fallback=None):
                if section == 'SLIP_VERIFICATION' and key == 'api_token':
                    return api_token
                if section == 'SLIP_VERIFICATION' and key == 'qr_api_url':
                    return qr_api_url
                return fallback

        # Pass the temporary config object to the handler
        handler = SlipOKApiHandler(debug=True, config_source=TempConfig())
        result_message = handler.test_authentication()

        # Show different message box based on success or failure
        CustomMessageBox.show(self, CustomMessageBox.Information, "ผลการทดสอบ SlipOK", result_message)

    def test_slipok_image_connection(self):
        """Tests the SlipOK image upload endpoint using credentials from the form."""
        api_token = self.slip_api_token_input.text().strip()
        api_url = self.slip_api_url_input.text().strip()

        if not api_token or not api_url:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ข้อมูลไม่ครบ", "กรุณากรอก API Token และ API URL (อัปโหลดรูป) ก่อนทำการทดสอบ")
            return

        class TempConfig:
            def get(self, section, key, fallback=None):
                if section == 'SLIP_VERIFICATION':
                    if key == 'api_token':
                        return api_token
                    if key == 'api_url':
                        return api_url
                return fallback

        handler = SlipOKApiHandler(debug=True, config_source=TempConfig())
        # Use a method on the handler specifically for testing the image endpoint
        result_message = handler.test_image_upload_authentication()
        CustomMessageBox.show(self, CustomMessageBox.Information, "ผลการทดสอบ SlipOK (อัปโหลด)", result_message)

    def test_smtp_connection(self):
        """Tests the SMTP connection using the settings from the form."""
        host = self.smtp_host_input.text().strip()
        port = self.smtp_port_input.text().strip()
        user = self.smtp_user_input.text().strip()
        password = self.smtp_password_input.text().strip()

        if not all([host, port, user, password]):
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ข้อมูลไม่ครบ", "กรุณากรอกข้อมูล SMTP ให้ครบถ้วนก่อนทำการทดสอบ")
            return

        class TempConfig:
            def __init__(self_inner):
                self_inner.data = {
                    'SMTP': {
                        'enabled': str(self.smtp_enable_checkbox.isChecked()),
                        'host': host,
                        'port': port,
                        'user': user,
                        'password': password
                    }
                }
            def get(self_inner, section, key, fallback=None):
                return self_inner.data.get(section, {}).get(key, fallback)
            def getint(self_inner, section, key, fallback=None):
                val = self_inner.get(section, key, fallback)
                try: return int(val)
                except (ValueError, TypeError): return fallback

        from app_payment.payment_handler import PaymentHandler
        # We use a static method on PaymentHandler to avoid needing a full instance
        success, message = PaymentHandler.send_test_email(TempConfig())
        icon = CustomMessageBox.Information if success else CustomMessageBox.Warning
        CustomMessageBox.show(self, icon, "ผลการทดสอบ SMTP", message)

    def _create_about_tab(self):
        """Populates the content of the About tab."""
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        main_layout.setSpacing(15)

        # --- App Icon ---
        icon_label = QLabel()
        app_icon = get_icon("app_image/icon.ico")
        icon_label.setPixmap(app_icon.pixmap(QSize(250, 250)))
        main_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignCenter)

        # --- App Name ---
        app_name_label = QLabel("MiKA RENTAL")
        app_name_label.setStyleSheet("font-size: 24pt; font-weight: bold;")
        main_layout.addWidget(app_name_label, 0, Qt.AlignmentFlag.AlignCenter)

        # --- Version ---
        try:
            # This works correctly after the project is installed/built.
            version = importlib.metadata.version('Mika-Rental')
            version_text = f"Version {version}"
        except importlib.metadata.PackageNotFoundError:
            version_text = "Version 0.1.0" # Fallback for development mode
        version_label = QLabel(version_text)
        version_label.setStyleSheet("font-size: 10pt; color: #888;")
        main_layout.addWidget(version_label, 0, Qt.AlignmentFlag.AlignCenter)

        main_layout.addSpacing(20)

        # --- Creator & Details ---
        try:
            meta = importlib.metadata.metadata('Mika-Rental')
            authors = meta.get_all('Author')
            creator_text = ', '.join(authors) if authors else "NiVARA"
        except importlib.metadata.PackageNotFoundError:
            creator_text = "NiRU, MiKA" # Fallback for development mode
        creator_label = QLabel(creator_text)
        creator_label.setStyleSheet("font-size: 11pt; font-weight: bold;")
        main_layout.addWidget(creator_label, 0, Qt.AlignmentFlag.AlignCenter)

        main_layout.addSpacing(10)

        # --- Program Status ---
        status_group = QGroupBox("สถานะโปรแกรม")
        # เปลี่ยนไปใช้ QVBoxLayout เพื่อให้จัดกลางได้
        status_group_layout = QVBoxLayout(status_group)
        status_group_layout.setSpacing(8)

        mode_text = "<b>โหมดเซิร์ฟเวอร์</b>"
        
        mode_label = QLabel(f"สถานะการทำงาน: {mode_text}")
        mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_group_layout.addWidget(mode_label)

        # --- FIX: Add item status summary section ---
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        status_group_layout.addWidget(line)

        item_summary_layout = QHBoxLayout()
        item_summary_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        item_summary_layout.setSpacing(20)

        summary = {}
        try:
            # Ensure we use the instance passed to this dialog
            if self.db_instance and self.db_instance.conn:
                summary = self.db_instance.get_item_status_summary()
        except Exception as e:
            print(f"Could not get item summary for about tab: {e}")

        status_map = {
            'available': 'พร้อมให้เช่า',
            'rented': 'กำลังถูกเช่า',
            'pending_return': 'รอการยืนยันคืน',
            'suspended': 'ระงับใช้งาน'
        }

        for status, display_text in status_map.items():
            count = summary.get(status, 0)
            item_label = QLabel(f"{display_text}: <b>{count}</b>")
            item_summary_layout.addWidget(item_label)
        
        status_group_layout.addLayout(item_summary_layout)

        main_layout.addWidget(status_group)

        main_layout.addStretch() # Add stretch at the end to push all content to the top

        return widget

    def _change_super_admin_avatar(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "เลือกรูปโปรไฟล์", "", "Image Files (*.png *.jpg *.jpeg)")
        if not file_name:
            return
        
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

            self.super_admin_avatar_label.setPixmap(cropped_pixmap.scaled(self.super_admin_avatar_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _get_setting(self, section, option, fallback=''):
        """
        Helper to get setting from the correct source based on mode.
        - Hardware/UI settings always come from the local .ini file.
        - Other settings come from the server DB if in remote mode, otherwise from local .ini.
        """
        # This dialog is for server settings, so it should always use the provided db_instance.
        if self.db_instance and self.db_instance.conn:
            try:
                value = self.db_instance.get_system_setting(f"{section.upper()}.{option.lower()}")
                return value if value is not None else fallback
            except Exception as e:
                print(f"Warning: Could not retrieve setting {section}.{option} from DB: {e}")
        return fallback

    def _get_setting_old(self, section, option, fallback=''):
        """
        Helper to get setting from the correct source based on mode.
        - Hardware/UI settings always come from the local .ini file.
        - Other settings come from the server DB if in remote mode, otherwise from local .ini.
        """
        # This dialog is for server settings, so it should always use the provided db_instance.
        if self.db_instance and self.db_instance.conn:
            try:
                value = self.db_instance.get_system_setting(f"{section.upper()}.{option.lower()}")
                return value if value is not None else fallback
            except Exception as e:
                print(f"Warning: Could not retrieve setting {section}.{option} from DB: {e}")
        return fallback

    def _save_setting(self, section, option, value) -> tuple[bool, str]:
        """Helper to save setting to the correct destination."""
        # In server mode, always save to the server DB.
        # The set_system_setting method in DBManagement handles the encryption internally,
        # so we just need to call it with the correct key and value.
        if self.db_instance and self.db_instance.conn:
            setting_key = f"{section.upper()}.{option.lower()}"
            return self.db_instance.set_system_setting(setting_key, str(value))
        return False, "No database instance available."

    def _save_super_admin_settings(self):
        """Saves only the Super Admin account settings."""
        # --- Permission Check ---
        is_super_admin_logged_in = self.current_user and self.current_user.get('id') == 1
        if not is_super_admin_logged_in:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ไม่ได้รับอนุญาต", "คุณต้องล็อกอินด้วยบัญชี Super Admin (ID: 1) เพื่อบันทึกส่วนนี้")
            return

        try:
            self._save_super_admin_logic()
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "บันทึกข้อมูล Super Admin เรียบร้อยแล้ว")
        except ValueError as e:
            # Catch specific validation errors
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ข้อมูลไม่ถูกต้อง", str(e))
        except Exception as e:
            # Catch other unexpected errors
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", f"ไม่สามารถบันทึกข้อมูล Super Admin ได้: {e}")

    def _save_super_admin_logic(self):
        """Saves only the Super Admin account settings."""
        try:
            # Fetch original data to compare against
            original_data = self.db_instance.get_user_by_id(1)
            if not original_data:
                raise ValueError("ไม่พบข้อมูล Super Admin (ID: 1)")

            # --- REVISED: Build a dictionary of only the fields that have new values ---
            update_data = {}

            # Get new values from input fields
            new_username = sanitize_input(self.super_admin_username_input.text().strip())
            new_email = sanitize_input(self.super_admin_email_input.text().strip())
            new_first_name = sanitize_input(self.super_admin_first_name_input.text().strip())
            new_last_name = sanitize_input(self.super_admin_last_name_input.text().strip())
            new_phone = sanitize_input(self.super_admin_phone_input.text().strip())
            new_location = sanitize_input(self.super_admin_location_input.text().strip())
            old_password = self.super_admin_old_password_input.text()
            new_password = self.super_admin_password_input.text()

            # --- Validation ---
            if not new_username or not new_first_name:
                raise ValueError("กรุณากรอก 'ชื่อผู้ใช้ใหม่' และ 'ชื่อ' เป็นอย่างน้อย")

            if new_password:
                # --- NEW: Require old password to change password ---
                if not old_password:
                    raise ValueError("กรุณากรอกรหัสผ่านปัจจุบันเพื่อเปลี่ยนรหัสผ่านใหม่")
                if not self.db_instance.verify_user(original_data['username'], old_password):
                    raise ValueError("รหัสผ่านปัจจุบันไม่ถูกต้อง")
                if new_password != self.super_admin_confirm_password_input.text():
                    raise ValueError("กรุณากรอกรหัสผ่านใหม่ของ Super Admin ให้ตรงกัน")
                if not is_valid_password(new_password):
                    raise ValueError("รหัสผ่านต้องมีความยาวอย่างน้อย 8 ตัวอักษร และมีทั้งตัวอักษรและตัวเลข")
                update_data['password'] = new_password

            if new_email and not is_valid_email(new_email):
                raise ValueError("รูปแบบอีเมลไม่ถูกต้อง")
            if new_phone and not is_valid_phone(new_phone):
                raise ValueError("รูปแบบเบอร์โทรศัพท์ไม่ถูกต้อง")
            if is_username_taken(new_username, self.db_instance, user_id=1):
                raise ValueError("ชื่อผู้ใช้นี้ถูกใช้โดยผู้ใช้อื่นแล้ว")
            if new_email and is_email_taken(new_email, self.db_instance, user_id=1):
                raise ValueError("อีเมลนี้ถูกใช้โดยผู้ใช้อื่นแล้ว")
    
            # --- Call the updated update_user method ---
            self.db_instance.update_user(1, username=new_username, email=new_email, first_name=new_first_name, last_name=new_last_name, phone=new_phone, location=new_location, password=new_password, avatar_path=self.new_avatar_data)

        except Exception as e:
            # Re-raise the exception to be caught by the calling method
            raise e

    def _on_tab_changed(self, index):
        """Updates the save button text and visibility when the tab changes."""
        self.adjustSize()
        tab_text = self.tab_widget.tabText(index)

        button_texts = {
            "บัญชี Super Admin": "บันทึกข้อมูล Super Admin",
            "การชำระเงิน": "บันทึกการตั้งค่าการชำระเงิน",
            "การส่งอีเมล (SMTP)": "บันทึกการตั้งค่า SMTP",
            "การทำงานของระบบ": "บันทึกการตั้งค่าการทำงาน",
        }

        if tab_text in button_texts:
            self.save_button.setText(button_texts[tab_text])
            self.save_button.show()
        else: # For "About" or other non-saving tabs
            self.save_button.hide()
        


    def _save_current_tab_settings(self):
        """Saves the settings for the currently active tab."""
        current_index = self.tab_widget.currentIndex()
        current_tab_name = self.tab_widget.tabText(current_index)

        try:
            if current_tab_name == "บัญชี Super Admin":
                self._save_super_admin_settings()
            elif current_tab_name == "การชำระเงิน":
                self._save_payment_settings()
            elif current_tab_name == "การส่งอีเมล (SMTP)":
                self._save_smtp_settings()
            elif current_tab_name == "การทำงานของระบบ":
                self._save_workflow_settings()
            else:
                CustomMessageBox.show(self, CustomMessageBox.Warning, "ไม่พบแท็บ", f"ไม่พบการดำเนินการบันทึกสำหรับแท็บ '{current_tab_name}'")
        except Exception as e:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", f"ไม่สามารถบันทึกการตั้งค่าสำหรับแท็บ '{current_tab_name}' ได้:\n{e}")

    def _save_payment_settings(self):
        """Saves only the Payment settings."""
        # Save the primary gateway choice
        primary_gateway_value = self.gateway_map.get(self.payment_gateway_combo.currentText(), 'auto')

        active_gateways = []
        for i in range(self.active_gateways_list.count()):
            item_name = self.active_gateways_list.item(i).text()
            key = self._get_key_from_name(item_name)
            if key: active_gateways.append(key)

        settings_to_save = [
            ('PAYMENT', 'primary_gateway', primary_gateway_value),
            ('PAYMENT', 'gateway_priority', ",".join(active_gateways)),
            ('PROMPTPAY', 'phone_number', sanitize_input(self.promptpay_phone_input.text().strip())),
            ('SCB_API', 'biller_id', sanitize_input(self.scb_biller_id_input.text().strip())),
            ('SCB_API', 'sandbox_enabled', str(self.scb_sandbox_checkbox.isChecked())),
            ('SCB_API', 'biller_name', sanitize_input(self.scb_biller_name_input.text().strip())),
            ('SCB_API', 'app_name', sanitize_input(self.scb_app_name_input.text().strip())),
            ('SCB_API', 'callback_url', sanitize_input(self.scb_callback_url_input.text().strip())),
            ('SCB_API', 'api_key', sanitize_input(self.scb_api_key_input.text().strip())),
            ('SCB_API', 'api_secret', self.scb_api_secret_input.text().strip()),
            ('KTB_API', 'sandbox_enabled', str(self.ktb_sandbox_checkbox.isChecked())),
            ('KTB_API', 'api_key', sanitize_input(self.ktb_api_key_input.text().strip())),
            ('KTB_API', 'api_secret', self.ktb_api_secret_input.text().strip()),
            ('SLIP_VERIFICATION', 'api_url', sanitize_input(self.slip_api_url_input.text().strip())),
            ('SLIP_VERIFICATION', 'qr_api_url', sanitize_input(self.slip_qr_api_url_input.text().strip())),
            ('SLIP_VERIFICATION', 'api_token', self.slip_api_token_input.text().strip()),
            ('SLIP_VERIFICATION', 'receiver_conditions', sanitize_input(self.slip_receiver_conditions_input.toPlainText().strip())),
            ('SLIP_VERIFICATION', 'check_duplicate', str(self.slip_check_duplicate_checkbox.isChecked())),
            ('SLIPOK_QR_GEN', 'enabled', str(self.slipok_qr_gen_enabled_checkbox.isChecked())),
            ('SLIPOK_QR_GEN', 'merchant_id', sanitize_input(self.slipok_merchant_id_input.text().strip())),
            ('SLIPOK_QR_GEN', 'api_url', sanitize_input(self.slipok_qr_gen_url_input.text().strip())),
            ('SLIPOK_QR_GEN', 'api_token', self.slipok_qr_gen_api_token_input.text().strip()),
        ]

        all_successful = True
        error_messages = []

        for section, option, value in settings_to_save:
            success, message = self._save_setting(section, option, value)
            if not success:
                all_successful = False
                error_messages.append(message)

        if all_successful:
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "บันทึกการตั้งค่าการชำระเงินเรียบร้อยแล้ว")
        else:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", "ไม่สามารถบันทึกการตั้งค่าบางรายการได้:\n" + "\n".join(error_messages))

    def _save_smtp_settings(self):
        """Saves only the SMTP settings."""
        settings_to_save = [
            ('SMTP', 'enabled', str(self.smtp_enable_checkbox.isChecked())),
            ('SMTP', 'host', sanitize_input(self.smtp_host_input.text().strip())),
            ('SMTP', 'port', sanitize_input(self.smtp_port_input.text().strip())),
            ('SMTP', 'user', sanitize_input(self.smtp_user_input.text().strip())),
            ('SMTP', 'password', self.smtp_password_input.text().strip()),
        ]

        all_successful = True
        error_messages = []

        for section, option, value in settings_to_save:
            success, message = self._save_setting(section, option, value)
            if not success:
                all_successful = False
                error_messages.append(message)

        if all_successful:
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "บันทึกการตั้งค่า SMTP เรียบร้อยแล้ว")
        else:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", "ไม่สามารถบันทึกการตั้งค่า SMTP ได้:\n" + "\n".join(error_messages))

    def _save_workflow_settings(self):
        """Saves only the Workflow settings."""
        settings_to_save = [
            ('WORKFLOW', 'auto_confirm_return', str(self.auto_confirm_return_checkbox.isChecked())),
        ]
        all_successful = True
        error_messages = []
        for section, option, value in settings_to_save:
            success, message = self._save_setting(section, option, value)
            if not success:
                all_successful = False
                error_messages.append(message)
        if all_successful:
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "บันทึกการตั้งค่าการทำงานของระบบเรียบร้อยแล้ว")
        else:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", "ไม่สามารถบันทึกการตั้งค่าได้:\n" + "\n".join(error_messages))