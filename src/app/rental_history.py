from PyQt6.QtWidgets import (
    QVBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QApplication
)
from .base_dialog import BaseDialog
from app_db.db_management import get_db_instance
from theme import PALETTES
from app_config import app_config
from PyQt6.QtCore import QDateTime, Qt
from PyQt6.QtGui import QColor

class RentalHistoryDialog(BaseDialog):
    def __init__(self, item_id, item_name, parent=None):
        super().__init__(parent)
        self.item_id = item_id
        self.db_instance = get_db_instance() # Get the currently active DB instance
        self.setWindowTitle(f"ประวัติการยืม-คืน: {item_name}")
        
        # Adjust window size based on screen geometry
        screen = QApplication.primaryScreen()
        available_geom = screen.availableGeometry()
        self.resize(int(available_geom.width() * 0.6), int(available_geom.height() * 0.6)) # ~60% width, 60% height
        # Center the dialog on the current screen
        self.center_on_screen()

        layout = QVBoxLayout(self)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(3)
        self.history_table.setHorizontalHeaderLabels(["ผู้เช่า-ยืม", "วันที่", "ส่งคืน"])
        
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive) # ผู้เช่า-ยืม
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)     # วันที่
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)     # ส่งคืน

        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.history_table)

        close_button = QPushButton("ปิด")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

        self.load_history()

    def load_history(self):
        history_data = self.db_instance.get_rental_history_for_item(self.item_id)
        current_theme_name = app_config.get('UI', 'theme', fallback='light')
        palette = PALETTES.get(current_theme_name, PALETTES['light'])
        text_color = QColor(palette['text'])

        self.history_table.setRowCount(len(history_data))
        
        for row_num, rental in enumerate(history_data):
            username = rental.get('username', 'N/A')
            rent_date_str = self.format_datetime(rental.get('rent_date'))
            return_date_str = self.format_datetime(rental.get('return_date'), default_text="ยังไม่คืน")
            username_item = QTableWidgetItem(username)
            username_item.setForeground(text_color)
            rent_date_item = QTableWidgetItem(rent_date_str)
            rent_date_item.setForeground(text_color)
            return_date_item = QTableWidgetItem(return_date_str)
            return_date_item.setForeground(text_color)
            self.history_table.setItem(row_num, 0, username_item)
            self.history_table.setItem(row_num, 1, rent_date_item)
            self.history_table.setItem(row_num, 2, return_date_item)

    def format_datetime(self, dt_obj, default_text="-") -> str:
        if not dt_obj:
            return default_text
        
        # The datetime from SQLite is a string, so we must parse it.
        # The format is 'yyyy-MM-dd HH:mm:ss'. We also specify it's in UTC.
        dt = QDateTime.fromString(str(dt_obj).split('.')[0], "yyyy-MM-dd HH:mm:ss")
        if not dt.isValid():
            return default_text # Return default if parsing fails
        dt.setTimeSpec(Qt.TimeSpec.UTC)
        
        offset_hours = app_config.getint('TIME', 'utc_offset_hours', fallback=7)
        offset_seconds = offset_hours * 3600
        local_dt = dt.toOffsetFromUtc(offset_seconds)

        return local_dt.toString("yyyy-MM-dd HH:mm:ss")
