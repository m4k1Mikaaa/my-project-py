import requests
import uuid
from datetime import datetime
from app_config import app_config
import time

class SCBApiHandler:
    def __init__(self, debug=False, config_source=None):
        # Use the override if provided (for testing), otherwise use the global app_config
        self.config_source = config_source if config_source else app_config

        self.api_key = self.config_source.get('SCB_API', 'api_key', fallback='')
        self.api_secret = self.config_source.get('SCB_API', 'api_secret', fallback='')
        self.app_name = self.config_source.get('SCB_API', 'app_name', fallback='')
        self.callback_url = self.config_source.get('SCB_API', 'callback_url', fallback='')
        self.debug = debug

        # In-memory token storage to avoid frequent disk writes
        self._access_token = None
        self._token_expires_at = 0

        # Biller ID is also essential
        self.biller_id = self.config_source.get('SCB_API', 'biller_id', fallback='')

        # Determine the base URL from settings
        self.is_sandbox = self.config_source.get('SCB_API', 'sandbox_enabled', fallback='True').lower() == 'true'
        if self.is_sandbox:
            self.base_url = "https://api-sandbox.partners.scb" # URL สำหรับ Sandbox
        else:
            self.base_url = "https://api.partners.scb" # Production URL

    def is_configured(self):
        """Checks if the SCB API is configured."""
        # Biller ID is also essential for creating QR codes
        return bool(self.api_key and self.api_secret and self.biller_id)

    def _get_access_token(self) -> tuple[str | None, str | None]:
        """
        Retrieves a valid access token.
        It checks the stored token's expiry date first. If the token is expired or
        doesn't exist, it requests a new one.
        Returns a tuple of (token, error_message).
        """
        if not self.is_configured():
            return None, "SCB API is not configured in settings."

        # Check if the in-memory token is still valid (with a 60-second buffer)
        if self._access_token and self._token_expires_at > time.time() + 60:
            return self._access_token, None

        # If token is invalid or expired, request a new one

        # Correctly construct the path for sandbox and production based on documentation
        path = "/partners/sandbox/v1/oauth/token" if self.is_sandbox else "/partners/v1/oauth/token"
        url = f"{self.base_url}{path}"
        headers = {
            'Content-Type': 'application/json',
            'resourceOwnerId': self.api_key, # Per documentation, this must be the applicationKey (API Key).
            'requestUId': str(uuid.uuid4()),
            'Accept-Language': 'EN', # Required header
            'User-Agent': 'Mika-Rental-Client/1.0',
            'Accept': '*/*'
        }
        data = { # Body as per SCB API documentation
            "applicationKey": self.api_key,
            "applicationSecret": self.api_secret
        }
        try:
            if self.debug:
                print("\n--- SCB Auth Request ---")
                print(f"URL: POST {url}")
                print(f"Headers: {headers}")
                print(f"Body: {data}")

            response = requests.post(url, headers=headers, json=data, timeout=15) # Send as JSON data

            if self.debug:
                print("\n--- SCB Auth Response ---")
                print(f"Status Code: {response.status_code}")
                print(f"Headers: {response.headers}")
                try:
                    print(f"Body: {response.json()}")
                except requests.exceptions.JSONDecodeError:
                    print(f"Body: {response.text}")
                print("--------------------")

            # ตรวจสอบ status code ก่อน raise_for_status เพื่อให้จัดการ error message จาก SCB ได้ดีขึ้น
            if response.status_code != 200:
                error_desc = "Unknown Error"
                try:
                    error_desc = response.json().get('status', {}).get('description', response.reason)
                except requests.exceptions.JSONDecodeError:
                    error_desc = response.reason
                
                # สร้างข้อความ error ที่สื่อความหมายมากขึ้น
                full_error_message = f"Authentication failed with status {response.status_code}: {error_desc}"
                print(f"SCB Auth Error: {full_error_message}")
                
                # กรณีพิเศษสำหรับ API Key/Secret ผิด
                if response.status_code == 401:
                    full_error_message += "\n(This often means the API Key or API Secret is incorrect.)"
                
                return None, full_error_message

            response.raise_for_status()
            token_data = response.json().get('data', {})
            
            access_token = token_data.get('accessToken') # Correct key is 'accessToken'
            expires_at_timestamp = token_data.get('expiresAt') # Correct key is 'expiresAt'

            if not (access_token and expires_at_timestamp):
                error_desc = response.json().get('status', {}).get('description', 'Invalid response body from SCB')
                print(f"SCB Auth Error: {error_desc}")
                return None, f"Authentication failed: {error_desc}"

            self._access_token = access_token
            self._token_expires_at = expires_at_timestamp
            return access_token, None
        except requests.exceptions.Timeout:
            return None, "การเชื่อมต่อเพื่อขอ Token หมดเวลา (Timeout)"
        except requests.exceptions.SSLError as e:
            return None, f"ปัญหาการเชื่อมต่อปลอดภัย (SSL Error): {e}"
        except requests.exceptions.ConnectionError as e:
            return None, f"ปัญหาการเชื่อมต่อเครือข่าย: {e}"
        except requests.exceptions.RequestException as e:
            error_message = f"ไม่สามารถเชื่อมต่อกับ SCB API ได้: {e}"
            print(f"SCB Auth Error: {error_message}")
            return None, error_message
        except Exception as e:
            error_message = f"เกิดข้อผิดพลาดไม่คาดคิดระหว่างการขอ Token: {e}"
            print(f"SCB Auth Error: {error_message}")
            return None, error_message

    def create_qr_code(self, amount: float, ref1: str, ref2: str = "MIKARENTAL", ref3: str = "INV") -> tuple[str | None, str | None, str | None]:
        """
        Requests a QR code for a specific payment.
        ref1 is typically the bill or invoice number.
        """
        access_token, error = self._get_access_token()
        if not access_token:
            print(f"SCB QR Create Error: Could not get access token. Reason: {error}")
            return None, None, None # Return None with no message, caller will handle it

        # Correctly construct the path for sandbox and production based on documentation
        path = "/partners/sandbox/v1/payment/qrcode/create" if self.is_sandbox else "/partners/v1/payment/qrcode/create"
        url = f"{self.base_url}{path}"
        headers = {
            'Content-Type': 'application/json',
            'authorization': f'Bearer {access_token}',
            'resourceOwnerId': self.api_key,
            'requestUId': str(uuid.uuid4()),
            'Accept-Language': 'EN',
            'User-Agent': 'Mika-Rental-Client/1.0'
        }
        payload = {
            "qrType": "PP",
            "ppType": "BILLERID",
            "ppId": self.biller_id,
            "amount": f"{amount:.2f}",
            "ref1": ref1,
            "ref2": ref2,
            "ref3": ref3,
            "expiryTime": 30, # กำหนดให้ QR Code หมดอายุใน 30 นาที
        }
        
        # Only include merchantInfo if a callback URL is actually configured.
        # This makes the polling method cleaner as we don't send an empty/unused callback.
        if self.callback_url:
            payload["merchantInfo"] = {
                "appName": self.app_name,
                "callbackUrl": self.callback_url
            }

        try:
            if self.debug:
                print("\n--- SCB QR Create Request ---")
                print(f"URL: POST {url}")
                print(f"Headers: {headers}")
                print(f"Body: {payload}")

            response = requests.post(url, headers=headers, json=payload, timeout=15) # เพิ่ม Timeout

            if self.debug:
                print("\n--- SCB QR Create Response ---")
                print(f"Status Code: {response.status_code}")
                print(f"Headers: {response.headers}")
                print(f"Body: {response.json()}")
                print("--------------------")

            response.raise_for_status()
            qr_data = response.json().get('data', {})
            # The transactionId is usually the same as the ref1 we sent
            return qr_data.get('qrRawData'), qr_data.get('qrImage'), qr_data.get('transactionId', ref1)
        except requests.exceptions.Timeout:
            print("SCB QR Create Error: Connection timed out.")
            return None, None, None
        except requests.exceptions.RequestException as e:
            print(f"SCB QR Create Error: {e}")
            return None, None, None

    def inquire_payment_status(self, transaction_id: str) -> tuple[bool, str]:
        """
        Inquires about the status of a specific bill payment transaction.
        """
        access_token, error = self._get_access_token()
        if not access_token:
            return False, f"ไม่สามารถยืนยันตัวตนกับ SCB ได้: {error}"

        # Correctly construct the path for sandbox and production
        # The base_url for sandbox is "https://api-sandbox.partners.scb/partners", so the path should start with "/sandbox/v1/..."
        path = "/partners/sandbox/v1/payment/billpayment/inquiry" if self.is_sandbox else "/partners/v1/payment/billpayment/inquiry"
        url = f"{self.base_url}{path}"
        headers = {
            'Content-Type': 'application/json',
            'authorization': f'Bearer {access_token}',
            'resourceOwnerId': self.api_key,
            'requestUId': str(uuid.uuid4()),
            'Accept-Language': 'EN',
            'User-Agent': 'Mika-Rental-Client/1.0'
        }

        # Per documentation, this is a POST request with a JSON body.
        payload = {
            'billerId': self.biller_id,
            'reference1': transaction_id,
            # SCB API (both sandbox and production) expects YYYY-MM-DD format for this endpoint.
            'transactionDate': datetime.now().strftime('%Y-%m-%d'),
            'eventCode': '00300100' # Fixed value as per documentation
        }
        try:
            if self.debug:
                print("\n--- SCB Inquiry Request ---")
                print(f"URL: POST {url}")
                print(f"Headers: {headers}")
                print(f"Body: {payload}")

            response = requests.post(url, headers=headers, json=payload, timeout=15)

            if self.debug:
                print("\n--- SCB Inquiry Response ---")
                print(f"Status Code: {response.status_code}")
                print(f"Headers: {response.headers}")
                print(f"Body: {response.json()}")
                print("--------------------")

            response.raise_for_status()
            inquiry_data = response.json()
            
            # Check if the transaction was successful
            if inquiry_data.get('status', {}).get('code') == 1000 and inquiry_data.get('data'):
                return True, "ชำระเงินสำเร็จ"
            else:
                # ให้ข้อมูลเพิ่มเติมหากไม่สำเร็จ
                error_desc = inquiry_data.get('status', {}).get('description', 'Transaction not found or not yet paid')
                return False, f"ยังไม่พบรายการชำระเงิน: {error_desc}"
        except requests.exceptions.Timeout:
            return False, "การเชื่อมต่อเพื่อตรวจสอบสถานะหมดเวลา (Timeout)"
        except requests.exceptions.SSLError as e:
            return False, f"ปัญหาการเชื่อมต่อปลอดภัย (SSL Error): {e}"
        except requests.exceptions.ConnectionError as e:
            return False, f"ปัญหาการเชื่อมต่อเครือข่าย: {e}"
        except requests.exceptions.RequestException as e:
            return False, f"ไม่สามารถตรวจสอบการชำระเงินได้เนื่องจาก: {e}"

    # --- Test Methods for Console ---
    def test_authentication(self) -> str:
        """For console testing: Authenticates and returns a status message."""
        if not self.is_configured():
            return "SCB API is not configured in settings."
        
        token, error = self._get_access_token()
        if token:
            return "Authentication Successful. A new token has been obtained and stored."
        else:
            return f"Authentication Failed: {error}"

    def test_create_qr(self, amount: float) -> str:
        """For console testing: Creates a QR and returns a status message."""
        if not self.is_configured():
            return "SCB API is not configured in settings."

        # A unique reference for testing
        test_ref = f"TEST{str(uuid.uuid4())[:8]}"
        raw_data, image_data, trans_id = self.create_qr_code(amount, test_ref)

        if raw_data and image_data:
            return f"QR Code creation successful!\nRaw Data: {raw_data[:50]}...\nImage Data (Base64): {image_data[:50]}..."
        else:
            return "QR Code creation failed. Check console logs for details."

    # คุณจะต้องเพิ่มฟังก์ชันสำหรับตรวจสอบสถานะการชำระเงิน (Payment Inquiry) ที่นี่
    # โดยปกติจะใช้ transactionId ที่ได้จากตอนสร้าง QR Code
    # def verify_payment(self, transaction_id: str) -> bool:
    #     ...
    #     return True # if paid