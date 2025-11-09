from PyQt6.QtWidgets import (
    QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QTabWidget, QWidget,
    QComboBox, QHBoxLayout, QGroupBox, QLabel, QFrame, QCheckBox, QListWidget, QSlider, QSizePolicy,
    QSpinBox, QFileDialog, QApplication
) # sourcery skip: extract-method
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QPixmap
import qtawesome as qta
import os
import importlib.metadata
from app.base_dialog import BaseDialog
from app_db.db_management import db_manager
from app_config import app_config, AppConfig
from app.custom_message_box import CustomMessageBox
from app.utils import get_icon
from theme import theme
from app_payment.scb_api_handler import SCBApiHandler
from app_payment.slipok_api_handler import SlipOKApiHandler
from validators import sanitize_input

INPUT_FIELD_MIN_WIDTH = 300

class ShortcutLineEdit(QLineEdit):
    """A QLineEdit that captures a key press and displays its name."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, event):
        # --- NEW: Map special keys to user-friendly characters ---
        key_map = {
            Qt.Key.Key_AsciiTilde: "~",
            Qt.Key.Key_QuoteLeft: "`",
            # สามารถเพิ่มการ map ปุ่มอื่นๆ ได้ที่นี่
        }
        
        key = event.key()
        
        if key in key_map:
            key_name = key_map[key]
        else:
            key_name = Qt.Key(key).name
            # Remove the "Key_" prefix for cleaner display
            if key_name.startswith("Key_"):
                key_name = key_name[4:]
        self.setText(key_name)

class LocalSettingsDialog(BaseDialog):
    """
    A dedicated dialog for managing local settings stored in the app_config.ini file.
    This dialog does not interact with the server database.
    """
    def __init__(self, main_window_ref, parent=None, config_instance=None):
        super().__init__(parent)
        self.main_window_ref = main_window_ref
        # This dialog always works on a config file instance.
        self.config = config_instance if config_instance else app_config

        self.setWindowTitle("ตั้งค่า Local")
        self.setMinimumWidth(850)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.tab_widget = QTabWidget()
        # Create tabs first, then call update methods that might depend on them
        self.tab_widget.addTab(self._create_general_tab(), "ทั่วไป")
        self.tab_widget.addTab(self._create_shortcuts_tab(), "ปุ่มลัด")
        self.tab_widget.addTab(self._create_connectivity_tab(), "การเชื่อมต่อ")
        self.tab_widget.addTab(self._create_payment_tab(), "การชำระเงิน")
        self.tab_widget.addTab(self._create_smtp_tab(), "การส่งอีเมล (SMTP)")
        self.tab_widget.addTab(self._create_devices_tab(), "อุปกรณ์")
        self.tab_widget.addTab(self._create_about_tab(), "ข้อมูลโปรแกรม")
        self.tab_widget.currentChanged.connect(self._on_tab_changed) # Adjust size and button text

        main_layout.addWidget(self.tab_widget)

        # --- Save/Cancel Buttons ---
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

        # Call UI update methods after all widgets have been created
        self._on_tab_changed(0) # Initial setup for the first tab

        self.adjust_and_center()

    def _get_setting(self, section, option, fallback=''):
        """
        Helper to get a setting specifically from the local .ini file instance,
        bypassing any server-side configuration by using the config object's own get method,
        which correctly handles decryption.
        """
        # --- FIX: Directly read from the config parser and handle decryption here ---
        # This avoids the complex logic in AppConfig.get() which can sometimes return bytes
        # when we need a string for a QLineEdit.
        raw_value = self.config.config.get(section, option, fallback=fallback)
        return raw_value

    def _create_general_tab(self):
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        main_layout.setSpacing(20)

        # --- UI Settings ---
        ui_group = QGroupBox("ลักษณะโปรแกรม (UI)")
        ui_layout = QVBoxLayout(ui_group) # Main layout for the group

        # --- Top row for Mode, Theme, and Auto-logout ---
        top_row_layout = QHBoxLayout()
        top_row_layout.setSpacing(15)

        # --- NEW: Mode Switch Button ---
        top_row_layout.addWidget(QLabel("<b>โหมด:</b>"))
        self.db_mode_button = QPushButton()
        self.db_mode_button.setCheckable(True)
        self.db_mode_button.clicked.connect(self._toggle_db_mode)
        top_row_layout.addWidget(self.db_mode_button)

        # --- NEW: Theme Switch Button ---
        top_row_layout.addWidget(QLabel("<b>ธีม:</b>"))
        self.theme_button = QPushButton()
        self.theme_button.setCheckable(True)
        self.theme_button.clicked.connect(self._toggle_theme)
        top_row_layout.addWidget(self.theme_button)

        # --- NEW: Auto Logout Slider ---
        top_row_layout.addWidget(QLabel("<b>ออกจากระบบอัตโนมัติ:</b>"))
        self.auto_logout_slider = QSlider(Qt.Orientation.Horizontal)
        self.auto_logout_slider.setRange(0, 180) # 0 to 3 hours
        self.auto_logout_slider.setSingleStep(5)
        self.auto_logout_slider.setPageStep(15)
        self.auto_logout_slider.setToolTip("ตั้งค่าเวลาที่จะให้ออกจากระบบอัตโนมัติ (0 = ปิดใช้งาน)")
        self.auto_logout_slider.setValue(int(self._get_setting('UI', 'auto_logout_minutes', fallback=15)))
        self.auto_logout_label = QLabel()
        self.auto_logout_slider.valueChanged.connect(self._update_auto_logout_label)
        self._update_auto_logout_label(self.auto_logout_slider.value()) # Initial update
        top_row_layout.addWidget(self.auto_logout_slider)
        top_row_layout.addWidget(self.auto_logout_label)

        # --- FIX: Add the top row layout to the main UI group layout ---
        ui_layout.addLayout(top_row_layout)

        # --- Workflow Settings (moved here for better grouping) ---
        self.auto_confirm_return_checkbox = QCheckBox("ยืนยันการรับคืนสินค้าอัตโนมัติ")
        self.auto_confirm_return_checkbox.setToolTip("เมื่อเปิดใช้งาน, สินค้าที่ถูกส่งคืนจะเปลี่ยนสถานะเป็น 'พร้อมให้เช่า' ทันที\nโดยไม่ต้องให้ผู้ดูแลระบบกดยืนยันการรับคืนด้วยตนเอง")
        is_auto_confirm = self._get_setting('WORKFLOW', 'auto_confirm_return', fallback='False').lower() == 'true'
        self.auto_confirm_return_checkbox.setChecked(is_auto_confirm)
        ui_layout.addWidget(self.auto_confirm_return_checkbox)
        main_layout.addWidget(ui_group)
        # --- END FIX ---

        # --- Get shortcuts from config for dynamic labels ---
        console_shortcut_value = self._get_setting('SHORTCUTS', 'console', 'AsciiTilde')
        console_shortcut = "~" if console_shortcut_value == "AsciiTilde" else console_shortcut_value

        # --- NEW: Console Background Settings ---
        console_bg_group = QGroupBox(f"ตั้งค่าพื้นหลัง Console ({console_shortcut})")
        console_bg_layout = QFormLayout(console_bg_group)
        console_bg_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # File Path
        path_layout = QHBoxLayout()
        self.console_bg_path_input = QLineEdit(self._get_setting('CONSOLE_BACKGROUND', 'path', ''))
        self.console_bg_path_input.setPlaceholderText("ใช้ภาพพื้นหลังเริ่มต้น")
        browse_button = QPushButton("เลือกไฟล์...")
        browse_button.clicked.connect(self._select_console_bg_file)
        reset_button = QPushButton("คืนค่า")
        reset_button.clicked.connect(self._reset_console_bg_path)
        path_layout.addWidget(self.console_bg_path_input)
        path_layout.addWidget(browse_button)
        path_layout.addWidget(reset_button)
        console_bg_layout.addRow("ไฟล์ภาพพื้นหลัง:", path_layout)

        # --- NEW: Scale Slider ---
        scale_layout = QHBoxLayout()
        self.console_bg_scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.console_bg_scale_slider.setRange(10, 200) # 10% to 200%
        self.console_bg_scale_slider.setValue(int(self._get_setting('CONSOLE_BACKGROUND', 'scale', '100')))
        self.console_bg_scale_label = QLabel()
        self.console_bg_scale_slider.valueChanged.connect(self._update_console_scale_label)
        self._update_console_scale_label(self.console_bg_scale_slider.value())

        scale_layout.addWidget(self.console_bg_scale_slider)
        scale_layout.addWidget(self.console_bg_scale_label)
        console_bg_layout.addRow("ขนาดภาพพื้นหลัง (%):", scale_layout)

        # --- NEW: Image Opacity Slider ---
        image_opacity_layout = QHBoxLayout()
        self.console_bg_image_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.console_bg_image_opacity_slider.setRange(0, 255)
        self.console_bg_image_opacity_slider.setValue(int(self._get_setting('CONSOLE_BACKGROUND', 'image_opacity', '10')))
        self.console_bg_image_opacity_label = QLabel()
        self.console_bg_image_opacity_slider.valueChanged.connect(self._update_console_image_opacity_label)
        self._update_console_image_opacity_label(self.console_bg_image_opacity_slider.value())
        image_opacity_layout.addWidget(self.console_bg_image_opacity_slider)
        image_opacity_layout.addWidget(self.console_bg_image_opacity_label)
        console_bg_layout.addRow("ความโปร่งใสรูปภาพ:", image_opacity_layout)

        # Position ComboBox
        self.console_bg_position_combo = QComboBox()
        self.position_map = {
            "มุมล่างขวา": "bottom right",
            "ตรงกลาง": "center",
            "ยืดเต็มจอ": "stretch",
            "ปูกระเบื้อง": "tile",
            "มุมบนซ้าย": "top left",
            "มุมบนขวา": "top right",
            "มุมล่างซ้าย": "bottom left",
        }
        self.console_bg_position_combo.addItems(self.position_map.keys())

        # Load current setting
        current_pos_value = self._get_setting('CONSOLE_BACKGROUND', 'position', 'bottom right')
        current_repeat_value = self._get_setting('CONSOLE_BACKGROUND', 'repeat', 'no-repeat')
        current_display_name = "มุมล่างขวา" # Default
        if current_pos_value == 'stretch': current_display_name = "ยืดเต็มจอ"
        elif current_repeat_value == 'repeat': current_display_name = "ปูกระเบื้อง"
        else: # Find by position value
            current_display_name = next((k for k, v in self.position_map.items() if v == current_pos_value), "มุมล่างขวา")
        self.console_bg_position_combo.setCurrentText(current_display_name)
        console_bg_layout.addRow("ตำแหน่งภาพพื้นหลัง:", self.console_bg_position_combo)

        main_layout.addWidget(console_bg_group)
        # --- END NEW ---

        admin_local_shortcut_value = self._get_setting('SHORTCUTS', 'admin_local', 'F2')
        admin_local_shortcut = "~" if admin_local_shortcut_value == "AsciiTilde" else admin_local_shortcut_value
        # --- Admin Account Settings ---
        admin_group = QGroupBox(f"บัญชี Admin Console ({admin_local_shortcut})")
        admin_layout = QFormLayout(admin_group)
        admin_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.admin_username_input = QLineEdit(self._get_setting('END_ADMIN', 'id', fallback='admin'))
        self.admin_username_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        admin_layout.addRow("ชื่อผู้ใช้ (Username):", self.admin_username_input)

        self.admin_old_password_input = QLineEdit()
        self.admin_old_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.admin_old_password_input.setPlaceholderText("กรอกรหัสผ่านปัจจุบันเพื่อเปลี่ยน")
        admin_layout.addRow("รหัสผ่านปัจจุบัน:", self.admin_old_password_input)

        self.admin_password_input = QLineEdit()
        self.admin_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.admin_password_input.setPlaceholderText("เว้นว่างไว้หากไม่ต้องการเปลี่ยน")
        admin_layout.addRow("รหัสผ่านใหม่:", self.admin_password_input)

        self.admin_confirm_password_input = QLineEdit()
        self.admin_confirm_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.admin_confirm_password_input.setPlaceholderText("ยืนยันรหัสผ่านใหม่")
        admin_layout.addRow("ยืนยันรหัสผ่าน:", self.admin_confirm_password_input)
        main_layout.addWidget(admin_group)

        main_layout.addStretch()
        return widget

    def _create_shortcuts_tab(self):
        """Creates the tab for managing shortcut keys."""
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        main_layout.setSpacing(20)

        shortcut_group = QGroupBox("ตั้งค่าปุ่มลัด (Shortcut Keys)")
        shortcut_layout = QFormLayout(shortcut_group)
        shortcut_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # --- NEW: Map AsciiTilde to ~ for display ---
        shortcut_map = {
            'console': ("เปิด Console:", self._get_setting('SHORTCUTS', 'console', '~')),
            'about': ("เปิดหน้าข้อมูลโปรแกรม:", self._get_setting('SHORTCUTS', 'about', 'F1')),
            'admin_local': ("เปิด Admin Panel (Local):", self._get_setting('SHORTCUTS', 'admin_local', 'F2')),
            'admin_server': ("เปิด Admin Panel (Server):", self._get_setting('SHORTCUTS', 'admin_server', 'F3')),
            'fullscreen': ("สลับโหมดเต็มจอ:", self._get_setting('SHORTCUTS', 'fullscreen', 'F11')),
        }

        self.shortcut_inputs = {}
        for key, (label, value) in shortcut_map.items():
            line_edit = ShortcutLineEdit()
            # Display '~' if the stored value is 'AsciiTilde'
            display_value = "~" if value == "AsciiTilde" else value
            line_edit.setText(display_value)
            self.shortcut_inputs[key] = line_edit
            shortcut_layout.addRow(label, line_edit)
        main_layout.addWidget(shortcut_group)
        main_layout.addStretch()
        return widget

    def _create_connectivity_tab(self):
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        main_layout.setSpacing(20)

        # --- Local Database Settings ---
        local_db_group = QGroupBox("ฐานข้อมูล Local (SQLite)")
        local_db_layout = QVBoxLayout(local_db_group)
        
        db_form_layout = QFormLayout()
        db_form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.local_db_path_input = QLineEdit(self._get_setting('LOCAL_DATABASE', 'path', fallback=''))
        self.local_db_path_input.setReadOnly(True)
        db_form_layout.addRow("ตำแหน่งไฟล์:", self.local_db_path_input)
        local_db_layout.addLayout(db_form_layout)

        db_button_layout = QHBoxLayout()
        select_db_button = QPushButton("เลือกไฟล์...")
        select_db_button.clicked.connect(self._select_local_db_file)
        create_db_button = QPushButton("สร้างใหม่...")
        create_db_button.clicked.connect(self._create_new_local_db_file)
        db_button_layout.addStretch()
        db_button_layout.addWidget(select_db_button)
        db_button_layout.addWidget(create_db_button)
        local_db_layout.addLayout(db_button_layout)
        main_layout.addWidget(local_db_group)

        # --- Server DB Settings ---
        server_db_group = QGroupBox("ฐานข้อมูลเซิร์ฟเวอร์")
        # Use a QVBoxLayout to hold both the form and the test button
        server_db_main_layout = QVBoxLayout(server_db_group)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.db_type_combo = QComboBox()
        self.db_type_combo.addItems(["postgresql", "mysql"])
        self.db_type_combo.setCurrentText(self._get_setting('DATABASE', 'db_type', fallback='postgresql'))
        form_layout.addRow("ประเภทฐานข้อมูล:", self.db_type_combo)

        self.db_host_input = QLineEdit(self._get_setting('DATABASE', 'host', fallback='localhost'))
        form_layout.addRow("Host:", self.db_host_input)
        self.db_port_input = QLineEdit(self._get_setting('DATABASE', 'port', fallback='5432'))
        form_layout.addRow("Port:", self.db_port_input)
        self.db_dbname_input = QLineEdit(self._get_setting('DATABASE', 'database', fallback=''))
        form_layout.addRow("ชื่อฐานข้อมูล:", self.db_dbname_input)
        self.db_user_input = QLineEdit(self._get_setting('DATABASE', 'user', fallback=''))
        form_layout.addRow("ชื่อผู้ใช้:", self.db_user_input)
        self.db_password_input = QLineEdit(str(self._get_setting('DATABASE', 'password', fallback='')))
        self.db_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("รหัสผ่าน:", self.db_password_input)
        server_db_main_layout.addLayout(form_layout)

        # --- Test Connection Button ---
        test_button_layout = QHBoxLayout()
        test_db_button = QPushButton("ทดสอบการเชื่อมต่อเซิร์ฟเวอร์")
        test_db_button.clicked.connect(self.test_db_connection)
        test_button_layout.addStretch()
        test_button_layout.addWidget(test_db_button)
        server_db_main_layout.addLayout(test_button_layout)


        main_layout.addWidget(server_db_group)
        main_layout.addStretch()
        return widget

    def _create_payment_tab(self):
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
        """Creates the 'Auto' tab for ordering payment gateways."""
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
            if key in self.all_gateways: self.active_gateways_list.addItem(self.all_gateways[key])
        for key, name in self.all_gateways.items():
            if key not in active_keys: self.inactive_gateways_list.addItem(name)
        main_layout.addWidget(priority_group)
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
        promptpay_group = QGroupBox("ตั้งค่า PromptPay")
        promptpay_layout = QVBoxLayout(promptpay_group)
        promptpay_desc = QLabel("ใช้สำหรับสร้าง QR Code แบบ PromptPay ทั่วไป ไม่สามารถตรวจสอบสถานะการชำระเงินอัตโนมัติได้")
        promptpay_desc.setWordWrap(True) 
        promptpay_desc.setStyleSheet("margin-bottom: 2px; color: #6c757d;")
        promptpay_layout.addWidget(promptpay_desc)
        promptpay_form_layout = QFormLayout()
        promptpay_form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.promptpay_phone_input = QLineEdit(self._get_setting('PROMPTPAY', 'phone_number', fallback=''))
        self.promptpay_phone_input.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        promptpay_form_layout.addRow("เบอร์โทรศัพท์ PromptPay:", self.promptpay_phone_input)
        promptpay_layout.addLayout(promptpay_form_layout)
        main_layout.addWidget(promptpay_group)
        return widget

    def _create_scb_tab(self):
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
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
        scb_layout.addRow("SCB Biller Name:", self.scb_biller_name_input)
        self.scb_biller_id_input = QLineEdit(self._get_setting('SCB_API', 'biller_id', fallback=''))
        scb_layout.addRow("SCB Biller ID:", self.scb_biller_id_input)
        self.scb_api_key_input = QLineEdit(str(self._get_setting('SCB_API', 'api_key', fallback='')))
        scb_layout.addRow("SCB API Key:", self.scb_api_key_input)
        self.scb_api_secret_input = QLineEdit(str(self._get_setting('SCB_API', 'api_secret', fallback='')))
        self.scb_api_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        scb_layout.addRow("SCB API Secret:", self.scb_api_secret_input)
        self.scb_app_name_input = QLineEdit(self._get_setting('SCB_API', 'app_name', fallback=''))
        scb_layout.addRow("SCB App Name:", self.scb_app_name_input)
        self.scb_callback_url_input = QLineEdit(self._get_setting('SCB_API', 'callback_url', fallback=''))
        scb_layout.addRow("SCB Callback URL:", self.scb_callback_url_input)
        main_layout.addWidget(scb_group)

        # --- Test Connection Button for SCB ---
        scb_test_button_layout = QHBoxLayout()
        scb_test_button = QPushButton("ทดสอบการเชื่อมต่อ SCB")
        scb_test_button.clicked.connect(self.test_scb_connection)
        scb_test_button_layout.addStretch()
        scb_test_button_layout.addWidget(scb_test_button)
        # Add the button layout to the main form layout as a new row
        scb_layout.addRow(scb_test_button_layout)

        return widget

    def _create_ktb_tab(self):
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
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
        self.ktb_api_key_input = QLineEdit(str(self._get_setting('KTB_API', 'api_key', fallback='')))
        ktb_layout.addRow("KTB API Key (Client ID):", self.ktb_api_key_input)
        self.ktb_api_secret_input = QLineEdit(str(self._get_setting('KTB_API', 'api_secret', fallback='')))
        self.ktb_api_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
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
        slip_verify_group = QGroupBox("API ตรวจสอบสลิป")
        slip_verify_layout = QFormLayout(slip_verify_group)
        slip_verify_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.slip_api_url_input = QLineEdit(self._get_setting('SLIP_VERIFICATION', 'api_url', fallback=''))
        slip_verify_layout.addRow("API URL (อัปโหลดรูป):", self.slip_api_url_input)

        self.slip_qr_api_url_input = QLineEdit(self._get_setting('SLIP_VERIFICATION', 'qr_api_url', fallback=''))
        slip_verify_layout.addRow("API URL (สแกน QR):", self.slip_qr_api_url_input)
        self.slip_api_token_input = QLineEdit(str(self._get_setting('SLIP_VERIFICATION', 'api_token', fallback='')))
        self.slip_api_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        slip_verify_layout.addRow("API Token:", self.slip_api_token_input)
        self.slip_check_duplicate_checkbox = QCheckBox("ตรวจสอบสลิปซ้ำ (แนะนำให้เปิด)")
        check_duplicate_setting = self._get_setting('SLIP_VERIFICATION', 'check_duplicate', fallback='True')
        is_check_duplicate_enabled = str(check_duplicate_setting).lower() == 'true'
        self.slip_check_duplicate_checkbox.setChecked(is_check_duplicate_enabled)
        slip_verify_layout.addRow(self.slip_check_duplicate_checkbox)
        from PyQt6.QtWidgets import QTextEdit
        self.slip_receiver_conditions_input = QTextEdit(self._get_setting('SLIP_VERIFICATION', 'receiver_conditions', fallback=''))
        self.slip_receiver_conditions_input.setPlaceholderText('ใส่เงื่อนไขบัญชีผู้รับในรูปแบบ JSON Array\nเช่น [{"accountNumber": "1234567890"}, {"accountNameTH": "บริษัท มิกะ"}]')
        slip_verify_layout.addRow("เงื่อนไขบัญชีผู้รับ (JSON):", self.slip_receiver_conditions_input)
        main_layout.addWidget(slip_verify_group)

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

        slipok_qr_group = QGroupBox("SlipOK QR Generation")
        slipok_qr_layout = QFormLayout(slipok_qr_group)
        slipok_qr_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.slipok_qr_gen_enabled_checkbox = QCheckBox("เปิดใช้งานการสร้าง QR ผ่าน SlipOK API")
        is_slipok_qr_enabled = self._get_setting('SLIPOK_QR_GEN', 'enabled', fallback='False').lower() == 'true'
        self.slipok_qr_gen_enabled_checkbox.setChecked(is_slipok_qr_enabled)
        slipok_qr_layout.addRow(self.slipok_qr_gen_enabled_checkbox)
        self.slipok_merchant_id_input = QLineEdit(self._get_setting('SLIPOK_QR_GEN', 'merchant_id', fallback=''))
        slipok_qr_layout.addRow("Merchant ID:", self.slipok_merchant_id_input)
        self.slipok_qr_gen_url_input = QLineEdit(self._get_setting('SLIPOK_QR_GEN', 'api_url', fallback=''))
        slipok_qr_layout.addRow("API URL (สร้าง QR):", self.slipok_qr_gen_url_input)
        # --- NEW: Add the missing api_token field for QR generation ---
        self.slipok_qr_gen_api_token_input = QLineEdit(str(self._get_setting('SLIPOK_QR_GEN', 'api_token', fallback='')))
        self.slipok_qr_gen_api_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.slipok_qr_gen_api_token_input.setPlaceholderText("ใช้ Token เดียวกับส่วนตรวจสอบสลิปได้")
        slipok_qr_layout.addRow("API Token (สร้าง QR):", self.slipok_qr_gen_api_token_input)
        main_layout.addWidget(slipok_qr_group)
        return widget

    def test_slipok_qr_connection(self):
        """Attempts to authenticate with SlipOK API using the credentials from the form."""
        api_token = self.slip_api_token_input.text().strip()
        qr_api_url = self.slip_qr_api_url_input.text().strip()

        if not api_token or not qr_api_url:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ข้อมูลไม่ครบ", "กรุณากรอก API Token และ API URL (สแกน QR) ก่อนทำการทดสอบ")
            return

        class TempConfig:
            def get(self, section, key, fallback=None):
                if section == 'SLIP_VERIFICATION':
                    if key == 'api_token':
                        return api_token
                    if key == 'qr_api_url':
                        return qr_api_url
                return fallback

        handler = SlipOKApiHandler(debug=True, config_source=TempConfig())
        result_message = handler.test_authentication()
        CustomMessageBox.show(self, CustomMessageBox.Information, "ผลการทดสอบ SlipOK", result_message)

    def test_slipok_image_connection(self):
        """Tests the SlipOK image upload endpoint."""
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


    def _create_devices_tab(self):
        widget = QWidget()
        main_layout = QVBoxLayout(widget) # Main layout for the tab
        main_layout.setSpacing(20)

        # --- Camera Settings Group ---
        camera_group = QGroupBox("ตั้งค่ากล้อง Webcam")
        camera_group_layout = QVBoxLayout(camera_group) # Use QVBoxLayout for more control

        form_layout = QFormLayout() # Form for the settings
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # --- Camera Index Selection ---
        camera_selection_layout = QHBoxLayout()
        self.camera_device_combo = QComboBox()
        self.camera_device_combo.setMinimumWidth(INPUT_FIELD_MIN_WIDTH - 120) # Adjust width
        camera_selection_layout.addWidget(self.camera_device_combo)
        scan_button = QPushButton("สแกนหากล้อง")
        scan_button.clicked.connect(self.scan_for_cameras)
        camera_selection_layout.addWidget(scan_button)
        camera_selection_layout.addStretch()
        form_layout.addRow("เลือก Camera Index:", camera_selection_layout)

        # --- Resolution Setting ---
        self.camera_resolution_combo = QComboBox()
        self.camera_resolution_combo.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        resolutions = ["640x480", "800x600", "1280x720", "1920x1080"]
        self.camera_resolution_combo.addItems(resolutions)
        self.camera_resolution_combo.setEditable(True) # Allow custom resolutions
        self.camera_resolution_combo.setCurrentText(self._get_setting('CAMERA', 'resolution', fallback='1280x720'))
        form_layout.addRow("ความละเอียด (Resolution):", self.camera_resolution_combo)

        # --- FPS Setting ---
        self.camera_fps_combo = QComboBox()
        self.camera_fps_combo.setMinimumWidth(INPUT_FIELD_MIN_WIDTH)
        fps_options = ["15", "30", "60"]
        self.camera_fps_combo.addItems(fps_options)
        self.camera_fps_combo.setEditable(True) # Allow custom FPS
        self.camera_fps_combo.setCurrentText(self._get_setting('CAMERA', 'fps', fallback='30'))
        form_layout.addRow("FPS:", self.camera_fps_combo)

        camera_group_layout.addLayout(form_layout)

        # --- Test Camera Button ---
        test_camera_layout = QHBoxLayout()
        test_camera_button = QPushButton("ทดสอบกล้องที่เลือก")
        test_camera_button.clicked.connect(self.test_selected_camera)
        test_camera_layout.addStretch()
        test_camera_layout.addWidget(test_camera_button)
        camera_group_layout.addLayout(test_camera_layout)

        main_layout.addWidget(camera_group)
        main_layout.addStretch()

        # Initial population of the camera list on first creation
        self.populate_camera_list()

        return widget

    def populate_camera_list(self, available_indices=None):
        """Populates the camera dropdown list."""
        self.camera_device_combo.clear()
        if available_indices:
            for i in available_indices:
                self.camera_device_combo.addItem(f"Camera {i}", userData=i)
        else:
            # Default list if no scan has been performed
            for i in range(10):
                self.camera_device_combo.addItem(f"Camera {i}", userData=i)
        current_index = int(self._get_setting('CAMERA', 'device_index', fallback=0))
        combo_index = self.camera_device_combo.findData(current_index)
        if combo_index != -1:
            self.camera_device_combo.setCurrentIndex(combo_index)

    def _create_smtp_tab(self):
        """Populates the content of the SMTP settings tab for local config."""
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
        self.smtp_password_input = QLineEdit(str(self._get_setting('SMTP', 'password', fallback='')))
        self.smtp_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("รหัสผ่าน (App Password):", self.smtp_password_input)
        smtp_layout.addLayout(form_layout)

        # --- Test SMTP Button ---
        test_button_layout = QHBoxLayout()
        test_button = QPushButton("ทดสอบการส่งอีเมล")
        test_button.clicked.connect(self.test_smtp_connection)
        test_button_layout.addStretch()
        test_button_layout.addWidget(test_button)
        smtp_layout.addLayout(test_button_layout)

        main_layout.addWidget(smtp_group)
        return widget

    def _create_about_tab(self):
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        main_layout.setSpacing(15)
        icon_label = QLabel()
        app_icon = get_icon("app_image/icon.ico")
        icon_label.setPixmap(app_icon.pixmap(QSize(250, 250)))
        main_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignCenter)
        app_name_label = QLabel("MiKA RENTAL")
        app_name_label.setStyleSheet("font-size: 24pt; font-weight: bold;")
        main_layout.addWidget(app_name_label, 0, Qt.AlignmentFlag.AlignCenter)
        try:
            version = importlib.metadata.version('Mika-Rental')
            version_text = f"Version {version}"
        except importlib.metadata.PackageNotFoundError:
            version_text = "Version 0.1.0"
        version_label = QLabel(version_text)
        version_label.setStyleSheet("font-size: 10pt; color: #888;")
        main_layout.addWidget(version_label, 0, Qt.AlignmentFlag.AlignCenter)
        main_layout.addSpacing(20)

        # --- Creator ---
        try:
            meta = importlib.metadata.metadata('Mika-Rental')
            authors = meta.get_all('Author')
            creator_text = ', '.join(authors) if authors else "NiVARA"
        except importlib.metadata.PackageNotFoundError:
            creator_text = "NiRU, MiKA" # Fallback for development mode
        creator_label = QLabel(creator_text)
        creator_label.setStyleSheet("font-size: 11pt; font-weight: bold;")
        main_layout.addWidget(creator_label, 0, Qt.AlignmentFlag.AlignCenter)
        status_group = QGroupBox("สถานะโปรแกรม")
        status_group_layout = QVBoxLayout(status_group)
        status_group_layout.setSpacing(8)
        mode_text = "<b>โหมด Local</b>"
        mode_label = QLabel(f"สถานะการทำงาน: {mode_text}")
        mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_group_layout.addWidget(mode_label)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        status_group_layout.addWidget(line)
        item_summary_layout = QHBoxLayout()
        item_summary_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        item_summary_layout.setSpacing(20)
        summary = {}
        try:
            from app_db.db_management import get_db_instance
            local_db_instance = get_db_instance(is_remote=False)
            if local_db_instance and local_db_instance.conn:
                summary = local_db_instance.get_item_status_summary()
        except Exception as e:
            print(f"Could not get item summary for local about tab: {e}")
        status_map = {'available': 'พร้อมให้เช่า', 'rented': 'กำลังถูกเช่า', 'pending_return': 'รอการยืนยันคืน', 'suspended': 'ระงับใช้งาน'}
        for status, display_text in status_map.items():
            count = summary.get(status, 0)
            item_label = QLabel(f"{display_text}: <b>{count}</b>")
            item_summary_layout.addWidget(item_label)
        status_group_layout.addLayout(item_summary_layout)
        main_layout.addWidget(status_group)
        main_layout.addStretch(1)

        # --- NEW: Shortcut Info ---
        shortcut_group = QGroupBox("ปุ่มลัด (Shortcuts)")
        shortcut_layout = QFormLayout(shortcut_group)
        shortcut_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        shortcuts_to_display = {
            "เปิด Console": self._get_setting('SHORTCUTS', 'console', '~'),
            "เปิดหน้าข้อมูลโปรแกรม": self._get_setting('SHORTCUTS', 'about', 'F1'),
            "เปิด Admin Panel (Local)": self._get_setting('SHORTCUTS', 'admin_local', 'F2'),
            "เปิด Admin Panel (Server)": self._get_setting('SHORTCUTS', 'admin_server', 'F3'),
            "สลับโหมดเต็มจอ": self._get_setting('SHORTCUTS', 'fullscreen', 'F11'),
        }
        for desc, key in shortcuts_to_display.items():
            # Display '~' if the stored value is 'AsciiTilde'
            display_key = "~" if key == "AsciiTilde" else key
            shortcut_layout.addRow(f"<b>{display_key}</b>:", QLabel(desc))
        main_layout.addWidget(shortcut_group)

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

        handler = SCBApiHandler(debug=True, config_source=TempConfig())
        result_message = handler.test_authentication()
        
        if "Successful" in result_message:
            CustomMessageBox.show(self, CustomMessageBox.Information, "ผลการทดสอบ SCB", result_message)
        else:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ผลการทดสอบ SCB", result_message)

    def test_ktb_connection(self):
        """Attempts to authenticate with KTB API using the credentials from the form."""
        from app_payment.ktb_api_handler import KTBApiHandler # Local import
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
        success, message = PaymentHandler.send_test_email(TempConfig())
        icon = CustomMessageBox.Information if success else CustomMessageBox.Warning
        CustomMessageBox.show(self, icon, "ผลการทดสอบ SMTP", message)

    def test_db_connection(self):
        """
        Attempts to connect to the remote database using the settings currently
        entered in the form, without saving them first.
        """
        # Create a temporary, in-memory config object for the test
        class TempConfig:
            def __init__(self_inner):
                self_inner.data = {
                    'DATABASE': {
                        'db_type': self.db_type_combo.currentText(),
                        'host': self.db_host_input.text(),
                        'port': self.db_port_input.text(),
                        'database': self.db_dbname_input.text(),
                        'user': self.db_user_input.text(),
                        'password': self.db_password_input.text()
                    }
                }
            def get(self_inner, section, key, fallback=None):
                return self_inner.data.get(section, {}).get(key, fallback)
            def getint(self_inner, section, key, fallback=None):
                val = self_inner.get(section, key, fallback)
                try:
                    return int(val)
                except (ValueError, TypeError):
                    return fallback

        test_config = TempConfig()

        try:
            from app_db.db_management import DBManagement
            test_db = DBManagement()
            test_db._connect_remote(config_object=test_config)
            test_db.close_connection()
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "เชื่อมต่อฐานข้อมูลเซิร์ฟเวอร์สำเร็จ!")
        except Exception as e:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "เชื่อมต่อล้มเหลว", f"ไม่สามารถเชื่อมต่อฐานข้อมูลได้:\n{e}")

    def scan_for_cameras(self):
        """Scans for available cameras and updates the dropdown."""
        if not self.main_window_ref:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ผิดพลาด", "ไม่สามารถสแกนหากล้องได้ในโหมดนี้")
            return
        
        CustomMessageBox.show(self, CustomMessageBox.Information, "กำลังสแกน...", "กำลังค้นหากล้องที่เชื่อมต่ออยู่ กรุณารอสักครู่...")
        available_cameras = self.main_window_ref.find_available_cameras()
        self.populate_camera_list(available_indices=available_cameras)
        CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", f"พบกล้อง {len(available_cameras)} ตัว")

    def test_selected_camera(self):
        """Opens the camera capture dialog to test the selected camera."""
        from app_payment.camera_capture_dialog import CameraCaptureDialog
        
        selected_index = self.camera_device_combo.currentData()
        # Temporarily update config so the dialog uses the correct index
        self.config.update_config('CAMERA', 'device_index', str(selected_index))
        
        dialog = CameraCaptureDialog(self)
        try:
            dialog.exec()
        finally:
            # Ensure the camera is released even if the dialog crashes or is closed.
            dialog.release_camera()

    def _select_local_db_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "เลือกไฟล์ฐานข้อมูล SQLite", os.path.dirname(self.local_db_path_input.text()), "Database Files (*.db *.sqlite *.sqlite3)")
        if file_name:
            # --- FIX: Immediately save and re-initialize when a new file is selected ---
            try:
                # 1. Update UI
                self.local_db_path_input.setText(file_name)
                
                # 2. Save new path to config
                self.config.update_config('LOCAL_DATABASE', 'path', file_name.replace('\\', '/'))
                
                # 3. Re-initialize the database connection
                new_instance = db_manager.create_and_initialize_local_db()
                if new_instance and self.main_window_ref:
                    # Refresh main window items
                    self.main_window_ref.load_items()
                    # If a local admin panel is open, tell it to use the new instance
                    if self.main_window_ref.local_admin_panel and self.main_window_ref.local_admin_panel.isVisible():
                        self.main_window_ref.local_admin_panel.reinitialize_db_instance(new_instance)
                
                CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", f"เลือกใช้ฐานข้อมูล:\n{file_name}\nเรียบร้อยแล้ว")
            except Exception as e:
                CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", f"ไม่สามารถเริ่มต้นการเชื่อมต่อฐานข้อมูลใหม่ได้: {e}")

    def _create_new_local_db_file(self):
        """Opens a dialog to create a new SQLite DB file, saves the path, and initializes it."""
        file_name, _ = QFileDialog.getSaveFileName(self, "สร้างไฟล์ฐานข้อมูล SQLite ใหม่", os.path.dirname(self.local_db_path_input.text()), "Database Files (*.db)")
        if file_name:
            if not file_name.endswith('.db'):
                file_name += '.db'
            
            # --- FIX: Immediately save the new path and re-initialize the database ---
            try:
                # 1. Update the UI
                self.local_db_path_input.setText(file_name)
                
                # 2. Save the new path to the config file
                self.config.update_config('LOCAL_DATABASE', 'path', file_name.replace('\\', '/'))
                
                # 3. Re-initialize the database connections. This will create the new file and tables.
                db_manager.create_and_initialize_local_db()
                
                CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", f"สร้างและเลือกใช้ฐานข้อมูลใหม่ที่:\n{file_name}\nเรียบร้อยแล้ว")

            except Exception as e:
                CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", f"ไม่สามารถสร้างหรือเริ่มต้นฐานข้อมูลใหม่ได้: {e}")

    def _save_current_tab_settings(self):
        """Saves the settings for the currently active tab."""
        current_index = self.tab_widget.currentIndex()
        current_tab_name = self.tab_widget.tabText(current_index)

        save_actions = {
            "ทั่วไป": self._save_general_settings,
            "ปุ่มลัด": self._save_shortcuts_settings,
            "การเชื่อมต่อ": self._save_connectivity_settings,
            "การชำระเงิน": self._save_payment_settings_to_config,
            "การส่งอีเมล (SMTP)": self._save_smtp_settings,
            "อุปกรณ์": self._save_devices_settings,
        }

        save_function = save_actions.get(current_tab_name)
        if save_function:
            save_function()

    def _save_general_settings(self):
        """Saves only the settings from the General & Account tab."""
        try:
            # --- Save Admin Settings ---
            new_username = sanitize_input(self.admin_username_input.text().strip())
            if not new_username:
                CustomMessageBox.show(self, CustomMessageBox.Warning, "ข้อมูลไม่ครบ", "กรุณากรอกชื่อผู้ใช้ Admin")
                return
    
            new_password = self.admin_password_input.text()
            if new_password:
                # --- NEW: Require old password to change password ---
                current_password = self.config.get('END_ADMIN', 'password', fallback='')
                old_password_entered = self.admin_old_password_input.text()
                if current_password and old_password_entered != current_password:
                    raise ValueError("รหัสผ่านปัจจุบันของ Admin Console ไม่ถูกต้อง")
                if new_password != self.admin_confirm_password_input.text():
                    CustomMessageBox.show(self, CustomMessageBox.Warning, "รหัสผ่านไม่ตรงกัน", "กรุณากรอกรหัสผ่านใหม่ของ Admin ให้ตรงกัน")
                    return
                self.config.update_config('END_ADMIN', 'password', new_password)
            
            self.config.update_config('END_ADMIN', 'id', new_username)

            # --- NEW: Save Console Background Settings ---
            self.config.update_config('CONSOLE_BACKGROUND', 'path', self.console_bg_path_input.text().strip())
            self.config.update_config('CONSOLE_BACKGROUND', 'image_opacity', str(self.console_bg_image_opacity_slider.value()))
            self.config.update_config('CONSOLE_BACKGROUND', 'scale', str(self.console_bg_scale_slider.value()))
            
            # --- NEW: Save Console Background Position ---
            selected_display_name = self.console_bg_position_combo.currentText()
            position_value = self.position_map.get(selected_display_name, 'bottom right')
            
            if position_value == 'stretch':
                self.config.update_config('CONSOLE_BACKGROUND', 'position', 'center') # Position doesn't matter
                self.config.update_config('CONSOLE_BACKGROUND', 'repeat', 'no-repeat')
            elif position_value == 'tile':
                self.config.update_config('CONSOLE_BACKGROUND', 'position', 'top left') # Tiling starts from top-left
                self.config.update_config('CONSOLE_BACKGROUND', 'repeat', 'repeat')
            else: # For all other positions like 'center', 'bottom right', etc.
                self.config.update_config('CONSOLE_BACKGROUND', 'position', position_value)
                self.config.update_config('CONSOLE_BACKGROUND', 'repeat', 'no-repeat')
            self.config.update_config('WORKFLOW', 'auto_confirm_return', str(self.auto_confirm_return_checkbox.isChecked()))


            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "บันทึกการตั้งค่าทั่วไปและบัญชีเรียบร้อยแล้ว")
    
        except Exception as e:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", f"ไม่สามารถบันทึกการตั้งค่าทั่วไปได้:\n{e}")

    def _save_connectivity_settings(self):
        """Saves only the settings from the Connectivity tab."""
        try:
            # --- Save Local DB Path ---
            old_local_db_path = self._get_setting('LOCAL_DATABASE', 'path', fallback='')
            new_local_db_path = sanitize_input(self.local_db_path_input.text().strip().replace('\\', '/'))
            self.config.update_config('LOCAL_DATABASE', 'path', new_local_db_path)
            # --- Save Server DB Settings ---
            self.config.update_config('DATABASE', 'enabled', str(self.db_mode_button.isChecked()))
            self.config.update_config('DATABASE', 'db_type', self.db_type_combo.currentText())
            self.config.update_config('DATABASE', 'host', sanitize_input(self.db_host_input.text()))
            self.config.update_config('DATABASE', 'port', sanitize_input(self.db_port_input.text()))
            self.config.update_config('DATABASE', 'database', sanitize_input(self.db_dbname_input.text()))
            self.config.update_config('DATABASE', 'user', sanitize_input(self.db_user_input.text()))
            self.config.update_config('DATABASE', 'password', self.db_password_input.text())
    
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "บันทึกการตั้งค่าการเชื่อมต่อเรียบร้อยแล้ว")
    
            # Re-initialize databases after saving settings
            if self.main_window_ref:
                db_path_has_changed = new_local_db_path and (new_local_db_path != old_local_db_path)
                
                # This block now only runs if the user MANUALLY typed a new path into the QLineEdit
                # and then clicked save. The "Select File" and "Create New" buttons handle
                # re-initialization themselves.
                if db_path_has_changed:
                    new_instance = db_manager.create_and_initialize_local_db()
                    if new_instance:
                        # If a local admin panel is open, tell it to use the new instance
                        if self.main_window_ref.local_admin_panel and self.main_window_ref.local_admin_panel.isVisible():
                            self.main_window_ref.local_admin_panel.reinitialize_db_instance(new_instance)
                        # Also refresh the main window items
                        self.main_window_ref.load_items()
                else:
                    # If the path hasn't changed, just switch the mode if necessary.
                    # The main window will handle refreshing items if the mode changes. This is now handled by the toggle button itself.
                    pass
    
        except Exception as e:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", f"ไม่สามารถบันทึกการตั้งค่าการเชื่อมต่อได้: {e}")

    def _save_payment_settings_to_config(self):
        """Helper method to contain the payment saving logic."""
        # Save the primary gateway choice
        selected_gateway_text = self.payment_gateway_combo.currentText()
        gateway_value = self.gateway_map.get(selected_gateway_text, 'auto')
        self.config.update_config('PAYMENT', 'primary_gateway', gateway_value)

        # Save the priority order (this is now separate)
        active_gateways = []
        for i in range(self.active_gateways_list.count()):
            item_name = self.active_gateways_list.item(i).text()
            key = self._get_key_from_name(item_name)
            if key: active_gateways.append(key)
        self.config.update_config('PAYMENT', 'gateway_priority', ",".join(active_gateways))

        self.config.update_config('PROMPTPAY', 'phone_number', sanitize_input(self.promptpay_phone_input.text().strip()))
        self.config.update_config('SCB_API', 'biller_id', sanitize_input(self.scb_biller_id_input.text().strip()))
        self.config.update_config('SCB_API', 'sandbox_enabled', str(self.scb_sandbox_checkbox.isChecked()))
        self.config.update_config('SCB_API', 'biller_name', sanitize_input(self.scb_biller_name_input.text().strip()))
        self.config.update_config('SCB_API', 'app_name', sanitize_input(self.scb_app_name_input.text().strip()))
        self.config.update_config('SCB_API', 'callback_url', sanitize_input(self.scb_callback_url_input.text().strip()))
        self.config.update_config('SCB_API', 'api_key', sanitize_input(self.scb_api_key_input.text().strip()))
        self.config.update_config('SCB_API', 'api_secret', self.scb_api_secret_input.text().strip())
        self.config.update_config('KTB_API', 'sandbox_enabled', str(self.ktb_sandbox_checkbox.isChecked()))
        self.config.update_config('KTB_API', 'api_key', sanitize_input(self.ktb_api_key_input.text().strip()))
        self.config.update_config('KTB_API', 'api_secret', self.ktb_api_secret_input.text().strip())
        self.config.update_config('SLIP_VERIFICATION', 'api_url', sanitize_input(self.slip_api_url_input.text().strip()))
        self.config.update_config('SLIP_VERIFICATION', 'qr_api_url', sanitize_input(self.slip_qr_api_url_input.text().strip()))
        self.config.update_config('SLIP_VERIFICATION', 'api_token', self.slip_api_token_input.text().strip())
        self.config.update_config('SLIP_VERIFICATION', 'receiver_conditions', sanitize_input(self.slip_receiver_conditions_input.toPlainText().strip()))
        self.config.update_config('SLIP_VERIFICATION', 'check_duplicate', str(self.slip_check_duplicate_checkbox.isChecked()))
        self.config.update_config('SLIPOK_QR_GEN', 'enabled', str(self.slipok_qr_gen_enabled_checkbox.isChecked()))
        self.config.update_config('SLIPOK_QR_GEN', 'merchant_id', sanitize_input(self.slipok_merchant_id_input.text().strip()))
        self.config.update_config('SLIPOK_QR_GEN', 'api_url', sanitize_input(self.slipok_qr_gen_url_input.text().strip()))
        self.config.update_config('SLIPOK_QR_GEN', 'api_token', self.slipok_qr_gen_api_token_input.text().strip())
        CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "บันทึกการตั้งค่าการชำระเงินเรียบร้อยแล้ว")

    def _save_devices_settings(self):
        """Saves only the settings from the Devices tab."""
        try:
            selected_camera_index = self.camera_device_combo.currentData()
            self.config.update_config('CAMERA', 'resolution', self.camera_resolution_combo.currentText())
            self.config.update_config('CAMERA', 'fps', self.camera_fps_combo.currentText())
            self.config.update_config('CAMERA', 'device_index', str(selected_camera_index))
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "บันทึกการตั้งค่าอุปกรณ์เรียบร้อยแล้ว")
        except Exception as e:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", f"ไม่สามารถบันทึกการตั้งค่าอุปกรณ์ได้: {e}")

    def _save_shortcuts_settings(self):
        """Saves only the settings from the Shortcuts tab."""
        try:
            for key, line_edit in self.shortcut_inputs.items():
                value_to_save = line_edit.text()
                # --- NEW: Convert user-friendly '~' back to 'AsciiTilde' for storage ---
                if value_to_save == "~":
                    value_to_save = "AsciiTilde"
                self.config.update_config('SHORTCUTS', key, value_to_save)
            
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "บันทึกการตั้งค่าปุ่มลัดเรียบร้อยแล้ว")
            # Inform the user that a restart might be needed for some shortcuts to take full effect everywhere.
            CustomMessageBox.show(self, CustomMessageBox.Information, "แจ้งเตือน", "ปุ่มลัดจะมีผลทันที แต่อาจต้องรีสตาร์ทโปรแกรมเพื่อให้คำอธิบายในบางหน้าจออัปเดตตาม")

        except Exception as e:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", f"ไม่สามารถบันทึกการตั้งค่าปุ่มลัดได้: {e}")

    def _save_smtp_settings(self):
        """Saves only the settings from the SMTP tab."""
        try:
            self.config.update_config('SMTP', 'enabled', str(self.smtp_enable_checkbox.isChecked()))
            self.config.update_config('SMTP', 'host', sanitize_input(self.smtp_host_input.text().strip()))
            self.config.update_config('SMTP', 'port', sanitize_input(self.smtp_port_input.text().strip()))
            self.config.update_config('SMTP', 'user', sanitize_input(self.smtp_user_input.text().strip()))
            self.config.update_config('SMTP', 'password', self.smtp_password_input.text().strip())
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "บันทึกการตั้งค่า SMTP เรียบร้อยแล้ว")
        except Exception as e:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", f"ไม่สามารถบันทึกการตั้งค่า SMTP ได้: {e}")

    def _update_auto_logout_label(self, value):
        """Updates the label for the auto-logout slider."""
        if value == 0:
            self.auto_logout_label.setText("<b>ปิดใช้งาน</b>")
        else:
            self.auto_logout_label.setText(f"<b>{value}</b> นาที")

    def _select_console_bg_file(self):
        """Opens a file dialog to select a background image for the console."""
        file_name, _ = QFileDialog.getOpenFileName(self, "เลือกไฟล์ภาพพื้นหลัง", "", "Image Files (*.png *.jpg *.jpeg *.bmp)")
        if file_name:
            self.console_bg_path_input.setText(file_name.replace('\\', '/'))

    def _update_console_scale_label(self, value):
        """Updates the label for the console background scale slider."""
        self.console_bg_scale_label.setText(f"<b>{value}</b> %")

    def _update_console_image_opacity_label(self, value):
        """Updates the label for the console background image opacity slider."""
        self.console_bg_image_opacity_label.setText(f"<b>{value}</b> / 255")

    def _reset_console_bg_path(self):
        """Clears the console background image path input."""
        self.console_bg_path_input.clear()

    def _on_tab_changed(self, index):
        """Updates the save button text and visibility when the tab changes."""
        self.adjustSize()
        tab_text = self.tab_widget.tabText(index)

        button_texts = {
            "ทั่วไป": "บันทึกการตั้งค่าทั่วไป",
            "ปุ่มลัด": "บันทึกการตั้งค่าปุ่มลัด",
            "การเชื่อมต่อ": "บันทึกการตั้งค่าการเชื่อมต่อ",
            "การชำระเงิน": "บันทึกการตั้งค่าการชำระเงิน",
            "การส่งอีเมล (SMTP)": "บันทึกการตั้งค่า SMTP",
            "อุปกรณ์": "บันทึกการตั้งค่าอุปกรณ์",
        }

        if tab_text in button_texts:
            self.save_button.setText(button_texts[tab_text])
            self.save_button.show()
        else: # For "About" or other non-saving tabs
            self.save_button.hide()
        
        self._update_db_mode_button_ui()
        self._update_theme_button_ui()
    def _toggle_theme(self):
        """Handles the click of the theme switch button."""
        is_dark_mode = self.theme_button.isChecked()
        new_theme = "dark" if is_dark_mode else "light"
        
        # Save the new theme to the config file immediately
        self.config.update_config('UI', 'theme', new_theme)

        # Live update if possible
        if self.main_window_ref and self.main_window_ref.current_theme != new_theme:
            self.main_window_ref.current_theme = new_theme
            theme.apply_theme(self.main_window_ref.app, new_theme)
            self.main_window_ref.update_theme_dependent_widgets()
        
        # Update the button's own UI
        self._update_theme_button_ui()

    def _update_theme_button_ui(self):
        """Updates the appearance and text of the theme switch button."""
        # Read the theme directly from the config object to get the latest value
        # after it has been potentially updated by _toggle_theme.
        is_dark_mode = self.config.get('UI', 'theme', fallback='light') == 'dark'
        
        self.theme_button.setChecked(is_dark_mode)
        
        if is_dark_mode:
            self.theme_button.setText("Dark")
            self.theme_button.setStyleSheet("background-color: #5a5a5a; color: white; font-weight: bold; border-radius: 14px; padding: 5px 20px; min-width: 80px; max-width: 80px;")
        else:
            self.theme_button.setText("Light")
            self.theme_button.setStyleSheet("background-color: #e0e0e0; color: black; font-weight: bold; border-radius: 14px; padding: 5px 20px; min-width: 80px; max-width: 80px;")

    def _toggle_db_mode(self):
        """Handles the click of the mode switch button."""
        use_server = self.db_mode_button.isChecked()
        
        # If the main window reference exists, use its switch method for a live update
        if self.main_window_ref:
            success, message = self.main_window_ref.switch_database_mode(use_server)
            # Update the button style to reflect the actual final state
            self._update_db_mode_button_ui()
        else:
            # Fallback for standalone mode (e.g., admin_tool.py)
            # Just save the config and update the UI of this dialog
            self.config.update_config('DATABASE', 'enabled', str(use_server))
            self._update_db_mode_button_ui()
            CustomMessageBox.show(self, CustomMessageBox.Information, "บันทึกแล้ว", f"เปลี่ยนโหมดเป็น {'Server' if use_server else 'Local'} แล้ว\nกรุณารีสตาร์ทโปรแกรมเพื่อให้การเปลี่ยนแปลงมีผล")

    def _update_db_mode_button_ui(self):
        """Updates the appearance and text of the mode switch button and toggles server settings visibility."""
        is_server_mode = self.config.get('DATABASE', 'enabled', fallback='False').lower() == 'true' # Read from config
        self.db_mode_button.setChecked(is_server_mode)
        self.db_mode_button.setChecked(is_server_mode)
        
        if is_server_mode:
            self.db_mode_button.setText("Server")
            self.db_mode_button.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; border-radius: 14px; padding: 5px 20px; min-width: 80px; max-width: 80px;")
        else:
            self.db_mode_button.setText("Local")
            self.db_mode_button.setStyleSheet("background-color: #3498db; color: white; font-weight: bold; border-radius: 14px; padding: 5px 20px; min-width: 80px; max-width: 80px;")
        
        # Refresh the payment tab to show/hide the "Use Server Settings" option
        is_server_enabled = is_server_mode
        if hasattr(self, 'payment_gateway_combo') and is_server_enabled:
            if self.payment_gateway_combo.findText("ใช้การตั้งค่าจากเซิร์ฟเวอร์") == -1:
                 self.gateway_map["ใช้การตั้งค่าจากเซิร์ฟเวอร์"] = "server"
                 self.payment_gateway_combo.addItem("ใช้การตั้งค่าจากเซิร์ฟเวอร์")
        else:
            index = self.payment_gateway_combo.findText("ใช้การตั้งค่าจากเซิร์ฟเวอร์")
            if index != -1:
                self.payment_gateway_combo.removeItem(index)