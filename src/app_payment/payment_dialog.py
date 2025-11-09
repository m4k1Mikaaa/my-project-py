from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QFrame, QApplication, QFileDialog
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QBuffer, QTimer, pyqtSignal
import qtawesome as qta
import uuid
import base64
from app.base_dialog import BaseDialog
from app_db.db_management import db_manager
from app_payment.payment_handler import PaymentHandler
from app_payment.scb_api_handler import SCBApiHandler
from app_config import app_config
from theme import PALETTES
from app_payment.ktb_api_handler import KTBApiHandler
from app_payment.slipok_api_handler import SlipOKApiHandler
from app.custom_message_box import CustomMessageBox
from app_payment.slip_verifier import SlipVerifier
from .camera_capture_dialog import CameraCaptureDialog
from .slip_qr_scanner_dialog import SlipQRScannerDialog
from validators import is_valid_image_data

class PaymentDialog(BaseDialog):
    slip_verified = pyqtSignal(dict) # Signal to emit verified slip data

    # --- REFACTORED: Initialize handlers once in the constructor ---
    def _initialize_handlers(self):
        """Initializes all payment handlers with the correct config source."""
        self.scb_handler = SCBApiHandler(debug=True, config_source=self.config_source)
        self.ktb_handler = KTBApiHandler(config_source=self.config_source)
        self.slipok_handler = SlipOKApiHandler(debug=True, config_source=self.config_source)

    def __init__(self, item_data, user_data, parent=None, fixed_amount=None, fixed_duration=None, transaction_ref=None, db_instance=None, history_id=None):
        super().__init__(parent)
        self.item_data = item_data
        self.user_data = user_data
        # Use the passed db_instance, or get the active one as a fallback.
        self.db_instance = db_instance if db_instance else db_manager.get_active_instance()

        self.history_id = history_id # Store the history ID
        self.transaction_id = transaction_ref # ใช้ transaction_ref ที่ส่งเข้ามา
        self.polling_timer = None
        self.polling_elapsed_time = 0
        self.qr_code_timeout_seconds = 1800 # 30 นาทีสำหรับ SCB QR Code
        self.POLLING_TIMEOUT_SECONDS = 300 # 5 นาที
        self.available_gateways = []
        self.current_gateway_index = 0
        self.qr_image_bytes = None # สำหรับเก็บข้อมูลรูปภาพ QR Code

        # --- FIX: Set the correct config source based on the DB instance ---
        # If the db_instance is for a remote connection (PostgreSQL), it should be the config source.
        # Otherwise (SQLite), fall back to the local app_config (.ini file).
        if self.db_instance and hasattr(self.db_instance.conn, 'get_backend_pid'): # A reliable way to check for psycopg2 connection
            self.config_source = self.db_instance
        else:
            self.config_source = app_config

        # --- REFACTORED: Initialize handlers after config_source is set ---
        self._initialize_handlers()

        self.last_generated_qr_pixmap = None # เก็บ QR Code ล่าสุดที่สร้าง
        self.setWindowTitle(f"ชำระเงินสำหรับ: {self.item_data['name']}")
        self.setMinimumSize(400, 550)

        # --- Use fixed amount and duration passed from the caller ---
        self.amount = fixed_amount if fixed_amount is not None else 0.0
        self.duration_str = fixed_duration or "N/A"
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
        self.qr_info_label = QLabel("ใช้แอปธนาคารของคุณเพื่อสแกน")
        self.qr_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.qr_info_label)

        # --- Transaction Reference with Copy Button ---
        if self.transaction_id:
            ref_container = QWidget()
            ref_layout = QHBoxLayout(ref_container)
            ref_layout.setContentsMargins(0, 5, 0, 5)
            ref_layout.setSpacing(10)
            ref_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            ref_layout.addWidget(QLabel("<b>รหัสอ้างอิง:</b>"))
            ref_label = QLabel(self.transaction_id)
            ref_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            # Use config_source to be compatible with both local and server mode
            current_theme_name = self.config_source.get('UI', 'theme', fallback='light') or 'light'
            icon_color = PALETTES[current_theme_name].get('text', '#000000')

            self.copy_button = QPushButton(qta.icon('fa5s.copy', color=icon_color), "")
            self.copy_button.setObjectName("IconButton") # ใช้สไตล์เดียวกับปุ่มไอคอนอื่นๆ
            self.copy_button.setFixedSize(28, 28)
            self.copy_button.setToolTip("คัดลอกรหัสอ้างอิง")
            self.copy_button.clicked.connect(self.copy_transaction_ref)
            ref_layout.addWidget(ref_label)
            ref_layout.addWidget(self.copy_button)
            layout.addWidget(ref_container)

        # --- Details and Buttons ---
        layout.addWidget(QLabel(f"<h3>ยอดชำระ: <font color='#0078d7'>{self.amount:.2f}</font> บาท</h3>"), alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(QLabel(f"ระยะเวลาเช่า: {self.duration_str}"), alignment=Qt.AlignmentFlag.AlignCenter)

        button_layout = QHBoxLayout()
        # ปุ่มสำหรับเปลี่ยนช่องทาง
        self.switch_gateway_button = QPushButton(qta.icon('fa5s.exchange-alt', color='white'), " เปลี่ยนช่องทาง")
        self.switch_gateway_button.clicked.connect(self.switch_gateway)
        self.switch_gateway_button.setVisible(False) # ซ่อนไว้เป็นค่าเริ่มต้น

        self.send_email_button = QPushButton(qta.icon('fa5s.envelope', color='white'), " ส่งบิลไปที่อีเมล")
        self.send_email_button.clicked.connect(self.send_email)
        
        # ปุ่มสำหรับอัปโหลดสลิป (จะแสดงเมื่อใช้ PromptPay พื้นฐาน)
        self.upload_slip_button = QPushButton(qta.icon('fa5s.upload', color='white'), " อัปโหลดสลิป")
        self.upload_slip_button.clicked.connect(self.upload_and_verify_slip)
        self.upload_slip_button.setVisible(False) # ซ่อนไว้เป็นค่าเริ่มต้น

        # ปุ่มสำหรับถ่ายภาพสลิป
        self.capture_slip_button = QPushButton(qta.icon('fa5s.camera', color='white'), " ถ่ายภาพสลิป")
        self.capture_slip_button.clicked.connect(self.capture_and_verify_slip)
        self.capture_slip_button.setVisible(False) # ซ่อนไว้เป็นค่าเริ่มต้น

        # ปุ่มสำหรับสแกน QR จากสลิป
        self.scan_slip_qr_button = QPushButton(qta.icon('fa5s.qrcode', color='white'), " สแกน QR สลิป")
        self.scan_slip_qr_button.clicked.connect(self.scan_and_verify_slip_qr)
        self.scan_slip_qr_button.setVisible(False) # ซ่อนไว้เป็นค่าเริ่มต้น

        # เปลี่ยนเป็นปุ่มสำหรับปิด หรือเลือกที่จะชำระภายหลัง
        self.close_button = QPushButton(qta.icon('fa5s.times', color='white'), " ชำระภายหลัง / ปิด")
        self.close_button.clicked.connect(self.reject) # ใช้ reject เพื่อบ่งบอกว่ายังไม่สำเร็จ

        button_layout.addStretch()
        button_layout.addWidget(self.switch_gateway_button)
        button_layout.addWidget(self.send_email_button)
        button_layout.addWidget(self.capture_slip_button)
        button_layout.addWidget(self.scan_slip_qr_button)
        button_layout.addWidget(self.upload_slip_button)
        button_layout.addWidget(self.close_button)
        layout.addLayout(button_layout)

        self.generate_and_display_qr()
        self.update_icons() # Set initial icon colors
        self.adjust_and_center()

    def generate_and_display_qr(self):
        if self.amount <= 0:
            self.qr_label.setText("ไม่มีค่าใช้จ่าย")
            self.send_email_button.setEnabled(False)
            return

        # --- Determine gateway priority based on settings ---
        self._setup_gateway_priority()

        if not self.available_gateways:
            error_message = "ยังไม่ได้ตั้งค่าช่องทางการชำระเงิน\nกรุณาตั้งค่าอย่างน้อยหนึ่งช่องทาง:\n- PromptPay (พื้นฐาน)\n- SlipOK/Slip2Go\n- SCB API"
            self.qr_label.setText(error_message)
            self.qr_label.setStyleSheet("background-color: white; color: black;")
            self.send_email_button.setEnabled(False)
            self.close_button.setText("ปิด")
            # Disable all other buttons except close
            for btn in [self.switch_gateway_button, self.upload_slip_button, self.capture_slip_button, self.scan_slip_qr_button]:
                btn.setVisible(False)

        # Show switch button if more than one gateway is available
        if len(self.available_gateways) > 1:
            self.switch_gateway_button.setVisible(True)

        # Generate QR for the first available gateway
        self.current_gateway_index = 0
        self._generate_qr_for_current_gateway()

    def _setup_gateway_priority(self):
        """Sets up the list of available gateways in the correct priority order."""
        # --- REFACTORED LOGIC ---
        # The config_source is now correctly set in the __init__ based on the db_instance.
        # We can now directly read from it.
        
        primary_gateway = self.config_source.get('PAYMENT', 'primary_gateway', fallback='auto')
        priority_str = self.config_source.get('PAYMENT', 'gateway_priority', fallback='slipok,scb,ktb,promptpay')
        
        # --- FIX: Ensure priority_str is a string, not bytes, especially when coming from the DB ---
        if isinstance(priority_str, bytes):
            priority_str = priority_str.decode('utf-8')

        all_gateways_in_order = [key.strip() for key in priority_str.split(',') if key.strip()]

        if primary_gateway != 'auto' and primary_gateway in all_gateways_in_order:
            # If a specific gateway is forced, make it the only one in the list.
            ordered_gateways = [primary_gateway]
        else: # 'auto' or invalid setting
            ordered_gateways = all_gateways_in_order

        # Check which of the ordered gateways are actually configured
        self.available_gateways = []
        for gw in ordered_gateways:
            # The config_source is now correctly set for the entire dialog instance,
            # and the handlers are initialized in the constructor.
            if gw == 'slipok' and self.slipok_handler.is_qr_generation_configured():
                self.available_gateways.append(gw)
            elif gw == 'scb' and self.scb_handler.is_configured():
                self.available_gateways.append(gw)
            elif gw == 'ktb' and self.ktb_handler.is_configured():
                self.available_gateways.append(gw)
            # --- FIX: Use a new PaymentHandler instance with the correct config_source. ---
            # The old code was creating a default PaymentHandler which incorrectly reads from the global app_config.
            elif gw == 'promptpay' and PaymentHandler(config_source=self.config_source).is_configured_for_promptpay():
                self.available_gateways.append(gw)

        # --- FALLBACK: If no other gateways are configured, but local PromptPay is, use it. ---
        if not self.available_gateways and PaymentHandler(config_source=self.config_source).is_configured_for_promptpay():
            print("No API gateways configured. Falling back to basic PromptPay.")
            self.available_gateways.append('promptpay')


    def _generate_qr_for_current_gateway(self):
        """Generates a QR code for the gateway at the current index."""
        if not self.available_gateways:
            return

        # Reset UI state before generating new QR
        self._reset_ui_for_new_qr()

        gateway = self.available_gateways[self.current_gateway_index]
        qr_generated = False

        if gateway == 'slipok':
            print("Attempting to generate QR with SlipOK...")
            qr_generated = self.try_generate_slipok_qr()
        elif gateway == 'scb':
            print("Attempting to generate QR with SCB...")
            qr_generated = self.try_generate_scb_qr()
        elif gateway == 'ktb':
            print("Attempting to generate QR with KTB...")
            qr_generated = self.try_generate_ktb_qr()
        elif gateway == 'promptpay':
            print("Attempting to generate QR with local PromptPay...")
            qr_generated = self.generate_local_qr()

        # --- REFACTORED FALLBACK LOGIC ---
        # If the primary gateway failed to generate a QR, and it wasn't the local promptpay itself,
        # try to generate a local PromptPay QR as a fallback.
        if not qr_generated and gateway != 'promptpay':
            print(f"{gateway.upper()} failed. Falling back to local PromptPay generation.")
            self.qr_info_label.setText("กำลังลองช่องทางสำรอง (PromptPay)...")
            QApplication.processEvents() # Update UI immediately
            qr_generated = self.generate_local_qr()

        # If still no QR code could be generated after all fallbacks, show an error.
        if not qr_generated:
            self.qr_label.setText("ระบบชำระเงินไม่พร้อมใช้งาน\n(ไม่สามารถสร้าง QR Code ได้)")

    def try_generate_slipok_qr(self) -> bool:
        self.qr_label.setText("กำลังเชื่อมต่อกับ SlipOK API...")
        QApplication.processEvents()
        image_b64, error_message = self.slipok_handler.generate_qr_code(self.amount, self.transaction_id)

        if image_b64:
            pixmap = QPixmap()
            self.qr_image_bytes = base64.b64decode(image_b64)
            pixmap.loadFromData(self.qr_image_bytes)
            self.qr_label.setPixmap(pixmap.scaled(280, 280, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            # SlipOK QR might not need polling, assuming it's a standard PromptPay QR.
            # We will rely on manual slip upload/scan for verification.
            self.upload_slip_button.setVisible(True)
            self.capture_slip_button.setVisible(True)
            self.scan_slip_qr_button.setVisible(True)
            return True

        self.qr_label.setText(f"ไม่สามารถสร้าง QR ผ่าน SlipOK\n{error_message}")
        return False

    def try_generate_scb_qr(self) -> bool:
        self.qr_label.setText("กำลังเชื่อมต่อกับ SCB API...")
        QApplication.processEvents()
        raw_data, image_b64, api_transaction_id = self.scb_handler.create_qr_code(self.amount, self.transaction_id)
        if image_b64:
            pixmap = QPixmap()
            self.qr_image_bytes = base64.b64decode(image_b64)
            pixmap.loadFromData(self.qr_image_bytes)
            self.qr_label.setPixmap(pixmap.scaled(280, 280, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            if api_transaction_id: self.transaction_id = api_transaction_id
            self.start_qr_countdown()
            self.start_payment_polling()
            return True
        
        # If we reach here, it means QR generation failed.
        # The error message is already printed to the console by the handler.
        # We set the label text to inform the user and return False to allow fallback.
        self.qr_label.setText("ไม่สามารถเชื่อมต่อ SCB API")
        self.qr_info_label.setText("กำลังลองช่องทางชำระเงินอื่น...")
        QApplication.processEvents() # Update UI immediately
        return False

    def try_generate_ktb_qr(self) -> bool:
        # Placeholder for KTB QR generation. Currently just shows a message.
        self.qr_label.setText("KTB API ยังไม่รองรับการสร้าง QR Code")
        self.qr_info_label.setText("กำลังลองช่องทางชำระเงินอื่น...")
        QApplication.processEvents() # Update UI immediately
        return False # Return False to allow fallback to PromptPay

    def generate_local_qr(self) -> bool:
        local_payment_handler = PaymentHandler(config_source=self.config_source)
        pixmap = local_payment_handler.generate_qr_code(self.amount)
        if pixmap:
            # ดึงข้อมูล bytes จาก pixmap เพื่อใช้ในการส่งอีเมล
            buffer = QBuffer()
            buffer.open(QBuffer.OpenModeFlag.WriteOnly)
            pixmap.save(buffer, "PNG")
            self.qr_image_bytes = buffer.data().data()
            self.last_generated_qr_pixmap = pixmap # บันทึก pixmap ไว้

            scaled_pixmap = pixmap.scaled(280, 280, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.qr_label.setPixmap(scaled_pixmap)
            # แสดงปุ่มอัปโหลดสลิปเมื่อใช้ QR พื้นฐาน
            self.upload_slip_button.setVisible(True)
            self.capture_slip_button.setVisible(True)
            self.scan_slip_qr_button.setVisible(True)
            self.close_button.setText("ปิด") # เปลี่ยนข้อความปุ่ม
            return True
        else:
            self.qr_label.setText("ไม่สามารถสร้าง QR Code ได้\n(กรุณาตั้งค่า PromptPay)")
            return False

    def switch_gateway(self):
        """Cycles to the next available payment gateway and generates a new QR code."""
        if len(self.available_gateways) <= 1:
            return

        # Stop any active polling from the previous gateway
        if self.polling_timer and self.polling_timer.isActive():
            self.polling_timer.stop()
        if hasattr(self, 'qr_countdown_timer') and self.qr_countdown_timer.isActive():
            self.qr_countdown_timer.stop()

        # Move to the next gateway, looping back to the start if necessary
        self.current_gateway_index = (self.current_gateway_index + 1) % len(self.available_gateways)
        self._generate_qr_for_current_gateway()

    def _reset_ui_for_new_qr(self):
        """Resets buttons and labels before generating a new QR code."""
        self.upload_slip_button.setVisible(False)
        self.capture_slip_button.setVisible(False)
        self.scan_slip_qr_button.setVisible(False)
        self.close_button.setText("ชำระภายหลัง / ปิด")

    def _redisplay_last_qr(self):
        """Displays the last successfully generated QR code without regenerating it."""
        if self.last_generated_qr_pixmap:
            scaled_pixmap = self.last_generated_qr_pixmap.scaled(280, 280, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.qr_label.setPixmap(scaled_pixmap)
            # Also make sure the correct buttons are visible for this QR type
            current_gateway = self.available_gateways[self.current_gateway_index]
            if current_gateway in ['promptpay', 'slipok']:
                self.upload_slip_button.setVisible(True)
                self.capture_slip_button.setVisible(True)
                self.scan_slip_qr_button.setVisible(True)
        else:
            # If for some reason there's no last QR, regenerate it as a fallback
            self._generate_qr_for_current_gateway()

    def _set_status_message(self, message: str):
        """Clears the QR pixmap and displays a text message in its place."""
        self.qr_label.clear()
        self.qr_label.setText(message)
        self.qr_label.setStyleSheet("background-color: white; color: black; border: 1px solid #e0e0e0; border-radius: 8px; padding: 10px;")
        QApplication.processEvents()

    def send_email(self):
        email_handler = PaymentHandler(config_source=self.config_source)
        success, message = email_handler.send_bill_email_with_image(
            recipient_email=self.user_data['email'],
            recipient_name=f"{self.user_data.get('first_name', '')} {self.user_data.get('last_name', '')}".strip(),
            item_name=self.item_data['name'],
            amount=self.amount,
            rental_duration=self.duration_str,
            qr_image_bytes=self.qr_image_bytes
        )
        icon = CustomMessageBox.Information if success else CustomMessageBox.Warning
        CustomMessageBox.show(self, icon, "ผลการส่งอีเมล", message)

    def upload_and_verify_slip(self):
        """Handles the slip upload and verification process."""
        slip_verifier = SlipVerifier(config_source=self.config_source)
        if not slip_verifier.is_configured():
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ไม่ได้ตั้งค่า", "ยังไม่ได้ตั้งค่าระบบตรวจสอบสลิป กรุณาติดต่อผู้ดูแล")
            return

        file_name, _ = QFileDialog.getOpenFileName(self, "เลือกไฟล์สลิป", "", "Image Files (*.png *.jpg *.jpeg)")
        if not file_name:
            return

        # --- NEW: Validate file content before processing ---
        with open(file_name, 'rb') as f:
            image_bytes = f.read()
        if not is_valid_image_data(image_bytes):
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ไฟล์ไม่ถูกต้อง", "กรุณาเลือกไฟล์รูปภาพประเภท .png หรือ .jpg เท่านั้น")
            return
        # --- END VALIDATION ---

        # แสดงข้อความว่ากำลังตรวจสอบ
        self._set_status_message("กำลังตรวจสอบสลิป...")
        
        # ใช้ verify_slip_from_path สำหรับไฟล์
        is_valid, message, slip_data = slip_verifier.verify_slip_from_path(file_name, self.amount)

        if is_valid:
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", message)
            self.slip_verified.emit(slip_data)
            self.accept()
        else:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ตรวจสอบไม่สำเร็จ", message)
            # Always redisplay the QR code on any verification failure.
            self._redisplay_last_qr()

    def capture_and_verify_slip(self):
        """Handles slip capture via camera and verification."""
        slip_verifier = SlipVerifier(config_source=self.config_source)
        if not slip_verifier.is_configured():
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ไม่ได้ตั้งค่า", "ยังไม่ได้ตั้งค่าระบบตรวจสอบสลิป กรุณาติดต่อผู้ดูแล")
            return

        capture_dialog = CameraCaptureDialog(self)
        if capture_dialog.exec():
            image_bytes = capture_dialog.get_captured_image_bytes()
            if not image_bytes:
                return

            # แสดงข้อความว่ากำลังตรวจสอบ
            self._set_status_message("กำลังตรวจสอบสลิป...")

            # ใช้ verify_slip_from_bytes สำหรับข้อมูลภาพใน memory
            is_valid, message, slip_data = slip_verifier.verify_slip_from_bytes(image_bytes, self.amount)

            if is_valid:
                CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", message)
                self.slip_verified.emit(slip_data)
                self.accept()
            else:
                CustomMessageBox.show(self, CustomMessageBox.Critical, "ตรวจสอบไม่สำเร็จ", message)
                # Always redisplay the QR code on any verification failure.
                self._redisplay_last_qr()

    def scan_and_verify_slip_qr(self):
        """Handles slip QR scanning and verification."""
        slip_verifier = SlipVerifier(config_source=self.config_source)
        if not slip_verifier.is_configured():
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ไม่ได้ตั้งค่า", "ยังไม่ได้ตั้งค่าระบบตรวจสอบสลิป กรุณาติดต่อผู้ดูแล")
            return

        scanner_dialog = SlipQRScannerDialog(self)
        scanner_dialog.qr_code_found.connect(self.on_slip_qr_found)
        scanner_dialog.exec()

    def on_slip_qr_found(self, qr_data: str):
        """Callback function when the scanner finds a QR code."""
        self._set_status_message("กำลังตรวจสอบข้อมูล QR Code...")

        slip_verifier = SlipVerifier(config_source=self.config_source)
        is_valid, message, slip_data = slip_verifier.verify_slip_from_qr_data(qr_data, self.amount)

        if is_valid:
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", message)
            self.slip_verified.emit(slip_data)
            self.accept() # Close the payment dialog
        else:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ตรวจสอบไม่สำเร็จ", message)
            # Always redisplay the QR code on any verification failure.
            self._redisplay_last_qr()

    def start_payment_polling(self):
        """Starts a timer to periodically check the payment status."""
        if not self.transaction_id:
            return
        
        self.polling_elapsed_time = 0
        self.polling_timer = QTimer(self)
        self.polling_timer.setInterval(5000)  # ตรวจสอบทุก 5 วินาที
        self.polling_timer.timeout.connect(self.check_payment_status)
        self.polling_timer.start()
        self.send_email_button.setEnabled(False) # ปิดการใช้งานปุ่มส่งอีเมลขณะตรวจสอบ
        self.close_button.setEnabled(False) # ปิดปุ่มชำระภายหลังชั่วคราว
        self.update_polling_status_label()

    def check_payment_status(self):
        """The function called by the timer to check payment status via API."""
        if not self.transaction_id:
            if self.polling_timer: self.polling_timer.stop()
            return

        self.polling_elapsed_time += self.polling_timer.interval() / 1000 # เพิ่มเวลาที่ผ่านไป (วินาที)
        self.update_polling_status_label()
        
        is_paid, message = self.scb_handler.inquire_payment_status(self.transaction_id)
        if is_paid:
            self.polling_timer.stop()
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "ตรวจสอบพบการชำระเงินเรียบร้อยแล้ว")
            self.accept() # Signal success
        elif "ไม่สามารถตรวจสอบการชำระเงินได้" in message: # Handle API/network errors
            self.polling_timer.stop()
            CustomMessageBox.show(self, CustomMessageBox.Warning, "การเชื่อมต่อผิดพลาด", message)
            self.qr_label.setText("การเชื่อมต่อล้มเหลว\nกรุณาตรวจสอบอินเทอร์เน็ต")
            self.qr_info_label.setText("-")
            self.close_button.setEnabled(True)
        elif self.polling_elapsed_time >= self.POLLING_TIMEOUT_SECONDS:
            self.polling_timer.stop()
            CustomMessageBox.show(self, CustomMessageBox.Warning, "หมดเวลา", "หมดเวลาในการตรวจสอบการชำระเงิน\nคุณสามารถลองอีกครั้ง หรือเลือกชำระภายหลัง")
            # ล้าง QR Code ออกจากหน้าจอเมื่อหมดเวลา Polling
            self.qr_label.clear()
            self.qr_label.setText("หมดเวลาในการตรวจสอบอัตโนมัติ")
            self.qr_info_label.setText("กรุณาปิดและลองใหม่อีกครั้ง")
            self.close_button.setEnabled(True)
        else:
            # หากยังไม่หมดเวลาและยังไม่จ่าย ก็ให้อัปเดตเวลาของ QR Code ไปด้วย
            pass # Countdown is handled by its own timer now

    def start_qr_countdown(self):
        """Starts a separate timer for the QR code expiration countdown."""
        self.qr_countdown_timer = QTimer(self)
        self.qr_countdown_timer.setInterval(1000) # Update every second
        self.qr_countdown_timer.timeout.connect(self.update_qr_countdown_label)
        self.qr_countdown_timer.start()
        self.update_qr_countdown_label() # Initial update

    def update_polling_status_label(self):
        remaining_seconds = self.POLLING_TIMEOUT_SECONDS - self.polling_elapsed_time
        minutes = int(remaining_seconds // 60)
        seconds = int(remaining_seconds % 60)
        # แสดงเวลา QR Code หมดอายุไปพร้อมกัน
        self.update_qr_countdown_label()

    def update_qr_countdown_label(self):
        """Updates the QR code expiration countdown label."""
        remaining_seconds = self.qr_code_timeout_seconds - self.polling_elapsed_time
        minutes = int(remaining_seconds // 60)
        seconds = int(remaining_seconds % 60)
        self.qr_info_label.setText(f"QR Code นี้จะหมดอายุใน {minutes}:{seconds:02d} นาที")

    def get_amount(self):
        return self.amount

    def copy_transaction_ref(self):
        """Copies the transaction reference to the clipboard and provides visual feedback."""
        if self.transaction_id:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.transaction_id)
            
            original_icon = self.copy_button.icon()
            self.copy_button.setIcon(qta.icon('fa5s.check', color='green'))
            QTimer.singleShot(1500, lambda: self.copy_button.setIcon(original_icon))

    def update_icons(self):
        """Updates icons in the dialog to match the current theme."""
        if hasattr(self, 'copy_button'):
            current_theme_name = self.config_source.get('UI', 'theme', fallback='light')
            palette = PALETTES.get(current_theme_name, PALETTES['light'])
            icon_color = palette.get('text', '#000000')
            self.copy_button.setIcon(qta.icon('fa5s.copy', color=icon_color))

    def closeEvent(self, event):
        """Ensure the timer stops when the dialog is closed."""
        if self.polling_timer:
            self.polling_timer.stop()
        if hasattr(self, 'qr_countdown_timer') and self.qr_countdown_timer:
            self.qr_countdown_timer.stop()
        super().closeEvent(event)
