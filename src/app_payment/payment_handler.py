import qrcode
from promptpay import qrcode as pp_qrcode
from PIL import Image
from io import BytesIO
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QDateTime, Qt
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime
from app_config import app_config
from app_db.db_management import db_manager

class PaymentHandler:
    def __init__(self, scb_api_handler=None, db_instance=None, config_source=None):
        self.config_source = config_source if config_source else app_config
        self.promptpay_phone = self.config_source.get('PROMPTPAY', 'phone_number', fallback='')
        self.scb_api_handler = scb_api_handler
        # Use the passed db_instance, or get the globally active one as a fallback.
        self.db_instance = db_instance if db_instance else db_manager.get_active_instance()

    def is_configured(self) -> bool:
        """Checks if the local PromptPay method is configured."""
        return self.is_configured_for_promptpay() or (self.scb_api_handler and self.scb_api_handler.is_configured())

    def is_configured_for_promptpay(self) -> bool:
        """Checks if only the local PromptPay method is configured."""
        # A payment method is considered configured if either local PromptPay is set
        # OR an external API handler (like SCB) is configured.
        return bool(self.promptpay_phone)

    def generate_qr_code(self, amount: float) -> QPixmap:
        """
        Generates a PromptPay QR code for the given amount.
        Returns a QPixmap for display.
        """
        if not self.promptpay_phone:
            return None

        try:
            payload = pp_qrcode.generate_payload(self.promptpay_phone, amount)
            img = qrcode.make(payload)
            
            # Convert PIL image to QPixmap
            buffer = BytesIO()
            img.save(buffer, "PNG")
            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue())
            return pixmap
        except Exception as e:
            print(f"Error generating QR code: {e}")
            return None

    def get_qr_code_image_bytes(self, amount: float) -> bytes:
        """
        Generates a PromptPay QR code and returns it as PNG image bytes.
        """
        if not self.promptpay_phone:
            return None
        try:
            payload = pp_qrcode.generate_payload(self.promptpay_phone, amount)
            img = qrcode.make(payload)
            buffer = BytesIO()
            img.save(buffer, "PNG")
            return buffer.getvalue()
        except Exception as e:
            print(f"Error getting QR code image bytes: {e}")
            return None

    @staticmethod
    def send_test_email(config_source) -> tuple[bool, str]:
        """
        A static method to send a test email using provided SMTP settings.
        `config_source` is an object that has a `get` and `getint` method, like AppConfig.
        """
        sender_email = config_source.get('SMTP', 'user')
        if not config_source.get('SMTP', 'enabled', fallback='True').lower() == 'true':
            return False, "การส่งอีเมลไม่พร้อมใช้งาน"

        password = config_source.get('SMTP', 'password')
        smtp_host = config_source.get('SMTP', 'host')
        smtp_port = config_source.getint('SMTP', 'port')

        if not all([sender_email, password, smtp_host, smtp_port]) or 'your_email' in sender_email:
            return False, "การตั้งค่า SMTP ยังไม่สมบูรณ์"

        # The recipient is the same as the sender for the test
        recipient_email = sender_email

        msg = MIMEMultipart()
        msg['Subject'] = "Mika Rental - Test Email"
        msg['From'] = sender_email
        msg['To'] = recipient_email

        html_body = f"""
        <h3>This is a test email from Mika Rental.</h3>
        <p>If you received this, your SMTP settings are configured correctly.</p>
        <p><b>Host:</b> {smtp_host}<br>
           <b>Port:</b> {smtp_port}<br>
           <b>User:</b> {sender_email}</p>
        """
        msg.attach(MIMEText(html_body, 'html'))

        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(sender_email, password)
                server.sendmail(sender_email, recipient_email, msg.as_string())
            return True, f"ส่งอีเมลทดสอบไปยัง '{recipient_email}' สำเร็จ!"
        except Exception as e:
            return False, f"ไม่สามารถส่งอีเมลได้: {e}"

    def send_bill_email_with_image(self, recipient_email: str, recipient_name: str, item_name: str, amount: float, rental_duration: str, qr_image_bytes: bytes) -> tuple[bool, str]:
        """
        Sends a bill with a pre-generated QR code image to the user's email.
        The QR code image is passed as bytes.
        """
        sender_email = app_config.get('SMTP', 'user')
        # Check if email sending is enabled first
        if not self.config_source.get('SMTP', 'enabled', fallback='True').lower() == 'true':
            return False, "การส่งอีเมลไม่พร้อมใช้งาน"

        password = app_config.get('SMTP', 'password')
        smtp_host = app_config.get('SMTP', 'host')
        smtp_port = app_config.getint('SMTP', 'port')

        if not all([sender_email, password, smtp_host, smtp_port]) or 'your_email' in sender_email:
            return False, "SMTP settings are not configured."

        # Create the email
        msg = MIMEMultipart('related')
        msg['Subject'] = f"ใบแจ้งค่าบริการสำหรับ {item_name}"
        msg['From'] = sender_email
        msg['To'] = recipient_email

        # Email body
        billing_date = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        html_body = f"""
        <!DOCTYPE html>
        <html lang="th">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Tahoma', sans-serif;
                    background-color: #f4f4f4;
                    margin: 0;
                    padding: 0;
                }}
                .container {{
                    max-width: 600px;
                    margin: 20px auto;
                    background-color: #ffffff;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                }}
                .header {{
                    background-color: #0078d7;
                    color: #ffffff;
                    padding: 20px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 24px;
                }}
                .content {{
                    padding: 30px;
                }}
                .content h2 {{
                    color: #333333;
                    font-size: 20px;
                }}
                .details-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 20px;
                }}
                .details-table td {{
                    padding: 8px 0;
                    border-bottom: 1px solid #eeeeee;
                }}
                .details-table td:first-child {{
                    font-weight: bold;
                    color: #555555;
                }}
                .total {{
                    text-align: center;
                    margin: 20px 0;
                }}
                .total p {{
                    font-size: 18px;
                    color: #333333;
                }}
                .total .amount {{
                    font-size: 28px;
                    font-weight: bold;
                    color: #0078d7;
                }}
                .qr-section {{
                    text-align: center;
                    margin-top: 20px;
                }}
                .footer {{
                    text-align: center;
                    padding: 20px;
                    font-size: 12px;
                    color: #888888;
                    background-color: #f9f9f9;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>MiKA RENTAL</h1>
                </div>
                <div class="content">
                    <h2>ใบแจ้งค่าบริการ</h2>
                    <table class="details-table">
                        <tr><td>วันที่ออกบิล:</td><td>{billing_date}</td></tr>
                        <tr><td>สำหรับคุณ:</td><td>{recipient_name}</td></tr>
                        <tr><td>รายการ:</td><td>{item_name}</td></tr>
                        <tr><td>ระยะเวลาเช่า:</td><td>{rental_duration}</td></tr>
                    </table>
                    <div class="total">
                        <p>ยอดชำระทั้งหมด</p>
                        <p class="amount">{amount:.2f} บาท</p>
                    </div>
                    <div class="qr-section">
                        <p>กรุณาสแกน QR Code ด้านล่างเพื่อชำระเงิน</p>
                        <img src="cid:qrcode_image" alt="PromptPay QR Code" style="max-width: 250px; margin-top: 10px;">
                    </div>
                </div>
                <div class="footer">
                    <p>ขอบคุณที่ใช้บริการ</p>
                </div>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_body, 'html'))

        # Attach QR code image
        if not qr_image_bytes:
            return False, "ไม่มีข้อมูลรูปภาพ QR Code ที่จะส่ง"

        image = MIMEImage(qr_image_bytes, name="qrcode.png")
        image.add_header('Content-ID', '<qrcode_image>')
        msg.attach(image)

        # Send the email
        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(sender_email, password)
                server.sendmail(sender_email, recipient_email, msg.as_string())
            return True, "ส่งอีเมลสำเร็จ"
        except Exception as e:
            return False, f"ไม่สามารถส่งอีเมลได้: {e}"

    def send_receipt_email(self, history_id: int) -> tuple[bool, str]:
        """
        Sends a payment receipt email based on a rental history record.
        Uses the db_instance provided during initialization.
        """

        # 1. Fetch all necessary data from the database
        history_record = self.db_instance.get_history_record_by_id(history_id)
        if not history_record:
            return False, "ไม่พบข้อมูลประวัติการเช่า"

        user_data = self.db_instance.get_user_by_id(history_record['user_id'])
        if not user_data:
            return False, "ไม่พบข้อมูลผู้ใช้"
        item_data = self.db_instance.get_item_by_id(history_record['item_id'])
        if not item_data:
            return False, "ไม่พบข้อมูลสินค้า"

        # Check if email sending is enabled first
        if not self.config_source.get('SMTP', 'enabled', fallback='True').lower() == 'true':
            return False, "การส่งอีเมลไม่พร้อมใช้งาน"

        # 2. Check SMTP configuration
        sender_email = app_config.get('SMTP', 'user')
        password = app_config.get('SMTP', 'password')
        smtp_host = app_config.get('SMTP', 'host')
        smtp_port = app_config.getint('SMTP', 'port')

        if not all([sender_email, password, smtp_host, smtp_port]) or 'your_email' in sender_email:
            return False, "SMTP settings are not configured."

        # 3. Prepare email content
        recipient_email = user_data['email']
        recipient_name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
        item_name = item_data['name']
        amount_paid = history_record['amount_due']
        
        payment_date_utc = QDateTime.fromString(str(history_record['payment_date']).split('.')[0], "yyyy-MM-dd HH:mm:ss")
        payment_date_utc.setTimeSpec(Qt.TimeSpec.UTC)
        offset_hours = app_config.getint('TIME', 'utc_offset_hours', fallback=7)
        payment_date_local = payment_date_utc.toOffsetFromUtc(offset_hours * 3600)
        payment_date_str = payment_date_local.toString("dd/MM/yyyy HH:mm:ss")

        transaction_ref = history_record.get('transaction_ref', 'N/A')

        # 4. Create the email message
        msg = MIMEMultipart('related')
        msg['Subject'] = f"ใบเสร็จรับเงินสำหรับ {item_name}"
        msg['From'] = sender_email
        msg['To'] = recipient_email

        html_body = f"""
        <!DOCTYPE html>
        <html lang="th">
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Tahoma', sans-serif; background-color: #f4f4f4; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }}
                .header {{ background-color: #27ae60; color: #ffffff; padding: 20px; text-align: center; border-top-left-radius: 8px; border-top-right-radius: 8px; }}
                .header h1 {{ margin: 0; font-size: 24px; }}
                .content {{ padding: 30px; }}
                .content h2 {{ color: #333333; font-size: 20px; border-bottom: 2px solid #eeeeee; padding-bottom: 10px; }}
                .details-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                .details-table td {{ padding: 10px 0; border-bottom: 1px solid #eeeeee; }}
                .details-table td:first-child {{ font-weight: bold; color: #555555; width: 40%; }}
                .total {{ text-align: right; margin-top: 20px; }}
                .total p {{ font-size: 18px; color: #333333; margin: 5px 0; }}
                .total .amount {{ font-size: 28px; font-weight: bold; color: #27ae60; }}
                .footer {{ text-align: center; padding: 20px; font-size: 12px; color: #888888; background-color: #f9f9f9; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>ใบเสร็จรับเงิน</h1>
                </div>
                <div class="content">
                    <h2>ขอบคุณที่ใช้บริการ MiKA RENTAL</h2>
                    <p>เรียนคุณ {recipient_name},</p>
                    <p>เราได้รับชำระเงินของคุณเรียบร้อยแล้ว นี่คือรายละเอียดการทำรายการของคุณ:</p>
                    <table class="details-table">
                        <tr><td>วันที่ชำระเงิน:</td><td>{payment_date_str}</td></tr>
                        <tr><td>รายการ:</td><td>{item_name}</td></tr>
                        <tr><td>รหัสอ้างอิง:</td><td>{transaction_ref}</td></tr>
                    </table>
                    <div class="total">
                        <p>ยอดชำระทั้งหมด</p>
                        <p class="amount">{amount_paid:.2f} บาท</p>
                    </div>
                </div>
                <div class="footer">
                    <p>ขอบคุณที่ใช้บริการ</p>
                </div>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_body, 'html'))

        # 5. Send the email
        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(sender_email, password)
                server.sendmail(sender_email, recipient_email, msg.as_string())
            return True, "ส่งใบเสร็จรับเงินสำเร็จ"
        except Exception as e:
            # Log the error but don't block the main process
            print(f"ไม่สามารถส่งใบเสร็จรับเงินสำหรับ history_id {history_id} ได้: {e}")
            return False, f"ไม่สามารถส่งอีเมลได้: {e}"
