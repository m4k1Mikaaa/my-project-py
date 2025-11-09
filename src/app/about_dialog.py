from PyQt6.QtWidgets import (
    QVBoxLayout, QLabel, QWidget, QFrame, QGroupBox, QFormLayout
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from .base_dialog import BaseDialog
from .utils import get_icon
from app_config import app_config
from app_db.db_management import get_db_instance
import importlib.metadata

class ClickableIconLabel(QLabel):
    """A QLabel that counts rapid clicks."""
    clicked_rapidly = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def mousePressEvent(self, event):
        self.clicked_rapidly.emit()
        super().mousePressEvent(event)
class AboutDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.click_count = 0
        self.setWindowTitle("ข้อมูลโปรแกรม")
        self.setMinimumSize(500, 650)

        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.setSpacing(15)

        # --- App Icon ---
        icon_label = ClickableIconLabel()
        app_icon = get_icon("app_image/pic.png")
        icon_label.setPixmap(app_icon.pixmap(QSize(250, 250)))
        icon_label.clicked_rapidly.connect(self.handle_icon_click)
        main_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignCenter)

        # --- App Name ---
        app_name_label = QLabel("MiKA RENTAL")
        app_name_label.setStyleSheet("font-size: 24pt; font-weight: bold;")
        main_layout.addWidget(app_name_label, 0, Qt.AlignmentFlag.AlignCenter)

        # --- Version ---
        try:
            # This works correctly after the project is installed/built.
            version = importlib.metadata.version('Mika-Rental')
            version_text = f"Version {version}"
        except importlib.metadata.PackageNotFoundError:
            version_text = "Version 0.1.0" # Fallback for development mode
        version_label = QLabel(version_text)
        version_label.setStyleSheet("font-size: 10pt; color: #888;")
        main_layout.addWidget(version_label, 0, Qt.AlignmentFlag.AlignCenter)

        main_layout.addSpacing(20)

        # --- Creator ---
        try:
            meta = importlib.metadata.metadata('Mika-Rental')
            authors = meta.get_all('Author')
            creator_text = ', '.join(authors) if authors else "NiVARA"
        except importlib.metadata.PackageNotFoundError:
            creator_text = "NiRU, MiKA" # Fallback for development mode
        creator_label = QLabel(creator_text)
        creator_label.setStyleSheet("font-size: 11pt; font-weight: bold;")
        main_layout.addWidget(creator_label, 0, Qt.AlignmentFlag.AlignCenter)

        # --- Separator ---
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(separator)

        # --- Program Status ---
        status_group = QGroupBox("สถานะโปรแกรม")
        status_layout = QFormLayout(status_group)
        status_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        is_server_mode = app_config.get('DATABASE', 'enabled', fallback='False').lower() == 'true'
        if is_server_mode:
            mode_text = "<b>โหมดเซิร์ฟเวอร์</b>"
        else:
            mode_text = "<b>โหมด Local</b>"
        
        status_layout.addRow("สถานะการทำงาน:", QLabel(mode_text))

        # --- Item Status Summary ---
        summary = {}
        try:
            # Get the currently active DB instance (local or remote)
            # Ensure we get the instance from the main window if available
            db_instance = self.main_window._get_db_instance_for_refresh() if self.main_window else get_db_instance(is_remote=is_server_mode)
            if db_instance:
                summary = db_instance.get_item_status_summary()
        except ConnectionError:
            status_layout.addRow(QLabel("<b><font color='#f39c12'>ไม่สามารถโหลดข้อมูลสรุปได้</font></b>"))
        status_map = {
            'available': 'พร้อมให้เช่า:',
            'rented': 'กำลังถูกเช่า:',
            'pending_return': 'รอการยืนยันคืน:',
            'suspended': 'ระงับใช้งาน:'
        }

        # Separator inside the group
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        status_layout.addRow(line)

        for status, display_text in status_map.items():
            count = summary.get(status, 0)
            status_layout.addRow(display_text, QLabel(f"<b>{count}</b> รายการ"))

        main_layout.addWidget(status_group)

        main_layout.addStretch()

        self.adjust_and_center()

    def handle_icon_click(self):
        self.click_count += 1
        if self.click_count >= 10:
            self.click_count = 0 # Reset counter
            if self.main_window and hasattr(self.main_window, 'open_admin_console'):
                # Close the about dialog before opening the console
                self.close()
                self.main_window.open_admin_console()