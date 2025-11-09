from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QFrame
)
from PyQt6.QtCore import Qt
import qtawesome as qta
from .base_dialog import BaseDialog
from app_payment.payment_handler import PaymentHandler
from .custom_message_box import CustomMessageBox

class PaymentDialog(BaseDialog):
    def __init__(self, item_data, user_data, parent=None, fixed_amount=None, fixed_duration=None):
        super().__init__(parent)
        self.item_data = item_data
        self.user_data = user_data
        self.payment_handler = PaymentHandler()

        self.setWindowTitle(f"ชำระเงินสำหรับ: {self.item_data['name']}")
        self.setMinimumSize(400, 550)

        # --- Calculate Amount or use fixed amount ---
        if fixed_amount is not None:
            self.amount = fixed_amount
            self.duration_str = fixed_duration or "N/A"
        else:
            self.amount, self.duration_str = self.calculate_amount()

        # --- Main Layout ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # --- Header ---
        header_label = QLabel("สแกนเพื่อชำระเงิน")
        header_label.setStyleSheet("font-size: 16pt; font-weight: bold;")
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header_label)

        # --- QR Code ---
        self.qr_label = QLabel("กำลังสร้าง QR Code...")
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setStyleSheet("""
            background-color: white;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 10px;
        """)
        # ใช้ QFrame เพื่อสร้างเงา
        qr_frame = QFrame()
        qr_frame_layout = QVBoxLayout(qr_frame)
        qr_frame_layout.setContentsMargins(0,0,0,0)
        qr_frame_layout.addWidget(self.qr_label)
        qr_frame.setObjectName("QRFrame") # สามารถใช้สำหรับ styling เพิ่มเติม
        
        layout.addWidget(self.qr_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(QLabel("ใช้แอปธนาคารของคุณเพื่อสแกน"), alignment=Qt.AlignmentFlag.AlignCenter)

        # --- Details and Buttons ---
        layout.addWidget(QLabel(f"<h3>ยอดชำระ: <font color='#0078d7'>{self.amount:.2f}</font> บาท</h3>"), alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(QLabel(f"ระยะเวลาเช่า: {self.duration_str}"), alignment=Qt.AlignmentFlag.AlignCenter)

        button_layout = QHBoxLayout()
        send_email_button = QPushButton(qta.icon('fa5s.envelope'), " ส่งบิลไปที่อีเมล")
        send_email_button.clicked.connect(self.send_email)
        
        confirm_payment_button = QPushButton(qta.icon('fa5s.check-circle'), " ยืนยันการชำระเงินและส่งคืน")
        confirm_payment_button.clicked.connect(self.confirm_payment)

        button_layout.addStretch()
        button_layout.addWidget(send_email_button)
        button_layout.addWidget(confirm_payment_button)
        layout.addLayout(button_layout)

        self.generate_and_display_qr()
        self.adjust_and_center()

    def calculate_amount(self):
        from datetime import datetime
        rent_date_str = self.item_data.get('rent_date')
        price_per_minute = float(self.item_data.get('price_per_minute', 0.0))

        if not rent_date_str or price_per_minute <= 0:
            return 0.0, "N/A"

        rent_date = datetime.strptime(str(rent_date_str).split('.')[0], "%Y-%m-%d %H:%M:%S")
        now = datetime.utcnow()
        duration_seconds = (now - rent_date).total_seconds()

        total_minutes_rented = duration_seconds / 60
        calculated_amount = total_minutes_rented * price_per_minute

        # สร้างข้อความแสดงระยะเวลา
        minutes_in_a_day = 1440
        days = int(total_minutes_rented // minutes_in_a_day)
        hours = int((total_minutes_rented % minutes_in_a_day) // 60)
        minutes = int(total_minutes_rented % 60)
        duration_str = "{} วัน {} ชั่วโมง {} นาที".format(days, hours, minutes)
        
        return calculated_amount, duration_str

    def generate_and_display_qr(self):
        if self.amount > 0:
            pixmap = self.payment_handler.generate_qr_code(self.amount)
            if pixmap: # ปรับขนาดให้พอดีกับ Label ที่ยืดหยุ่นได้
                scaled_pixmap = pixmap.scaled(280, 280, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.qr_label.setPixmap(scaled_pixmap)
            else:
                self.qr_label.setText("ไม่สามารถสร้าง QR Code ได้\n(กรุณาตั้งค่า PromptPay)")
        else:
            self.qr_label.setText("ไม่มีค่าใช้จ่าย")

    def send_email(self):
        success, message = self.payment_handler.send_bill_email(
            recipient_email=self.user_data['email'],
            recipient_name=f"{self.user_data.get('first_name', '')} {self.user_data.get('last_name', '')}".strip(),
            item_name=self.item_data['name'],
            amount=self.amount,
            rental_duration=self.duration_str
        )
        icon = CustomMessageBox.Information if success else CustomMessageBox.Warning
        CustomMessageBox.show(self, icon, "ผลการส่งอีเมล", message)

    def confirm_payment(self):
        self.accept()

    def get_amount(self):
        return self.amount
