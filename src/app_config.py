import configparser
import os
import sys
import base64
import bcrypt
import logging
import subprocess

def get_app_root():
    """
    Determines the root directory for the application's data files.
    - In a PyInstaller bundle, this is the directory containing the executable.
    - In a development environment, this is the project root.
    """
    if hasattr(sys, '_MEIPASS'):
        # Running in a PyInstaller bundle
        return os.path.dirname(sys.executable)
    else:
        # Running in a development environment
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

APP_ROOT = get_app_root()
CONFIG_FILE = os.path.join(APP_ROOT, 'app_config.ini')

class AppConfig:
    def __init__(self, config_path=CONFIG_FILE):
        self.config = configparser.ConfigParser(delimiters=('='))
        self.config_path = config_path
        # This allows a temporary override for specific contexts like the Admin Panel
        self.db_instance_override = None

        if not os.path.exists(self.config_path):
            self.create_default_config()
        else:
            self._load_and_migrate_config()

    def _initialize_encryption(self):
        if not os.path.exists(self.config_path):
            self.create_default_config()
        self.config.read(self.config_path)

        # ตรวจสอบและเพิ่มส่วนที่ขาดหายไปเพื่อความเข้ากันได้กับเวอร์ชันเก่า
        needs_save = False
        if not self.config.has_section('TIMEZONES'):
            self.config['TIMEZONES'] = {
                "UTC+07:00 Bangkok, Hanoi, Jakarta": "7",
                "UTC-08:00 Pacific Time (US & Canada)": "-8",
                "UTC-05:00 Eastern Time (US & Canada)": "-5",
                "UTC-00:00 London, Dublin, Lisbon": "0",
                "UTC+01:00 Berlin, Rome, Paris": "1",
                "UTC+03:00 Moscow, Istanbul": "3",
                "UTC+08:00 Beijing, Singapore, Taipei": "8",
                "UTC+09:00 Tokyo, Seoul": "9",
            }
            needs_save = True
        if not self.config.has_section('PROMPTPAY'):
            self.config['PROMPTPAY'] = {
                'phone_number': ''
            }
            needs_save = True
        if not self.config.has_section('SMTP'):
            self.config['SMTP'] = {
                'host': 'smtp.gmail.com',
                'port': '587',
                'user': 'your_email@gmail.com',
                'password': 'your_app_password'
            }
        if not self.config.has_section('CAMERA'):
            self.config['CAMERA'] = {
                'device_index': '0'
            }
            needs_save = True
        if not self.config.has_section('SLIP_VERIFICATION'):
            self.config['SLIP_VERIFICATION'] = {
                'api_url': '',
                'qr_api_url': '',
                'api_token': ''
            }
            needs_save = True

        if not self.config.has_section('LOCAL_DATABASE'):
            self.config['LOCAL_DATABASE'] = {
                'path': os.path.join(APP_ROOT, 'local_mika_rental.db').replace('\\', '/')
            }
            needs_save = True
        
        if not self.config.has_option('END_ADMIN', 'bypass_console_login'):
            if not self.config.has_section('END_ADMIN'):
                self.config.add_section('END_ADMIN')
            self.config.set('END_ADMIN', 'bypass_console_login', 'False')
            needs_save = True

        if not self.config.has_section('WORKFLOW'):
            self.config['WORKFLOW'] = {
                'auto_confirm_return': 'False'
            }
            needs_save = True

        
        if needs_save:
            self.save_config()

    def load_config(self):
        """Loads the configuration from the .ini file."""
        if not os.path.exists(self.config_path):
            self.create_default_config()
        self.config.read(self.config_path, encoding='utf-8')

    def _load_and_migrate_config(self):
        """
        Loads the config file. Simplified to just read the file.
        """
        if not os.path.exists(self.config_path):
            self.create_default_config()
            return
        self._initialize_encryption()

    def create_default_config(self):
        self.config['DATABASE'] = {
            'enabled': 'False',
            'db_type': 'postgresql',
            'host': 'localhost',
            'port': '5432',
            'database': 'postgres',
            'user': 'postgres',
            'password': ''
        }
        self.config['LOCAL_DATABASE'] = {
            # Use forward slashes for consistency in config files
            'path': os.path.join(APP_ROOT, 'local_mika_rental.db').replace('\\', '/')
        }
        # Hash the default admin password for better security
        default_admin_pass = 'admin1234'
        self.config['END_ADMIN'] = {
            'ID': 'admin',
            'password': default_admin_pass,
            'bypass_console_login': 'False'
        }
        self.config['TIME'] = {
            'utc_offset_hours': '7'
        }
        self.config['UI'] = {
            'theme': 'light',
            'auto_logout_minutes': '15'  # Default to 15 minutes, 0 to disable
        }
        self.config['TIMEZONES'] = {
            "UTC+07:00 Bangkok, Hanoi, Jakarta": "7", # ใช้ : แทน =
            "UTC-08:00 Pacific Time (US & Canada)": "-8", # ใช้ : แทน =
            "UTC-05:00 Eastern Time (US & Canada)": "-5", # ใช้ : แทน =
            "UTC-00:00 London, Dublin, Lisbon": "0", # ใช้ : แทน =
            "UTC+01:00 Berlin, Rome, Paris": "1", # ใช้ : แทน =
            "UTC+03:00 Moscow, Istanbul": "3", # ใช้ : แทน =
            "UTC+08:00 Beijing, Singapore, Taipei": "8", # ใช้ : แทน =
            "UTC+09:00 Tokyo, Seoul": "9", # ใช้ : แทน =
        }
        self.config['PROMPTPAY'] = {
            'phone_number': ''
        }
        self.config['SMTP'] = {
            'enabled': 'False',
            'host': 'smtp.gmail.com',
            'port': '587',
            'user': 'your_email@gmail.com',
            'password': ''
        }
        self.config['PAYMENT'] = {
            'primary_gateway': 'auto'
        }
        self.config['CAMERA'] = {
            'device_index': '0'
        }
        self.config['SLIP_VERIFICATION'] = {
            'api_url': 'https://connect.slip2go.com/api/verify-slip/qr-image/info',
            'qr_api_url': 'https://connect.slip2go.com/api/verify-slip/qr-code/info',
            'api_token': '',
            'receiver_conditions': '[]',
            'check_duplicate': 'True'
        }
        self.config['SLIPOK_QR_GEN'] = {
            'enabled': 'False',
            'merchant_id': '',
            'api_url': 'https://connect.slip2go.com/api/qr-payment/generate-qr-code',
            'api_token': ''
        }

        self.config['WORKFLOW'] = {
            'auto_confirm_return': 'False'
        }

        self.config['CONSOLE_BACKGROUND'] = {
            'path': '',
            'image_opacity': '10', # ค่าเริ่มต้น (0-255)
            'scale': '100', # ค่าเริ่มต้น (1-200%)
            'position': 'bottom right',
            'repeat': 'no-repeat'
        }

        self.config['SHORTCUTS'] = {
            'console': 'AsciiTilde',
            'about': 'F1',
            'admin_local': 'F2',
            'admin_server': 'F3',
            'fullscreen': 'F11'
        }

        self.config['SECURITY'] = {
            'max_failed_attempts': '5',
            'lockout_duration_minutes': '15',
            'failed_attempts': '0',
            'locked_until': '',
            'webhook_rate_limit_enabled': 'True',
            'webhook_rate_limit_max_requests': '20',
            'webhook_rate_limit_window_seconds': '60'
        }


        self.save_config()

    def save_config(self):
        """Saves the configuration to the file in plaintext format."""
        with open(self.config_path, 'w', encoding='utf-8') as configfile:
            self.config.write(configfile)

    def update_config(self, section, option, value):
        """Updates a value in the config and saves the file."""
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, option, str(value))
        self.save_config()

    def get(self, section: str, key: str, fallback=None):
        """Gets a value from the config file."""
        if self.config.has_option(section, key):
            return self.config.get(section, key)
        else:
            return fallback

    def getint(self, section, key, fallback=None):
        """Gets an integer value from the config."""
        value_str = self.get(section, key, fallback=None)
        if value_str is not None:
            try:
                return int(value_str)
            except (ValueError, TypeError):
                return fallback
        return fallback

# Create a single instance to be used throughout the application
app_config = AppConfig(CONFIG_FILE)
