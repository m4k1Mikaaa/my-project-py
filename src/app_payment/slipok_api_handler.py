import requests
import uuid
import json
from app_config import app_config

class SlipOKApiHandler:
    """Handles all interactions with the SlipOK/Slip2Go API, including verification and QR generation."""
    def __init__(self, debug=False, config_source=None):
        self.debug = debug
        self.config_source = config_source if config_source else app_config
        # Verification settings
        self.verify_api_url = self.config_source.get('SLIP_VERIFICATION', 'api_url', fallback='')
        self.verify_qr_api_url = self.config_source.get('SLIP_VERIFICATION', 'qr_api_url', fallback='')        
        self.check_duplicate = self.config_source.get('SLIP_VERIFICATION', 'check_duplicate', fallback='True').lower() == 'true'
        
        # --- REVISED: Read api_token from both sections for compatibility ---
        # Prioritize the token from the QR generation section. If it's empty, fall back to the verification section's token.
        # This allows a single token in the verification section to be used for both features.
        self.qr_gen_api_token = self.config_source.get('SLIPOK_QR_GEN', 'api_token', fallback='') or self.config_source.get('SLIP_VERIFICATION', 'api_token', fallback='')
        self.verify_api_token = self.config_source.get('SLIP_VERIFICATION', 'api_token', fallback='')

        # Load receiver conditions for verification
        self.receiver_conditions = []
        conditions_str = self.config_source.get('SLIP_VERIFICATION', 'receiver_conditions', fallback='')
        if conditions_str:
            try:
                self.receiver_conditions = json.loads(conditions_str)
            except json.JSONDecodeError:
                print(f"[SlipOK Handler Error] Invalid JSON in receiver_conditions: {conditions_str}") # Keep as print for startup errors

        # QR Generation settings
        self.qr_gen_enabled = self.config_source.get('SLIPOK_QR_GEN', 'enabled', fallback='False').lower() == 'true'
        self.merchant_id = self.config_source.get('SLIPOK_QR_GEN', 'merchant_id', fallback='')
        self.qr_gen_api_url = self.config_source.get('SLIPOK_QR_GEN', 'api_url', fallback='')

    def is_verification_configured(self):
        """Checks if the slip verification part is configured."""
        return bool(self.verify_api_url or self.verify_qr_api_url) and bool(self.verify_api_token)

    def is_qr_generation_configured(self):
        """Checks if the QR code generation part is configured."""
        return self.qr_gen_enabled and bool(self.qr_gen_api_token) and bool(self.merchant_id) and bool(self.qr_gen_api_url)

    def generate_qr_code(self, amount: float, ref1: str) -> tuple[str | None, str | None]:
        """
        Generates a QR code using the SlipOK/Slip2Go API.
        Returns a tuple of (qr_image_base64, error_message).
        """
        if not self.is_qr_generation_configured():
            return None, "SlipOK QR Generation is not configured."

        url = self.qr_gen_api_url
        headers = {
            'Authorization': f'Bearer {self.qr_gen_api_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        # NOTE: The payload structure is an assumption based on common patterns.
        # This may need to be adjusted based on the official SlipOK documentation.
        payload = {
            "qrType": "PP", # Explicitly request a PromptPay QR
            "merchantId": self.merchant_id,
            "amount": f"{amount:.2f}",
            "reference1": ref1,
            "reference2": "MIKARENTAL",
            "detail": "Rental Service Payment",
            "channel": "MOBILE_BANKING" # Specify the payment channel
        }

        try:
            if self.debug:
                print(f"\n--- SlipOK QR Gen Request ---\nURL: POST {url}\nHeaders: {headers}\nPayload: {payload}\n--------------------")

            response = requests.post(url, headers=headers, json=payload, timeout=20)
            response.raise_for_status()
            response_data = response.json()

            if self.debug:
                print(f"\n--- SlipOK QR Gen Response ---\nStatus: {response.status_code}\nBody: {response_data}\n--------------------")

            if response_data.get('isSuccess'):
                # Assuming the API returns a base64 encoded image in `data.qrImage`
                qr_image_b64 = response_data.get('data', {}).get('qrImage')
                return qr_image_b64, None
            else:
                error_message = response_data.get('message', 'Failed to generate QR code.')
                return None, error_message

        except requests.exceptions.RequestException as e:
            error_msg = f"Could not connect to SlipOK QR API: {e}"
            print(f"[SlipOK Handler Error] {error_msg}")
            return None, error_msg

    def verify_slip_from_path(self, image_path: str, expected_amount: float) -> tuple[bool, str, dict | None]:
        """Verifies a payment slip from a file path."""
        if not self.verify_api_url:
            return False, "ยังไม่ได้ตั้งค่า API URL สำหรับอัปโหลดรูปสลิป", None        
        try:
            with open(image_path, 'rb') as image_file:
                files = {'file': (image_path, image_file, 'image/jpeg')}
                # Pass expected_amount to be included in checkCondition
                return self._send_verification_to_api(url=self.verify_api_url, files=files, data={}, expected_amount=expected_amount)
        except FileNotFoundError:
            return False, "ไม่พบไฟล์รูปภาพที่เลือก", None
        except Exception as e:
            return False, f"เกิดข้อผิดพลาดในการอ่านไฟล์: {e}", None

    def verify_slip_from_bytes(self, image_bytes: bytes, expected_amount: float) -> tuple[bool, str, dict | None]:
        """Verifies a payment slip from image bytes."""
        if not self.verify_api_url:
            return False, "ยังไม่ได้ตั้งค่า API URL สำหรับอัปโหลดรูปสลิป", None
        files = {'file': ('captured_slip.jpg', image_bytes, 'image/jpeg')}
        # Pass expected_amount to be included in checkCondition
        return self._send_verification_to_api(url=self.verify_api_url, files=files, data={}, expected_amount=expected_amount)

    def verify_slip_from_qr_data(self, qr_data: str, expected_amount: float) -> tuple[bool, str, dict | None]:
        """Verifies a payment slip from the raw QR data string."""
        if not self.verify_qr_api_url:
            return False, "ยังไม่ได้ตั้งค่า QR API URL สำหรับตรวจสอบสลิป", None
        
        # For QR code verification, we should NOT send the expected amount.
        # The API reads the amount from the QR data and returns it to us.
        # We then perform the amount check on our side after getting the response.
        check_condition = {
            "checkDuplicate": self.check_duplicate
        }
        
        # The receiver conditions from config go inside the 'checkReceiver' key, which is an array.
        if self.receiver_conditions:
            if isinstance(self.receiver_conditions, dict):
                check_condition["checkReceiver"] = [self.receiver_conditions] # Wrap single dict in a list
            else:
                check_condition["checkReceiver"] = self.receiver_conditions

        payload = {
            "payload": {
                "qrCode": qr_data,
                "checkCondition": check_condition
            }
        }
        return self._send_verification_to_api(url=self.verify_qr_api_url, data=payload, expected_amount=expected_amount) # Pass expected_amount for local check

    def _send_verification_to_api(self, url: str, files: dict | None = None, data: dict | None = None, expected_amount: float | None = None) -> tuple[bool, str, dict | None]:
        """Internal method to handle the verification API request."""
        if not self.is_verification_configured():
            return False, "ฟังก์ชันตรวจสอบสลิปยังไม่ได้ถูกตั้งค่า", None

        headers = {'Authorization': f'Bearer {self.verify_api_token}', 'Accept': 'application/json'}
        request_args = {'headers': headers, 'timeout': 30}
        if files: request_args['files'] = files
        # If sending JSON data (like for QR verification), use the 'json' parameter.
        # If sending form data (like for image upload), use the 'data' parameter.
        if data and not files:
            # This is for QR code verification (sends as application/json)
            # The payload is already constructed correctly in verify_slip_from_qr_data
            request_args['json'] = data
        elif files:
            # For image upload (multipart/form-data), the API expects 'checkCondition' as a separate JSON string field.
            form_data = {}
            if expected_amount is not None:
                # --- REVISED LOGIC FOR FORM DATA ---
                # Build the checkCondition object correctly, then convert to JSON string.
                check_condition = {
                    "checkDuplicate": self.check_duplicate,
                    "checkAmount": {"type": "eq", "amount": float(expected_amount)} # amount is a number
                }
                if self.receiver_conditions:
                    # The receiver conditions from config go inside the 'checkReceiver' key.
                    if isinstance(self.receiver_conditions, dict):
                        check_condition["checkReceiver"] = [self.receiver_conditions]
                    else:
                        check_condition["checkReceiver"] = self.receiver_conditions
                form_data['checkCondition'] = json.dumps(check_condition) # Convert the dict to a JSON string

            request_args['data'] = form_data

        try:
            if self.debug:
                print(f"\n--- SlipOK Verification Request ---\nURL: POST {url}\nArgs: {request_args}\n--------------------")

            response = requests.post(url, **request_args)
            response_data = response.json()
            print(f"[SlipOK Handler] Verification Response: {response_data}") # Added for debugging

            # Updated success check based on new documentation (code: "200000", "200200", or "200501")
            # 200000 = Slip is valid and conditions are met.
            # 200200 = Slip is valid, but conditions were not met (e.g., amount mismatch).
            # 200501 = Slip is duplicated.
            # We will check for both, but rely on the presence of 'data' to confirm success.
            if response.status_code >= 400:
                error_message = response_data.get('message', f'API Error with status code {response.status_code}')
                return False, f"ตรวจสอบสลิปไม่สำเร็จ: {error_message}", None

            response_code = str(response_data.get('code'))
            if response_code in ['200000', '200200', '200501'] and response_data.get('data'):
                slip_data = response_data.get('data', {})
                if slip_data and 'amount' in slip_data:
                    # Update sender/receiver name extraction to be more robust against API inconsistencies.
                    # The API has been observed to return 'sender' or 'seender'.
                    sender_info = slip_data.get('sender') or slip_data.get('seender') or {}
                    sender_name = sender_info.get('account', {}).get('name', 'ไม่ระบุ')

                    receiver_name = slip_data.get('receiver', {}).get('account', {}).get('name', 'ไม่ระบุ')
                    slip_amount = float(slip_data.get('amount', -1.0))

                    # Rename 'transactedAt' to 'dateTime' to match new documentation for consistency
                    if 'dateTime' in slip_data and 'transactedAt' not in slip_data:
                        slip_data['transactedAt'] = slip_data['dateTime']

                    # --- Perform amount check locally for all verification types ---
                    # --- FIX: Convert expected_amount to float before comparison ---
                    # This handles cases where expected_amount is a Decimal from the database,
                    # which would cause a TypeError when subtracting a float.
                    if expected_amount is not None and abs(slip_amount - float(expected_amount)) > 0.01:
                        error_message = f"ยอดเงินในสลิป ({slip_amount:.2f}) ไม่ตรงกับยอดที่ต้องชำระ ({expected_amount:.2f})"
                        return False, error_message, slip_data

                    # If the code is 200000 or 200200, the slip data is valid.
                    # 200000: All server-side conditions met.
                    # 200200: Slip is valid, but server-side conditions failed (which is fine if we check locally).
                    if response_code in ['200000', '200200']:
                        success_message = f"ตรวจสอบสำเร็จ: ยอดชำระ {slip_amount:.2f} บาท ถูกต้อง\nจาก: {sender_name}\nถึง: {receiver_name}"
                        return True, success_message, slip_data
                    elif response_code == '200501': # Handle duplicate slip
                        error_message = response_data.get('message', 'สลิปนี้ถูกใช้งานแล้ว')
                        return False, f"ตรวจสอบสลิปไม่สำเร็จ: {error_message}", slip_data

                else:
                    error_message = response_data.get('message', 'API did not return expected slip data.')
                    return False, f"ตรวจสอบสลิปไม่สำเร็จ: {error_message}", None
            else:
                error_message = response_data.get('message', 'ข้อมูลในสลิปไม่ถูกต้องหรือไม่สามารถอ่านได้ (API Error)')
                return False, f"ตรวจสอบสลิปไม่สำเร็จ: {error_message}", None
        except requests.exceptions.Timeout:
            return False, "ไม่สามารถเชื่อมต่อกับเซิร์ฟเวอร์ได้: การเชื่อมต่อหมดเวลา (Connection Timeout)", None
        except requests.exceptions.SSLError as e:
            return False, f"ปัญหาการเชื่อมต่อแบบปลอดภัย (SSL Error):\n{e}\n(อาจเกิดจาก Antivirus หรือ Firewall ขององค์กร)", None
        except requests.exceptions.ConnectionError as e:
            return False, f"ปัญหาการเชื่อมต่อเครือข่าย: {e}\n(อาจเกิดจาก Firewall, Antivirus หรือปัญหาอินเทอร์เน็ต)", None
        except requests.exceptions.RequestException as e:
            return False, f"ไม่สามารถเชื่อมต่อกับเซิร์ฟเวอร์ตรวจสอบสลิปได้: {e}", None
        except Exception as e:
            return False, f"เกิดข้อผิดพลาดในการตรวจสอบสลิป: {e}", None

    def test_authentication(self) -> str:
        """
        For console/UI testing: Checks if the API token is valid by fetching account info.
        Returns a status message.
        """
        # Use the verification token for this test
        if not self.verify_api_token:
            return "ยังไม่ได้ตั้งค่า API Token"

        # Use the specific QR verification URL for the test
        if not self.verify_qr_api_url:
            return "ยังไม่ได้ตั้งค่า API URL (สแกน QR) สำหรับ SlipOK/Slip2Go"

        url = self.verify_qr_api_url # Use the verification URL

        headers = {'Authorization': f'Bearer {self.verify_api_token}', 'Accept': 'application/json'}
        
        # Use a sample payload to test the endpoint, without any conditions.
        # This QR code data is a non-functional example.
        test_payload = {
            "payload": {
                "qrCode": "MIKA-RENTAL-TEST-PAYLOAD"
            }
        }

        try:
            print(f"[SlipOK Test] Sending test request to {url} with payload: {test_payload}")
            response = requests.post(url, headers=headers, json=test_payload, timeout=15)
            response.raise_for_status()
            response_data = response.json()

            # The API should return an error for a fake QR, but a 200 OK status means the connection is good.
            # We check for a specific "slip not found" code or message.
            if str(response_data.get('code')) == '404001' or "Slip not found" in response_data.get('message', ''):
                return "เชื่อมต่อสำเร็จ!\nAPI Token และ URL ถูกต้อง (API ตอบกลับว่าไม่พบสลิปทดสอบ ซึ่งเป็นผลที่คาดหวัง)"
            
            # If we get a 200000, it means the test QR was somehow valid, which is also a success.
            if str(response_data.get('code')) == '200000':
                return "เชื่อมต่อสำเร็จ!\nAPI Token และ URL ถูกต้อง (API ตอบกลับว่าพบสลิปทดสอบ)"

            return f"เชื่อมต่อสำเร็จ แต่ API ตอบกลับสถานะที่ไม่คาดคิด:\nCode: {response_data.get('code')}\nMessage: {response_data.get('message', 'No message')}"
        except requests.exceptions.RequestException as e:
            return f"เชื่อมต่อล้มเหลว: {e}"

    def test_image_upload_authentication(self) -> str:
        """
        For console/UI testing: Checks if the image upload endpoint is reachable.
        It sends an empty request, which should result in a validation error from the API,
        proving that the URL and token are correct.
        """
        if not self.verify_api_token:
            return "ยังไม่ได้ตั้งค่า API Token"

        if not self.verify_api_url:
            return "ยังไม่ได้ตั้งค่า API URL (อัปโหลดรูป) สำหรับ SlipOK/Slip2Go"

        url = self.verify_api_url # Use the verification URL
        headers = {'Authorization': f'Bearer {self.verify_api_token}', 'Accept': 'application/json'}

        try:
            # Send a POST request with no files. The API should reject it with a 422 or similar error.
            response = requests.post(url, headers=headers, timeout=15)
            
            # We expect an error code (like 422 Unprocessable Entity) because we didn't send a file.
            # This proves the endpoint is reachable and the token is likely valid.
            if 400 <= response.status_code < 500:
                return "เชื่อมต่อสำเร็จ!\nAPI Token และ URL (อัปโหลดรูป) ถูกต้อง (API ตอบกลับว่าข้อมูลไม่สมบูรณ์ ซึ่งเป็นผลที่คาดหวัง)"
            return f"เชื่อมต่อสำเร็จ แต่ API ตอบกลับสถานะที่ไม่คาดคิด: {response.status_code}\n{response.text}"
        except requests.exceptions.RequestException as e:
            return f"เชื่อมต่อล้มเหลว: {e}"