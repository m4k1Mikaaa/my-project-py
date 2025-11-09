import sys
from PyQt6.QtWidgets import QApplication, QMessageBox, QFileDialog, QPushButton
from PyQt6.QtCore import Qt

def run_admin_tool():
    """
    Main function to run the standalone admin configuration tool.
    """
    # 1. Create QApplication instance first.
    app = QApplication(sys.argv)

    # --- FIX: Set AppUserModelID for Windows Taskbar Icon ---
    # This ensures the standalone tool uses the same taskbar icon identity.
    if sys.platform == 'win32':
        import ctypes
        myappid = 'nivara.mika_rental.1.0' # Must be the same as in main.py
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    # 2. Import other modules after app creation.
    try:
        from app_config import AppConfig, get_app_root, app_config as global_app_config
        from app_db.db_management import initialize_databases, db_manager, get_db_instance
        from theme import theme, apply_theme
        from app_admin.login import AdminLoginWindow
        from app_setting.local_settings_dialog import LocalSettingsDialog
        from app_setting.server_settings_dialog import SystemSettingsDialog # Updated import
        from app.utils import get_icon
    except ImportError as e:
        QMessageBox.critical(None, "Import Error", f"Failed to import a required module: {e}\nPlease ensure all dependencies are installed.")
        sys.exit(1)

    try:
        # 3. Load theme and set icon. We don't initialize the main DB here.
        # Use the global config instance which reads the default app_config.ini
        current_theme = global_app_config.get('UI', 'theme', fallback='light')
        theme.apply_theme(app, current_theme) # Apply theme before showing any dialog
        app.setWindowIcon(get_icon("app_image/icon.ico"))

        # 4. Show Admin Login window. This tool always uses local auth.
        login_dialog = AdminLoginWindow(main_window_ref=None, auth_only=True, force_local_auth=True)
        if login_dialog.exec():
            # 5. On successful login, ask user which mode they want to configure.
            msg_box = QMessageBox()
            msg_box.setWindowTitle("เลือกโหมดการตั้งค่า")
            msg_box.setText("คุณต้องการแก้ไขการตั้งค่าสำหรับโหมดใด?")
            msg_box.setIcon(QMessageBox.Icon.Question)
            local_button = msg_box.addButton("แก้ไขไฟล์ Local (.ini)", QMessageBox.ButtonRole.ActionRole)
            server_button = msg_box.addButton("แก้ไขบน Server", QMessageBox.ButtonRole.ActionRole)
            msg_box.exec()

            clicked_button = msg_box.clickedButton()

            if clicked_button == local_button:
                # --- Local .ini file editing mode ---
                config_path, _ = QFileDialog.getOpenFileName(
                    None, 
                    "เลือกไฟล์ Configuration (.ini) ที่ต้องการแก้ไข", 
                    get_app_root(), 
                    "INI Files (*.ini)"
                )
                if config_path:
                    selected_config = AppConfig(config_path=config_path)
                    settings_dialog = LocalSettingsDialog(main_window_ref=None, parent=None, config_instance=selected_config)
                    settings_dialog.exec()

            elif clicked_button == server_button:
                # --- Remote Server settings editing mode ---
                # Use the global config to find the server, then connect.
                if not global_app_config.get('DATABASE', 'enabled', 'False').lower() == 'true':
                    QMessageBox.warning(None, "Server Mode Disabled", "โหมด Server ยังไม่ได้ถูกเปิดใช้งานในไฟล์ app_config.ini หลัก")
                    return

                # Create a dedicated DB instance for the server.
                try:
                    # We need to initialize the db_manager to establish the connection
                    db_manager.initialize_databases()
                    remote_conn = db_manager.get_instance_for_mode(is_remote=True)
                    if not remote_conn:
                        raise ConnectionError("The connection object was not created.")
                    remote_db_instance = get_db_instance(is_remote=True) # Now get the instance wrapper
                except Exception as e:
                    QMessageBox.critical(None, "Connection Failed", f"ไม่สามารถเชื่อมต่อฐานข้อมูลเซิร์ฟเวอร์ได้:\n\n{e}\n\nกรุณาตรวจสอบการตั้งค่าใน app_config.ini และสิทธิ์การเข้าถึงบนเซิร์ฟเวอร์")
                    return
                
                # Open settings dialog in remote mode, passing the remote DB instance.
                settings_dialog = SystemSettingsDialog(main_window_ref=None, parent=None, db_instance=remote_db_instance)
                settings_dialog.exec()
                remote_db_instance.close_connection()

    except Exception as e:
        QMessageBox.critical(None, "Application Error", f"An unexpected error occurred:\n\n{e}")
        sys.exit(1)

    # 6. Exit the application when the dialogs are closed.
    sys.exit(0)

if __name__ == "__main__":
    run_admin_tool()