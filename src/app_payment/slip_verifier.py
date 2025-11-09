from .slipok_api_handler import SlipOKApiHandler

class SlipVerifier:
    """Handles verification of payment slips via an external API like SlipOK/Slip2Go."""
    def __init__(self, config_source=None):
        # This class now acts as a facade/wrapper for the SlipOKApiHandler
        # to maintain compatibility with existing code that uses it.
        self.handler = SlipOKApiHandler(config_source=config_source)

    def is_configured(self):
        """Checks if the slip verification API is configured."""
        return self.handler.is_verification_configured()

    def verify_slip_from_path(self, image_path: str, expected_amount: float) -> tuple[bool, str, dict | None]:
        """
        Verifies a payment slip from a file path by sending it to an external API.
        """
        return self.handler.verify_slip_from_path(image_path, expected_amount)

    def verify_slip_from_bytes(self, image_bytes: bytes, expected_amount: float) -> tuple[bool, str, dict | None]:
        """
        Verifies a payment slip from image bytes by sending it to an external API.
        """
        return self.handler.verify_slip_from_bytes(image_bytes, expected_amount)

    def verify_slip_from_qr_data(self, qr_data: str, expected_amount: float) -> tuple[bool, str, dict | None]:
        """
        Verifies a payment slip from the raw QR data string.
        """
        return self.handler.verify_slip_from_qr_data(qr_data, expected_amount)