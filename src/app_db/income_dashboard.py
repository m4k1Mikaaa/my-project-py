from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QWidget, QFrame, QGridLayout, QPushButton, QGroupBox,
    QDateEdit, QTableWidget, QHeaderView, QTableWidgetItem, QAbstractItemView, QLineEdit,
)
from PyQt6.QtCore import Qt, QDate, QDateTime
import qtawesome as qta
from app.base_dialog import BaseDialog
from theme import PALETTES
from app_config import app_config
from datetime import date, timedelta
import math

class StatCard(QWidget):
    """A card widget to display a single statistic."""
    def __init__(self, title, value, icon_name, icon_color, parent=None):
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.setMinimumSize(220, 100)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Icon on the left
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(40, 40))
        layout.addWidget(icon_label)

        # Text on the right
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        
        title_label = QLabel(title)
        title_label.setObjectName("StatCardTitle") # For styling
        title_label.setStyleSheet("font-size: 10pt; font-weight: bold;")
        
        value_label = QLabel(value)
        value_label.setObjectName("StatCardValue") # For styling
        value_label.setStyleSheet("font-size: 18pt; font-weight: bold;")

        text_layout.addWidget(title_label)
        text_layout.addWidget(value_label)
        text_layout.addStretch()

        layout.addLayout(text_layout)

class IncomeDashboard(BaseDialog):
    def __init__(self, parent=None, db_instance=None):
        super().__init__(parent)
        self.db_instance = db_instance
        self.setWindowTitle("Dashboard")
        self.setMinimumSize(1200, 800)

        # Pagination for the table
        self.current_page = 1
        self.items_per_page = 20

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # Header
        header_label = QLabel("Dashboard")
        header_label.setStyleSheet("font-size: 18pt; font-weight: bold;")
        main_layout.addWidget(header_label, 0, Qt.AlignmentFlag.AlignCenter)

        # --- Date Filter Toolbar ---
        filter_toolbar = QHBoxLayout()
        filter_toolbar.setSpacing(10)
        
        self.today_button = QPushButton("วันนี้")
        self.month_button = QPushButton("เดือนนี้")
        self.year_button = QPushButton("ปีนี้")
        self.all_time_button = QPushButton("ทั้งหมด")
        self.today_button.clicked.connect(self.filter_today)
        self.month_button.clicked.connect(self.filter_this_month)
        self.year_button.clicked.connect(self.filter_this_year)
        self.all_time_button.clicked.connect(self.filter_all_time)
        
        filter_toolbar.addWidget(self.today_button)
        filter_toolbar.addWidget(self.month_button)
        filter_toolbar.addWidget(self.year_button)
        filter_toolbar.addWidget(self.all_time_button)
        filter_toolbar.addSpacing(20)
        
        filter_toolbar.addWidget(QLabel("เลือกช่วง:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(QDate.currentDate().addMonths(-1))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(QDate.currentDate())
        self.apply_date_range_button = QPushButton("ค้นหา")
        self.apply_date_range_button.clicked.connect(self.apply_custom_date_range)
        
        filter_toolbar.addWidget(self.start_date_edit)
        filter_toolbar.addWidget(QLabel("ถึง"))
        filter_toolbar.addWidget(self.end_date_edit)
        filter_toolbar.addWidget(self.apply_date_range_button)
        filter_toolbar.addStretch()
        main_layout.addLayout(filter_toolbar)
        
        # Stats Grid
        self.stats_grid = QGridLayout()
        self.stats_grid.setSpacing(15)
        main_layout.addLayout(self.stats_grid)
        
        # --- History Table Section ---
        history_group = QGroupBox("ประวัติการชำระเงินทั้งหมด")
        history_layout = QVBoxLayout(history_group)

        table_toolbar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("ค้นหาจากชื่อรายการ, ผู้ใช้, หรือรหัสอ้างอิง...")
        self.search_input.textChanged.connect(self.on_search_changed)
        table_toolbar.addWidget(self.search_input)
        history_layout.addLayout(table_toolbar)
        
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(7)
        self.history_table.setHorizontalHeaderLabels(["ID", "วันที่", "รายการ", "ผู้ใช้", "ยอดชำระ", "สถานะ", "ช่องทาง"])
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        history_layout.addWidget(self.history_table)
        
        # Pagination for table
        pagination_layout = QHBoxLayout()
        self.prev_page_button = QPushButton(" < ก่อนหน้า")
        self.prev_page_button.clicked.connect(self.prev_page)
        self.page_label = QLabel("หน้า 1 / 1")
        self.next_page_button = QPushButton("ถัดไป > ")
        self.next_page_button.clicked.connect(self.next_page)
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.prev_page_button)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_page_button)
        pagination_layout.addStretch()
        history_layout.addLayout(pagination_layout)
        
        main_layout.addWidget(history_group, 1) # Give stretch factor
        
        self.filter_this_month() # Load initial data for the current month
        self.adjust_and_center()

    def on_search_changed(self):
        self.current_page = 1
        self.load_table_data()

    def filter_today(self):
        today = date.today().strftime('%Y-%m-%d')
        self.load_summary_data(today, today)
        self.load_table_data(start_date=today, end_date=today)

    def filter_this_month(self):
        today = date.today()
        start_of_month = today.replace(day=1).strftime('%Y-%m-%d')
        self.load_summary_data(start_of_month, today.strftime('%Y-%m-%d'))
        self.load_table_data(start_date=start_of_month, end_date=today.strftime('%Y-%m-%d'))

    def filter_this_year(self):
        today = date.today()
        start_of_year = today.replace(day=1, month=1).strftime('%Y-%m-%d')
        self.load_summary_data(start_of_year, today.strftime('%Y-%m-%d'))
        self.load_table_data(start_date=start_of_year, end_date=today.strftime('%Y-%m-%d'))

    def filter_all_time(self):
        self.load_summary_data()
        self.load_table_data()
    
    def apply_custom_date_range(self):
        start_date = self.start_date_edit.date().toString('yyyy-MM-dd')
        end_date = self.end_date_edit.date().toString('yyyy-MM-dd')
        self.load_summary_data(start_date, end_date)
        self.load_table_data(start_date=start_date, end_date=end_date)

    def load_summary_data(self, start_date=None, end_date=None):
        if not self.db_instance: return

        summary = self.db_instance.get_income_summary(start_date, end_date)
        
        # Clear existing cards
        while self.stats_grid.count():
            child = self.stats_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        current_theme_name = app_config.get('UI', 'theme', fallback='light')
        palette = PALETTES.get(current_theme_name, PALETTES['light'])
        
        cards_data = [
            ("รายรับทั้งหมด", summary.get('total_paid', 0.0), 'fa5s.coins', palette['success']),
            ("ค้างชำระทั้งหมด", summary.get('total_pending', 0.0), 'fa5s.file-invoice-dollar', palette['warning']),
            ("ยอดโอนชำระ", summary.get('total_transfer', 0.0), 'fa5s.exchange-alt', palette['info']),
            ("ยอดชำระเงินสด", summary.get('total_cash', 0.0), 'fa5s.money-bill-wave', '#27ae60'),
            ("ยอดที่ยกเว้น", summary.get('total_waived', 0.0), 'fa5s.handshake', palette['disabled_text']),
        ]
        
        for i, (title, value, icon, color) in enumerate(cards_data):
            card = StatCard(title, f"{value:,.2f} บาท", icon, color)
            self.stats_grid.addWidget(card, 0, i)

        self.update_theme()
    
    def load_table_data(self, start_date=None, end_date=None):
        if not self.db_instance: return

        search_text = self.search_input.text()
        records, total_count = self.db_instance.get_all_payment_history_paginated(
            page=self.current_page,
            items_per_page=self.items_per_page,
            search_text=search_text,
            start_date=start_date,
            end_date=end_date
        )
        
        self.history_table.setRowCount(len(records))
        for row, record in enumerate(records):
            self.history_table.setItem(row, 0, QTableWidgetItem(str(record['id'])))
            self.history_table.setItem(row, 1, QTableWidgetItem(self.format_datetime(record['return_date'])))
            self.history_table.setItem(row, 2, QTableWidgetItem(record['item_name']))
            self.history_table.setItem(row, 3, QTableWidgetItem(record['username']))
            self.history_table.setItem(row, 4, QTableWidgetItem(f"{record['amount_due']:.2f}"))
            self.history_table.setItem(row, 5, QTableWidgetItem(record['payment_status']))
            
            # Determine payment channel
            channel = "เงินสด" if record.get('transaction_ref') is None else "โอนชำระ"
            self.history_table.setItem(row, 6, QTableWidgetItem(channel))
        
        self.update_pagination_controls(total_count)

    def update_pagination_controls(self, total_items):
        total_pages = math.ceil(total_items / self.items_per_page) if total_items > 0 else 1
        self.page_label.setText(f"หน้า {self.current_page} / {total_pages}")
        self.prev_page_button.setEnabled(self.current_page > 1)
        self.next_page_button.setEnabled(self.current_page < total_pages)
    
    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.apply_custom_date_range()
    
    def next_page(self):
        self.current_page += 1
        self.apply_custom_date_range()

    def format_datetime(self, dt_obj, default_text="-") -> str:
        if not dt_obj: return default_text
        dt = QDateTime.fromString(str(dt_obj).split('.')[0], "yyyy-MM-dd HH:mm:ss")
        if not dt.isValid(): return default_text
        dt.setTimeSpec(Qt.TimeSpec.UTC)
        offset_hours = app_config.getint('TIME', 'utc_offset_hours', fallback=7)
        local_dt = dt.toOffsetFromUtc(offset_hours * 3600)
        return local_dt.toString("yyyy-MM-dd HH:mm")
    
    def update_theme(self):
        """Applies theme-specific styles to the cards."""
        current_theme_name = app_config.get('UI', 'theme', fallback='light')
        palette = PALETTES.get(current_theme_name, PALETTES['light'])
        self.setStyleSheet(f"""
            #StatCard {{
                background-color: {palette['base']};
                border: 1px solid {palette['disabled_text']};
                border-radius: 8px;
            }}
        """)