import sys
import os
from PyQt6.QtWidgets import QApplication, QMessageBox
import traceback
from PyQt6.QtCore import Qt

# --- Suppress OpenCV warnings ---
# This prevents the console from being flooded with "can't be used to capture by index"
# warnings when scanning for available cameras.
os.environ['OPENCV_LOG_LEVEL'] = 'ERROR'

def global_exception_hook(exctype, value, tb):
    """
    Global exception handler to catch unhandled exceptions and display them in a message box.
    This prevents the application from crashing silently.
    """
    from app.custom_message_box import CustomMessageBox

    traceback_details = "".join(traceback.format_exception(exctype, value, tb))
    error_message = f"ผิดพลาดทางเทคนิคนิดหน่อย~:\n\n{value}\n\n{traceback_details}"
    print(error_message) # Also print to console for debugging

    # We don't have a parent window here, so we pass None.
    CustomMessageBox.show(None, CustomMessageBox.Critical, "Application Error", error_message)
    sys.exit(1) # Exit after showing the error

if __name__ == "__main__":
    # --- NEW: Enable High DPI Scaling using environment variables (more reliable) ---
    # This must be done BEFORE the QApplication is created.
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

    # --- เปิดใช้งานการเรนเดอร์ด้วย OpenGL ---
    # การตั้งค่านี้จะบอกให้ Qt ใช้ GPU (การ์ดจอ) ในการช่วยวาดหน้าต่างและวิดเจ็ตต่างๆ
    # ซึ่งอาจช่วยเพิ่มประสิทธิภาพการทำงาน แต่ก็อาจทำให้เกิดปัญหากับไดรเวอร์การ์ดจอบางรุ่น
    # หรือในสภาพแวดล้อมบางอย่าง (เช่น Virtual Machine) ทำให้โปรแกรมปิดตัวเองลง
    # จึงขอปิดการใช้งานส่วนนี้ไปก่อนเพื่อความเสถียร
    # QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseDesktopOpenGL)

    # 1. สร้าง QApplication instance เป็นอันดับแรกสุดเสมอ
    app = QApplication(sys.argv)

    # --- FIX: Set AppUserModelID for Windows Taskbar Icon ---
    # This tells Windows that all windows of this app belong to the same group.
    if sys.platform == 'win32':
        import ctypes
        myappid = 'nivara.mika_rental.1.0' # arbitrary string
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    # --- NEW: Install the global exception handler ---
    sys.excepthook = global_exception_hook

    # 2. Import โมดูลอื่นๆ ที่จำเป็น *หลังจาก* ที่ app ถูกสร้างแล้ว
    # เพื่อป้องกันปัญหา QPaintDevice และการปิดตัวลงโดยไม่ทราบสาเหตุ
    from app.main_window import MainWindow
    from app.utils import get_icon
    from build_utils import create_icon_if_needed
    from app_db.db_management import initialize_databases, db_manager
    from app_payment.webhook_server import WebhookServer

    # 3. --- NEW: Automatically create .ico file if it doesn't exist ---
    create_icon_if_needed()

    # 4. เริ่มต้นการทำงานของฐานข้อมูล (การตรวจสอบการเชื่อมต่อจะถูกจัดการใน MainWindow)
    initialize_databases()

    # 5. เริ่มต้น Webhook Server ใน Thread แยก
    # --- FIX: Set the server thread as a daemon thread ---
    # การตั้งค่า daemon=True จะทำให้ Thread นี้ถูกปิดโดยอัตโนมัติเมื่อโปรแกรมหลักปิดตัวลง
    # ซึ่งจะช่วยแก้ปัญหา Terminal ค้างหลังจากปิดโปรแกรม
    webhook_server = WebhookServer(daemon=True)
    webhook_server.run_in_thread()

    main_win = MainWindow(app)  # ส่ง app instance เข้าไป

    # --- FIX: Set the icon AFTER the main window is created ---
    # This can sometimes improve reliability for the taskbar icon on Windows.
    app.setWindowIcon(get_icon("app_image/icon.ico"))
    main_win.show()

    # 6. --- Graceful Shutdown Logic ---
    # เชื่อมต่อ Signal aboutToQuit ของ QApplication เข้ากับฟังก์ชัน shutdown
    # เพื่อให้แน่ใจว่าทรัพยากรต่างๆ จะถูกปิดอย่างถูกต้องก่อนที่โปรแกรมจะจบการทำงาน
    app.aboutToQuit.connect(main_win.shutdown_child_windows)  # ปิด Console ก่อน
    app.aboutToQuit.connect(db_manager.close_all_connections)  # ปิดการเชื่อมต่อ DB
    app.aboutToQuit.connect(webhook_server.shutdown)  # ปิด Webhook Server
    app.setQuitOnLastWindowClosed(True) # โปรแกรมจะปิดเมื่อหน้าต่างสุดท้ายถูกปิด

    # 7. เริ่มต้น event loop ของโปรแกรม
    exit_code = app.exec()
    sys.exit(exit_code)
