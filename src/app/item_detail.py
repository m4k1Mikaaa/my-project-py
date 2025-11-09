from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox, QWidget, QApplication, QGridLayout, QGroupBox, QFormLayout,
    QDateEdit, QTimeEdit, QFrame, QSlider, QTextEdit
) # sourcery skip: extract-method
import qtawesome as qta # type: ignore
import uuid
import math
from PyQt6.QtGui import QPixmap, QCloseEvent
from PyQt6.QtCore import Qt, QDateTime, QDate, QTime, QSize, QLocale
from .base_dialog import BaseDialog
from app_config import app_config
from app_db.db_management import get_db_instance, db_signals
from theme import PALETTES
from .rental_history import RentalHistoryDialog
from .image_viewer import ImageViewerDialog
from .custom_message_box import CustomMessageBox
from app_payment.payment_dialog import PaymentDialog
from .utils import set_image_on_label

class ItemDetailWindow(BaseDialog):
    def __init__(self, item_id, current_user, parent=None):
        super().__init__(parent)
        self.item_id = item_id
        self.current_user = current_user
        self.main_window = parent
        self.db_instance = self.main_window._get_db_instance_for_refresh() if self.main_window else get_db_instance()

        self.item_data = self.db_instance.get_item_by_id(self.item_id)
        if not self.item_data:
            self.close()
            return

        self.setWindowTitle(f"รายละเอียด: {self.item_data['name']}")
        self.setMinimumWidth(800)

        self._init_ui()
        self._update_ui()

        self.adjust_and_center()
        db_signals.data_changed.connect(self._handle_data_change)

    def _init_ui(self):
        """Initializes the user interface widgets and layout once."""
        # --- REVISED: Use QGridLayout for better control over column widths ---
        main_layout = QGridLayout(self)
        main_layout.setColumnStretch(0, 2) # Image column
        main_layout.setColumnStretch(1, 3) # Details column

        # --- Left Panel (Image) ---
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setToolTip("ดับเบิลคลิกเพื่อดูภาพขนาดเต็ม")
        self.image_label.mouseDoubleClickEvent = self.view_full_image
        main_layout.addWidget(self.image_label, 0, 0, Qt.AlignmentFlag.AlignTop)

        # --- Right Panel (Details) ---
        details_panel = QWidget()
        self.details_layout = QVBoxLayout(details_panel)
        # General Info
        general_group = QGroupBox("ข้อมูลทั่วไป")
        general_group_layout = QVBoxLayout(general_group)

        self.name_label = QLabel()
        self.name_label.setStyleSheet("font-size: 16pt; font-weight: bold;")
        self.name_label.setWordWrap(True)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        general_group_layout.addWidget(self.name_label)

        brand_form_layout = QFormLayout()
        brand_form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.brand_label = QLabel()
        self.brand_label.setWordWrap(True)
        brand_form_layout.addRow("<b>ยี่ห้อ/รุ่น:</b>", self.brand_label)
        general_group_layout.addLayout(brand_form_layout)

        desc_label_header = QLabel("<b>รายละเอียด:</b>")
        desc_label_header.setAlignment(Qt.AlignmentFlag.AlignLeft)
        general_group_layout.addWidget(desc_label_header)
        # --- FIX: Revert to QLabel and ensure word wrap works with the new grid layout ---
        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        general_group_layout.addWidget(self.desc_label)

        # Pricing Info
        self.pricing_group = QGroupBox("ราคา")
        self.pricing_form_layout = QFormLayout(self.pricing_group)
        self.pricing_form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        # Rental Info
        self.rental_info_group = QGroupBox("ข้อมูลการเช่า")
        rental_info_form_layout = QFormLayout(self.rental_info_group)
        rental_info_form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.rental_duration_value_label = QLabel("-")
        rental_info_form_layout.addRow("<b>ระยะเวลาเช่าปัจจุบัน:</b>", self.rental_duration_value_label)

        # Status and History
        status_history_layout = QHBoxLayout()
        self.latest_renter_widget = self._create_latest_renter_widget()
        self.status_value_label = QLabel()
        self.status_value_label.setObjectName("status")
        self.status_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_history_layout.addWidget(self.latest_renter_widget)
        status_history_layout.addStretch()
        status_history_layout.addWidget(self.status_value_label)

        self.details_layout.addWidget(general_group)
        self.details_layout.addWidget(self.pricing_group)
        self.details_layout.addWidget(self.rental_info_group)
        self.details_layout.addStretch()
        self.details_layout.addLayout(status_history_layout)

        main_layout.addWidget(details_panel, 0, 1)

        # --- Separator ---
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(separator, 1, 0, 1, 2) # Span across both columns

        # --- Future Cost Calculator ---
        self.future_cost_widget = QWidget()
        future_cost_layout = QVBoxLayout(self.future_cost_widget)
        future_cost_layout.setContentsMargins(0, 10, 0, 10)

        self.future_cost_title = QLabel("<b>คำนวณค่าบริการในอนาคต</b>")
        future_cost_layout.addWidget(self.future_cost_title)

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)

        self.future_date_edit = QDateEdit()
        self.future_date_edit.setCalendarPopup(True)
        # --- FIX: Use QLocale object instead of string from locale.setlocale ---
        self.future_date_edit.setLocale(QLocale("C"))
        self.future_date_edit.dateChanged.connect(self.calculate_future_cost)
        self.future_date_edit.dateChanged.connect(self._update_min_time)

        # --- NEW: Graphical Time Slider ---
        time_slider_layout = QHBoxLayout()
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 1439) # 24 * 60 - 1 minutes in a day
        self.time_slider.setSingleStep(15) # Snap to 15-minute intervals
        self.time_slider.setPageStep(60)   # Page up/down moves by an hour
        self.time_slider.valueChanged.connect(self._on_slider_value_changed)
        self.time_display_label = QLabel("00:00")
        time_slider_layout.addWidget(self.time_slider)
        time_slider_layout.addWidget(self.time_display_label)

        self.reset_datetime_button = QPushButton(" เวลาปัจจุบัน")
        self.reset_datetime_button.setIcon(qta.icon('fa5s.clock', color='white'))
        self.reset_datetime_button.setToolTip("รีเซ็ตเป็นเวลาปัจจุบัน")
        self.reset_datetime_button.clicked.connect(self._reset_future_datetime)

        self.rent_button = QPushButton("เช่า-ยืม")
        self.rent_button.setObjectName("rent_button")
        self.rent_button.setMinimumHeight(40)
        self.rent_button.clicked.connect(self.rent_item)

        self.return_button = QPushButton("ส่งคืน")
        self.return_button.setObjectName("return_button")
        self.return_button.setMinimumHeight(40)
        self.return_button.clicked.connect(self.return_item)

        controls_layout.addWidget(QLabel("วันที่:"))
        controls_layout.addWidget(self.future_date_edit)
        controls_layout.addWidget(self.reset_datetime_button)
        controls_layout.addSpacing(10)
        controls_layout.addWidget(QLabel("เวลา:"))
        controls_layout.addLayout(time_slider_layout, 1) # Add the slider layout, make it stretchable
        controls_layout.addSpacing(20)

        add_time_buttons = {"+1 นาที": (1, "minutes"), "+1 ชั่วโมง": (1, "hours"), "+1 วัน": (1, "days")}
        for text, (amount, unit) in add_time_buttons.items():
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, u=unit, a=amount: self._add_time(u, a))
            controls_layout.addWidget(button)

        controls_layout.addSpacing(10)

        subtract_time_buttons = {"-1 นาที": (-1, "minutes"), "-1 ชั่วโมง": (-1, "hours"), "-1 วัน": (-1, "days")}
        for text, (amount, unit) in subtract_time_buttons.items():
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, u=unit, a=amount: self._add_time(u, a))
            controls_layout.addWidget(button)

        controls_layout.addStretch()

        future_cost_layout.addLayout(controls_layout)

        self.future_cost_label = QLabel("ค่าบริการส่วนเพิ่ม: 0.00 บาท")
        self.future_cost_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        self.total_future_cost_label = QLabel("ค่าบริการรวมโดยประมาณ: 0.00 บาท")
        self.total_future_cost_label.setStyleSheet("font-weight: bold; font-size: 12pt; color: #0078d7;")

        future_cost_layout.addWidget(self.future_cost_label, alignment=Qt.AlignmentFlag.AlignCenter)
        future_cost_layout.addWidget(self.total_future_cost_label, alignment=Qt.AlignmentFlag.AlignCenter)

        main_layout.addWidget(self.future_cost_widget, 2, 0, 1, 2) # Span across both columns

        # --- Action Buttons (Rent/Return) are now separate from the calculator ---
        action_button_layout = QHBoxLayout()
        action_button_layout.setContentsMargins(0, 10, 0, 0) # Add some top margin
        action_button_layout.addWidget(self.rent_button)
        action_button_layout.addWidget(self.return_button)
        main_layout.addLayout(action_button_layout, 3, 0, 1, 2) # Add to the main grid layout


        # --- NEW: Login prompt label ---
        self.login_prompt_label = QLabel("กรุณาเข้าสู่ระบบเพื่อทำรายการ")
        self.login_prompt_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.login_prompt_label.setStyleSheet("font-weight: bold; font-size: 11pt; color: #f39c12;") # Use a warning color
        main_layout.addWidget(self.login_prompt_label, 4, 0, 1, 2) # Span across both columns

    def _create_latest_renter_widget(self):
        """Creates the widget for displaying the latest renter."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignmentFlag.AlignRight)
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon('fa5s.user-clock', color=PALETTES[app_config.get('UI', 'theme', 'light')]['text']).pixmap(QSize(16, 16)))
        self.latest_renter_label = QLabel()
        self.latest_renter_label.setStyleSheet(f"font-size: 10pt; font-weight: bold; color: {PALETTES[app_config.get('UI', 'theme', 'light')]['text']};")
        layout.addWidget(icon_label)
        layout.addWidget(self.latest_renter_label)
        return widget

    def _update_ui(self):
        """Updates all UI elements with the current item_data."""
        if not self.item_data:
            return

        # Update Image
        image_data_blob = self.item_data.get('image_path')
        set_image_on_label(self.image_label, image_data_blob, "No Image Available")

        # Update General Info
        self.name_label.setText(self.item_data['name'])
        self.brand_label.setText(self.item_data.get('brand', '-'))
        self.desc_label.setText(self.item_data.get('description', '-'))

        # Update Pricing Info
        # Clear previous pricing rows
        while self.pricing_form_layout.count():
            self.pricing_form_layout.removeRow(0)

        price_per_minute = float(self.item_data.get('price_per_minute', 0.0))
        price_unit = self.item_data.get('price_unit', 'ต่อวัน')
        price_model = self.item_data.get('price_model', 'per_minute')
        fixed_fee = float(self.item_data.get('fixed_fee', 0.0))
        grace_period_minutes = int(self.item_data.get('grace_period_minutes', 0))
        minimum_charge = float(self.item_data.get('minimum_charge', 0.0))

        # --- NEW: Hide cost calculator if the item is completely free ---
        is_free = price_per_minute <= 0 and fixed_fee <= 0 and minimum_charge <= 0
        self.future_cost_widget.setVisible(not is_free)
        # --- END NEW ---

        if price_model in ['fixed_fee_only', 'fixed_plus_overdue']:
            self.pricing_form_layout.addRow("<b>ค่าบริการรายครั้ง:</b>", QLabel(f"{fixed_fee:.2f} บาท"))
        if price_model == 'fixed_plus_overdue' and grace_period_minutes > 0:
            grace_text = self._format_grace_period(grace_period_minutes)
            self.pricing_form_layout.addRow("<b>ระยะเวลาผ่อนผัน:</b>", QLabel(grace_text))
        if price_model in ['fixed_plus_overdue', 'per_minute']:
            price_label_text = "<b>ค่าปรับเกินเวลา:</b>" if price_model == 'fixed_plus_overdue' else "<b>ราคาเช่า:</b>"
            price_display = "ฟรี"
            if price_per_minute > 0:
                if price_unit == "ต่อวัน": price_display = f"{price_per_minute * 1440:.2f} บาท/วัน"
                elif price_unit == "ต่อชั่วโมง": price_display = f"{price_per_minute * 60:.2f} บาท/ชั่วโมง"
                else: price_display = f"{price_per_minute:.2f} บาท/นาที"
            self.pricing_form_layout.addRow(price_label_text, QLabel(price_display))
        if price_model == 'per_minute' and minimum_charge > 0:
            self.pricing_form_layout.addRow("<b>ค่าบริการขั้นต่ำ:</b>", QLabel(f"{minimum_charge:.2f} บาท"))

        # Update Status and Latest Renter
        self.latest_renter_label.setText(self.item_data.get('latest_renter') or "ไม่มีประวัติ")

        self.update_button_states()
        self.calculate_future_cost()

    def update_button_states(self):
        status = self.item_data['status']
        renter_id = self.item_data['current_renter_id']
        
        is_rented_by_current_user = self.current_user is not None and renter_id == self.current_user['id']
        is_rented_by_other = status == 'rented' and not is_rented_by_current_user
        self.login_prompt_label.setVisible(self.current_user is None)

        # --- NEW: Logic to handle button visibility based on login status ---
        if self.current_user:
            if status == 'available':
                self.rent_button.setText("เช่า-ยืม")
                self.rent_button.setEnabled(True)
                self.rent_button.setProperty("status", "available")
                self.rent_button.setVisible(True)
            elif status == 'suspended':
                self.rent_button.setText("ระงับการใช้งาน")
                self.rent_button.setEnabled(False)
                self.rent_button.setProperty("status", "suspended")
                self.rent_button.setVisible(True)
            elif is_rented_by_other:
                self.rent_button.setText("ถูกเช่า-ยืมไปแล้ว")
                self.rent_button.setEnabled(False)
                self.rent_button.setProperty("status", "unavailable")
                self.rent_button.setVisible(True)
            else: # Rented by current user
                self.rent_button.setVisible(False)
        else: # No user logged in
            self.rent_button.setVisible(False)

        self.return_button.setVisible(status == 'rented' and is_rented_by_current_user)

        self.status_value_label.setText(self.item_data['status'].capitalize())
        self.status_value_label.setProperty("status", self.item_data['status'])

        # Adjust future cost calculator text based on rental status
        if is_rented_by_current_user:
            self.future_cost_title.setText("<b>คำนวณค่าบริการส่วนเพิ่ม (จากเวลาปัจจุบัน)</b>")
            self._reset_future_datetime() # Reset calculator to 'now'
            self.future_cost_label.setText("ค่าบริการส่วนเพิ่ม: 0.00 บาท")
            self.total_future_cost_label.show()
        else:
            self.future_cost_title.setText("<b>คำนวณค่าบริการในอนาคต</b>")
            # When not rented, the "total" cost is the only cost, so we show it in the main label
            # and hide the secondary one.
            self.future_cost_label.setText("ค่าบริการโดยประมาณ: 0.00 บาท")
            self._reset_future_datetime() # Reset calculator to 'now'
            self.total_future_cost_label.hide()

        # Refresh the button's style to apply the new property
        self.rent_button.style().unpolish(self.rent_button)
        self.rent_button.style().polish(self.rent_button)
        # Refresh status label style
        self.status_value_label.style().unpolish(self.status_value_label)
        self.status_value_label.style().polish(self.status_value_label)

        # Update rental duration label visibility and content
        self.update_rental_duration_label()

    def rent_item(self):
        if not self.current_user:
            self.main_window.open_user_login()
            # After login, the main window's current_user is updated.
            # We get the updated user data and retry the rent action.
            self.current_user = self.main_window.current_user
            if self.current_user:
                self.rent_item() # Retry the action automatically
            # If login failed, self.current_user is still None, so we just stop.
            return
        
        if self.item_data.get('status') != 'available':
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ไม่พร้อมใช้งาน", "ของชิ้นนี้ไม่พร้อมให้เช่า-ยืมในขณะนี้")
            return

        reply = CustomMessageBox.show(self, CustomMessageBox.Question, "ยืนยัน", f"คุณ {self.current_user['first_name']}, ต้องการเช่า-ยืมใช่หรือไม่?",
                                      buttons=CustomMessageBox.Yes | CustomMessageBox.No)
        if reply == CustomMessageBox.Yes:
            self.db_instance.rent_item(self.item_id, self.current_user['id'])
            CustomMessageBox.show(self.main_window, CustomMessageBox.Information, "สำเร็จ", f"คุณ {self.current_user['first_name']} ได้เช่า-ยืมเรียบร้อยแล้ว")

    def return_item(self):
        """
        Handles the item return process.
        1. Confirms the user wants to return the item.
        2. Immediately records the return in the database, stopping the rental timer and creating a history record with 'pending' payment status.
        3. If there is an amount due, it automatically opens the payment dialog.
        4. If there is no charge, it simply marks the return and closes.
        """
        # 1. Confirm the return action first.
        reply = CustomMessageBox.show(self, CustomMessageBox.Question, "ยืนยันการส่งคืน",
                                      f"คุณต้องการยืนยันการคืน '{self.item_data['name']}' ใช่หรือไม่?",
                                      buttons=CustomMessageBox.Yes | CustomMessageBox.No)
        if reply != CustomMessageBox.Yes:
            return

        # Re-fetch user data to ensure it's valid before proceeding, preventing crashes.
        current_user_data = self.db_instance.get_user_by_id(self.current_user['id'])
        if not current_user_data:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด",
                                  f"ไม่พบข้อมูลผู้ใช้ ID: {self.current_user['id']} ในระบบ ไม่สามารถดำเนินการคืนได้")
            return

        # 2. Calculate the cost and duration at the moment of return confirmation.
        # --- REFACTORED: This logic was moved from PaymentDialog.calculate_amount() ---
        from datetime import datetime
        rent_date_str = self.item_data.get('rent_date')
        price_per_minute = float(self.item_data.get('price_per_minute', 0.0))
        price_model = self.item_data.get('price_model', 'per_minute')
        fixed_fee = float(self.item_data.get('fixed_fee', 0.0))
        grace_period_minutes = int(self.item_data.get('grace_period_minutes', 0))
        minimum_charge = float(self.item_data.get('minimum_charge', 0.0))

        rent_date = datetime.strptime(str(rent_date_str).split('.')[0], "%Y-%m-%d %H:%M:%S")
        now = datetime.utcnow()
        duration_seconds = (now - rent_date).total_seconds()
        if duration_seconds < 0: duration_seconds = 0

        total_minutes_rented = math.ceil(duration_seconds / 60)
        base_cost = 0.0

        if price_model == 'fixed_fee_only':
            base_cost = fixed_fee
        elif price_model == 'fixed_plus_overdue':
            overdue_minutes = max(0, total_minutes_rented - grace_period_minutes)
            base_cost = fixed_fee + (overdue_minutes * price_per_minute)
        else: # 'per_minute' model
            time_based_cost = total_minutes_rented * price_per_minute
            base_cost = max(time_based_cost, minimum_charge)

        amount_to_charge = round(base_cost, 2)

        days = int(total_minutes_rented // 1440)
        hours = int((total_minutes_rented % 1440) // 60)
        minutes = int(total_minutes_rented % 60)
        duration_str = f"{days} วัน {hours} ชั่วโมง {minutes} นาที"

        # 3. Record the return in the database immediately. This stops the clock.
        transaction_ref = f"MIKA{str(uuid.uuid4().hex)[:12].upper()}" if amount_to_charge > 0.01 else None
        history_id = self.db_instance.return_item(
            item_id=self.item_id,
            amount_due=amount_to_charge,
            transaction_ref=transaction_ref,
            slip_data=None # FIX: Add missing required argument
        )

        # 4. Handle payment.
        if amount_to_charge <= 0:
            CustomMessageBox.show(self.main_window, CustomMessageBox.Information, "สำเร็จ", "บันทึกการส่งคืนเรียบร้อยแล้ว (ไม่มีค่าบริการ)")
        else:
            CustomMessageBox.show(self.main_window, CustomMessageBox.Information, "บันทึกการส่งคืน", "บันทึกการคืนเรียบร้อยแล้ว\nกรุณาชำระค่าบริการในหน้าต่างถัดไป")
            payment_dialog = PaymentDialog(
                item_data=self.item_data,
                user_data=current_user_data,
                parent=self.main_window, # Set main window as parent
                fixed_amount=amount_to_charge,
                fixed_duration=duration_str,
                transaction_ref=transaction_ref,
                db_instance=self.db_instance,
                history_id=history_id
            )
            # --- FIX: Connect the payment dialog signals to a handler ---
            payment_dialog.accepted.connect(lambda: self.on_payment_confirmed(history_id, None))
            payment_dialog.slip_verified.connect(lambda slip_data: self.on_payment_confirmed(history_id, slip_data))
            payment_dialog.open() # Use open() to not block the main event loop

        # Close this detail dialog after handling the return.
        self.accept()

    def on_payment_confirmed(self, history_id: int, slip_data: dict | None):
        """
        Callback for when a payment is confirmed for the item being returned.
        This is connected to the PaymentDialog's signals.
        """
        # The payment dialog already shows a success message.
        # We just need to update the database. The global signal will handle UI refresh.
        self.db_instance.update_payment_status(history_id, 'paid', slip_data=slip_data)

    def _format_grace_period(self, total_minutes: int) -> str:
        """Formats total minutes into a human-readable string (days, hours, minutes)."""
        if total_minutes <= 0:
            return ""
        
        days = total_minutes // 1440
        hours = (total_minutes % 1440) // 60
        minutes = total_minutes % 60
        
        parts = []
        if days > 0: parts.append(f"{days} วัน")
        if hours > 0: parts.append(f"{hours} ชั่วโมง")
        if minutes > 0: parts.append(f"{minutes} นาที")
        return " ".join(parts)

    def _reset_future_datetime(self):
        """Resets the future date and time edits to the current date and time."""
        now = QDateTime.currentDateTime()
        self._update_min_time(now.date())
        self.future_date_edit.setDate(now.date())
        
        # Set slider value
        minutes_of_day = now.time().hour() * 60 + now.time().minute()
        self.time_slider.setValue(minutes_of_day)

    def _add_time(self, unit: str, amount: int):
        """Helper function to add a specified duration to the future date/time edits."""
        # --- REVISED: Construct QDateTime from slider value ---
        slider_value = self.time_slider.value()
        hours = slider_value // 60
        minutes = slider_value % 60
        current_time = QTime(hours, minutes)
        current_dt = QDateTime(self.future_date_edit.date(), current_time)
        # --- END REVISED ---
        
        if unit == "minutes":
            new_dt = current_dt.addSecs(amount * 60)
        elif unit == "hours":
            new_dt = current_dt.addSecs(amount * 3600)
        elif unit == "days":
            new_dt = current_dt.addDays(amount)
        elif unit == "months":
            new_dt = current_dt.addMonths(amount)
        elif unit == "years":
            new_dt = current_dt.addYears(amount)
        else:
            return

        # Update the widgets with the new date and time
        minutes_of_day = new_dt.time().hour() * 60 + new_dt.time().minute()
        self.future_date_edit.setDate(new_dt.date())
        self.time_slider.setValue(minutes_of_day)

    def _on_slider_value_changed(self, value):
        """Updates the time display label and triggers cost calculation."""
        hours = value // 60
        minutes = value % 60
        self.time_display_label.setText(f"{hours:02d}:{minutes:02d}")
        self.calculate_future_cost()

    def update_rental_duration_label(self): # sourcery skip: extract-method
        """Updates the label that shows how long an item has been rented for."""
        status = self.item_data.get('status')
        rent_date = self.item_data.get('rent_date')

        if status == 'rented' and rent_date:
            # --- REFACTORED: Use a consistent method for duration calculation ---
            rent_datetime = QDateTime.fromString(str(rent_date).split('.')[0], "yyyy-MM-dd HH:mm:ss")
            rent_datetime.setTimeSpec(Qt.TimeSpec.UTC)
            # แปลงเป็นเวลาท้องถิ่นก่อนคำนวณ
            offset_hours = app_config.getint('TIME', 'utc_offset_hours', fallback=7)
            offset_seconds = offset_hours * 3600
            local_rent_datetime = rent_datetime.toOffsetFromUtc(offset_seconds)

            # คำนวณจากเวลาท้องถิ่น
            now_local = QDateTime.currentDateTime()

            days = local_rent_datetime.daysTo(now_local)
            hours = (local_rent_datetime.secsTo(now_local) // 3600) % 24
            minutes = (local_rent_datetime.secsTo(now_local) // 60) % 60
            
            duration_str = "{} วัน {} ชั่วโมง {} นาที".format(days, hours, minutes)
            self.rental_duration_value_label.setText(duration_str)
            self.rental_info_group.show()
        else:
            self.rental_duration_value_label.setText("-")
            self.rental_info_group.hide()

    def _update_min_time(self, date: QDate):
        """Update the minimum time if the selected date is today."""
        self.future_date_edit.setMinimumDate(QDate.currentDate())
        if date == QDate.currentDate():
            now = QTime.currentTime()
            min_minutes = now.hour() * 60 + now.minute()
            self.time_slider.setMinimum(min_minutes)
        else:
            self.time_slider.setMinimum(0)

    def calculate_future_cost(self):
        from datetime import datetime
        rent_date_str = self.item_data.get('rent_date')
        price_per_minute = float(self.item_data.get('price_per_minute', 0.0))
        price_model = self.item_data.get('price_model', 'per_minute')
        fixed_fee = float(self.item_data.get('fixed_fee', 0.0))
        grace_period_minutes = int(self.item_data.get('grace_period_minutes', 0))
        minimum_charge = float(self.item_data.get('minimum_charge', 0.0))
        
        # --- REVISED: Construct QDateTime from slider value ---
        slider_value = self.time_slider.value()
        hours = slider_value // 60
        minutes = slider_value % 60
        future_qdatetime = QDateTime(self.future_date_edit.date(), QTime(hours, minutes))
        # --- END REVISED ---
        future_datetime = future_qdatetime.toUTC().toPyDateTime()

        is_rented_by_current_user = (self.current_user and 
                                     self.item_data['status'] == 'rented' and self.item_data['current_renter_id'] == self.current_user['id'])

        if is_rented_by_current_user:
            # --- Rented by current user: Calculate total cost and additional cost ---
            start_date = datetime.strptime(str(rent_date_str).split('.')[0], "%Y-%m-%d %H:%M:%S")

            # Calculate total duration from original rent date to the future date
            total_duration_seconds = (future_datetime - start_date).total_seconds()
            if total_duration_seconds < 0: total_duration_seconds = 0
            total_minutes = math.ceil(total_duration_seconds / 60)

            # Calculate additional duration from now to the future date
            additional_duration_seconds = (future_datetime - datetime.utcnow()).total_seconds()
            if additional_duration_seconds < 0: additional_duration_seconds = 0
            additional_minutes = math.ceil(additional_duration_seconds / 60)

            # Calculate costs based on the price model
            base_cost = 0.0
            if price_model == 'fixed_fee_only':
                base_cost = fixed_fee
                additional_cost = 0 # No additional cost for fixed fee
            elif price_model == 'fixed_plus_overdue':
                overdue_minutes = max(0, total_minutes - grace_period_minutes)
                base_cost = fixed_fee + (overdue_minutes * price_per_minute)
                additional_cost = additional_minutes * price_per_minute
            else: # per_minute model
                time_based_cost = total_minutes * price_per_minute
                base_cost = max(time_based_cost, minimum_charge)
                additional_cost = additional_minutes * price_per_minute

            total_cost = base_cost

            self.future_cost_label.setText(f"ค่าบริการส่วนเพิ่ม: {additional_cost:.2f} บาท")
            self.total_future_cost_label.setText(f"ค่าบริการรวมโดยประมาณ: {total_cost:.2f} บาท")
        else:
            # --- Not rented: Calculate a simple estimation from 'now' ---
            duration_seconds = (future_datetime - datetime.utcnow()).total_seconds()
            if duration_seconds < 0: duration_seconds = 0
            total_minutes = math.ceil(duration_seconds / 60) # ปัดเศษนาทีขึ้นเสมอ
            base_cost = 0.0
            
            if price_model == 'fixed_fee_only':
                base_cost = fixed_fee
            elif price_model == 'fixed_plus_overdue':
                base_cost = fixed_fee + (max(0, total_minutes - grace_period_minutes) * price_per_minute)
            else:
                time_based_cost = total_minutes * price_per_minute
                base_cost = max(time_based_cost, minimum_charge)
            
            calculated_amount = base_cost

            self.future_cost_label.setText(f"ค่าบริการโดยประมาณ: {calculated_amount:.2f} บาท")

    def view_full_image(self, event=None):
        if self.item_data.get('image_path'):
            dialog = ImageViewerDialog(self.item_data['image_path'], self)
            dialog.exec()

    def show_rental_history(self):
        if self.current_user:
            history_dialog = RentalHistoryDialog(self.item_id, self.item_data['name'], self)
            history_dialog.exec()
        else:
            CustomMessageBox.show(self, CustomMessageBox.Information, "กรุณาเข้าสู่ระบบ", "คุณต้องเข้าสู่ระบบก่อนจึงจะสามารถดูประวัติการเช่า-ยืมได้")
            self.main_window.open_user_login()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Rescale image on window resize
        image_data_blob = self.item_data.get('image_path')
        set_image_on_label(self.image_label, image_data_blob, "No Image")

    def showEvent(self, event):
        super().showEvent(event)
        # Ensure button is positioned correctly when the dialog is first shown
        image_data_blob = self.item_data.get('image_path')
        set_image_on_label(self.image_label, image_data_blob, "No Image Available")

    def _handle_data_change(self, table_name: str):
        """Reloads item data if the 'items' table has changed."""
        if table_name == 'items':
            self._reload_data()

    def _reload_data(self):
        """Fetches the latest data for the current item and updates the UI."""
        latest_item_data = self.db_instance.get_item_by_id(self.item_id)
        if latest_item_data:
            self.item_data = latest_item_data
            self._update_ui()

    def closeEvent(self, event: QCloseEvent):
        """Disconnect signals when the dialog is closed."""
        try:
            db_signals.data_changed.disconnect(self._handle_data_change)
        except TypeError: # Signal was not connected or already disconnected
            pass
        super().closeEvent(event)
