from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QScrollArea, QWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QLabel, QFileDialog, QMenu, QScroller, QSpacerItem, QGraphicsDropShadowEffect
)
import qtawesome as qta
from app.base_dialog import BaseDialog
from app_db.db_management import db_manager, get_db_instance, db_signals
from app_payment.payment_dialog import PaymentDialog
from app_payment.receipt_dialog import ReceiptDialog
from app_config import app_config
from theme import PALETTES
from PyQt6.QtCore import QDateTime, Qt, QSize
from PyQt6.QtGui import QColor
import math

class ClickableTotalWidget(QWidget):
    """A custom widget to show a clickable total summary."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.amount_label = QLabel("-.--")
        self.prompt_label = QLabel("[กดเพื่อแสดง]")
        self.is_expanded = False
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        title_label = QLabel("<b>ยอดรวมทั้งหมด:</b>")
        self.amount_label.setStyleSheet("font-size: 12pt; font-weight: bold; color: #27ae60;")
        self.amount_label.hide() # Initially hidden
        self.prompt_label.setStyleSheet("font-size: 9pt; color: #808080;")

        layout.addWidget(title_label)
        layout.addWidget(self.amount_label)
        layout.addWidget(self.prompt_label)
        
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("คลิกเพื่อแสดง/ซ่อนยอดรวม")

    def set_total(self, total: float):
        self.amount_label.setText(f"{total:,.2f} บาท")

    def mousePressEvent(self, event):
        self.is_expanded = not self.is_expanded
        self.amount_label.setVisible(self.is_expanded)
        self.prompt_label.setVisible(not self.is_expanded)
        super().mousePressEvent(event)

class PaymentHistoryDialog(BaseDialog):
    def __init__(self, user_data, is_admin_view=False, parent=None, db_instance=None):
        super().__init__(parent)
        self.user_data = user_data
        self.is_admin_view = is_admin_view
        # Use the passed db_instance if provided, otherwise get the currently active one.
        # This ensures the dialog works correctly whether opened by a user or an admin.
        self.db_instance = db_instance if db_instance else get_db_instance(is_remote=app_config.get('DATABASE', 'enabled', 'False').lower() == 'true')
        self.setWindowTitle(f"ประวัติการชำระเงิน: {self.user_data['username']}")
        self.setMinimumSize(800, 600)
        self.current_filter = None  # None means show all
        self.items_per_page = 15
        self.current_page = 1
        self.all_history_records = []

        layout = QVBoxLayout(self)

        # --- Toolbar ---
        toolbar_layout = QHBoxLayout()

        # --- NEW: Total Summary ---
        self.total_summary_widget = ClickableTotalWidget(self)
        toolbar_layout.addWidget(self.total_summary_widget)
        # --- END NEW ---

        self.filter_button = QPushButton(" คัดกรอง")
        self.filter_button.setIcon(qta.icon('fa5s.filter', color='white'))
        self.filter_button.clicked.connect(self.show_filter_menu)

        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.filter_button)
        layout.addLayout(toolbar_layout)

        # --- History Table ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("HistoryScrollContent") # Name for styling
        self.list_layout = QVBoxLayout(self.scroll_content)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.scroll_content)
        # เปิดใช้งาน Smooth Scrolling สำหรับ Touch
        QScroller.grabGesture(self.scroll_area.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)

        layout.addWidget(self.scroll_area)

        # --- Bottom Layout ---
        bottom_layout = QHBoxLayout()
        self.info_label = QLabel("คลิกที่ปุ่มในแต่ละรายการเพื่อดำเนินการ")

        # --- Pagination Controls ---
        self.pagination_widget = QWidget()
        pagination_layout = QHBoxLayout(self.pagination_widget)
        pagination_layout.setContentsMargins(0,0,0,0)
        pagination_layout.setSpacing(10)
        self.prev_page_button = QPushButton(" < ก่อนหน้า")
        self.prev_page_button.setFixedWidth(100)
        self.prev_page_button.clicked.connect(self.prev_page)
        self.page_label = QLabel("Page 1/1")
        self.next_page_button = QPushButton("ถัดไป > ")
        self.next_page_button.setFixedWidth(100)
        self.next_page_button.clicked.connect(self.next_page)
        pagination_layout.addWidget(self.prev_page_button)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_page_button)
        self.pagination_widget.setVisible(False) # Hide by default

        close_button = QPushButton("ปิด")
        close_button.clicked.connect(self.accept)
        
        bottom_layout.addWidget(self.info_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.pagination_widget)
        bottom_layout.addWidget(close_button)
        layout.addLayout(bottom_layout)

        self.load_history()
        self.update_theme() # Set initial icons and styles
        self.adjust_and_center()

        # Connect to the global signal to refresh when a payment status changes anywhere
        db_signals.payment_status_updated.connect(self.on_global_payment_status_updated)

    def load_history(self):
        self.all_history_records = self.db_instance.get_payment_history_for_user(self.user_data['id'])
        total_amount = sum(record.get('amount_due', 0.0) for record in self.all_history_records)
        self.total_summary_widget.set_total(total_amount)

        self.current_page = 1
        self.update_pagination_controls()
        self.display_current_page()

    def display_current_page(self):
        """Clears the list and displays only the items for the current page."""
        # --- FIX: Recreate the scroll content widget and layout to prevent any artifacts ---
        # This is a more robust way to clear the list than iterating and deleting.
        if self.scroll_area.widget():
            self.scroll_area.widget().deleteLater()

        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("HistoryScrollContent")
        self.list_layout = QVBoxLayout(self.scroll_content)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.scroll_content)
        # Filter records based on the current filter
        filtered_records = [
            record for record in self.all_history_records 
            if not self.current_filter or record['payment_status'] == self.current_filter
        ]

        start_index = (self.current_page - 1) * self.items_per_page
        end_index = start_index + self.items_per_page
        records_to_display = filtered_records[start_index:end_index]

        for record in records_to_display:
            # Apply filter
            if self.current_filter and record['payment_status'] != self.current_filter:
                continue

            card = self.create_history_card(record)
            self.list_layout.addWidget(card)

        self.list_layout.addStretch()

    def update_pagination_controls(self):
        """Updates the visibility and state of pagination buttons and label."""
        filtered_records = [
            record for record in self.all_history_records 
            if not self.current_filter or record['payment_status'] == self.current_filter
        ]
        total_items = len(filtered_records)
        total_pages = math.ceil(total_items / self.items_per_page)

        if total_pages > 1:
            self.pagination_widget.setVisible(True)
            self.page_label.setText(f"หน้า {self.current_page} / {total_pages}")
            self.prev_page_button.setEnabled(self.current_page > 1)
            self.next_page_button.setEnabled(self.current_page < total_pages)
        else:
            self.pagination_widget.setVisible(False)

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.update_pagination_controls()
            self.display_current_page()

    def next_page(self):
        self.current_page += 1
        self.update_pagination_controls()
        self.display_current_page()

    def create_history_card(self, record):
        current_theme_name = app_config.get('UI', 'theme', fallback='light')
        palette = PALETTES.get(current_theme_name, PALETTES['light'])

        card = QWidget()
        card.setObjectName("HistoryCard")
        card.setStyleSheet(f"""
            #HistoryCard {{
                background-color: {palette['base']};
                border: 1px solid {palette['disabled_text']};
                border-radius: 8px;
            }}
            #HistoryCard:hover {{
                border-color: {palette['highlight']};
            }}
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 2)
        card.setGraphicsEffect(shadow)

        main_layout = QHBoxLayout(card)
        main_layout.setContentsMargins(15, 12, 15, 12)
        main_layout.setSpacing(15)

        # Left side: Details
        details_layout = QVBoxLayout()
        details_layout.setSpacing(4)
        item_name_label = QLabel(f"<b>{record['item_name']}</b>")
        item_name_label.setStyleSheet("font-size: 12pt;")
        return_date_label = QLabel(f"วันที่คืน: {self.format_datetime(record['return_date'])}")
        return_date_label.setStyleSheet(f"color: {palette['disabled_text']};")
        amount_label = QLabel(f"ยอดชำระ: <b style='color:{palette['info']};'>{record['amount_due']:,.2f}</b> บาท")
        details_layout.addWidget(item_name_label)
        details_layout.addWidget(return_date_label)
        details_layout.addWidget(amount_label)
        details_layout.addStretch()

        # Right side: Status and Actions
        actions_layout = QHBoxLayout()
        actions_layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        actions_layout.setSpacing(10)

        status_map = {
            'pending': ('ค้างชำระ', palette['warning']),
            'paid': ('ชำระแล้ว', palette['success']),
            'waived': ('ยกเว้นค่าบริการ', palette['disabled_text'])
        }
        status_text, status_color = status_map.get(record['payment_status'], ('ไม่ทราบ', '#000000'))
        status_label = QLabel(status_text)
        status_label.setStyleSheet(f"""
            background-color: {status_color};
            color: white;
            font-weight: bold;
            padding: 4px 12px;
            border-radius: 13px;
            min-width: 90px;
        """)
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        actions_layout.addWidget(status_label)

        if record['payment_status'] == 'pending':
            pay_button = QPushButton(" ชำระเงิน")
            pay_button.setIcon(qta.icon('fa5s.qrcode', color='white'))
            pay_button.clicked.connect(lambda checked=False, r=record: self.open_payment_dialog(r))
            actions_layout.addWidget(pay_button)
        else:
            receipt_button = QPushButton(" ดูใบเสร็จ")
            receipt_button.setIcon(qta.icon('fa5s.receipt', color='white'))
            receipt_button.clicked.connect(lambda checked=False, r=record: self.open_receipt_dialog(r))
            actions_layout.addWidget(receipt_button)

        # Add admin menu button if in admin view
        if self.is_admin_view:
            # --- FIX: Get theme color for the icon ---
            icon_color = PALETTES[current_theme_name]['text']
            admin_menu_button = QPushButton()
            admin_menu_button.setIcon(qta.icon('fa5s.ellipsis-v', color=icon_color))
            admin_menu_button.setFixedSize(28, 28)
            admin_menu_button.setObjectName("IconButton")
            admin_menu_button.setToolTip("เมนูสำหรับผู้ดูแล")
            admin_menu_button.clicked.connect(lambda checked=False, r=record, b=admin_menu_button: self.show_admin_card_menu(r, b)) # type: ignore
            actions_layout.addWidget(admin_menu_button)

        main_layout.addLayout(details_layout, 3) # Give more space to details
        main_layout.addLayout(actions_layout)

        return card

    def get_selected_history_record(self):
        # This method is now only used by admin functions, which are not implemented in the new card view.
        # It needs to be adapted if admin actions are to be performed on cards.
        # For now, we can return None.
        return None

    def open_receipt_dialog(self, record):
        receipt_dialog = ReceiptDialog(
            history_id=record['id'], 
            parent=self, 
            db_instance=self.db_instance # Pass the correct DB instance
        )
        receipt_dialog.exec()

    def open_payment_dialog(self, record):
        """Opens the payment dialog for a pending record."""
        dummy_item_data = {'name': record['item_name']}
        payment_dialog = PaymentDialog(
            item_data=dummy_item_data, user_data=self.user_data, parent=self,
            fixed_amount=record['amount_due'], transaction_ref=record['transaction_ref'],
            fixed_duration=self.calculate_duration_string(record['rent_date'], record['return_date']),
            db_instance=self.db_instance # Pass the correct DB instance
        )
        # Connect signals to handle both successful polling and manual slip verification
        payment_dialog.accepted.connect(lambda: self.on_payment_confirmed(record, None))
        payment_dialog.slip_verified.connect(lambda slip_data: self.on_payment_confirmed(record, slip_data))

        payment_dialog.open() # Use open() to not block the main event loop

    def on_payment_confirmed(self, record, slip_data: dict | None):
        """
        Callback for when a payment is confirmed, either by API polling or slip verification.
        """
        from app.custom_message_box import CustomMessageBox # Local import
        # Update the status in the database, now with potential slip_data
        self.db_instance.update_payment_status(record['id'], 'paid', slip_data=slip_data)
        CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "บันทึกการชำระเงินเรียบร้อยแล้ว")
        
        self.load_history() # Refresh the history list
        # Notify main window to update its UI, ensuring parent() exists and has the method.
        if self.parent() and hasattr(self.parent(), 'check_pending_payments'):
            self.parent().check_pending_payments()

    def update_icons(self):
        """A method to be called by the main window when the theme changes."""
        # The name 'update_icons' is a convention used by the main window's theme switcher.
        self.update_theme()

    def update_theme(self):
        """Reloads history to apply new theme colors and updates toolbar icons."""
        self.filter_button.setIcon(qta.icon('fa5s.filter', color='white'))
        # Reloading the history will recreate the cards with the new theme colors
        self.load_history()

    def show_filter_menu(self):
        statuses = {
            "แสดงทั้งหมด": None,
            "ค้างชำระ": "pending",
            "ชำระแล้ว": "paid",
            "ยกเว้นค่าบริการ": "waived"
        }
        menu = QMenu(self.filter_button)
        for text, status_value in statuses.items():
            action = menu.addAction(text)
            action.triggered.connect(lambda checked=False, s=status_value: self.apply_filter(s))
        menu.exec(self.filter_button.mapToGlobal(self.filter_button.rect().bottomLeft()))

    def apply_filter(self, status: str | None):
        self.current_filter = status
        self.current_page = 1 # Reset to first page when filter changes
        self.update_pagination_controls()
        self.display_current_page()
        if status:
            self.filter_button.setText(f" คัดกรอง: {status.capitalize()}")
        else:
            self.filter_button.setText(" คัดกรอง")

    def show_admin_card_menu(self, record, button):
        """Shows a context menu for admin actions on a specific card."""
        menu = QMenu(button)

        if record['payment_status'] == 'pending':
            verify_action = menu.addAction(qta.icon('fa5s.search-dollar'), "ตรวจสอบด้วย API")
            verify_action.triggered.connect(lambda: self.verify_with_api_as_admin(record))

            mark_paid_action = menu.addAction(qta.icon('fa5s.check-circle'), "ยืนยันการชำระเงิน (เงินสด)")
            mark_paid_action.triggered.connect(lambda: self.update_status(record, 'paid'))

            waive_action = menu.addAction(qta.icon('fa5s.hand-holding-usd'), "ยกเว้นค่าบริการ")
            waive_action.triggered.connect(lambda: self.update_status(record, 'waived'))
        else: # If 'paid' or 'waived'
            revert_action = menu.addAction(qta.icon('fa5s.undo'), "เปลี่ยนสถานะเป็น 'ค้างชำระ'")
            revert_action.triggered.connect(lambda: self.update_status(record, 'pending'))

        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def verify_with_api_as_admin(self, record):
        from app.custom_message_box import CustomMessageBox
        transaction_ref = record.get('transaction_ref')
        if not transaction_ref:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ไม่มีข้อมูล", "ไม่พบ Transaction Reference สำหรับรายการนี้")
            return

        from app_payment.scb_api_handler import SCBApiHandler
        scb_handler = SCBApiHandler(debug=True, config_source=app_config) # Ensure it uses global app_config
        is_paid, message = scb_handler.inquire_payment_status(transaction_ref)

        if is_paid:
            self.db_instance.update_payment_status(record['id'], 'paid')
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", f"ตรวจสอบพบการชำระเงินสำหรับ {transaction_ref} เรียบร้อยแล้ว")
            self.load_history()
        else:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ยังไม่ชำระ", f"ไม่พบข้อมูลการชำระเงินสำหรับ {transaction_ref}: {message}")

    def update_status(self, record, new_status: str):
        from app.custom_message_box import CustomMessageBox # Import locally
        if new_status == 'paid':
            action_text = "ยืนยันการชำระเงิน"
        elif new_status == 'waived':
            action_text = "ยกเว้นค่าบริการ"
        else: # pending
            action_text = "เปลี่ยนสถานะเป็น 'ค้างชำระ'"
        reply = CustomMessageBox.show(self, CustomMessageBox.Question, "ยืนยัน", f"คุณต้องการ '{action_text}' สำหรับรายการนี้ใช่หรือไม่?",
                                      buttons=CustomMessageBox.Yes | CustomMessageBox.No)
        
        if reply == CustomMessageBox.Yes:
            self.db_instance.update_payment_status(record['id'], new_status)
            self.load_history()

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
        return local_dt.toString("yyyy-MM-dd HH:mm:ss")

    def calculate_duration_string(self, rent_date_str, return_date_str) -> str:
        """Calculates a human-readable duration string from two datetime strings."""
        if not rent_date_str or not return_date_str:
            return "N/A"

        rent_dt = QDateTime.fromString(str(rent_date_str).split('.')[0], "yyyy-MM-dd HH:mm:ss")
        return_dt = QDateTime.fromString(str(return_date_str).split('.')[0], "yyyy-MM-dd HH:mm:ss")

        total_seconds = rent_dt.secsTo(return_dt)
        if total_seconds < 0: total_seconds = 0

        days = total_seconds // (24 * 3600)
        hours = (total_seconds % (24 * 3600)) // 3600
        minutes = (total_seconds % 3600) // 60

        return f"{days} วัน {hours} ชั่วโมง {minutes} นาที"

    def on_global_payment_status_updated(self, user_id: int):
        """Slot to refresh the history list when a payment status changes globally."""
        if self.user_data and self.user_data['id'] == user_id:
            self.load_history()

    def closeEvent(self, event):
        """Disconnect signals when the dialog is closed."""
        try:
            db_signals.payment_status_updated.disconnect(self.on_global_payment_status_updated)
        except TypeError: # Signal was not connected or already disconnected
            pass
        super().closeEvent(event)

    def calculate_duration_string(self, rent_date_str, return_date_str) -> str:
        """Calculates a human-readable duration string from two datetime strings."""
        if not rent_date_str or not return_date_str:
            return "N/A"

        rent_dt = QDateTime.fromString(str(rent_date_str).split('.')[0], "yyyy-MM-dd HH:mm:ss")
        return_dt = QDateTime.fromString(str(return_date_str).split('.')[0], "yyyy-MM-dd HH:mm:ss")

        total_seconds = rent_dt.secsTo(return_dt)
        if total_seconds < 0: total_seconds = 0

        days = total_seconds // (24 * 3600)
        hours = (total_seconds % (24 * 3600)) // 3600
        minutes = (total_seconds % 3600) // 60

        return f"{days} วัน {hours} ชั่วโมง {minutes} นาที"

    def on_global_payment_status_updated(self, user_id: int):
        """Slot to refresh the history list when a payment status changes globally."""
        if self.user_data and self.user_data['id'] == user_id:
            self.load_history()

    def closeEvent(self, event):
        """Disconnect signals when the dialog is closed."""
        try:
            db_signals.payment_status_updated.disconnect(self.on_global_payment_status_updated)
        except TypeError: # Signal was not connected or already disconnected
            pass
        super().closeEvent(event)