from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QLabel, QFileDialog
)
import qtawesome as qta
from .base_dialog import BaseDialog
from app_db.db_management import db_manager
from app_payment.slip_verifier import SlipVerifier
from app.custom_message_box import CustomMessageBox
from theme import PALETTES
from .payment_dialog import PaymentDialog
from app_config import app_config
from PyQt6.QtCore import QDateTime, Qt

class PaymentHistoryDialog(BaseDialog):
    def __init__(self, user_data, is_admin_view=False, parent=None):
        super().__init__(parent)
        self.user_data = user_data
        self.is_admin_view = is_admin_view
        self.slip_verifier = SlipVerifier()
        self.setWindowTitle(f"ประวัติการชำระเงิน: {self.user_data['username']}")
        self.setMinimumSize(800, 600)

        layout = QVBoxLayout(self)

        # --- Button Layout (for Admin) ---
        if self.is_admin_view:
            button_layout = QHBoxLayout()
            mark_paid_button = QPushButton(qta.icon('fa5s.check-circle'), " ยืนยันการชำระเงิน (เงินสด)")
            mark_paid_button.clicked.connect(lambda: self.update_status('paid'))
            waive_button = QPushButton(qta.icon('fa5s.hand-holding-usd'), " ยกเว้นค่าบริการ")
            waive_button.clicked.connect(lambda: self.update_status('waived'))
            
            button_layout.addStretch()
            button_layout.addWidget(mark_paid_button)
            button_layout.addWidget(waive_button)
            layout.addLayout(button_layout)

        # --- History Table ---
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(["ID", "รายการ", "วันที่คืน", "ยอดชำระ (บาท)", "สถานะ"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.doubleClicked.connect(self.handle_double_click)
        layout.addWidget(self.history_table)

        # --- Bottom Layout ---
        bottom_layout = QHBoxLayout()
        self.info_label = QLabel("ดับเบิลคลิกที่รายการ 'ค้างชำระ' เพื่อชำระเงิน หรือดูรายละเอียดใบเสร็จสำหรับรายการอื่น")
        close_button = QPushButton("ปิด")
        close_button.clicked.connect(self.accept)
        
        # ปุ่มอัปโหลดสลิปสำหรับผู้ใช้
        self.upload_slip_button = QPushButton(qta.icon('fa5s.upload'), " อัปโหลดสลิปเพื่อตรวจสอบ")
        self.upload_slip_button.clicked.connect(self.upload_and_verify_slip)
        # ซ่อนปุ่มนี้ไว้ก่อน เนื่องจากยังไม่ได้เชื่อมต่อกับ SCB API จริง
        self.upload_slip_button.hide()

        bottom_layout.addWidget(self.info_label)
        bottom_layout.addStretch()
        # แสดงปุ่มเมื่อ is_admin_view เป็น false และปุ่มไม่ได้ถูกซ่อน
        if not self.is_admin_view and self.upload_slip_button.isVisible():
             bottom_layout.addWidget(self.upload_slip_button)
        bottom_layout.addWidget(close_button)
        layout.addLayout(bottom_layout)

        self.load_history()
        self.adjust_and_center()

    def load_history(self):
        history = db_manager.get_payment_history_for_user(self.user_data['id'])
        self.history_table.setRowCount(len(history))

        # Get the current theme's palette to use dynamic colors
        current_theme_name = app_config.get('UI', 'theme', fallback='light')
        palette = PALETTES.get(current_theme_name, PALETTES['light'])
        text_color = qta.color(palette['text'])

        status_map = {
            'pending': ('ค้างชำระ', palette['warning']),
            'paid': ('ชำระแล้ว', palette['success']),
            'waived': ('ยกเว้นค่าบริการ', palette['disabled_text'])
        }

        for row, record in enumerate(history):
            history_id = record['id']
            item_name = record['item_name']
            return_date = self.format_datetime(record['return_date'])
            amount_due = f"{record['amount_due']:.2f}"
            status_text, status_color = status_map.get(record['payment_status'], ('ไม่ทราบ', '#000000'))

            # Store full record data in the first item for later retrieval
            id_item = QTableWidgetItem(str(history_id))
            id_item.setData(Qt.ItemDataRole.UserRole, record)
            id_item.setForeground(text_color)

            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(Qt.GlobalColor.white)
            status_item.setBackground(qta.color(status_color))
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            item_name_item = QTableWidgetItem(item_name)
            item_name_item.setForeground(text_color)
            return_date_item = QTableWidgetItem(return_date)
            return_date_item.setForeground(text_color)
            amount_due_item = QTableWidgetItem(amount_due)
            amount_due_item.setForeground(text_color)

            self.history_table.setItem(row, 0, id_item)
            self.history_table.setItem(row, 1, item_name_item)
            self.history_table.setItem(row, 2, return_date_item)
            self.history_table.setItem(row, 3, amount_due_item)
            self.history_table.setItem(row, 4, status_item)

    def get_selected_history_record(self):
        selected_items = self.history_table.selectedItems()
        if not selected_items:
            return None
        # Get the item from the first column which holds the data
        id_item = self.history_table.item(selected_items[0].row(), 0)
        return id_item.data(Qt.ItemDataRole.UserRole)

    def handle_double_click(self, index):
        id_item = self.history_table.item(index.row(), 0)
        record = id_item.data(Qt.ItemDataRole.UserRole)
        
        if record and record['payment_status'] == 'pending':
            # Re-create a dummy item_data dict for PaymentDialog
            dummy_item_data = {'name': record['item_name']}
            # Re-create a dummy duration string
            duration_str = "N/A" # We don't need to recalculate this

            payment_dialog = PaymentDialog(
                item_data=dummy_item_data, 
                user_data=self.user_data, 
                parent=self,
                fixed_amount=record['amount_due'],
                fixed_duration=duration_str
            )
            if payment_dialog.exec():
                # User confirmed payment, so we mark it as paid
                db_manager.update_payment_status(record['id'], 'paid')
                CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "บันทึกการชำระเงินเรียบร้อยแล้ว")
                self.load_history()

    def upload_and_verify_slip(self):
        record = self.get_selected_history_record()
        if not record or record['payment_status'] != 'pending':
            CustomMessageBox.show(self, CustomMessageBox.Warning, "เลือกรายการไม่ถูกต้อง", "กรุณาเลือกรายการที่ 'ค้างชำระ' เพื่อตรวจสอบสลิป")
            return

        if not self.slip_verifier.is_configured():
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ไม่ได้ตั้งค่า", "ยังไม่ได้ตั้งค่าระบบตรวจสอบสลิป กรุณาติดต่อผู้ดูแล")
            return

        file_name, _ = QFileDialog.getOpenFileName(self, "เลือกไฟล์สลิป", "", "Image Files (*.png *.jpg *.jpeg)")
        if not file_name:
            return

        expected_amount = float(record['amount_due'])
        is_valid, message = self.slip_verifier.verify_slip(file_name, expected_amount)

        if is_valid:
            db_manager.update_payment_status(record['id'], 'paid')
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", message)
            self.load_history()
        else:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ตรวจสอบไม่สำเร็จ", message)

    def update_status(self, new_status: str):
        if not self.is_admin_view: return

        record = self.get_selected_history_record()
        if not record:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ไม่ได้เลือก", "กรุณาเลือกรายการที่ต้องการอัปเดต")
            return

        if record['payment_status'] != 'pending':
            CustomMessageBox.show(self, CustomMessageBox.Information, "ตรวจสอบแล้ว", "รายการนี้ถูกจัดการเรียบร้อยแล้ว")
            return

        action_text = "ยืนยันการชำระเงิน" if new_status == 'paid' else "ยกเว้นค่าบริการ"
        reply = CustomMessageBox.show(self, CustomMessageBox.Question, "ยืนยัน", f"คุณต้องการ '{action_text}' สำหรับรายการนี้ใช่หรือไม่?",
                                      buttons=CustomMessageBox.Yes | CustomMessageBox.No)
        
        if reply == CustomMessageBox.Yes:
            db_manager.update_payment_status(record['id'], new_status)
            self.load_history()

    def format_datetime(self, dt_obj, default_text="-") -> str:
        if not dt_obj:
            return default_text
        dt = QDateTime.fromString(str(dt_obj).split('.')[0], "yyyy-MM-dd HH:mm:ss")
        dt.setTimeSpec(Qt.TimeSpec.UTC)
        offset_hours = app_config.getint('TIME', 'utc_offset_hours', fallback=7)
        offset_seconds = offset_hours * 3600
        local_dt = dt.toOffsetFromUtc(offset_seconds)
        return local_dt.toString("yyyy-MM-dd HH:mm:ss")