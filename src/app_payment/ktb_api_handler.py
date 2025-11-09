import requests
from app_config import app_config

class KTBApiHandler:
    def __init__(self, config_source=None):
        self.config_source = config_source if config_source else app_config

        self.api_key = self.config_source.get('KTB_API', 'api_key', fallback='')
        self.api_secret = self.config_source.get('KTB_API', 'api_secret', fallback='')
        self.access_token = None

        is_sandbox = self.config_source.get('KTB_API', 'sandbox_enabled', fallback='True').lower() == 'true'
        if is_sandbox:
            self.base_url = "https://api-sandbox.krungthai.com" # Example Sandbox URL
        else:
            self.base_url = "https://api.krungthai.com" # Example Production URL

    def is_configured(self):
        """Checks if the KTB API is configured."""
        return bool(self.api_key and self.api_secret)

    def _get_access_token(self) -> bool:
        """
        Requests a new access token from KTB API.
        This typically uses OAuth 2.0 client_credentials grant type.
        """
        if not self.is_configured():
            return False
        
        url = f"{self.base_url}/oauth/v2/token"
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.api_key,
            'client_secret': self.api_secret
        }
        try:
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()
            self.access_token = token_data.get('access_token')
            return bool(self.access_token)
        except requests.exceptions.RequestException as e:
            print(f"KTB Auth Error: {e}")
            return False

    # --- Test Methods for Console ---
    def test_authentication(self) -> str:
        """For console testing: Authenticates and returns a status message."""
        if not self.is_configured():
            return "KTB API is not configured in settings."
        
        if self._get_access_token():
            return f"KTB Authentication Successful. Token: {self.access_token[:15]}..."
        else:
            return "KTB Authentication Failed. Check API Key/Secret and network."

    def test_create_qr(self, amount: float) -> str:
        """
        For console testing: Simulates QR creation.
        This method needs to be implemented based on KTB's actual QR code API.
        """
        if not self.is_configured():
            return "KTB API is not configured in settings."
        
        if not self.access_token and not self._get_access_token():
            return "KTB Authentication failed, cannot create QR code."

        # This is a placeholder for the actual KTB QR creation logic.
        # url = f"{self.base_url}/v1/payment/qr/create"
        # ... headers and data for KTB ...
        # response = requests.post(url, ...)
        
        return f"Simulating KTB QR Code creation for {amount:.2f} THB... \n(This function needs to be implemented with actual KTB API specs)"