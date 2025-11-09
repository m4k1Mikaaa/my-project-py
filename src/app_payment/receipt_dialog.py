from PyQt6.QtWidgets import (
    QVBoxLayout, QFormLayout, QLabel, QPushButton, QFrame, QWidget, QHBoxLayout, QApplication, QGroupBox,
    QMenu
)
from app.base_dialog import BaseDialog
from theme import PALETTES
from app_config import app_config
from PyQt6.QtCore import QDateTime, Qt, QTimer
import json
import qtawesome as qta
from app.custom_message_box import CustomMessageBox
from app_db.db_management import get_db_instance

class ReceiptDialog(BaseDialog):
    def __init__(self, history_id, parent=None, db_instance=None, is_admin_view=False):
        super().__init__(parent)
        self.history_id = history_id
        # Use the passed db_instance. It's crucial that the caller provides the correct one.
        self.db_instance = db_instance if db_instance else get_db_instance()
        self.setWindowTitle("รายละเอียดใบเสร็จ")
        self.setMinimumWidth(450)

        self.is_admin_view = is_admin_view
        # Fetch data
        self.history_record = self.db_instance.get_history_record_by_id(self.history_id)
        if not self.history_record:
            self.close() # Should not happen if called correctly
            return
            
        self.user_data = self.db_instance.get_user_by_id(self.history_record['user_id'])
        self.item_data = self.db_instance.get_item_by_id(self.history_record['item_id'])

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("ใบเสร็จ")
        header_label.setStyleSheet("font-size: 16pt; font-weight: bold;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        # --- NEW: Admin Menu Button ---
        if self.is_admin_view:
            self._create_admin_menu_button(header_layout)

        layout.addLayout(header_layout)

        # Details
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        form_layout.setContentsMargins(10, 10, 10, 10)

        # --- Get formatted data ---
        item_name = self.item_data.get('name', 'N/A') if self.item_data else 'N/A'
        user_name = f"{self.user_data.get('first_name', '')} {self.user_data.get('last_name', '')}".strip() if self.user_data else 'N/A'
        payment_date = self.format_datetime(self.history_record.get('payment_date'), "ยังไม่ชำระ")
        transaction_ref = self.history_record.get('transaction_ref', '-')
        amount_due = self.history_record.get('amount_due', 0.0)
        status = self.history_record.get('payment_status', 'N/A')
        slip_data_json = self.history_record.get('slip_data_json')
        slip_data = {}
        if slip_data_json:
            try:
                slip_data = json.loads(slip_data_json)
            except json.JSONDecodeError:
                print(f"Could not parse slip_data_json for history_id {self.history_id}")

        status_map = {
            'paid': 'ชำระแล้ว',
            'waived': 'ยกเว้นค่าบริการ',
            'pending': 'ค้างชำระ'
        }
        status_text = status_map.get(status, status.capitalize())

        # --- Add rows to form ---
        form_layout.addRow("<b>รายการ:</b>", QLabel(item_name))
        form_layout.addRow("<b>สำหรับคุณ:</b>", QLabel(user_name))
        form_layout.addRow("<b>วันที่ชำระเงิน:</b>", QLabel(payment_date))

        # --- Transaction Ref with Copy Button ---
        ref_container = QWidget()
        ref_layout = QHBoxLayout(ref_container)
        ref_layout.setContentsMargins(0, 0, 0, 0)
        ref_layout.setSpacing(10)
        ref_label = QLabel(transaction_ref)
        ref_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # --- FIX: Use the correct config source (the db_instance) to get the theme ---
        config_source = self.db_instance
        current_theme_name = config_source.get('UI', 'theme', fallback='light') or 'light'
        icon_color = PALETTES[current_theme_name].get('text', '#000000')

        self.copy_button = QPushButton(qta.icon('fa5s.copy', color=icon_color), "")
        self.copy_button.setObjectName("IconButton") # ใช้สไตล์เดียวกับปุ่มไอคอนอื่นๆ
        self.copy_button.setFixedSize(28, 28)
        self.copy_button.setToolTip("คัดลอกรหัสอ้างอิง")
        self.copy_button.clicked.connect(self.copy_transaction_ref)
        ref_layout.addWidget(ref_label)
        ref_layout.addWidget(self.copy_button)
        ref_layout.addStretch()
        form_layout.addRow("<b>รหัสอ้างอิง:</b>", ref_container)

        # --- Display detailed slip info if available ---
        if slip_data:
            slip_details_group = QGroupBox("รายละเอียดจากสลิป")
            slip_layout = QFormLayout(slip_details_group)
            slip_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

            # Use .get() with a default empty dict to prevent errors if keys are missing
            sender_info = slip_data.get('sender', {}) or {}
            sender_name = sender_info.get('account', {}).get('name', 'N/A')
            sender_bank = sender_info.get('bank', {}).get('name', 'N/A')
            sender_account = sender_info.get('account', {}).get('bank', {}).get('account', 'N/A')
            slip_layout.addRow("<b>จาก (ผู้โอน):</b>", QLabel(f"{sender_name}"))
            slip_layout.addRow("<b>ธนาคารผู้โอน:</b>", QLabel(f"{sender_bank} (xxx-{sender_account[-4:] if len(sender_account) > 4 else 'xxxx'})"))

            receiver_info = slip_data.get('receiver', {}) or {}
            receiver_name = receiver_info.get('account', {}).get('name', 'N/A')
            receiver_bank = receiver_info.get('bank', {}).get('name', 'N/A')
            receiver_account = receiver_info.get('account', {}).get('bank', {}).get('account', 'N/A')
            slip_layout.addRow("<b>ถึง (ผู้รับ):</b>", QLabel(f"{receiver_name}"))
            slip_layout.addRow("<b>ธนาคารผู้รับ:</b>", QLabel(f"{receiver_bank} (xxx-{receiver_account[-4:] if len(receiver_account) > 4 else 'xxxx'})"))

            slip_trans_ref = slip_data.get('transRef', 'N/A')
            slip_layout.addRow("<b>รหัสอ้างอิงธนาคาร:</b>", QLabel(slip_trans_ref))

            form_layout.addRow(slip_details_group)

        # --- Separator ---
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        form_layout.addRow(separator)

        # --- Amount and Status ---
        amount_label = QLabel(f"<h3><font color='#0078d7'>{amount_due:.2f}</font> บาท</h3>")
        amount_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.addRow("<b>ยอดชำระ:</b>", amount_label)

        # --- FIX: Wrap status label in a layout to control its size ---
        status_container = QWidget()
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(0,0,0,0)
        status_layout.addStretch() # Push the label to the right
        status_label = QLabel(f"<b>{status_text}</b>")
        status_label.setObjectName("status")
        status_label.setProperty("status", status)
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter) # Center text within the label
        status_layout.addWidget(status_label)
        # --- END FIX ---
        form_layout.addRow("<b>สถานะ:</b>", status_container)

        layout.addLayout(form_layout)
        layout.addStretch()

        # --- Close Button ---
        close_button = QPushButton("ปิด")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

        self.update_icons() # Set initial icons after all widgets are created
        self.adjust_and_center()

    def _create_admin_menu_button(self, layout):
        """Creates and configures the admin menu button."""
        self.admin_menu_button = QPushButton()
        self.admin_menu_button.setFixedSize(28, 28)
        self.admin_menu_button.setObjectName("IconButton")
        self.admin_menu_button.setToolTip("เมนูสำหรับผู้ดูแล")
        self.admin_menu_button.clicked.connect(self.show_admin_menu)
        layout.addWidget(self.admin_menu_button)

    def update_icons(self):
        """
        Updates icons in the dialog to match the current theme.
        This method is called by the main window's theme switcher.
        """
        current_theme_name = app_config.get('UI', 'theme', fallback='light')
        palette = PALETTES.get(current_theme_name, PALETTES['light'])
        icon_color = palette.get('text', '#000000')

        if hasattr(self, 'admin_menu_button'):
            self.admin_menu_button.setIcon(qta.icon('fa5s.ellipsis-v', color=icon_color))

        # Also update the copy button icon
        self.copy_button.setIcon(qta.icon('fa5s.copy', color=icon_color))

    def show_admin_menu(self):
        """Shows a context menu for admin actions on this receipt."""
        menu = QMenu(self)

        if self.history_record['payment_status'] == 'pending':
            mark_paid_action = menu.addAction(qta.icon('fa5s.check-circle'), "ยืนยันการชำระเงิน (เงินสด)")
            mark_paid_action.triggered.connect(lambda: self.update_status('paid'))

            waive_action = menu.addAction(qta.icon('fa5s.handshake'), "ยกเว้นค่าบริการ")
            waive_action.triggered.connect(lambda: self.update_status('waived'))
        else: # If 'paid' or 'waived'
            revert_action = menu.addAction(qta.icon('fa5s.undo'), "เปลี่ยนสถานะเป็น 'ค้างชำระ'")
            revert_action.triggered.connect(lambda: self.update_status('pending'))

        menu.exec(self.admin_menu_button.mapToGlobal(self.admin_menu_button.rect().bottomLeft()))

    def update_status(self, new_status: str):
        """Updates the payment status for this history record."""
        if new_status == 'paid':
            action_text = "ยืนยันการชำระเงิน"
        elif new_status == 'waived':
            action_text = "ยกเว้นค่าบริการ"
        else: # pending
            action_text = "เปลี่ยนสถานะเป็น 'ค้างชำระ'"
        
        reply = CustomMessageBox.show(self, CustomMessageBox.Question, "ยืนยัน", f"คุณต้องการ '{action_text}' สำหรับรายการนี้ใช่หรือไม่?",
                                      buttons=CustomMessageBox.Yes | CustomMessageBox.No)
        
        if reply == CustomMessageBox.Yes:
            self.db_instance.update_payment_status(self.history_id, new_status)
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "อัปเดตสถานะเรียบร้อยแล้ว")
            # Close and let the dashboard refresh itself
            self.accept()

    def format_datetime(self, dt_obj, default_text="-") -> str:
        if not dt_obj:
            return default_text
        
        dt = QDateTime.fromString(str(dt_obj).split('.')[0], "yyyy-MM-dd HH:mm:ss")
        if not dt.isValid():
            return default_text # Return default if parsing fails
        dt.setTimeSpec(Qt.TimeSpec.UTC)
        
        offset_hours = app_config.getint('TIME', 'utc_offset_hours', fallback=7)
        offset_seconds = offset_hours * 3600
        local_dt = dt.toOffsetFromUtc(offset_seconds)

        return local_dt.toString("dd/MM/yyyy HH:mm:ss")

    def copy_transaction_ref(self):
        """Copies the transaction reference to the clipboard and provides visual feedback."""
        transaction_ref = self.history_record.get('transaction_ref')
        if transaction_ref:
            clipboard = QApplication.clipboard()
            clipboard.setText(transaction_ref)
            
            # Visual feedback
            original_icon = self.copy_button.icon()
            self.copy_button.setIcon(qta.icon('fa5s.check', color='green'))
            QTimer.singleShot(1500, lambda: self.copy_button.setIcon(original_icon))