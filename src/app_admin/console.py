from PyQt6.QtWidgets import QVBoxLayout, QTextEdit, QLineEdit, QApplication, QWidget, QStackedLayout, QLabel, QGraphicsOpacityEffect, QGraphicsView
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QColor, QTextCharFormat, QFont, QPixmap, QPainter
import os
import sys
from app.utils import resource_path
from app.base_dialog import BaseDialog
import requests
import cv2
from app_payment.scb_api_handler import SCBApiHandler
from app_config import app_config # Keep this import
from app_setting.local_settings_dialog import LocalSettingsDialog
from app_setting.server_settings_dialog import SystemSettingsDialog # Updated import
from theme import theme
import secrets
from app.custom_message_box import CustomMessageBox
from app_db.db_management import get_db_instance
from app_payment.camera_capture_dialog import CameraCaptureDialog
from theme import PALETTES
from app_payment.ktb_api_handler import KTBApiHandler

class StreamRedirector(QObject):
    """
    A custom stream-like object that redirects stdout/stderr to a PyQt signal.
    """
    messageWritten = pyqtSignal(str)

    def write(self, text):
        # Emit the signal with the text. The receiver will handle threading.
        if text.strip(): # Avoid emitting signals for empty newlines
            self.messageWritten.emit(text)

    def flush(self):
        pass # This is needed for the stream interface.

class BackgroundLabel(QLabel):
    """A custom QLabel to handle background image scaling and positioning."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap = None
        self.scale_percent = 100
        self.position = 'bottom right'

    def set_pixmap(self, pixmap):
        self.pixmap = pixmap
        self.update()

    def set_scale(self, percent):
        self.scale_percent = percent
        self.update()

    def set_position(self, position):
        self.position = position
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.pixmap or self.pixmap.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        widget_size = self.size()
        
        # Calculate scaled pixmap size
        scaled_pixmap = self.pixmap.scaled(
            int(widget_size.width() * (self.scale_percent / 100.0)),
            int(widget_size.height() * (self.scale_percent / 100.0)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        # Calculate position
        px, py = 0, 0
        if 'right' in self.position:
            px = widget_size.width() - scaled_pixmap.width()
        elif 'center' in self.position:
            px = (widget_size.width() - scaled_pixmap.width()) / 2
        
        if 'bottom' in self.position:
            py = widget_size.height() - scaled_pixmap.height()
        elif 'center' in self.position:
            py = (widget_size.height() - scaled_pixmap.height()) / 2

        painter.drawPixmap(int(px), int(py), scaled_pixmap)

class AdminConsole(BaseDialog):
    def __init__(self, main_window_ref):
        # ทำให้ Console เป็นหน้าต่างอิสระ (ไม่มี parent)
        # แต่ยังคงเก็บ reference ของ main_window ไว้เพื่อเรียกใช้ฟังก์ชัน
        super().__init__(parent=None) 
        self.main_window_ref = main_window_ref
        self.admin_panel = None

        self.setWindowTitle("Console")

        # ปรับขนาดหน้าต่าง Console ตามขนาดหน้าจอ
        if main_window_ref and main_window_ref.screen():
            current_screen = main_window_ref.screen()
        else:
            current_screen = QApplication.primaryScreen()
        available_geom = current_screen.availableGeometry()
        self.resize(int(available_geom.width() * 0.6), int(available_geom.height() * 0.8))

        # Make it a top-level window, but its lifecycle is still managed by its parent (MainWindow)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint)
        self.center_on_screen()

        # --- NEW: Use QStackedLayout for background image ---
        container = QWidget()
        layout = QStackedLayout(container)
        layout.setStackingMode(QStackedLayout.StackingMode.StackAll)

        # --- Layer 1: Background Image (Bottom) ---
        self.background_label = BackgroundLabel()
        custom_bg_path = app_config.get('CONSOLE_BACKGROUND', 'path', '')
        if custom_bg_path and os.path.exists(custom_bg_path):
            bg_path = custom_bg_path
        else:
            bg_path = resource_path('app_image/bg.png')
        pixmap = QPixmap(bg_path)
        self.background_label.set_pixmap(pixmap)
        
        # Set scale and position from config
        scale = app_config.getint('CONSOLE_BACKGROUND', 'scale', 100)
        position = app_config.get('CONSOLE_BACKGROUND', 'position', 'bottom right')
        self.background_label.set_scale(scale)
        self.background_label.set_position(position)

        # --- Layer 2: Text Area (Top) ---
        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # --- NEW: Enable text selection by mouse ---
        self.output_area.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.output_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # --- FIX: Use theme color for console text ---
        from theme import PALETTES
        current_theme_name = app_config.get('UI', 'theme', fallback='light')
        text_color = PALETTES[current_theme_name]['text']

        self.output_area.setStyleSheet(f""" /* The text area itself must be transparent to see layers below */
            QTextEdit {{
                background-color: transparent; /* Make the background see-through */
                color: {text_color};
                font-family: 'Consolas', 'Courier New', monospace; font-size: 10pt;
                border: none;
            }}
        """)
        # --- Stacking Order ---
        # 1. Add the image background first (bottom layer).
        layout.addWidget(self.background_label)
        # 2. Add the text area last, so it's on the very top and can be interacted with.
        layout.addWidget(self.output_area)

        # We also need to disable mouse events on the background layers so they don't block text selection.
        image_opacity_effect = QGraphicsOpacityEffect()
        self.background_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        image_opacity = app_config.getint('CONSOLE_BACKGROUND', 'image_opacity', 10)
        image_opacity_effect.setOpacity(image_opacity / 255.0) # Opacity is 0.0 to 1.0
        self.background_label.setGraphicsEffect(image_opacity_effect)

        # --- FIX: Restore the main dialog layout and input line ---
        self.input_line = QLineEdit()
        self.input_line.returnPressed.connect(self.process_command)
        self.input_line.textChanged.connect(self.show_command_hint)
        self.input_line.setStyleSheet("border-top: 1px solid #444; padding: 4px;")

        main_dialog_layout = QVBoxLayout(self)
        main_dialog_layout.setContentsMargins(0, 0, 0, 0)
        main_dialog_layout.setSpacing(0)
        main_dialog_layout.addWidget(container, 1)
        main_dialog_layout.addWidget(self.input_line, 0)

        self.show_help()

        # --- FIX: Restore stdout/stderr redirection ---
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        self.stdout_redirector = StreamRedirector()
        self.stdout_redirector.messageWritten.connect(self.append_debug_text)
        sys.stdout = self.stdout_redirector
        self.stderr_redirector = StreamRedirector()
        self.stderr_redirector.messageWritten.connect(self.append_error_text)
        sys.stderr = self.stderr_redirector

    def _get_theme_color(self, color_name: str, fallback: str | None = None) -> str:
        """Helper to get a color from the current theme's palette."""
        current_theme_name = app_config.get('UI', 'theme', fallback='light')
        palette = PALETTES.get(current_theme_name, PALETTES['light'])
        # Use fallback if the color_name doesn't exist in the palette
        return palette.get(color_name, fallback if fallback is not None else palette['text'])

    def append_debug_text(self, text):
        """Appends debug text from stdout to the console, formatted nicely."""
        # Use a different color to distinguish from regular command output
        self.append_text(f"[stdout] {text.strip()}", self._get_theme_color('disabled_text'))

    def append_error_text(self, text):
        """Appends error text from stderr to the console, formatted nicely."""
        # Prepend with a visual indicator for system errors
        formatted_text = f"[stderr] {text.strip()}"
        self.append_text(formatted_text, self._get_theme_color('danger'))

    def process_command(self):
        command_text = self.input_line.text().strip()
        self.append_text(f"> {command_text}", self._get_theme_color('disabled_text')) # Color for user input
        self.input_line.clear()

        parts = command_text.split()
        command = parts[0].lower() if parts else ""

        if command == "admin":
            if len(parts) > 1 and parts[1].lower() in ["remote", "server"]:
                self.append_text("Opening Admin Panel (Remote Mode)...", self._get_theme_color('info'))
                self.main_window_ref.open_admin_panel(mode='remote')
            else:
                self.append_text("Opening Admin Panel (Local Mode)...", self._get_theme_color('info'))
                self.main_window_ref.open_admin_panel(mode='local')
        elif command == "main":
            self.append_text("Bringing main window to front...", self._get_theme_color('info'))
            if self.main_window_ref:
                self.main_window_ref.show()
                self.main_window_ref.activateWindow()
        elif command == "mode":
            if len(parts) > 1 and parts[1].lower() in ["local", "server"]:
                self.handle_mode_switch(parts[1].lower())
            else:
                self.append_text("Usage: mode <local|server>", self._get_theme_color('warning'))
        elif command == "db":
            if len(parts) > 1:
                sub_command = parts[1].lower()
                if sub_command == "init":
                    self.handle_db_init()
                elif sub_command in ["local", "server"]:
                    # Alias for 'mode' command for backward compatibility
                    self.handle_mode_switch(sub_command)
                else:
                    self.append_text("Usage: db <init|local|server>", self._get_theme_color('warning'))
            else:
                self.append_text("Usage: db <init|local|server>", self._get_theme_color('warning'))
        elif command in ["help", "?", "h"]:
            self.show_help()
        elif command == "force_exit":
            self.output_area.append("Forcing application shutdown...")
            QApplication.processEvents()
            sys.exit(1) # Force exit with a non-zero code to indicate abnormal termination
        elif command in ["exit", "quit"]:
            self.close()
        elif command in ["clear", "cls"]:
            self.output_area.clear()
        elif command == "ping":
            self.handle_ping_command(parts)
        elif command == "list":
            if len(parts) > 1 and parts[1].lower() == "cameras":
                self.handle_list_cameras()
            else:
                self.append_text("Usage: list cameras", self._get_theme_color('warning'))
        elif command == "test":
            if len(parts) < 2:
                self.append_text("Usage: test <target> [args...]", self._get_theme_color('warning'))
                self.append_text("Available targets: api, camera", self._get_theme_color('info'))
                return

            target = parts[1].lower()
            sub_command = parts[2] if len(parts) > 2 else ""

            # --- FIX: Pass the correct config source to the test command ---
            # Determine if we should test against the server DB's config or the local .ini
            is_server_mode = app_config.get('DATABASE', 'enabled', fallback='False').lower() == 'true'
            if is_server_mode:
                # In server mode, the config source for API tests should be the remote DB instance
                config_source = get_db_instance(is_remote=True)
            else:
                # In local mode, the config source is the global app_config (.ini file)
                config_source = app_config

            if target == "api":
                self.handle_test_api(sub_command, parts[3:], config_source)
            elif target == "camera":
                self.handle_test_camera(parts[2:])

        elif command == "set":
            self.handle_set_command(parts)
        elif command == "setting":
            is_remote_mode = len(parts) > 1 and parts[1].lower() in ["remote", "server"]
            if is_remote_mode:
                self.append_text("Opening Server Settings (forced remote connection)...", self._get_theme_color('info'))
                # --- NEW: Require login for remote settings ---
                from app_admin.login import AdminLoginWindow
                login_dialog = AdminLoginWindow(self.main_window_ref, auth_only=True, force_remote_auth=True)
                if login_dialog.exec():
                    db_instance_for_settings = login_dialog.db_instance
                    current_admin_user = login_dialog.user
                    if db_instance_for_settings:
                        settings_dialog = SystemSettingsDialog(main_window_ref=self.main_window_ref, parent=self, db_instance=db_instance_for_settings, current_user=current_admin_user)
                        settings_dialog.exec()
                    else:
                        self.append_text("Error: Login successful but no database instance was returned.", self._get_theme_color('danger'))
                else:
                    self.append_text("Login cancelled or failed.", self._get_theme_color('warning'))
            else:
                self.append_text("Opening Local Settings...", self._get_theme_color('info'))
                # Local settings dialog doesn't need a db_instance
                settings_dialog = LocalSettingsDialog(main_window_ref=self.main_window_ref, parent=self)
                settings_dialog.exec()

        elif command == "reset":
            self.handle_reset_command(parts)
        else:
            self.append_text(f"Error: Unknown command '{command}'", self._get_theme_color('danger'))

    def handle_db_init(self):
        """Handles the 'db init' command by forcing a remote connection."""
        self.append_text("Attempting to initialize server database schema...", self._get_theme_color('info'))
        QApplication.processEvents()
        try:
            # --- FIX: Temporarily enable server mode in config to allow connection ---
            # This allows `init-server` to work even if the server is currently disabled.
            was_enabled = app_config.get('DATABASE', 'enabled', 'False').lower() == 'true'
            if not was_enabled:
                app_config.update_config('DATABASE', 'enabled', 'True')

            # Get the globally managed remote instance.
            # We force a reconnect to ensure we're using the latest .ini settings.
            from app_db.db_management import _get_and_cache_instance
            remote_db = _get_and_cache_instance(is_remote=True, force_reconnect=True)
            if not remote_db or not remote_db.conn:
                raise ConnectionError("Could not connect to the remote database. Check config.")
            
            remote_db.create_remote_tables()
            self.append_text("Successfully created tables on the remote server.", self._get_theme_color('success'))

            # Create a default admin user on the server
            admin_pass = 'admin'
            self.append_text(f"Creating default server admin user 'admin'...", self._get_theme_color('info'))
            success, message = remote_db.create_admin_user('admin', admin_pass)
            if success:
                self.append_text(f"Successfully created admin user 'admin' with password '{admin_pass}'.", self._get_theme_color('success'))
                self.append_text("You can now log in to the remote admin panel.", self._get_theme_color('info'))
            else:
                self.append_text(f"Warning: Could not create admin user. {message}", self._get_theme_color('warning'))
        except Exception as e:
            self.append_text(f"Error initializing server database: {e}", self._get_theme_color('danger'))
        finally:
            # --- FIX: Restore the original 'enabled' setting ---
            if not was_enabled:
                app_config.update_config('DATABASE', 'enabled', 'False')

    def handle_mode_switch(self, mode: str):
        """Handles the 'mode local' or 'mode server' command."""
        success, message = self.main_window_ref.switch_database_mode(mode == 'server')
        self.append_text(message, self._get_theme_color('success') if success else self._get_theme_color('danger'))
        if success:
            self.append_text("All views have been refreshed.", self._get_theme_color('info'))

    def handle_test_api(self, api_name: str, args: list, config_source):
        """Handles 'test api <name>' commands."""
        if not api_name:
            self.append_text("Usage: test api <name> [args...]", self._get_theme_color('warning'))
            self.append_text("Available APIs: scb, ktb, slipok, slipok_qr", self._get_theme_color('info'))
            return

        full_command_name = f"test.{api_name}"
        result = self.main_window_ref.execute_test_command(full_command_name, args, config_source=config_source)
        self.append_text(result, self._get_theme_color('info') if "Success" in result else self._get_theme_color('danger'))

    def handle_list_cameras(self):
        """Handles the 'list cameras' command."""
        self.append_text("Scanning for available cameras...", self._get_theme_color('info'))
        QApplication.processEvents()
        available_cameras = self.main_window_ref.find_available_cameras() if self.main_window_ref else []

        if available_cameras:
            self.append_text(f"Found cameras at indices: {', '.join(map(str, available_cameras))}", self._get_theme_color('success'))
        else:
            self.append_text("No cameras found.", self._get_theme_color('warning'))

    def handle_test_camera(self, args: list):
        """Handles the 'test camera [index]' command."""
        try:
            # Use specified index or the one from config
            index_to_test = int(args[0]) if args else app_config.getint('CAMERA', 'device_index', 0)
            self.append_text(f"Testing camera at index {index_to_test}...", self._get_theme_color('info'))
            # Temporarily set config for the dialog to use
            app_config.update_config('CAMERA', 'device_index', str(index_to_test))
            dialog = CameraCaptureDialog(self)
            dialog.exec()
        except ValueError:
            self.append_text("Error: Invalid camera index. Must be a number.", self._get_theme_color('danger'))
        except Exception as e:
            self.append_text(f"Error opening camera test dialog: {e}", self._get_theme_color('danger'))

    def handle_ping_command(self, parts):
        host = parts[1] if len(parts) > 1 else "google.com"
        url = f"http://{host}"
        self.output_area.append(f"Pinging {url}...")
        QApplication.processEvents()
        try:
            response = requests.get(url, timeout=5)
            if 200 <= response.status_code < 300:
                self.append_text(f"Success! Received response from {host} (Status: {response.status_code})", self._get_theme_color('success'))
            else:
                self.append_text(f"Ping failed: Host responded with status {response.status_code}", self._get_theme_color('warning'))
        except requests.exceptions.RequestException as e:
            self.append_text(f"Ping failed: Could not connect to {host}. Error: {e}", self._get_theme_color('danger'))

    def handle_set_command(self, parts):
        if len(parts) < 3:
            self.append_text("Usage: set <key> <value>", self._get_theme_color('warning'))
            return

        key = parts[1].lower()
        value = " ".join(parts[2:])

        # --- Refactored 'set' command logic ---
        try:
            if key == "theme" and value.lower() in ["light", "dark"]:
                self.main_window_ref.current_theme = value.lower()
                theme.apply_theme(self.main_window_ref.app, self.main_window_ref.current_theme)
                self.main_window_ref.update_theme_dependent_widgets()
                app_config.update_config('UI', 'theme', value.lower())
                self.append_text(f"Theme set to '{value.lower()}'.", "green")
            elif key == "autologout":
                minutes = int(value)
                app_config.update_config('UI', 'auto_logout_minutes', str(minutes))
                self.append_text(f"Auto-logout time set to {minutes} minutes.", "green")
            elif key == "gateway":
                allowed_gateways = ['auto', 'slipok', 'scb', 'ktb', 'promptpay']
                if value.lower() in allowed_gateways:
                    app_config.update_config('PAYMENT', 'primary_gateway', value.lower())
                    self.append_text(f"Primary payment gateway set to '{value.lower()}'.", "green")
                else:
                    self.append_text(f"Error: Invalid gateway. Allowed values are: {', '.join(allowed_gateways)}", "red")
            elif key == "camera":
                index = int(value)
                app_config.update_config('CAMERA', 'device_index', str(index))
                self.append_text(f"Camera device index set to '{index}'.", "green")
            elif '.' in key: # Generic config setter: set section.key value
                section, option = key.split('.', 1)
                app_config.update_config(section.upper(), option, value)
                self.append_text(f"Config '{section.upper()}.{option}' set to '{value}'.", "green")
            else:
                self.append_text(f"Error: Unknown config key '{key}'.", "red")
        except ValueError:
            self.append_text(f"Error: Invalid value type for '{key}'.", "red")
        except Exception as e:
            self.append_text(f"Error setting config: {e}", "red")

    def handle_reset_command(self, parts):
        """Handles the 'reset' command to restore default settings or reset passwords."""
        if len(parts) < 2:
            self.append_text("Usage: reset [config|superadmin]", "orange")
            return

        sub_command = parts[1].lower()

        if sub_command == "config":
            self._handle_reset_config()
        elif sub_command == "superadmin":
            self._handle_reset_superadmin()
        else:
            self.append_text("Usage: reset [config|superadmin]", self._get_theme_color('warning'))

    def _handle_reset_superadmin(self):
        """Handles resetting the Super Admin (ID: 1) password on the server."""
        reply = CustomMessageBox.show(
            self, CustomMessageBox.Question, "ยืนยันการรีเซ็ตรหัสผ่าน",
            "คุณแน่ใจหรือไม่ว่าต้องการรีเซ็ตรหัสผ่านของ Super Admin (ID: 1)?\n"
            "รหัสผ่านใหม่จะถูกสร้างขึ้นและแสดงผลบนหน้าจอนี้",
            buttons=CustomMessageBox.Yes | CustomMessageBox.No
        )

        if reply == CustomMessageBox.Yes:
            try:
                db_instance = get_db_instance(is_remote=True)
                new_password = ''.join(secrets.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for i in range(12))
                db_instance.update_user(1, password=new_password)
                
                self.append_text("Super Admin password has been reset successfully.", self._get_theme_color('success'))
                self.append_text(f"New Password: {new_password}", self._get_theme_color('info'))
            except Exception as e:
                self.append_text(f"Error resetting Super Admin password: {e}", self._get_theme_color('danger'))
        else:
            self.append_text("Operation cancelled.", self._get_theme_color('warning'))

    def _handle_reset_config(self):
        """Handles resetting the local .ini configuration file."""
        try:
            reply = CustomMessageBox.show(
                self, CustomMessageBox.Question, "ยืนยันการรีเซ็ต",
                "คุณแน่ใจหรือไม่ว่าต้องการรีเซ็ตการตั้งค่าทั้งหมดของโปรแกรม (ไฟล์ .ini)?\n"
                "โปรแกรมจำเป็นต้องรีสตาร์ทหลังจากนี้",
                buttons=CustomMessageBox.Yes | CustomMessageBox.No
            )
            if reply == CustomMessageBox.Yes:
                self.append_text("กำลังรีเซ็ตการตั้งค่า...", self._get_theme_color('info'))
                if os.path.exists(app_config.config_path):
                    os.remove(app_config.config_path)
                    self.append_text(f"ลบไฟล์การตั้งค่าเก่าเรียบร้อย: {app_config.config_path}", self._get_theme_color('warning'))
                
                app_config.create_default_config()
                self.append_text("สร้างไฟล์การตั้งค่าเริ่มต้นใหม่เรียบร้อยแล้ว", self._get_theme_color('success'))
                self.append_text("กรุณาปิดและเปิดโปรแกรมใหม่อีกครั้ง", self._get_theme_color('warning'))
            else:
                self.append_text("Operation cancelled.", self._get_theme_color('warning'))
        except Exception as e:
            self.append_text(f"เกิดข้อผิดพลาดระหว่างการรีเซ็ต: {e}", self._get_theme_color('danger'))

    def show_command_hint(self, text):
        """Provides dynamic hints for commands as the user types."""
        # This can be expanded with more complex hint logic if needed.
        # For now, a static placeholder is sufficient.
        self.input_line.setPlaceholderText("Type 'help' or 'h' for a list of commands.")

    def append_text(self, text, color=None):
        """Appends text to the output area with optional color."""
        cursor = self.output_area.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        
        # Check if the text contains HTML tags
        if '<' in text and '>' in text:
            # If it's HTML, insert it as such and add a newline
            cursor.insertHtml(text)
            cursor.insertText("\n")
        else:
            # Otherwise, treat it as plain text and apply the specified color
            char_format = QTextCharFormat()
            if color: # If a specific color is provided, use it
                char_format.setForeground(QColor(color))
            cursor.setCharFormat(char_format)
            cursor.insertText(text + "\n")

        self.output_area.setTextCursor(cursor)
        self.output_area.ensureCursorVisible()

    def show_help(self):
        # --- NEW: Dynamically get shortcut keys from config ---
        shortcuts = {
            'console': app_config.get('SHORTCUTS', 'console', 'AsciiTilde'),
            'admin_local': app_config.get('SHORTCUTS', 'admin_local', 'F2'),
            'admin_server': app_config.get('SHORTCUTS', 'admin_server', 'F3'),
        }

        self.output_area.clear()
        self.append_text(f"--- MiKA Rental Console Help (Press `{shortcuts['console']}` to close) ---", self._get_theme_color('info'))

        commands = {
            "General": {
                "help, ?": "แสดงข้อความช่วยเหลือนี้",
                "clear / cls": "ล้างหน้าจอ Console",
                f"exit, quit": f"ปิดหน้าต่าง Console (`{shortcuts['console']}`)",
            },
            "Application & UI": {
                "main": "แสดงหน้าต่างรายการหลัก",
                "admin": f"เปิด Admin Panel (Local) ({shortcuts['admin_local']})",
                "admin remote": f"เปิด Admin Panel (Server) ({shortcuts['admin_server']})",
                "setting": "เปิดหน้าต่างตั้งค่า Local",
                "setting remote": "เปิดหน้าต่างตั้งค่า Server",
                "set theme <light|dark>": "เปลี่ยนธีมของโปรแกรม",
                "set autologout <minutes>": "ตั้งเวลาออกจากระบบอัตโนมัติ (0 = ปิด)",
            },
            "Database & Admin": {
                "db local": "สลับการใช้งานฐานข้อมูลเป็น Local (SQLite)",
                "db server": "สลับการใช้งานฐานข้อมูลเป็น Server (ที่ตั้งค่าไว้)",
                "db init-server": "สร้างตารางที่จำเป็นทั้งหมดบนฐานข้อมูลเซิร์ฟเวอร์",
            },
            "System & API Testing": {
                "ping [host]": "ทดสอบการเชื่อมต่ออินเทอร์เน็ต (ค่าเริ่มต้น: google.com)",
                "list cameras": "แสดงรายการกล้องที่เชื่อมต่ออยู่",
                "camera test [index]": "ทดสอบกล้องตาม index ที่ระบุ (ค่าเริ่มต้นคือที่ตั้งไว้)",
                "test scb": "ทดสอบการเชื่อมต่อ SCB API",
                "test ktb": "ทดสอบการเชื่อมต่อ KTB API",
                "test slipok": "ทดสอบการเชื่อมต่อ SlipOK (QR/Image)",
                "test slipok_qr <amount>": "ทดสอบสร้าง QR Code ผ่าน SlipOK API",
            },
            "Reset & Maintenance": {
                "reset config": "รีเซ็ตการตั้งค่าทั้งหมดของโปรแกรมเป็นค่าเริ่มต้น",
                "reset superadmin": "รีเซ็ตรหัสผ่านของ Super Admin (ID: 1) บนเซิร์ฟเวอร์",
                "force_exit": "บังคับปิดโปรแกรม (ในกรณีที่ค้าง)",
            },
            "Quick Configuration (set)": {
                "set gateway <value>": "ตั้งค่าช่องทางชำระเงินหลัก (auto, slipok, scb, ktb, promptpay)",
                "set camera.index <index>": "ตั้งค่า Index ของกล้องที่จะใช้งาน",
                "set <api>.<key> <value>": "ตั้งค่า API ต่างๆ (เช่น: set scb.api_key ...)"
            }
        }
        
        for category, cmds in commands.items():
            self.append_text(f"\n--- {category} Commands ---", self._get_theme_color('info')) # Teal
            for cmd, desc in cmds.items():
                # Use theme colors for the help text
                cmd_color = self._get_theme_color('success')
                desc_color = self._get_theme_color('disabled_text')
                self.append_text(f"  <font color='{cmd_color}'>{cmd:<30}</font> <font color='{desc_color}'>// {desc}</font>")

        self.append_text("-" * 80, self._get_theme_color('info'))
        self.output_area.append("\n")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F2:
            self.close()

    def closeEvent(self, event):
        """Restore original stderr when the console is closed."""
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr

        # print("Admin Console closed, stdout/stderr restored.") # Commented out to reduce console noise
        super().closeEvent(event)
