from flask import Flask, request, jsonify
from threading import Thread
from app_db.db_management import get_db_instance
import logging
from app_config import app_config
import requests
import time
from functools import wraps
import hmac
import hashlib
import base64

# Configure logging to be less verbose in the console
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# --- NEW: Simple In-Memory Rate Limiter ---
rate_limit_tracker = {}

def rate_limit(limit, per_seconds):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Get config settings for rate limiting
            is_enabled = app_config.get('SECURITY', 'webhook_rate_limit_enabled', 'True').lower() == 'true'
            current_limit = app_config.getint('SECURITY', 'webhook_rate_limit_max_requests', limit)
            current_per_seconds = app_config.getint('SECURITY', 'webhook_rate_limit_window_seconds', per_seconds)

            if not is_enabled:
                return f(*args, **kwargs)

            ip = request.remote_addr
            now = time.time()

            # Clean up old entries
            rate_limit_tracker[ip] = [t for t in rate_limit_tracker.get(ip, []) if now - t < current_per_seconds]

            if len(rate_limit_tracker[ip]) >= current_limit:
                print(f"[Webhook Rate Limit] IP {ip} blocked for exceeding rate limit.")
                return jsonify({"status": "error", "message": "Rate limit exceeded"}), 429

            rate_limit_tracker[ip].append(now)
            return f(*args, **kwargs)
        return wrapped
    return decorator
# --- END NEW ---

class WebhookServer:
    def __init__(self, host='0.0.0.0', port=9898, daemon=False):
        self.app = Flask(__name__)
        self.host = host
        self.port = port
        self.thread = None
        self.server_started = False
        self.daemon = daemon

        def shutdown_server():
            """Function to shutdown the Flask server."""
            func = request.environ.get('werkzeug.server.shutdown')
            if func: func()

        # --- Route for SCB Webhook ---
        @self.app.route('/scb/callback', methods=['POST'])
        @rate_limit(limit=20, per_seconds=60) # Default: 20 requests per minute per IP
        def scb_callback():
            """Endpoint to receive payment confirmation from SCB."""
            try:
                # --- NEW: Signature Verification ---
                # Get the signature from the header
                scb_signature = request.headers.get('X-Scb-Signature')
                if not scb_signature:
                    print("[Webhook] SCB callback rejected: Missing X-Scb-Signature header.")
                    return jsonify({"status": "error", "message": "Missing signature"}), 401

                # Get the raw request body
                raw_body = request.get_data()
                
                # Get the API secret from the correct config source
                db_instance = get_db_instance(is_remote=app_config.get('DATABASE', 'enabled', 'False').lower() == 'true')
                api_secret = db_instance.get_system_setting('SCB_API.api_secret')
                if not api_secret:
                    print("[Webhook] SCB callback rejected: API Secret not configured on server.")
                    return jsonify({"status": "error", "message": "Server configuration error"}), 500

                # Calculate our own signature
                digest = hmac.new(api_secret.encode('utf-8'), msg=raw_body, digestmod=hashlib.sha256).digest()
                expected_signature = base64.b64encode(digest).decode('utf-8')

                # Compare signatures in a constant-time manner
                if not hmac.compare_digest(expected_signature, scb_signature):
                    print(f"[Webhook] SCB callback rejected: Invalid signature from IP {request.remote_addr}.")
                    return jsonify({"status": "error", "message": "Invalid signature"}), 403
                # --- END Signature Verification ---

                payload = request.json
                print(f"[Webhook] Received SCB payload: {payload}")

                # Extract key information from the webhook payload
                transaction_id = payload.get('transactionId')
                amount = payload.get('amount')
                # You can add more validation here, e.g., checking the amount

                if not transaction_id:
                    print("[Webhook] Error: transactionId not found in payload.")
                    return jsonify({"status": "error", "message": "Missing transactionId"}), 400

                # Find the corresponding record in the database
                history_record = db_instance.get_history_record_by_transaction_ref(transaction_id)

                if history_record and history_record['payment_status'] == 'pending':
                    # Update payment status to 'paid'
                    # Pass the instance to ensure the email handler uses the same connection
                    db_instance.update_payment_status(history_record['id'], 'paid', db_instance_for_email=db_instance)
                    print(f"[Webhook] Success: Updated payment status for transaction {transaction_id} to 'paid'.")
                elif history_record:
                    print(f"[Webhook] Info: Transaction {transaction_id} already processed.")
                else:
                    print(f"[Webhook] Warning: No pending record found for transaction {transaction_id}.")

                # Do not close the connection here. The get_db_instance() function now manages
                # shared instances, which are closed when the application exits.
                # If it were a dedicated instance, we would close it.
                return jsonify({"status": "success"}), 200

            except Exception as e:
                print(f"[Webhook] Error processing webhook: {e}")
                return jsonify({"status": "error", "message": "Internal server error"}), 500

        # --- Route for SlipOK/Slip2Go Webhook ---
        @self.app.route('/slipok/callback', methods=['POST'])
        @rate_limit(limit=20, per_seconds=60) # Also apply rate limit to SlipOK
        def slipok_callback():
            """Endpoint to receive payment confirmation from SlipOK/Slip2Go."""
            try:
                # --- NEW: Signature Verification for SlipOK ---
                # Assuming SlipOK sends a signature in a header. This is a common practice.
                # The header name 'X-SlipOK-Signature' is an assumption. Please verify with SlipOK documentation.
                slipok_signature = request.headers.get('X-SlipOK-Signature')
                if not slipok_signature:
                    print("[Webhook] SlipOK callback rejected: Missing X-SlipOK-Signature header.")
                    return jsonify({"status": "error", "message": "Missing signature"}), 401

                raw_body = request.get_data()
                
                # Use the API token as the secret key for HMAC
                db_instance = get_db_instance(is_remote=app_config.get('DATABASE', 'enabled', 'False').lower() == 'true')
                api_secret = db_instance.get_system_setting('SLIP_VERIFICATION.api_token')
                if not api_secret:
                    print("[Webhook] SlipOK callback rejected: API Token (secret) not configured on server.")
                    return jsonify({"status": "error", "message": "Server configuration error"}), 500

                # Calculate our own signature
                digest = hmac.new(api_secret.encode('utf-8'), msg=raw_body, digestmod=hashlib.sha256).digest()
                expected_signature = base64.b64encode(digest).decode('utf-8')

                if not hmac.compare_digest(expected_signature, slipok_signature):
                    print(f"[Webhook] SlipOK callback rejected: Invalid signature from IP {request.remote_addr}.")
                    return jsonify({"status": "error", "message": "Invalid signature"}), 403

                payload = request.json
                print(f"[Webhook] Received SlipOK payload: {payload}")

                # Extract key information from the webhook payload
                # NOTE: The payload structure is an assumption. Adjust keys based on actual SlipOK documentation.
                # We assume the transaction reference is in `data.reference1` or `data.ref_1`.
                data = payload.get('data', {})
                transaction_ref = data.get('reference1') or data.get('ref_1')
                is_success = payload.get('isSuccess', False)

                if not transaction_ref:
                    print("[Webhook] Error: Transaction reference (reference1/ref_1) not found in SlipOK payload.")
                    return jsonify({"status": "error", "message": "Missing transaction reference"}), 400

                if not is_success:
                    print(f"[Webhook] Info: Received non-success callback for {transaction_ref}. Ignoring.")
                    return jsonify({"status": "ignored", "message": "Payload was not successful"}), 200

                # Get a database instance appropriate for the current mode
                db_instance = get_db_instance(is_remote=app_config.get('DATABASE', 'enabled', 'False').lower() == 'true')

                history_record = db_instance.get_history_record_by_transaction_ref(transaction_ref)

                if history_record and history_record['payment_status'] == 'pending':
                    db_instance.update_payment_status(history_record['id'], 'paid', db_instance_for_email=db_instance)
                    print(f"[Webhook] Success: Updated payment status for SlipOK transaction {transaction_ref} to 'paid'.")
                elif history_record:
                    print(f"[Webhook] Info: SlipOK transaction {transaction_ref} already processed.")
                else:
                    print(f"[Webhook] Warning: No pending record found for SlipOK transaction {transaction_ref}.")

                return jsonify({"status": "success"}), 200
            except Exception as e:
                print(f"[Webhook] Error processing SlipOK webhook: {e}")
                return jsonify({"status": "error", "message": "Internal server error"}), 500

        @self.app.route('/shutdown', methods=['POST'])
        def shutdown():
            """Endpoint to gracefully shutdown the server."""
            shutdown_server()
            return "Server shutting down..."

    def run_in_thread(self):
        """Runs the Flask server in a separate thread."""
        if not self.thread:
            self.thread = Thread(target=self.app.run, kwargs={'host': self.host, 'port': self.port}, daemon=self.daemon)
            self.thread.start()
            self.server_started = True

    def shutdown(self):
        """Sends a request to the shutdown endpoint to stop the server."""
        # --- FIX: Add more robust checks before attempting shutdown ---
        if not self.server_started or not self.thread or not self.thread.is_alive():
            return
        try:
            # Send a request to the server to trigger its shutdown function
            requests.post(f"http://127.0.0.1:{self.port}/shutdown")
            # Wait for the thread to finish. This is crucial.
            # The timeout prevents the main app from hanging indefinitely if the server fails to shut down.
            self.thread.join(timeout=2.0)
        except requests.exceptions.ConnectionError:
            # This is expected if the server shuts down before the request can complete.
            pass
        except Exception as e:
            # Log any other unexpected errors during shutdown.
            print(f"[Webhook Shutdown] An error occurred during shutdown: {e}")