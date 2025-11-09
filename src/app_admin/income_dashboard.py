from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QWidget, QFrame, QGridLayout, QPushButton, QGroupBox,
    QDateEdit, QTableWidget, QHeaderView, QTableWidgetItem, QAbstractItemView, QLineEdit, QGraphicsDropShadowEffect, QApplication,
    QMenu
)
from PyQt6.QtCore import Qt, QDate, QDateTime, QSize, QModelIndex, QPoint
from PyQt6.QtGui import QColor
import qtawesome as qta
from app.base_dialog import BaseDialog
from theme import PALETTES
from app_config import app_config
from datetime import date, timedelta
import math
from app_payment.receipt_dialog import ReceiptDialog

class StatCard(QWidget):
    """A card widget to display a single statistic."""
    def __init__(self, title, value, icon_name, icon_color, parent=None):
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.setMinimumSize(200, 100) # Adjust size

        # --- NEW: Add shadow effect ---
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(2, 2)
        self.setGraphicsEffect(shadow)
        # --- END NEW ---

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Icon on the left
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(36, 36)) # Slightly smaller icon
        layout.addWidget(icon_label)

        # Text on the right
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        
        title_label = QLabel(title)
        title_label.setObjectName("StatCardTitle")
        title_label.setStyleSheet("font-size: 10pt; font-weight: bold;")
        
        value_label = QLabel(value)
        value_label.setObjectName("StatCardValue")
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
        self.total_items_for_pagination = 0 # Initialize for pagination logic
        
        # --- NEW: Filter and Sort states ---
        self.current_filter_status = None
        self.current_sort_criteria = {'by': 'return_date', 'order': 'DESC'}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("Dashboard")
        header_label.setStyleSheet("font-size: 18pt; font-weight: bold;")
        
        # --- NEW: Theme Toggle Button ---
        self.theme_button = QPushButton()
        self.theme_button.setObjectName("IconButton")
        self.theme_button.clicked.connect(self.toggle_theme)
        # --- END NEW ---

        header_layout.addWidget(header_label)
        header_layout.addStretch()
        header_layout.addWidget(self.theme_button)
        main_layout.addLayout(header_layout)

        # --- Date Filter Toolbar ---
        filter_toolbar = QHBoxLayout()
        filter_toolbar.setSpacing(10)
        
        self.today_button = QPushButton("วันนี้")
        self.week_button = QPushButton("สัปดาห์นี้") # New button
        self.month_button = QPushButton("เดือนนี้")
        self.year_button = QPushButton("ปีนี้")
        self.all_time_button = QPushButton("ทั้งหมด / รีเฟรช")
        self.today_button.clicked.connect(self.filter_today)
        self.week_button.clicked.connect(self.filter_this_week) # Connect new button
        self.month_button.clicked.connect(self.filter_this_month)
        self.year_button.clicked.connect(self.filter_this_year)
        self.all_time_button.clicked.connect(self.filter_all_time)
        
        filter_toolbar.addWidget(self.today_button)
        filter_toolbar.addWidget(self.week_button)
        filter_toolbar.addWidget(self.month_button)
        filter_toolbar.addWidget(self.year_button)
        filter_toolbar.addWidget(self.all_time_button)
        filter_toolbar.addSpacing(20)
        
        filter_toolbar.addWidget(QLabel("เลือกช่วง:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setMinimumWidth(120) # เพิ่มความกว้าง
        self.start_date_edit.setDate(QDate.currentDate().addDays(-7)) # Default to last 7 days
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setMinimumWidth(120) # เพิ่มความกว้าง
        self.end_date_edit.setDate(QDate.currentDate())
        self.apply_date_range_button = QPushButton("ค้นหา")
        self.apply_date_range_button.clicked.connect(self.apply_custom_date_range)
        
        filter_toolbar.addWidget(self.start_date_edit)
        filter_toolbar.addWidget(QLabel("ถึง"))
        filter_toolbar.addWidget(self.end_date_edit)
        filter_toolbar.addWidget(self.apply_date_range_button)
        filter_toolbar.addStretch()
        main_layout.addLayout(filter_toolbar)
        
        # --- REVISED: Stats Grid in its own GroupBox for better visual separation ---
        stats_group = QGroupBox("สรุปภาพรวม")
        self.stats_grid = QGridLayout()
        self.stats_grid.setSpacing(15)
        stats_group.setLayout(self.stats_grid)
        main_layout.addWidget(stats_group)
        
        history_group = QGroupBox("ประวัติการชำระเงินทั้งหมด")
        history_layout = QVBoxLayout(history_group)

        table_toolbar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("ค้นหาจากชื่อรายการ, ผู้ใช้, หรือรหัสอ้างอิง...")
        self.search_input.textChanged.connect(self.on_search_changed)

        # --- NEW: Filter and Sort Buttons ---
        self.filter_button = QPushButton()
        self.filter_button.setObjectName("IconButton")
        self.filter_button.setToolTip("คัดกรองตามสถานะ")
        self.filter_button.clicked.connect(self.show_filter_menu)
        self.sort_button = QPushButton()
        self.sort_button.setObjectName("IconButton")
        self.sort_button.setToolTip("จัดเรียงรายการ")
        self.sort_button.clicked.connect(self.show_sort_menu)
        table_toolbar.addWidget(self.filter_button)
        table_toolbar.addWidget(self.sort_button)
        table_toolbar.addWidget(self.search_input, 1) # Give search input stretch factor
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
        # --- NEW: Connect double click signal to open receipt details ---
        self.history_table.doubleClicked.connect(self.open_receipt_details)
        history_layout.addWidget(self.history_table)
        
        # Pagination for table
        pagination_layout = QHBoxLayout()
        self.prev_page_button = QPushButton(" < ก่อนหน้า")
        self.prev_page_button.setFixedWidth(100)
        self.prev_page_button.clicked.connect(self.prev_page)
        self.page_label = QLabel("หน้า 1 / 1")
        self.next_page_button = QPushButton("ถัดไป > ")
        self.next_page_button.setFixedWidth(100)
        self.next_page_button.clicked.connect(self.next_page)
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.prev_page_button)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_page_button)
        pagination_layout.addStretch()
        history_layout.addLayout(pagination_layout)
        
        main_layout.addWidget(history_group, 1) # Give stretch factor
        
        self.filter_all_time() # Load initial data for all time
        self.update_icons() # Initial icon setup
        self.adjust_and_center()

    def on_search_changed(self):
        self.current_page = 1
        self.load_table_data()

    def open_receipt_details(self, index: QModelIndex):
        """Opens the receipt dialog for the double-clicked row."""
        if not index.isValid():
            return

        try:
            history_id_item = self.history_table.item(index.row(), 0)
            if not history_id_item: # เพิ่มการตรวจสอบเพื่อความปลอดภัย
                return

            history_id = int(history_id_item.text())

            # Open the ReceiptDialog, passing the admin context
            receipt_dialog = ReceiptDialog(history_id=history_id, parent=self, db_instance=self.db_instance, is_admin_view=True)
            receipt_dialog.exec()
        except (ValueError, AttributeError) as e:
            print(f"Error opening receipt details: {e}")

    def filter_today(self):
        today = date.today().strftime('%Y-%m-%d')
        self._load_data_for_range(today, today)

    def filter_this_week(self):
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())
        self._load_data_for_range(start_of_week.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d'))

    def filter_this_month(self):
        today = date.today()
        start_of_month = today.replace(day=1).strftime('%Y-%m-%d')
        self._load_data_for_range(start_of_month, today.strftime('%Y-%m-%d'))

    def filter_this_year(self):
        today = date.today()
        start_of_year = today.replace(day=1, month=1).strftime('%Y-%m-%d')
        self._load_data_for_range(start_of_year, today.strftime('%Y-%m-%d'))

    def filter_all_time(self):
        self.load_summary_data()
        # --- NEW: Reset date edits to a wide range to reflect "all time" ---
        self.start_date_edit.setDate(QDate(2000, 1, 1))
        self.end_date_edit.setDate(QDate.currentDate())
        # --- END NEW ---
        self.load_table_data()
    
    def apply_custom_date_range(self):
        start_date = self.start_date_edit.date().toString('yyyy-MM-dd')
        end_date = self.end_date_edit.date().toString('yyyy-MM-dd')
        self._load_data_for_range(start_date, end_date)

    def _load_data_for_range(self, start_date=None, end_date=None):
        """Helper to load both summary and table data for a given range."""
        # --- NEW: Update the date edits to reflect the selected range ---
        if start_date:
            self.start_date_edit.setDate(QDate.fromString(start_date, 'yyyy-MM-dd'))
        if end_date:
            self.end_date_edit.setDate(QDate.fromString(end_date, 'yyyy-MM-dd'))
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
            card = StatCard(title, f"{value:,.2f}", icon, color) # Remove "บาท" for cleaner look
            self.stats_grid.addWidget(card, 0, i)

        self.update_icons()
    
    def load_table_data(self, start_date=None, end_date=None):
        # --- FIX: Always use the date range from the UI when loading table data ---
        # This ensures that pagination works correctly with the currently selected date range.
        # The date range is now correctly set by _load_data_for_range before this is called.
        # We still need to read them for pagination calls.
        current_start_date = self.start_date_edit.date().toString('yyyy-MM-dd')
        current_end_date = self.end_date_edit.date().toString('yyyy-MM-dd')

        if not self.db_instance: return

        search_text = self.search_input.text()
        sort_by = self.current_sort_criteria.get('by', 'return_date')
        sort_order = self.current_sort_criteria.get('order', 'DESC')

        records, total_count = self.db_instance.get_all_payment_history_paginated(
            page=self.current_page,
            items_per_page=self.items_per_page,
            search_text=search_text,
            start_date=current_start_date if start_date is not None else None, # Pass None if filtering all time
            end_date=current_end_date if end_date is not None else None,
            status_filter=self.current_filter_status,
            sort_by=sort_by,
            sort_order=sort_order
        )
        self.total_items_for_pagination = total_count # Store total count for pagination
        
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
            self.load_table_data()
    
    def next_page(self):
        # --- FIX: Check against total pages before incrementing ---
        # This prevents going to a non-existent page and causing pagination errors.
        total_pages = math.ceil(self.total_items_for_pagination / self.items_per_page) if self.total_items_for_pagination > 0 else 1
        if self.current_page < total_pages:
            self.current_page += 1
            self.load_table_data()

    def format_datetime(self, dt_obj, default_text="-") -> str:
        if not dt_obj: return default_text
        dt = QDateTime.fromString(str(dt_obj).split('.')[0], "yyyy-MM-dd HH:mm:ss")
        if not dt.isValid(): return default_text
        dt.setTimeSpec(Qt.TimeSpec.UTC)
        offset_hours = app_config.getint('TIME', 'utc_offset_hours', fallback=7)
        local_dt = dt.toOffsetFromUtc(offset_hours * 3600)
        return local_dt.toString("yyyy-MM-dd HH:mm")

    def toggle_theme(self):
        """Toggles the application's theme and updates this dialog."""
        current_theme = app_config.get('UI', 'theme', fallback='light')
        new_theme = "dark" if current_theme == "light" else "light"
        app_config.update_config('UI', 'theme', new_theme)
        
        # Find the main window instance to call its global theme update
        main_window = self.parent().main_window_ref if self.parent() else None
        if main_window:
            main_window.toggle_theme()
        else: # Fallback if no main window ref
            from theme import theme
            theme.apply_theme(QApplication.instance(), new_theme)
            self.update_icons()

    def update_icons(self):
        """Applies theme-specific styles to the cards."""
        current_theme_name = app_config.get('UI', 'theme', fallback='light')
        palette = PALETTES.get(current_theme_name, PALETTES['light'])
        self.setStyleSheet(f"""
            QGroupBox {{ border: 1px solid {palette['disabled_text']}; }}
            #StatCard {{
                background-color: {palette['base']};
                border: 1px solid {palette['window']};
                border-radius: 8px;
            }}
        """)
        # Update theme toggle button icon
        if current_theme_name == 'dark':
            self.theme_button.setIcon(qta.icon('fa5s.sun'))
            self.theme_button.setIconSize(QSize(28, 28))
            self.theme_button.setToolTip("เปลี่ยนเป็นโหมดสว่าง")
        else:
            self.theme_button.setIcon(qta.icon('fa5s.moon'))
            self.theme_button.setIconSize(QSize(25, 25))
            self.theme_button.setToolTip("เปลี่ยนเป็นโหมดมืด")
        self.update_filter_button_state()
        self.update_sort_button_state()

    def show_filter_menu(self):
        """Displays a menu to filter items by payment status."""
        menu = QMenu(self.filter_button)
        
        statuses = {
            "แสดงทั้งหมด": None,
            "ชำระแล้ว": "paid",
            "ค้างชำระ": "pending",
            "ยกเว้นค่าบริการ": "waived",
            "---": None,
            "เฉพาะโอนชำระ": "transfer",
            "เฉพาะเงินสด": "cash",
        }

        for text, status_value in statuses.items():
            if status_value is None:
                menu.addSeparator()
                continue
            action = menu.addAction(text)
            action.triggered.connect(lambda checked=False, s=status_value: self.apply_filter(s))

        menu.exec(self.filter_button.mapToGlobal(self.filter_button.rect().bottomLeft()))

    def apply_filter(self, status: str | None):
        """Applies the selected status filter and reloads the table."""
        self.current_filter_status = status
        self.current_page = 1
        self.apply_custom_date_range() # Reloads data with the new filter
        self.update_filter_button_state()

    def update_filter_button_state(self):
        """Updates the filter button's appearance based on the current filter state."""
        palette = PALETTES[app_config.get('UI', 'theme', fallback='light')]
        status = self.current_filter_status

        if status:
            status_map = {
                "paid": "ชำระแล้ว", "pending": "ค้างชำระ", "waived": "ยกเว้นฯ",
                "transfer": "โอนชำระ", "cash": "เงินสด"
            }
            status_text = status_map.get(status, status.capitalize())
            self.filter_button.setText(f" {status_text}")
            self.filter_button.setStyleSheet(f"background-color: {palette['info']}; color: white;")
            self.filter_button.setIcon(qta.icon('fa5s.filter', color='white'))
        else:
            self.filter_button.setObjectName("IconButton")
            self.filter_button.setText("")
            self.filter_button.setStyleSheet("")
            self.filter_button.setIcon(qta.icon('fa5s.filter', color=PALETTES[app_config.get('UI', 'theme', fallback='light')]['text']))

    def show_sort_menu(self):
        """Displays a menu to sort items."""
        menu = QMenu(self.sort_button)

        menu.addAction("ค่าเริ่มต้น (วันที่ล่าสุด)").triggered.connect(lambda: self.apply_sort('return_date', 'DESC'))
        menu.addSeparator()

        sort_options = {
            "วันที่ (เก่าสุด)": ('return_date', 'ASC'),
            "---": None,
            "ยอดชำระ (มากไปน้อย)": ('amount_due', 'DESC'),
            "ยอดชำระ (น้อยไปมาก)": ('amount_due', 'ASC'),
        }

        for text, criteria in sort_options.items():
            if criteria:
                action = menu.addAction(text)
                action.triggered.connect(lambda checked=False, by=criteria[0], order=criteria[1]: self.apply_sort(by, order))
            else:
                menu.addSeparator()

        menu.exec(self.sort_button.mapToGlobal(QPoint(0, self.sort_button.height())))

    def apply_sort(self, sort_by: str, sort_order: str):
        """Applies the selected sort criteria and reloads items."""
        self.current_sort_criteria = {'by': sort_by, 'order': sort_order}
        self.current_page = 1
        self.apply_custom_date_range() # Reloads data with the new sort
        self.update_sort_button_state()

    def update_sort_button_state(self):
        """Updates the sort button's appearance based on the current sort state."""
        palette = PALETTES[app_config.get('UI', 'theme', fallback='light')]
        sort_by = self.current_sort_criteria.get('by')
        is_default_sort = (sort_by == 'return_date' and self.current_sort_criteria.get('order') == 'DESC')

        if not is_default_sort and sort_by:
            order = self.current_sort_criteria.get('order', 'ASC')
            icon_name = 'fa5s.sort-amount-down' if order == 'ASC' else 'fa5s.sort-amount-up'
            sort_map = {'return_date': 'วันที่', 'amount_due': 'ยอดชำระ'}
            text = f"{sort_map.get(sort_by, sort_by.capitalize())}"
            self.sort_button.setStyleSheet(f"background-color: {palette['info']}; color: white;")
            self.sort_button.setIcon(qta.icon(icon_name, color='white'))
            self.sort_button.setText(f" {text}")
        else:
            self.sort_button.setObjectName("IconButton")
            self.sort_button.setStyleSheet("")
            self.sort_button.setIcon(qta.icon('fa5s.sort', color=PALETTES[app_config.get('UI', 'theme', fallback='light')]['text']))
            self.sort_button.setText("")