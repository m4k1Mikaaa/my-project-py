from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QApplication,
    QLabel, QLineEdit, QPushButton, QScrollArea, QGridLayout,
    QMenu, QSpacerItem, QSizePolicy, QFrame, QScroller, QScrollerProperties
) # Import QApplication for screen geometry
from PyQt6.QtCore import Qt, QSize, QTimer, QEvent, QPoint, QPointF, QElapsedTimer, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QCursor, QCloseEvent, QMouseEvent
import math
import qtawesome as qta
from app_config import app_config
from theme import theme, PALETTES
from app_db.db_management import get_db_instance
from .item_edit import ItemDialog
from app.item_card import ItemCard
from app.custom_message_box import CustomMessageBox # Keep this import
from .user_management_dialog import UserManagementDialog
from app_setting.server_settings_dialog import SystemSettingsDialog # Updated import
from app_setting.local_settings_dialog import LocalSettingsDialog
from app_payment.payment_dialog import PaymentDialog
from app.base_dialog import BaseDialog
from .income_dashboard import IncomeDashboard # Import the new dashboard
from app_db.db_management import db_signals
import uuid

class AdminPanel(QDialog):
    def __init__(self, main_window_ref, is_remote=False, db_instance=None, current_admin_user=None):
        # ทำให้ AdminPanel เป็นหน้าต่างอิสระ (ไม่มี parent)
        # แต่ยังคงเก็บ reference ของ main_window ไว้เพื่อเรียกใช้ฟังก์ชัน
        super().__init__(None)
        self.main_window_ref = main_window_ref
        self.is_remote = is_remote
        self.selected_item_id = None
        self.db_instance = db_instance # Store the passed DB instance
        self.current_admin_user = current_admin_user # Store the logged-in admin user
        # --- Window Management ---
        self.item_edit_dialog = None
        self.user_management_dialog = None # Keep this import
        self.current_sort_criteria = {'by': 'name', 'order': 'ASC'}
        self.income_dashboard = None # Add instance manager for the new dashboard
        # --- End Window Management ---
        self.cards = []
        self.current_filter_status = None # สถานะการกรองปัจจุบัน
        self.grid_spacer = None # สำหรับป้องกันการหดของ layout
        self.last_num_cols = 0 # สำหรับตรวจสอบว่าต้อง relayout หรือไม่
        self.all_items = []
        self.current_page = 1
        self.items_per_page = 27 # 3 rows * 9 columns

        # ทำให้หน้าต่างไม่เป็น Modal และมีปุ่ม Minimize/Maximize
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint)

        # Adjust window size based on screen geometry
        if main_window_ref:
            current_screen = main_window_ref.screen()
        else:
            current_screen = QApplication.primaryScreen()
        
        available_geom = current_screen.availableGeometry()
        self.resize(int(available_geom.width() * 0.7), int(available_geom.height() * 0.8)) # ~70% width, 80% height
        self._center_on_screen() # จัดกลางจอ

        title_mode = "Remote" if self.is_remote else "Local"
        self.setWindowTitle(f"Admin Panel ({title_mode}) - จัดการรายการ")

        layout = QVBoxLayout(self)

        # --- Toolbar Widget ---
        toolbar_widget = QWidget()
        toolbar_widget.setObjectName("ToolbarWidget")
        button_layout = QHBoxLayout(toolbar_widget)
        button_layout.setContentsMargins(8, 8, 8, 8)
        button_layout.setSpacing(8)

        self.add_button = QPushButton(" เพิ่ม")
        self.edit_button = QPushButton(" แก้ไข")
        self.delete_button = QPushButton(" ลบ")
        self.refresh_button = QPushButton(" รีเฟรช")
        self.force_return_button = QPushButton(" บังคับคืน")
        self.confirm_return_button = QPushButton(" ยืนยันรับคืน") # ปุ่มใหม่
        self.user_management_button = QPushButton(" จัดการผู้ใช้")
        self.income_button = QPushButton(" รายรับ")
        self.settings_menu_button = QPushButton(" ตั้งค่าระบบ")
        self.filter_button = QPushButton()
        self.filter_button.setObjectName("IconButton")
        self.sort_button = QPushButton()
        self.sort_button.setObjectName("IconButton")
        self.theme_button = QPushButton() # ปุ่มสลับธีมใหม่

        self.add_button.clicked.connect(self.add_item)
        self.edit_button.clicked.connect(self.edit_item)
        self.delete_button.clicked.connect(self.delete_item)
        self.refresh_button.clicked.connect(self.load_items)
        self.force_return_button.clicked.connect(self.force_return_item)
        self.force_return_button.setVisible(False) # ซ่อนไว้ก่อน
        self.confirm_return_button.clicked.connect(self.confirm_item_return)
        self.confirm_return_button.setVisible(False) # ซ่อนไว้ก่อน
        self.user_management_button.clicked.connect(self.open_user_management)
        self.income_button.clicked.connect(self.open_income_dashboard) # Connect the new button
        self.settings_menu_button.clicked.connect(self.open_system_settings)
        self.filter_button.clicked.connect(self.show_filter_menu)
        self.sort_button.clicked.connect(self.show_sort_menu)
        self.theme_button.clicked.connect(self.toggle_theme)

        # --- Search Input ---
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("ค้นหาตามชื่อรายการ...")
        self.search_input.textChanged.connect(self.filter_items_by_name)

        # --- Pagination Controls (moved to toolbar) ---
        pagination_container = QWidget()
        pagination_layout = QHBoxLayout(pagination_container)
        pagination_layout.setContentsMargins(10, 0, 10, 0) # Add horizontal margins
        pagination_layout.setSpacing(5)
        self.prev_page_button = QPushButton(" < ก่อนหน้า")
        self.prev_page_button.setFixedWidth(100)
        self.prev_page_button.clicked.connect(self.prev_page)
        self.page_label = QLabel("หน้า 1/1")
        self.next_page_button = QPushButton("ถัดไป > ")
        self.next_page_button.setFixedWidth(100)
        self.next_page_button.clicked.connect(self.next_page)
        pagination_layout.addWidget(self.prev_page_button)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_page_button)
        
        self.pagination_widget = pagination_container
        self.pagination_widget.setVisible(False) # Hide by default

        # --- จบส่วนปุ่มตั้งค่าระบบ ---
        
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.edit_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.confirm_return_button)
        button_layout.addWidget(self.force_return_button)
        button_layout.addSpacing(20) # Add some space
        button_layout.addWidget(self.search_input, 1) # Add search input        
        button_layout.addWidget(self.pagination_widget) # Add pagination        
        button_layout.addWidget(self.filter_button)
        button_layout.addWidget(self.sort_button)
        button_layout.addStretch()
        button_layout.addWidget(self.income_button)
        button_layout.addWidget(self.user_management_button)
        button_layout.addWidget(self.settings_menu_button)
        button_layout.addWidget(self.theme_button)

        layout.addWidget(toolbar_widget)

        # --- Item Grid ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("MainScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.grid_container = QWidget()
        self.grid_container.setObjectName("GridContainer")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.grid_layout.setSpacing(15)

        self.scroll_area.setWidget(self.grid_container)

        layout.addWidget(self.scroll_area)
        QScroller.grabGesture(self.scroll_area.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture) # Re-enable for scrolling
        QTimer.singleShot(0, self.initialize_panel)
 
    def initialize_panel(self):
        """Initializes database connection and loads data."""
        self.update_icons() # Update icons first, regardless of DB connection
        try:
            # --- Database Connection for this Panel Instance ---
            # If a db_instance was passed during __init__ (i.e., remote mode), we use it.
            # Otherwise (local mode), we get the shared local instance.
            if not self.db_instance:
                self.db_instance = get_db_instance(is_remote=self.is_remote)

            # If after all attempts, db_instance is still not valid, raise a specific error.
            # This check is crucial.
            # The passed instance from login dialog should always be valid.
            if not self.db_instance or not self.db_instance.conn:
                raise ConnectionError(f"Failed to get a valid {'remote' if self.is_remote else 'local'} database connection.")

            # Connect signals and load initial data
            db_signals.data_changed.connect(self.handle_data_change)
            self.load_items()
        except ConnectionError as e:
            self.handle_connection_error()
        except Exception as e:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "Initialization Error", f"An unexpected error occurred during Admin Panel initialization: {e}")
            self.close()

    def reinitialize_db_instance(self, new_db_instance):
        """Updates the dialog's internal db_instance and reloads items."""
        self.db_instance = new_db_instance
        self.load_items()
        self.set_db_dependent_buttons_enabled(True)

    def update_icons(self):
        """Sets or updates icons for all buttons based on the current theme."""
        current_theme_name = app_config.get('UI', 'theme', fallback='light')
        icon_size = QSize(18, 18)

        buttons_with_icons = {
            self.add_button: ('fa5s.plus-circle', 'white'),
            self.edit_button: ('fa5s.edit', 'white'),
            self.delete_button: ('fa5s.trash-alt', 'white'),
            self.refresh_button: ('fa5s.sync-alt', 'white'),
            self.force_return_button: ('fa5s.undo', 'white'),
            self.confirm_return_button: ('fa5s.check-double', 'white'),
            self.user_management_button: ('fa5s.users', 'white'),
            self.income_button: ('fa5s.chart-line', 'white'), # Icon for the new button
            self.settings_menu_button: ('fa5s.cogs', 'white'),
            # Icons for sort/filter are handled in their state update methods
            # self.sort_button: ('fa5s.sort', 'white'),
            # self.filter_button: ('fa5s.filter', 'white'),
        }

        for button, (icon_name, color) in buttons_with_icons.items():
            # If color is None, qtawesome will not apply a specific color, letting the stylesheet take over.
            button.setIcon(qta.icon(icon_name, color=color))
            button.setIconSize(icon_size)

        # อัปเดตไอคอนปุ่มเปลี่ยนธีม
        self.theme_button.setObjectName("IconButton")
        if current_theme_name == 'dark':
            self.theme_button.setIcon(qta.icon('fa5s.sun'))
            self.theme_button.setIconSize(QSize(28, 28))
            self.theme_button.setToolTip("เปลี่ยนเป็นโหมดสว่าง")
        else:
            self.theme_button.setIcon(qta.icon('fa5s.moon'))
            self.theme_button.setIconSize(QSize(25, 25))
            self.theme_button.setToolTip("เปลี่ยนเป็นโหมดมืด")
        # Force re-applying the stylesheet to ensure the background color is correct on first load.
        self.theme_button.style().unpolish(self.theme_button)
        self.theme_button.style().polish(self.theme_button)
        
        # Update stateful buttons
        self.update_filter_button_state()
        self.update_sort_button_state()

    def set_db_dependent_buttons_enabled(self, enabled: bool):
        """Enables or disables buttons that require a database connection."""
        self.add_button.setEnabled(enabled)
        self.edit_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)
        self.refresh_button.setEnabled(enabled)
        self.confirm_return_button.setEnabled(enabled)
        self.force_return_button.setEnabled(enabled)
        self.user_management_button.setEnabled(enabled)
        self.filter_button.setEnabled(enabled)

    def update_sort_button_state(self):
        """Updates the sort button's appearance based on the current sort state."""
        palette = PALETTES[app_config.get('UI', 'theme', fallback='light')]
        sort_by = self.current_sort_criteria.get('by')
        is_default_sort = (sort_by == 'name' and self.current_sort_criteria.get('order') == 'ASC')

        if not is_default_sort and sort_by:
            order = self.current_sort_criteria.get('order', 'ASC')
            icon_name = 'fa5s.sort-amount-down' if order == 'ASC' else 'fa5s.sort-amount-up'
            sort_map = {'name': 'ชื่อ', 'price': 'ราคา', 'id': 'รายการ'}
            text = f"{sort_map.get(sort_by, sort_by.capitalize())}"
            self.sort_button.setStyleSheet(f"background-color: {palette['info']}; color: white;")
            self.sort_button.setIcon(qta.icon(icon_name, color='white'))
            self.sort_button.setText(f" {text}")
        else:
            self.sort_button.setStyleSheet("")
            self.sort_button.setIcon(qta.icon('fa5s.sort', color=PALETTES[app_config.get('UI', 'theme', fallback='light')]['text']))
            self.sort_button.setText("")

    def update_filter_button_state(self):
        """Updates the filter button's appearance based on the current filter state."""
        palette = PALETTES[app_config.get('UI', 'theme', fallback='light')]
        status = self.current_filter_status

        if status:
            status_text = status.replace('_', ' ').capitalize()
            self.filter_button.setText(f" {status_text}")
            self.filter_button.setStyleSheet(f"background-color: {palette['info']}; color: white;")
            self.filter_button.setIcon(qta.icon('fa5s.filter', color='white'))
        else:
            self.filter_button.setText("")
            self.filter_button.setStyleSheet("")
            self.filter_button.setIcon(qta.icon('fa5s.filter', color=PALETTES[app_config.get('UI', 'theme', fallback='light')]['text']))


    def handle_connection_error(self):
        """Shows an error message and closes the dialog if DB connection fails."""
        CustomMessageBox.show(self, CustomMessageBox.Critical, "Connection Error", f"Could not connect to the {'Remote' if self.is_remote else 'Local'} database.")
        self.close()

    def _center_on_screen(self):
        parent = self.main_window_ref
        current_screen = None
        if parent and parent.screen():
            current_screen = parent.screen()
        else:
            current_screen = QApplication.screenAt(QCursor.pos())
        
        if not current_screen:
            current_screen = QApplication.primaryScreen()

        screen_geometry = current_screen.geometry()
        self.move(screen_geometry.center() - self.frameGeometry().center())

    def load_items(self):
        try:
            sort_by = self.current_sort_criteria['by']
            sort_order = self.current_sort_criteria['order']
            # โหลดข้อมูลตามสถานะฟิลเตอร์
            if self.current_filter_status:
                items = self.db_instance.get_items_by_status(self.current_filter_status, get_all_columns=True, sort_by=sort_by, sort_order=sort_order)
            else:
                items = self.db_instance.get_all_items(sort_by=sort_by, sort_order=sort_order)
            
            self.all_items = items if items else []
            self.current_page = 1 # Reset to first page

        except AttributeError:
            # This can happen if db_instance is None after a failed re-connection attempt.
            self.handle_connection_error()
            return
        except Exception as e:
            self.all_items = []
            return
        
        self.display_current_page()

    def display_current_page(self):
        """Clears and repopulates the grid with items for the current page."""
        # --- REVERT: Back to simple grid population ---
        # Clear existing items
        while self.grid_layout.count():
            child = self.grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.cards.clear()
        self.selected_item_id = None
        self.force_return_button.setVisible(False)
        self.confirm_return_button.setVisible(False)

        # Apply search filter
        search_text = self.search_input.text().lower()
        filtered_items = [item for item in self.all_items if search_text in item['name'].lower()] if search_text else self.all_items

        # Pagination logic
        start_index = (self.current_page - 1) * self.items_per_page
        end_index = start_index + self.items_per_page
        items_to_display = filtered_items[start_index:end_index]

        # Layout logic
        self._relayout_items(items_to_display)

        # Update pagination controls
        self.update_pagination_controls(len(filtered_items))
        # --- END REVERT ---

    def update_pagination_controls(self, total_items):
        """Updates the visibility and state of pagination buttons and label."""
        total_pages = max(1, math.ceil(total_items / self.items_per_page))

        if total_pages > 1:
            self.pagination_widget.setVisible(True)
            self.page_label.setText(f"หน้า {self.current_page} / {total_pages}")
            self.prev_page_button.setEnabled(self.current_page > 1)
            self.next_page_button.setEnabled(self.current_page < total_pages)
        else:
            self.pagination_widget.setVisible(False)
        return total_pages

    def filter_items_by_name(self):
        """Filters the visible item cards based on the search input text."""
        self.current_page = 1 # Reset to first page on new search
        self.display_current_page()

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.display_current_page()

    def next_page(self):
        total_items = len([item for item in self.all_items if self.search_input.text().lower() in item['name'].lower()] if self.search_input.text() else self.all_items)
        total_pages = max(1, math.ceil(total_items / self.items_per_page))
        if self.current_page < total_pages:
            self.current_page += 1
            self.display_current_page()

    def add_item(self):
        # --- Non-Modal Logic ---
        if self.item_edit_dialog and self.item_edit_dialog.isVisible():
            self.item_edit_dialog.activateWindow()
            self.item_edit_dialog.raise_()
            return
        try:
            self.item_edit_dialog = ItemDialog(parent=self, db_instance=self.db_instance)
            self.item_edit_dialog.show()
        except Exception as e:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "เกิดข้อผิดพลาด", f"ไม่สามารถเปิดหน้าต่างเพิ่มรายการได้:\n{e}")

    def edit_item(self):
        if not self.selected_item_id:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ไม่ได้เลือก", "กรุณาเลือกรายการที่ต้องการแก้ไข")
            return
        
        # --- Non-Modal Logic ---
        if self.item_edit_dialog and self.item_edit_dialog.isVisible():
            self.item_edit_dialog.activateWindow()
            self.item_edit_dialog.raise_()
            return
        try:
            self.item_edit_dialog = ItemDialog(parent=self, item_id=self.selected_item_id, db_instance=self.db_instance)
            self.item_edit_dialog.show()
        except Exception as e:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "เกิดข้อผิดพลาด", f"ไม่สามารถเปิดหน้าต่างแก้ไขรายการได้:\n{e}")

    def delete_item(self):
        if not self.selected_item_id:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ไม่ได้เลือก", "กรุณาเลือกรายการที่ต้องการลบ")
            return

        reply = CustomMessageBox.show(self, CustomMessageBox.Question, "ยืนยันการลบ", f"คุณต้องการลบรายการ ID: {self.selected_item_id} ใช่หรือไม่?",
                                      buttons=CustomMessageBox.Yes | CustomMessageBox.No)
        if reply == CustomMessageBox.Yes:
            self.db_instance.delete_item(self.selected_item_id) # The data_changed signal will handle the reload

    def force_return_item(self):
        if not self.selected_item_id:
            return
        reply = CustomMessageBox.show(
            self, CustomMessageBox.Question, "ยืนยันการบังคับคืน",
            f"คุณต้องการบังคับคืนรายการ ID: {self.selected_item_id} ใช่หรือไม่?",
            buttons=CustomMessageBox.Yes | CustomMessageBox.No
        )
        if reply == CustomMessageBox.Yes:
            item_data = self.db_instance.get_item_by_id(self.selected_item_id)
            if not item_data:
                CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", "ไม่พบข้อมูลสินค้า")
                return

            # ดึงข้อมูลผู้ใช้ที่กำลังเช่าสินค้านี้
            renter_id = item_data.get('current_renter_id')
            user_data = None
            if renter_id:
                user_data = self.db_instance.get_user_by_id(renter_id)

            # --- FIX: Handle case where the renter user has been deleted (renter_id is NULL or user not found) ---
            if not user_data and item_data.get('status') == 'rented':
                # Create a dummy user_data object for calculation and dialog purposes.
                renter_username = item_data.get('renter_username', f'ผู้ใช้ที่ถูกลบ (ID: {renter_id})')
                # Use -1 for the ID to signify a deleted user in the history record.
                user_data = {'id': -1, 'username': renter_username, 'first_name': renter_username, 'last_name': '(ถูกลบ)', 'email': 'deleted@user.com'}
            elif not user_data:
                CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", "ไม่สามารถระบุข้อมูลผู้เช่าปัจจุบันของสินค้าได้")
                return
            
            calc_dialog = PaymentDialog(item_data, user_data, self, db_instance=self.db_instance)
            amount_to_charge = calc_dialog.get_amount()
            transaction_ref = f"MIKA{str(uuid.uuid4().hex)[:12].upper()}" if amount_to_charge > 0.01 else None
            self.db_instance.return_item(
                item_id=self.selected_item_id,
                amount_due=amount_to_charge,
                transaction_ref=transaction_ref, # Pass None for slip_data
                slip_data=None,  # Pass None for slip_data
                initiator='admin'
            )
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "บังคับคืนสินค้าเรียบร้อยแล้ว")

    def confirm_item_return(self):
        """Admin confirms the physical return of an item."""
        if not self.selected_item_id:
            return

        reply = CustomMessageBox.show(self, CustomMessageBox.Question, "ยืนยันการรับคืน",
                                      f"ยืนยันว่าได้รับสินค้า ID: {self.selected_item_id} คืนแล้วใช่หรือไม่?",
                                      buttons=CustomMessageBox.Yes | CustomMessageBox.No)
        if reply == CustomMessageBox.Yes:
            self.db_instance.confirm_return(self.selected_item_id)
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", f"ยืนยันการรับคืนสินค้า ID: {self.selected_item_id} เรียบร้อยแล้ว")

    def show_filter_menu(self):
        """Displays a menu to filter items by status."""
        menu = QMenu(self)
        
        statuses = {
            "ทั้งหมด": None,
            "พร้อมให้เช่า (Available)": "available",
            "กำลังถูกเช่า (Rented)": "rented",
            "รอการยืนยัน (Pending Return)": "pending_return",
            "ระงับใช้งาน (Suspended)": "suspended"
        }

        for text, status_value in statuses.items():
            action = menu.addAction(text)
            action.triggered.connect(lambda checked=False, s=status_value: self.apply_filter(s))

        menu.exec(self.filter_button.mapToGlobal(self.filter_button.rect().bottomLeft()))

    def apply_filter(self, status: str | None):
        """Applies the selected status filter and reloads items."""
        self.current_filter_status = status
        self.update_filter_button_state()
        self.load_items()

    def show_sort_menu(self):
        """Displays a menu to sort items."""
        menu = QMenu(self.sort_button)

        menu.addAction("ค่าเริ่มต้น (ชื่อ A-Z)").triggered.connect(lambda: self.apply_sort('name', 'ASC'))
        menu.addSeparator()

        sort_options = {
            "ราคาเริ่มต้น (น้อยไปมาก)": ('fixed_fee', 'ASC'),
            "ราคาเริ่มต้น (มากไปน้อย)": ('fixed_fee', 'DESC'),
            "ค่าปรับ (น้อยไปมาก)": ('price_per_minute', 'ASC'),
            "ค่าปรับ (มากไปน้อย)": ('price_per_minute', 'DESC'),
            "--- ": None,
            "รายการ (ใหม่สุด)": ('id', 'DESC'),
            "รายการ (เก่าสุด)": ('id', 'ASC'),
        }

        for text, criteria in sort_options.items():
            if criteria:
                action = menu.addAction(text)
                action.triggered.connect(lambda checked=False, by=criteria[0], order=criteria[1]: self.apply_sort(by, order))
            else:
                menu.addSeparator()

        menu.exec(self.sort_button.mapToGlobal(QPoint(0, self.sort_button.height())))

    def open_user_management(self):
        # --- Non-Modal Logic ---
        if self.user_management_dialog and self.user_management_dialog.isVisible():
            self.user_management_dialog.activateWindow()
            self.user_management_dialog.raise_()
            return
        
        self.user_management_dialog = UserManagementDialog(self)
        self.user_management_dialog.show()
        # --- End Non-Modal Logic ---

    def apply_sort(self, sort_by: str, sort_order: str):
        """Applies the selected sort criteria and reloads items."""
        self.current_sort_criteria = {'by': sort_by, 'order': sort_order}
        self.load_items()
        # Update button appearance
        self.update_sort_button_state()

    def open_income_dashboard(self):
        """Opens the income dashboard dialog."""
        # --- Non-Modal Logic ---
        if self.income_dashboard and self.income_dashboard.isVisible():
            self.income_dashboard.activateWindow()
            self.income_dashboard.raise_()
            return
        
        self.income_dashboard = IncomeDashboard(parent=self, db_instance=self.db_instance)
        self.income_dashboard.show()
        # --- End Non-Modal Logic ---

    def open_system_settings(self):
        """Opens the system settings dialog, passing the correct context (local/remote)."""
        if self.is_remote:
            # Remote admin edits settings stored on the server DB
            dialog = SystemSettingsDialog(
                main_window_ref=self.main_window_ref,
                parent=self,
                db_instance=self.db_instance,
                current_user=self.current_admin_user # Pass the admin user who logged into this panel
            )
        else:
            # Local admin edits the local app_config.ini file
            dialog = LocalSettingsDialog(main_window_ref=self.main_window_ref, parent=self) # No db_instance needed
        
        dialog.exec()

    def toggle_theme(self):
        """Calls the main window's theme toggle method."""
        if self.main_window_ref:
            self.main_window_ref.toggle_theme()
        # Ensure this panel's icons are also updated immediately.
        self.update_icons()

    def handle_data_change(self, table_name: str):
        """Slot to handle data changes from the database."""
        print(f"AdminPanel received data_changed signal for table: {table_name}")
        if table_name == 'items':
            self.load_items()

    def on_card_clicked(self, item_id):
        self.selected_item_id = item_id
        # This logic is now handled inside the ItemCard's mousePressEvent
        # by passing the event to its superclass, which propagates it up to the scroll area.
        # No code is needed here for that.

        item_data = self.db_instance.get_item_by_id(item_id)
        if item_data and item_data.get('status') == 'rented':
            self.force_return_button.setVisible(True)
        elif item_data and item_data.get('status') == 'pending_return':
            self.confirm_return_button.setVisible(True)
        else:
            self.force_return_button.setVisible(False)

        for card in self.cards:
            is_selected = (card.item_id == item_id)
            card.setProperty("selected", is_selected)
            # Refresh style
            card.style().unpolish(card)
            card.style().polish(card)

    def _relayout_items(self, items_to_display=None):
        """Re-arranges existing ItemCard widgets in the grid without reloading data."""
        if items_to_display is None:
            search_text = self.search_input.text().lower()
            filtered_items = [item for item in self.all_items if search_text in item['name'].lower()] if search_text else self.all_items
            start_index = (self.current_page - 1) * self.items_per_page
            items_to_display = filtered_items[start_index : start_index + self.items_per_page]

        while self.grid_layout.count():
            child = self.grid_layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)
        self.cards.clear()

        num_cols = 9
        for i, item_data in enumerate(items_to_display):
            row, col = divmod(i, num_cols)
            card = ItemCard(item_data)
            card.clicked.connect(self.on_card_clicked)
            card.mouseDoubleClickEvent = lambda _event, item_id=item_data['id']: self.on_card_double_clicked(item_id)
            self.grid_layout.addWidget(card, row, col)
            self.cards.append(card)

    def on_card_double_clicked(self, item_id):
        self.selected_item_id = item_id
        self.edit_item()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Debounce the relayout call to prevent excessive re-renders during resizing
        QTimer.singleShot(50, self._relayout_items)

    def closeEvent(self, event):
        """เมื่อปิดหน้า Admin ให้โหลดข้อมูลในหน้าหลักใหม่"""
        # Reset the correct panel reference in the main window
        if self.is_remote:
            self.main_window_ref.remote_admin_panel = None
        else:
            self.main_window_ref.local_admin_panel = None

        try:
            db_signals.data_changed.disconnect(self.handle_data_change)
        except TypeError: # Signal was not connected or already disconnected
            pass
        super().closeEvent(event)
        self.cards.clear()
        self.selected_item_id = None
        self.force_return_button.setVisible(False)
        self.confirm_return_button.setVisible(False)

        # Apply search filter
        search_text = self.search_input.text().lower()
        filtered_items = [item for item in self.all_items if search_text in item['name'].lower()] if search_text else self.all_items

        # Pagination logic
        start_index = (self.current_page - 1) * self.items_per_page
        end_index = start_index + self.items_per_page
        items_to_display = filtered_items[start_index:end_index]

        # Layout logic
        self._relayout_items(items_to_display)

        # Update pagination controls
        self.update_pagination_controls(len(filtered_items))

    def update_pagination_controls(self, total_items):
        """Updates the visibility and state of pagination buttons and label."""
        total_pages = max(1, math.ceil(total_items / self.items_per_page))

        if total_pages > 1:
            self.pagination_widget.setVisible(True)
            self.page_label.setText(f"หน้า {self.current_page} / {total_pages}")
            self.prev_page_button.setEnabled(self.current_page > 1)
            self.next_page_button.setEnabled(self.current_page < total_pages)
        else:
            self.pagination_widget.setVisible(False)
        return total_pages

    def filter_items_by_name(self):
        """Filters the visible item cards based on the search input text."""
        self.current_page = 1 # Reset to first page on new search
        self.display_current_page()

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.display_current_page()

    def next_page(self):
        total_items = len([item for item in self.all_items if self.search_input.text().lower() in item['name'].lower()] if self.search_input.text() else self.all_items)
        total_pages = max(1, math.ceil(total_items / self.items_per_page))
        if self.current_page < total_pages:
            self.current_page += 1
            self.display_current_page()

    def add_item(self):
        # --- Non-Modal Logic ---
        if self.item_edit_dialog and self.item_edit_dialog.isVisible():
            self.item_edit_dialog.activateWindow()
            self.item_edit_dialog.raise_()
            return
        try:
            self.item_edit_dialog = ItemDialog(parent=self, db_instance=self.db_instance)
            self.item_edit_dialog.show()
        except Exception as e:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "เกิดข้อผิดพลาด", f"ไม่สามารถเปิดหน้าต่างเพิ่มรายการได้:\n{e}")

    def edit_item(self):
        if not self.selected_item_id:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ไม่ได้เลือก", "กรุณาเลือกรายการที่ต้องการแก้ไข")
            return
        
        # --- Non-Modal Logic ---
        if self.item_edit_dialog and self.item_edit_dialog.isVisible():
            self.item_edit_dialog.activateWindow()
            self.item_edit_dialog.raise_()
            return
        try:
            self.item_edit_dialog = ItemDialog(parent=self, item_id=self.selected_item_id, db_instance=self.db_instance)
            self.item_edit_dialog.show()
        except Exception as e:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "เกิดข้อผิดพลาด", f"ไม่สามารถเปิดหน้าต่างแก้ไขรายการได้:\n{e}")

    def delete_item(self):
        if not self.selected_item_id:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ไม่ได้เลือก", "กรุณาเลือกรายการที่ต้องการลบ")
            return

        reply = CustomMessageBox.show(self, CustomMessageBox.Question, "ยืนยันการลบ", f"คุณต้องการลบรายการ ID: {self.selected_item_id} ใช่หรือไม่?",
                                      buttons=CustomMessageBox.Yes | CustomMessageBox.No)
        if reply == CustomMessageBox.Yes:
            self.db_instance.delete_item(self.selected_item_id) # The data_changed signal will handle the reload

    def force_return_item(self):
        if not self.selected_item_id:
            return
        reply = CustomMessageBox.show(
            self, CustomMessageBox.Question, "ยืนยันการบังคับคืน",
            f"คุณต้องการบังคับคืนรายการ ID: {self.selected_item_id} ใช่หรือไม่?",
            buttons=CustomMessageBox.Yes | CustomMessageBox.No
        )
        if reply == CustomMessageBox.Yes:
            item_data = self.db_instance.get_item_by_id(self.selected_item_id)
            if not item_data:
                CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", "ไม่พบข้อมูลสินค้า")
                return

            # ดึงข้อมูลผู้ใช้ที่กำลังเช่าสินค้านี้
            renter_id = item_data.get('current_renter_id')
            user_data = None
            if renter_id:
                user_data = self.db_instance.get_user_by_id(renter_id)

            # --- FIX: Handle case where the renter user has been deleted (renter_id is NULL or user not found) ---
            if not user_data and item_data.get('status') == 'rented':
                # Create a dummy user_data object for calculation and dialog purposes.
                renter_username = item_data.get('renter_username', f'ผู้ใช้ที่ถูกลบ (ID: {renter_id})')
                # Use -1 for the ID to signify a deleted user in the history record.
                user_data = {'id': -1, 'username': renter_username, 'first_name': renter_username, 'last_name': '(ถูกลบ)', 'email': 'deleted@user.com'}
            elif not user_data:
                CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", "ไม่สามารถระบุข้อมูลผู้เช่าปัจจุบันของสินค้าได้")
                return
            
            calc_dialog = PaymentDialog(item_data, user_data, self, db_instance=self.db_instance)
            amount_to_charge = calc_dialog.get_amount()
            transaction_ref = f"MIKA{str(uuid.uuid4().hex)[:12].upper()}" if amount_to_charge > 0.01 else None
            self.db_instance.return_item(
                item_id=self.selected_item_id,
                amount_due=amount_to_charge,
                transaction_ref=transaction_ref, # Pass None for slip_data
                slip_data=None,  # Pass None for slip_data
                initiator='admin'
            )
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "บังคับคืนสินค้าเรียบร้อยแล้ว")

    def confirm_item_return(self):
        """Admin confirms the physical return of an item."""
        if not self.selected_item_id:
            return

        reply = CustomMessageBox.show(self, CustomMessageBox.Question, "ยืนยันการรับคืน",
                                      f"ยืนยันว่าได้รับสินค้า ID: {self.selected_item_id} คืนแล้วใช่หรือไม่?",
                                      buttons=CustomMessageBox.Yes | CustomMessageBox.No)
        if reply == CustomMessageBox.Yes:
            self.db_instance.confirm_return(self.selected_item_id)
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", f"ยืนยันการรับคืนสินค้า ID: {self.selected_item_id} เรียบร้อยแล้ว")

    def show_filter_menu(self):
        """Displays a menu to filter items by status."""
        menu = QMenu(self)
        
        statuses = {
            "ทั้งหมด": None,
            "พร้อมให้เช่า (Available)": "available",
            "กำลังถูกเช่า (Rented)": "rented",
            "รอการยืนยัน (Pending Return)": "pending_return",
            "ระงับใช้งาน (Suspended)": "suspended"
        }

        for text, status_value in statuses.items():
            action = menu.addAction(text)
            action.triggered.connect(lambda checked=False, s=status_value: self.apply_filter(s))

        menu.exec(self.filter_button.mapToGlobal(self.filter_button.rect().bottomLeft()))

    def apply_filter(self, status: str | None):
        """Applies the selected status filter and reloads items."""
        self.current_filter_status = status
        self.update_filter_button_state()
        self.load_items()

    def open_user_management(self):
        # --- Non-Modal Logic ---
        if self.user_management_dialog and self.user_management_dialog.isVisible():
            self.user_management_dialog.activateWindow()
            self.user_management_dialog.raise_()
            return
        
        self.user_management_dialog = UserManagementDialog(self)
        self.user_management_dialog.show()
        # --- End Non-Modal Logic ---

    def open_income_dashboard(self):
        """Opens the income dashboard dialog."""
        # --- Non-Modal Logic ---
        if self.income_dashboard and self.income_dashboard.isVisible():
            self.income_dashboard.activateWindow()
            self.income_dashboard.raise_()
            return
        
        self.income_dashboard = IncomeDashboard(parent=self, db_instance=self.db_instance)
        self.income_dashboard.show()
        # --- End Non-Modal Logic ---

    def open_system_settings(self):
        """Opens the system settings dialog, passing the correct context (local/remote)."""
        if self.is_remote:
            # Remote admin edits settings stored on the server DB
            dialog = SystemSettingsDialog(
                main_window_ref=self.main_window_ref,
                parent=self,
                db_instance=self.db_instance,
                current_user=self.current_admin_user # Pass the admin user who logged into this panel
            )
        else:
            # Local admin edits the local app_config.ini file
            dialog = LocalSettingsDialog(main_window_ref=self.main_window_ref, parent=self) # No db_instance needed
        
        dialog.exec()

    def toggle_theme(self):
        """Calls the main window's theme toggle method."""
        if self.main_window_ref:
            self.main_window_ref.toggle_theme()
        # Ensure this panel's icons are also updated immediately.
        self.update_icons()

    def handle_data_change(self, table_name: str):
        """Slot to handle data changes from the database."""
        print(f"AdminPanel received data_changed signal for table: {table_name}")
        if table_name == 'items':
            self.load_items()

    def on_card_clicked(self, item_id):
        self.selected_item_id = item_id
        # This logic is now handled inside the ItemCard's mousePressEvent
        # by passing the event to its superclass, which propagates it up to the scroll area.
        # No code is needed here for that.

        item_data = self.db_instance.get_item_by_id(item_id)
        if item_data and item_data.get('status') == 'rented':
            self.force_return_button.setVisible(True)
        elif item_data and item_data.get('status') == 'pending_return':
            self.confirm_return_button.setVisible(True)
        else:
            self.force_return_button.setVisible(False)

        for card in self.cards:
            is_selected = (card.item_id == item_id)
            card.setProperty("selected", is_selected)
            # Refresh style
            card.style().unpolish(card)
            card.style().polish(card)

    def _relayout_items(self, items_to_display=None):
        """Re-arranges existing ItemCard widgets in the grid without reloading data."""
        if items_to_display is None:
            search_text = self.search_input.text().lower()
            filtered_items = [item for item in self.all_items if search_text in item['name'].lower()] if search_text else self.all_items
            start_index = (self.current_page - 1) * self.items_per_page
            items_to_display = filtered_items[start_index : start_index + self.items_per_page]

        while self.grid_layout.count():
            child = self.grid_layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)
        self.cards.clear()

        num_cols = 9
        for i, item_data in enumerate(items_to_display):
            row, col = divmod(i, num_cols)
            card = ItemCard(item_data)
            card.clicked.connect(self.on_card_clicked)
            card.mouseDoubleClickEvent = lambda _event, item_id=item_data['id']: self.on_card_double_clicked(item_id)
            self.grid_layout.addWidget(card, row, col)
            self.cards.append(card)

    def on_card_double_clicked(self, item_id):
        self.selected_item_id = item_id
        self.edit_item()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Debounce the relayout call to prevent excessive re-renders during resizing
        QTimer.singleShot(50, self._relayout_items)

    def closeEvent(self, event):
        """เมื่อปิดหน้า Admin ให้โหลดข้อมูลในหน้าหลักใหม่"""
        # Reset the correct panel reference in the main window
        if self.is_remote:
            self.main_window_ref.remote_admin_panel = None
        else:
            self.main_window_ref.local_admin_panel = None

        try:
            db_signals.data_changed.disconnect(self.handle_data_change)
        except TypeError: # Signal was not connected or already disconnected
            pass
        super().closeEvent(event)

    def delete_item(self):
        if not self.selected_item_id:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ไม่ได้เลือก", "กรุณาเลือกรายการที่ต้องการลบ")
            return

        reply = CustomMessageBox.show(self, CustomMessageBox.Question, "ยืนยันการลบ", f"คุณต้องการลบรายการ ID: {self.selected_item_id} ใช่หรือไม่?",
                                      buttons=CustomMessageBox.Yes | CustomMessageBox.No)
        if reply == CustomMessageBox.Yes:
            self.db_instance.delete_item(self.selected_item_id) # The data_changed signal will handle the reload

    def force_return_item(self):
        if not self.selected_item_id:
            return
        reply = CustomMessageBox.show(
            self, CustomMessageBox.Question, "ยืนยันการบังคับคืน",
            f"คุณต้องการบังคับคืนรายการ ID: {self.selected_item_id} ใช่หรือไม่?",
            buttons=CustomMessageBox.Yes | CustomMessageBox.No
        )
        if reply == CustomMessageBox.Yes:
            item_data = self.db_instance.get_item_by_id(self.selected_item_id)
            if not item_data:
                CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", "ไม่พบข้อมูลสินค้า")
                return

            # ดึงข้อมูลผู้ใช้ที่กำลังเช่าสินค้านี้
            renter_id = item_data.get('current_renter_id')
            user_data = None
            if renter_id:
                user_data = self.db_instance.get_user_by_id(renter_id)

            # --- FIX: Handle case where the renter user has been deleted (renter_id is NULL or user not found) ---
            if not user_data and item_data.get('status') == 'rented':
                # Create a dummy user_data object for calculation and dialog purposes.
                renter_username = item_data.get('renter_username', f'ผู้ใช้ที่ถูกลบ (ID: {renter_id})')
                # Use -1 for the ID to signify a deleted user in the history record.
                user_data = {'id': -1, 'username': renter_username, 'first_name': renter_username, 'last_name': '(ถูกลบ)', 'email': 'deleted@user.com'}
            elif not user_data:
                CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", "ไม่สามารถระบุข้อมูลผู้เช่าปัจจุบันของสินค้าได้")
                return
            
            calc_dialog = PaymentDialog(item_data, user_data, self, db_instance=self.db_instance)
            amount_to_charge = calc_dialog.get_amount()
            transaction_ref = f"MIKA{str(uuid.uuid4().hex)[:12].upper()}" if amount_to_charge > 0.01 else None
            self.db_instance.return_item(
                item_id=self.selected_item_id,
                amount_due=amount_to_charge,
                transaction_ref=transaction_ref, # Pass None for slip_data
                slip_data=None,  # Pass None for slip_data
                initiator='admin'
            )
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "บังคับคืนสินค้าเรียบร้อยแล้ว")

    def confirm_item_return(self):
        """Admin confirms the physical return of an item."""
        if not self.selected_item_id:
            return

        reply = CustomMessageBox.show(self, CustomMessageBox.Question, "ยืนยันการรับคืน",
                                      f"ยืนยันว่าได้รับสินค้า ID: {self.selected_item_id} คืนแล้วใช่หรือไม่?",
                                      buttons=CustomMessageBox.Yes | CustomMessageBox.No)
        if reply == CustomMessageBox.Yes:
            self.db_instance.confirm_return(self.selected_item_id)
            CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", f"ยืนยันการรับคืนสินค้า ID: {self.selected_item_id} เรียบร้อยแล้ว")

    def show_filter_menu(self):
        """Displays a menu to filter items by status."""
        menu = QMenu(self)
        
        statuses = {
            "ทั้งหมด": None,
            "พร้อมให้เช่า (Available)": "available",
            "กำลังถูกเช่า (Rented)": "rented",
            "รอการยืนยัน (Pending Return)": "pending_return",
            "ระงับใช้งาน (Suspended)": "suspended"
        }

        for text, status_value in statuses.items():
            action = menu.addAction(text)
            action.triggered.connect(lambda checked=False, s=status_value: self.apply_filter(s))

        menu.exec(self.filter_button.mapToGlobal(self.filter_button.rect().bottomLeft()))

    def apply_filter(self, status: str | None):
        """Applies the selected status filter and reloads items."""
        self.current_filter_status = status
        self.update_filter_button_state()
        self.load_items()

    def open_user_management(self):
        # --- Non-Modal Logic ---
        if self.user_management_dialog and self.user_management_dialog.isVisible():
            self.user_management_dialog.activateWindow()
            self.user_management_dialog.raise_()
            return
        
        self.user_management_dialog = UserManagementDialog(self)
        self.user_management_dialog.show()
        # --- End Non-Modal Logic ---

    def open_system_settings(self):
        """Opens the system settings dialog, passing the correct context (local/remote)."""
        if self.is_remote:
            # Remote admin edits settings stored on the server DB
            dialog = SystemSettingsDialog(
                main_window_ref=self.main_window_ref,
                parent=self,
                db_instance=self.db_instance,
                current_user=self.current_admin_user # Pass the admin user who logged into this panel
            )
        else:
            # Local admin edits the local app_config.ini file
            dialog = LocalSettingsDialog(main_window_ref=self.main_window_ref, parent=self) # No db_instance needed
        
        dialog.exec()

    def toggle_theme(self):
        """Calls the main window's theme toggle method."""
        if self.main_window_ref:
            self.main_window_ref.toggle_theme()
        # Ensure this panel's icons are also updated immediately.
        self.update_icons()

    def handle_data_change(self, table_name: str):
        """Slot to handle data changes from the database."""
        print(f"AdminPanel received data_changed signal for table: {table_name}")
        if table_name == 'items':
            self.load_items()

    def on_card_clicked(self, item_id):
        self.selected_item_id = item_id
        # This logic is now handled inside the ItemCard's mousePressEvent
        # by passing the event to its superclass, which propagates it up to the scroll area.
        # No code is needed here for that.

        item_data = self.db_instance.get_item_by_id(item_id)
        if item_data and item_data.get('status') == 'rented':
            self.force_return_button.setVisible(True)
        elif item_data and item_data.get('status') == 'pending_return':
            self.confirm_return_button.setVisible(True)
        else:
            self.force_return_button.setVisible(False)

        for card in self.cards:
            is_selected = (card.item_id == item_id)
            card.setProperty("selected", is_selected)
            # Refresh style
            card.style().unpolish(card)
            card.style().polish(card)

    def on_card_double_clicked(self, item_id):
        self.selected_item_id = item_id
        self.edit_item()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Debounce the relayout call to prevent excessive re-renders during resizing
        self._relayout_items()

    def closeEvent(self, event):
        """เมื่อปิดหน้า Admin ให้โหลดข้อมูลในหน้าหลักใหม่"""
        # Reset the correct panel reference in the main window
        if self.is_remote:
            self.main_window_ref.remote_admin_panel = None
        else:
            self.main_window_ref.local_admin_panel = None

        try:
            db_signals.data_changed.disconnect(self.handle_data_change)
        except TypeError: # Signal was not connected or already disconnected
            pass
        super().closeEvent(event)
