from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QScrollArea, QWidget, QLabel,
    QScroller, QGridLayout
)
from app.base_dialog import BaseDialog
from app_db.db_management import get_db_instance
from app_config import app_config
from PyQt6.QtCore import QDateTime, Qt
from app.item_card import ItemCard

class MyRentalsDialog(BaseDialog):
    def __init__(self, user_data, parent=None):
        super().__init__(parent)
        self.user_data = user_data
        self.main_window = parent
        # Get the correct database instance from the main window
        self.db_instance = self.main_window._get_db_instance_for_refresh() if self.main_window else get_db_instance()
        self.setWindowTitle(f"รายการที่กำลังยืม: {self.user_data['username']}")
        self.setMinimumSize(800, 450)

        layout = QVBoxLayout(self)

        # --- Rented Items Scroll Area ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # เปิดใช้งาน Smooth Scrolling สำหรับ Touch
        QScroller.grabGesture(self.scroll_area.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)

        self.scroll_content = QWidget()
        # เปลี่ยนจาก QHBoxLayout เป็น QGridLayout เพื่อให้มีการตัดแถว
        self.grid_layout = QGridLayout(self.scroll_content)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll_area.setWidget(self.scroll_content)
        layout.addWidget(self.scroll_area)

        # --- Bottom Layout ---
        bottom_layout = QHBoxLayout()
        info_label = QLabel("คลิกที่รายการเพื่อดูรายละเอียดและทำการคืน")
        close_button = QPushButton("ปิด")
        close_button.clicked.connect(self.accept)

        bottom_layout.addWidget(info_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(close_button)
        layout.addLayout(bottom_layout)

        self.load_rented_items()
        self.adjust_and_center()

    def load_rented_items(self):
        # Clear existing items
        while self.grid_layout.count():
            child = self.grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        rented_items = self.db_instance.get_rented_items_by_user(self.user_data['id'])

        # คำนวณจำนวนคอลัมน์ตามความกว้างของหน้าต่าง
        num_columns = max(1, self.width() // 220)

        for i, item_data in enumerate(rented_items):
            row = i // num_columns
            col = i % num_columns
            card = ItemCard(item_data)
            card.doubleClicked.connect(lambda item_id=item_data['id']: self.open_item_for_return(item_id))
            self.grid_layout.addWidget(card, row, col)

    def open_item_for_return(self, item_id: int):
        if item_id and self.main_window:
            # Get the ItemDetailWindow instance from the main window
            detail_dialog = self.main_window.open_item_detail(item_id, return_instance=True)
            if detail_dialog:
                # Connect the finished signal to reload data.
                # This ensures that after the detail/payment dialogs are closed, this list is refreshed.
                detail_dialog.finished.connect(self.load_rented_items)
                detail_dialog.finished.connect(self.main_window.check_current_rentals)

    def format_datetime(self, dt_obj, default_text="-") -> str:
        if not dt_obj:
            return default_text
        
        # Ensure dt_obj is a string before parsing
        dt_str = str(dt_obj).split('.')[0]
        dt = QDateTime.fromString(dt_str, "yyyy-MM-dd HH:mm:ss")
        
        if not dt.isValid():
            return dt_str # Fallback to original string if parsing fails

        dt.setTimeSpec(Qt.TimeSpec.UTC)
        offset_hours = app_config.getint('TIME', 'utc_offset_hours', fallback=7)
        offset_seconds = offset_hours * 3600
        local_dt = dt.toOffsetFromUtc(offset_seconds)
        return local_dt.toString("yyyy-MM-dd HH:mm:ss")