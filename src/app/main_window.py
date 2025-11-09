from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QApplication,
    QLabel, QLineEdit, QPushButton, QMessageBox, QScrollArea, QGridLayout,
    QMenu, QSpacerItem, QSizePolicy, QFrame, QScroller, QScrollerProperties
)
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal, QEvent, pyqtSlot, QPoint, QPointF, QElapsedTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap, QIcon, QWheelEvent, QMouseEvent
import math
import qtawesome as qta
import cv2
from theme import theme, PALETTES
from app_config import app_config
from app_db.db_management import db_manager, db_signals, get_db_instance, initialize_databases
from app_admin.login import AdminLoginWindow
from app_admin.admin import AdminPanel
from .login import UserLoginWindow
from .profile_view import UserProfileViewWindow
from .item_card import ItemCard
from .item_detail import ItemDetailWindow
from app_admin.console import AdminConsole
from app_user.my_rentals_dialog import MyRentalsDialog
from app_payment.payment_history_dialog import PaymentHistoryDialog
from app.utils import get_icon
from .custom_message_box import CustomMessageBox
from .about_dialog import AboutDialog

class ClickableLabel(QLabel):
    """A QLabel that emits a double-clicked signal."""
    doubleClicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)

class MainWindow(QMainWindow):
    # Signal to send camera list back to the requester
    cameraListReady = pyqtSignal(list)

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        # อ่านธีมล่าสุดจาก config, ถ้าไม่มีให้ใช้ 'light' เป็นค่าเริ่มต้น
        self.current_theme = app_config.get('UI', 'theme', fallback='light')
        theme.apply_theme(self.app, self.current_theme)

        self.setWindowTitle("MiKA RENTAL")
        # --- FIX: Explicitly set the window icon on the main window itself ---
        # This is more reliable for ensuring the taskbar icon appears correctly.
        self.setWindowIcon(get_icon("app_image/icon.ico"))

        # ปรับขนาดหน้าต่างหลักตามขนาดหน้าจอ
        current_screen = app.screenAt(QApplication.primaryScreen().geometry().center())
        if not current_screen:
            current_screen = QApplication.primaryScreen()
        
        available_geom = current_screen.availableGeometry()
        self.resize(int(available_geom.width() * 0.8), int(available_geom.height() * 0.8))
        
        # จัดหน้าต่างให้อยู่กลางจอ
        screen_geometry = current_screen.geometry()
        self.move(screen_geometry.center() - self.frameGeometry().center())

        
        self.current_user = None
        self.admin_console = None
        self.local_admin_panel = None
        self.remote_admin_panel = None
        self.current_filter_status = None  # สำหรับการกรองหน้าหลัก
        # --- Window Management for Non-Modal Dialogs ---
        self.current_sort_criteria = {'by': 'name', 'order': 'ASC'}
        self.open_detail_windows = {} # {item_id: window_instance}
        self.user_profile_window = None
        self.my_rentals_window = None
        self.payment_history_window = None
        self.about_dialog = None
        # --- End Window Management ---
        self.item_cards = [] # สำหรับเก็บ ItemCard widgets เพื่อ re-layout
        self.grid_spacer = None # สำหรับป้องกันการหดของ layout
        self.last_num_cols = 0 # สำหรับตรวจสอบว่าต้อง relayout หรือไม่
        self.all_items = []
        self.current_page = 1
        self.items_per_page = 27 # 3 rows * 9 columns

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- สร้าง Header Widget เพื่อรวมส่วนหัวและส่วนค้นหา ---
        header_widget = QWidget()
        header_widget.setObjectName("HeaderWidget")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 10, 10, 10)
        header_layout.setSpacing(10)

        # --- App Icon ---
        self.app_icon_label = ClickableLabel()
        # ใช้ get_icon เพื่อให้แน่ใจว่าหาไฟล์เจอทั้งใน dev และ build mode
        app_icon = get_icon("app_image/pic.png")
        pixmap = app_icon.pixmap(QSize(60, 60))
        self.app_icon_label.setPixmap(pixmap.scaled(QSize(60, 60), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.app_icon_label.setToolTip("ข้อมูลโปรแกรม (ดับเบิลคลิก)")
        self.app_icon_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.app_icon_label.doubleClicked.connect(self.open_about_dialog)
        header_layout.addWidget(self.app_icon_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("ค้นหารายการ เช่า-ยืม...")
        self.search_input.textChanged.connect(self.filter_items)

        self.filter_button = QPushButton()
        self.filter_button.setObjectName("IconButton")
        self.filter_button.setToolTip("คัดกรองตามสถานะ")
        self.filter_button.setFixedHeight(60) # กำหนดความสูงให้เท่ากับปุ่มอื่น
        self.filter_button.clicked.connect(self.show_main_filter_menu)

        self.sort_button = QPushButton()
        self.sort_button.setObjectName("IconButton")
        self.sort_button.setToolTip("จัดเรียงรายการ")
        self.sort_button.setFixedHeight(60)
        self.sort_button.clicked.connect(self.show_main_sort_menu)

        header_layout.addWidget(self.search_input, 2) # ให้ช่องค้นหายืดได้มากขึ้น

        # --- Pagination Controls (moved to header) ---
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
        pagination_layout.addStretch() # *** จัดให้อยู่ตรงกลาง ***
        pagination_layout.addWidget(self.prev_page_button)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_page_button)
        pagination_layout.addStretch()
        
        self.pagination_widget = pagination_container
        self.pagination_widget.setVisible(False) # Hide by default

        # --- สร้าง Layout สำหรับกลุ่มองค์ประกอบด้านขวา ---
        right_header_layout = QHBoxLayout()
        right_header_layout.setSpacing(10)

        # --- User Status Area ---
        user_status_layout = QHBoxLayout()
        self.avatar_label = QLabel()
        self.avatar_label.setObjectName("UserAvatarLabel")
        self.avatar_label.setFixedSize(60, 60) # ปรับขนาด Avatar
        self.user_name_label = QLabel()
        self.user_name_label.setObjectName("UserNameLabel")
        self.user_name_label.setWordWrap(True)
        user_status_layout.addWidget(self.avatar_label)
        user_status_layout.addWidget(self.user_name_label, 1) # เพิ่ม Stretch Factor เพื่อให้ขยายเต็มพื้นที่
        right_header_layout.addLayout(user_status_layout)
        # --- End User Status Area ---
        
        # --- Profile Button ---
        self.profile_button = QPushButton("ข้อมูลส่วนตัว")
        self.profile_button.clicked.connect(self.open_user_profile)
        self.profile_button.setToolTip("ข้อมูลส่วนตัว")
        self.profile_button.setVisible(False)
        right_header_layout.addWidget(self.profile_button)

        # --- My Rentals Button ---
        self.my_rentals_button = QPushButton()
        self.my_rentals_button.clicked.connect(self.open_my_rentals)
        self.my_rentals_button.setToolTip("รายการที่กำลังยืม")
        self.my_rentals_button.setVisible(False)
        right_header_layout.addWidget(self.my_rentals_button)

        # --- Payment History Button ---
        self.payment_history_button = QPushButton()
        self.payment_history_button.clicked.connect(self.open_payment_history)
        self.payment_history_button.setToolTip("การชำระเงิน")
        self.payment_history_button.setVisible(False)
        right_header_layout.addWidget(self.payment_history_button)

        self.login_button = QPushButton("เข้าสู่ระบบ / สมัครสมาชิก")
        self.login_button.setFixedHeight(60) # กำหนดความสูงให้เท่ากับปุ่มไอคอน
        self.login_button.clicked.connect(self.open_user_login)

        right_header_layout.addWidget(self.login_button)

        # --- Theme Toggle Button ---
        self.theme_button = QPushButton()
        self.theme_button.setObjectName("IconButton")
        self.theme_button.clicked.connect(self.toggle_theme)
        right_header_layout.addWidget(self.theme_button)
        # --- End Theme Toggle Button ---
        header_layout.addWidget(self.sort_button)
        header_layout.addWidget(self.filter_button)
        header_layout.addWidget(self.pagination_widget, 1) # ให้พื้นที่น้อยกว่าช่องค้นหา

        header_layout.addLayout(right_header_layout) # เพิ่มกลุ่มองค์ประกอบด้านขวาเข้าไปใน Header หลัก

        main_layout.addWidget(header_widget)

        # --- REVERT: Use a standard QScrollArea and QGridLayout ---
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
        # --- END REVERT ---
        
        main_layout.addWidget(self.scroll_area)

        QScroller.grabGesture(self.scroll_area.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        QTimer.singleShot(0, self.initial_load)

        # อัปเดต UI ทั้งหมดหลังจากสร้าง widget ทั้งหมดแล้ว
        self.update_theme_dependent_widgets()

        # Connect global signals
        db_signals.payment_status_updated.connect(self.on_payment_status_updated)
        db_signals.data_changed.connect(self.on_data_changed)

        # --- Auto Logout Timer ---
        self.auto_logout_timer = QTimer(self)
        self.auto_logout_timer.setSingleShot(True)
        self.auto_logout_timer.timeout.connect(self.auto_logout)

    def _get_db_instance_for_refresh(self):
        """
        Returns the globally initialized db_management instance.
        This avoids creating new connections on every refresh.
        """
        return get_db_instance(is_remote=app_config.get('DATABASE', 'enabled', 'False').lower() == 'true')

    def switch_database_mode(self, use_server: bool) -> tuple[bool, str]:
        """
        สลับโหมดฐานข้อมูลของโปรแกรมและรีเฟรชข้อมูลทั้งหมด
        ถูกเรียกใช้จาก Admin Console หรือ LocalSettingsDialog
        """
        try:
            current_setting = app_config.get('DATABASE', 'enabled', 'False').lower() == 'true'
            # If the mode isn't actually changing, do nothing.
            if use_server == current_setting:
                return True, f"โหมดฐานข้อมูลเป็น {'Server' if use_server else 'Local'} อยู่แล้ว"

            # --- NEW: Check if server settings are configured before switching ---
            if use_server:
                host = app_config.get('DATABASE', 'host', '').strip()
                port = app_config.get('DATABASE', 'port', '').strip()
                dbname = app_config.get('DATABASE', 'database', '').strip()
                user = app_config.get('DATABASE', 'user', '').strip()
                if not all([host, port, dbname, user]):
                    CustomMessageBox.show(self, CustomMessageBox.Warning, "การตั้งค่าไม่สมบูรณ์", "กรุณาตั้งค่าการเชื่อมต่อฐานข้อมูลเซิร์ฟเวอร์ก่อนเปิดใช้งานโหมด Server")
                    # Revert the button state in the settings dialog if it was called from there
                    if self.sender() and hasattr(self.sender(), 'setChecked'):
                        self.sender().setChecked(False)
                    return False, "การสลับโหมดล้มเหลว: การตั้งค่าเซิร์ฟเวอร์ไม่สมบูรณ์"
            # --- END NEW ---

            # 1. อัปเดตการตั้งค่าใน config
            app_config.update_config('DATABASE', 'enabled', str(use_server))

            # 2. เริ่มต้นการเชื่อมต่อฐานข้อมูลใหม่
            initialize_databases() # Re-initialize the global instance manager

            # 3. รับ instance ใหม่หลังจาก re-initialize
            new_instance = self._get_db_instance_for_refresh()

            # 3.5 Reset UI state before loading new data
            self.apply_main_filter(None) # Reset any active filters
            self.update_user_status() # Refresh user display

            # 4. โหลดข้อมูลรายการในหน้าหลักใหม่
            self.load_items()

            # 5. รีเฟรช Admin Panel ที่อาจจะเปิดอยู่โดยส่ง instance ใหม่ไปให้
            if use_server and self.remote_admin_panel and self.remote_admin_panel.isVisible():
                self.remote_admin_panel.reinitialize_db_instance(new_instance)
            elif not use_server and self.local_admin_panel and self.local_admin_panel.isVisible():
                self.local_admin_panel.reinitialize_db_instance(new_instance)
                
            return True, f"สลับโหมดฐานข้อมูลเป็น {'Server' if use_server else 'Local'} เรียบร้อยแล้ว"
        except Exception as e:
            # Show a message box to the user on failure
            CustomMessageBox.show(self, CustomMessageBox.Critical, "การสลับโหมดล้มเหลว", str(e))
            # Revert the config setting if the switch failed
            app_config.update_config('DATABASE', 'enabled', str(not use_server))
            return False, f"ไม่สามารถสลับโหมดฐานข้อมูลได้: {e}"
        finally:
            # --- NEW: Always log out the user when switching modes ---
            if self.current_user:
                self.current_user = None
                self.auto_logout_timer.stop()
                self.update_user_status() # Refresh the UI to reflect the logout

    def initial_load(self):
        self.load_items()
        self.update_user_status() # อัปเดตสถานะครั้งแรก

    def load_items(self):

        try:
            current_db_instance = self._get_db_instance_for_refresh()

            # Ensure we call get_all_items on the correct instance
            sort_by = self.current_sort_criteria['by']
            sort_order = self.current_sort_criteria['order']
            if self.current_filter_status:
                items = current_db_instance.get_items_by_status(self.current_filter_status, get_all_columns=True, sort_by=sort_by, sort_order=sort_order)
            else:
                items = current_db_instance.get_all_items(sort_by=sort_by, sort_order=sort_order)
            
            # Handle case where DB connection is fine but no items are returned
            if items is None:
                items = []

            self.all_items = items
            self.current_page = 1 # Reset to first page

        except ConnectionError as e:
            # This specific error is raised when the local DB file is not found.
            error_label = QLabel(str(e)) # Display the specific error message from db_management
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            error_label.setStyleSheet("font-size: 14pt; color: #f39c12;") # Warning color
            self.grid_layout.addWidget(error_label, 0, 0, 1, 5)
            self.all_items = []
            self.display_current_page() # This will clear the grid
            return # Stop further processing
        except Exception as e:
            # Differentiate between a connection error and a table-not-found error.
            error_message = str(e).lower()
            if 'relation' in error_message and 'does not exist' in error_message:
                # This is likely a psycopg2.errors.UndefinedTable error.
                display_text = "ฐานข้อมูลยังไม่พร้อมใช้งาน\nกรุณาใช้คำสั่ง 'db init-server' ใน Console (F2) เพื่อสร้างตาราง"
            else:
                # For other errors, assume it's a connection issue.
                display_text = f"ไม่สามารถเชื่อมต่อฐานข้อมูลเซิร์ฟเวอร์ได้\nกรุณาตรวจสอบการตั้งค่าหรือการเชื่อมต่อเครือข่าย"
            
            error_label = QLabel(display_text)
            # ... error handling for UI ...
            print(f"Database Error in load_items: ไม่สามารถดึงข้อมูลได้ (อาจเกิดจากปัญหาการเชื่อมต่อ)")
            self.all_items = []
            self.display_current_page() # This will update pagination
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
        self.item_cards.clear()

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

    def _relayout_items(self, items_to_display=None):
        """
        Re-arranges existing ItemCard widgets in the grid without reloading data.
        This is much faster and avoids flickering on resize.
        """
        if items_to_display is None:
            search_text = self.search_input.text().lower()
            filtered_items = [item for item in self.all_items if search_text in item['name'].lower()] if search_text else self.all_items
            start_index = (self.current_page - 1) * self.items_per_page
            items_to_display = filtered_items[start_index : start_index + self.items_per_page]

        # Clear grid layout
        while self.grid_layout.count():
            child = self.grid_layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None) # Use setParent(None) for safety
        self.item_cards.clear()

        # Calculate number of columns based on window width
        num_cols = 9

        # Re-populate grid
        for i, item_data in enumerate(items_to_display):
            row = i // num_cols
            col = i % num_cols
            card = ItemCard(item_data)
            card.doubleClicked.connect(self.open_item_detail)
            self.grid_layout.addWidget(card, row, col)
            self.item_cards.append(card)

    def filter_items(self):
        self.reset_auto_logout_timer() # Reset timer on search
        self.current_page = 1 # Reset to first page on new search
        self.display_current_page()

    def open_item_detail(self, item_id, return_instance=False):
        self.reset_auto_logout_timer() # Reset timer when user interacts
        # --- Non-Modal Logic ---
        if item_id in self.open_detail_windows and self.open_detail_windows[item_id]:
            win = self.open_detail_windows[item_id]
            win.show()
            win.activateWindow()
            win.raise_() # Bring to front
            if return_instance:
                return win
        else:
            win = ItemDetailWindow(item_id, self.current_user, self)
            win.finished.connect(lambda: self.on_child_window_closed('detail', item_id))
            self.open_detail_windows[item_id] = win
            win.show()
            if return_instance:
                return win

    def on_child_window_closed(self, window_type: str, key=None):
        """Callback to clear window reference when it's closed."""
        if window_type == 'detail' and key in self.open_detail_windows:
            self.open_detail_windows[key] = None
        # Add other window types here if needed
    
    def open_user_login(self):
        # ถ้าเป็นการเรียกใช้ครั้งแรก (ยังไม่มี user) ให้เปิดหน้า login
        # ถ้ามี user อยู่แล้ว (กดปุ่มออกจากระบบ) ให้ logout
        if self.current_user:
            self.current_user = None
            self.update_user_status()
            self.auto_logout_timer.stop() # Stop timer on manual logout
            self.load_items()
            return

        login_win = UserLoginWindow(self)
        # Prevent login attempt if in server mode but connection is down
        try:
            is_server_mode = app_config.get('DATABASE', 'enabled', fallback='False').lower() == 'true'
            if is_server_mode:
                # This will raise ConnectionError if the remote instance is not available.
                get_db_instance(is_remote=True)
        except ConnectionError:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "การเชื่อมต่อล้มเหลว",
                                  "ไม่สามารถเชื่อมต่อฐานข้อมูลเซิร์ฟเวอร์ได้\nกรุณาตรวจสอบการตั้งค่า หรือติดต่อผู้ดูแลระบบ")
            return # Stop the login process

        if login_win.exec():
            self.current_user = login_win.user_data
            self.update_user_status()
            self.reset_auto_logout_timer() # Start timer on successful login
            self.load_items()
    
    def open_user_profile(self):
        if not self.current_user:
            return
        self.reset_auto_logout_timer() # Reset timer on interaction

        # --- Non-Modal Logic ---
        if self.user_profile_window and self.user_profile_window.isVisible():
            self.user_profile_window.activateWindow()
            self.user_profile_window.raise_()
            return
        # --- End Non-Modal Logic ---
        
        # Fetch the latest user data using the user's ID, not by re-verifying the password.
        db_instance = self._get_db_instance_for_refresh()
        latest_user_data = db_instance.get_user_by_id(self.current_user['id'])
        if not latest_user_data:
            QMessageBox.critical(self, "Error", "Could not retrieve user data.")
            return
        
        self.user_profile_window = UserProfileViewWindow(user_data=latest_user_data, parent=self)
        self.user_profile_window.show()

    def open_my_rentals(self):
        if not self.current_user: return
        self.reset_auto_logout_timer() # Reset timer on interaction

        # --- Non-Modal Logic ---
        if self.my_rentals_window and self.my_rentals_window.isVisible():
            self.my_rentals_window.activateWindow()
            self.my_rentals_window.raise_()
            return
        
        self.my_rentals_window = MyRentalsDialog(self.current_user, parent=self)
        self.my_rentals_window.show()
        # --- End Non-Modal Logic ---

    def open_payment_history(self):
        if not self.current_user: return
        self.reset_auto_logout_timer() # Reset timer on interaction

        # --- REVISED: Open as a modal dialog ---
        # Pass the correct db_instance based on the current application mode
        current_db = self._get_db_instance_for_refresh()
        payment_history_dialog = PaymentHistoryDialog(
            self.current_user, 
            is_admin_view=False, 
            parent=self, # Set parent to self to make it modal
            db_instance=current_db
        )
        payment_history_dialog.exec()

    def open_about_dialog(self):
        """Opens the 'About' dialog."""
        self.reset_auto_logout_timer() # Reset timer on interaction

        # --- Non-Modal Logic ---
        if self.about_dialog and self.about_dialog.isVisible():
            self.about_dialog.activateWindow()
            self.about_dialog.raise_()
            return
        
        self.about_dialog = AboutDialog(self)
        self.about_dialog.show()
        # --- End Non-Modal Logic ---

    def show_main_filter_menu(self):
        """Displays a menu to filter items by status on the main window."""
        menu = QMenu(self)
        
        statuses = {
            "แสดงทั้งหมด": None,
            "พร้อมให้เช่า": "available",
            "กำลังถูกเช่า": "rented",
            "รอการยืนยัน": "pending_return",
            "ระงับใช้งาน": "suspended"
        }

        for text, status_value in statuses.items():
            action = menu.addAction(text)
            action.triggered.connect(lambda checked=False, s=status_value: self.apply_main_filter(s))

        menu.exec(self.filter_button.mapToGlobal(self.filter_button.rect().bottomLeft()))

    def apply_main_sort(self, sort_by: str, sort_order: str, is_active: bool):
        """Applies the selected sort criteria and reloads items."""
        self.reset_auto_logout_timer()
        self.current_sort_criteria = {'by': sort_by, 'order': sort_order, 'is_active': is_active}
        self.load_items()
        # Update button appearance
        self.update_sort_button_state()

    def apply_main_filter(self, status: str | None):
        """Applies the selected status filter and reloads items on the main window."""
        self.reset_auto_logout_timer() # Reset timer on interaction
        self.current_filter_status = status
        self.load_items()

        self.update_filter_button_state()

    def update_filter_button_state(self):
        """Updates the visual state of the filter button."""
        palette = PALETTES[self.current_theme]
        status = self.current_filter_status
        if status:
            # Active state: Use the 'info' color for consistency with the sort button
            self.filter_button.setStyleSheet(f"background-color: {palette['info']}; color: white;")
            self.filter_button.setIcon(qta.icon('fa5s.filter', color='white'))
            self.filter_button.setText(f" {status.replace('_', ' ').capitalize()}")
        else:
            # เมื่อยกเลิกการกรอง: กลับสู่สถานะปกติ
            self.filter_button.setStyleSheet("") # ล้างสไตล์ที่กำหนดเอง
            self.filter_button.setIcon(qta.icon('fa5s.filter', color=palette['text']))
            self.filter_button.setText("")

    def update_sort_button_state(self):
        """Updates the visual state of the sort button."""
        sort_by = self.current_sort_criteria.get('by')
        # --- REVISED: The default state is now only when no sort has been explicitly chosen,
        # or when the "Default" menu item is clicked. We can check if sort_by is None
        # or if it's the initial state. For simplicity, we'll treat any explicit selection
        # as "active". The "Default" menu action resets it to the initial state.
        is_default_sort = not self.current_sort_criteria.get('is_active', False)
        palette = PALETTES[self.current_theme]

        # --- REVISED: Improved icon and text feedback ---
        if not is_default_sort and sort_by:
            # Active state: when a non-default sort is applied
            order = self.current_sort_criteria.get('order', 'ASC')
            icon_name = 'fa5s.sort-amount-down' if order == 'ASC' else 'fa5s.sort-amount-up'
            
            # Create more descriptive text
            sort_map = {'name': 'ชื่อ', 'fixed_fee': 'ราคาเริ่มต้น', 'price_per_minute': 'ค่าปรับ', 'id': 'รายการ'}
            order_map = {'ASC': '(น้อยไปมาก)', 'DESC': '(มากไปน้อย)'}
            text = f"{sort_map.get(sort_by, sort_by.capitalize())}"

            self.sort_button.setStyleSheet(f"background-color: {palette['info']}; color: white;")
            self.sort_button.setIcon(qta.icon(icon_name, color='white'))
            self.sort_button.setText(f" {text}")
        else:
            # Default state: reset to look like other icon buttons
            self.sort_button.setStyleSheet("") # Clear specific stylesheet
            self.sort_button.setIcon(qta.icon('fa5s.sort', color=palette['text']))
            self.sort_button.setText("")

    def update_user_status(self):
        # เคลียร์ Pixmap เก่าออกก่อน เพื่อป้องกันไอคอนซ้อนกัน
        self.avatar_label.clear()

        # ดึงสีไอคอนหลักจากธีมปัจจุบัน
        current_theme_name = app_config.get('UI', 'theme', fallback='light')
        icon_color = PALETTES[current_theme_name]['text']

        avatar_size = self.avatar_label.size()

        if self.current_user:
            # แสดง Username แทนชื่อจริง
            self.user_name_label.setText(self.current_user['username'])
            # เปลี่ยนปุ่ม Login เป็นปุ่ม Logout (Icon)
            self.login_button.setText("ออกจากระบบ")
            self.login_button.setObjectName("") # Use default button style
            self.login_button.setToolTip("ออกจากระบบ")
            self.profile_button.setVisible(True)
            self.my_rentals_button.setVisible(True)
            self.payment_history_button.setVisible(True)
            self.check_pending_payments()
            self.check_current_rentals() # ตรวจสอบรายการที่ยืมอยู่ทันทีหลัง login

            avatar_data = self.current_user.get('avatar_path')
            pixmap = QPixmap()
            if avatar_data and pixmap.loadFromData(avatar_data):
                # กรณีมีรูปโปรไฟล์: แสดงรูป, เพิ่มกรอบ
                self.avatar_label.show()
                scaled_pixmap = pixmap.scaled(avatar_size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                self.avatar_label.setPixmap(scaled_pixmap)
                self.avatar_label.setProperty("class", "avatar-image") # ใช้ class จาก theme
            else:
                # กรณีไม่มีรูปโปรไฟล์: ซ่อน QLabel ของ avatar ไปเลย
                self.avatar_label.hide()
        else:
            # ซ่อนชื่อผู้ใช้เมื่อยังไม่ได้เข้าระบบ
            self.user_name_label.hide()
            # เปลี่ยนปุ่ม Logout กลับเป็นปุ่ม Login (Text)
            self.login_button.setText("เข้าสู่ระบบ / สมัครสมาชิก")
            self.login_button.setIcon(QIcon()) # Clear icon
            self.login_button.setIconSize(QSize()) # Reset icon size
            self.login_button.setObjectName("") # Reset object name to use default button style
            self.profile_button.setVisible(False)
            self.my_rentals_button.setVisible(False)
            self.payment_history_button.setVisible(False)
            # กรณีไม่ได้เข้าระบบ: แสดงไอคอนพื้นฐาน, ไม่มีกรอบ
            self.avatar_label.show()
            self._update_placeholder_icon() # อัปเดตไอคอน placeholder

    def update_user_status_from_child(self, new_user_data):
        self.current_user = new_user_data
        self.update_user_status()

    def check_current_rentals(self):
        """Checks if the user has currently rented items and updates the button."""
        if not self.current_user: return
        db_instance = self._get_db_instance_for_refresh()

        if db_instance.has_rented_items(self.current_user['id']):
            # มีรายการที่กำลังยืม: แสดงไอคอนพร้อมเครื่องหมายแจ้งเตือน
            self.my_rentals_button.setText("⚠ รายการที่ยืม")
        else:
            self.my_rentals_button.setText("รายการที่ยืม")

    def check_pending_payments(self):
        if not self.current_user: return
        db_instance = self._get_db_instance_for_refresh()

        if db_instance.has_pending_payments(self.current_user['id']):
            # มีรายการค้างชำระ: แสดงไอคอนพร้อมเครื่องหมายแจ้งเตือน
            self.payment_history_button.setText("⚠ การชำระเงิน (ค้างชำระ)")
        else:
            # ไม่มีรายการค้างชำระ: แสดงไอคอนปกติ
            self.payment_history_button.setText("การชำระเงิน")
            
    def update_theme_dependent_widgets(self):
        """Updates all widgets whose appearance depends on the current theme."""
        # อัปเดตสถานะผู้ใช้ (ซึ่งจะอัปเดตไอคอนต่างๆ ตามสถานะ login)
        # sourcery skip: merge-else-if-into-elif
        if self.current_user:
            self.check_current_rentals() # ตรวจสอบรายการที่ยืมอยู่
            self.update_user_status()
        else:
            # ถ้ายังไม่ login ให้อัปเดตเฉพาะไอคอน placeholder
            self._update_placeholder_icon()

        # อัปเดตไอคอนปุ่มเปลี่ยนธีม
        if self.current_theme == 'dark':
            self.theme_button.setIcon(qta.icon('fa5s.sun'))
            self.theme_button.setIconSize(QSize(28, 28))
            self.theme_button.setToolTip("เปลี่ยนเป็นโหมดสว่าง")
        else:
            self.theme_button.setIcon(qta.icon('fa5s.moon'))
            self.theme_button.setIconSize(QSize(25, 25))
            self.theme_button.setToolTip("เปลี่ยนเป็นโหมดมืด")

        # อัปเดตไอคอนปุ่ม Filter
        self.update_filter_button_state()
        self.update_sort_button_state()

        # แจ้งเตือนหน้าต่างอื่นๆ ที่เปิดอยู่ให้ทำการอัปเดต UI ตามธีม
        for widget in QApplication.topLevelWidgets():
            try:
                # --- FIX: Check if the widget is still valid before accessing it ---
                # This prevents a crash if a temporary widget (like a QMenu) has been deleted
                # but still exists in the topLevelWidgets list for a moment.
                if widget and widget is not self and hasattr(widget, 'update_icons'):
                    widget.update_icons()
            except RuntimeError:
                # This widget was deleted between the check and the method call, so we just ignore it.
                pass

    def _update_placeholder_icon(self):
        """Updates the placeholder avatar icon based on the current theme."""
        avatar_size = self.avatar_label.size()
        default_icon = qta.icon('fa5s.user-alt-slash', color=PALETTES[self.current_theme]['disabled_text'])
        self.avatar_label.setPixmap(default_icon.pixmap(avatar_size))

    def toggle_theme(self):
        """Toggles the application's theme between light and dark."""
        if self.current_theme == "light":
            self.current_theme = "dark"
        else:
            self.current_theme = "light"
        
        self.reset_auto_logout_timer() # Reset timer on interaction
        theme.apply_theme(self.app, self.current_theme)
        self.update_theme_dependent_widgets()
        
        app_config.update_config('UI', 'theme', self.current_theme)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Call relayout directly. The logic inside _relayout_items now prevents unnecessary work.
        QTimer.singleShot(50, self._relayout_items) # Use a timer to debounce

    def keyPressEvent(self, event):
        # --- NEW: Use configurable shortcuts ---
        key_map = {
            'console': app_config.get('SHORTCUTS', 'console', 'AsciiTilde'),
            'about': app_config.get('SHORTCUTS', 'about', 'F1'),
            'admin_local': app_config.get('SHORTCUTS', 'admin_local', 'F2'),
            'admin_server': app_config.get('SHORTCUTS', 'admin_server', 'F3'),
            'fullscreen': app_config.get('SHORTCUTS', 'fullscreen', 'F11'),
        }

        # Convert string key name to Qt.Key enum
        pressed_key_name = Qt.Key(event.key()).name.replace('Key_', '')

        if pressed_key_name == key_map['console']:
            self.open_admin_console()
        elif pressed_key_name == key_map['about']:
            # เปิดหน้าต่าง "เกี่ยวกับโปรแกรม"
            self.open_about_dialog()
        elif pressed_key_name == key_map['admin_local']:
            # เปิด Admin Panel (Local)
            # ต้องผ่านการ Login ก่อนเสมอ
            login_dialog = AdminLoginWindow(self, auth_only=True, force_local_auth=True)
            if login_dialog.exec():
                self.open_admin_panel(mode='local')
        elif pressed_key_name == key_map['admin_server']:
            # เปิด Admin Panel (Remote)
            # ฟังก์ชัน open_admin_panel จะจัดการเรื่องการ Login เอง
            self.open_admin_panel(mode='remote')
        elif pressed_key_name == key_map['fullscreen']:
            # Toggle fullscreen mode when F11 is pressed
            self.setWindowState(self.windowState() ^ Qt.WindowState.WindowFullScreen)
        super().keyPressEvent(event)

    def open_admin_console(self):
        """Requires admin login then opens the console."""
        # This will now correctly open the login window first.
        # If console already exists and is visible, just activate it to prevent multiple instances.
        if self.admin_console and self.admin_console.isVisible():
            self.admin_console.activateWindow()
            return

        # --- Re-enabled Login Logic with Bypass Option ---
        # Check if the bypass setting is enabled in the config
        bypass_login = app_config.get('END_ADMIN', 'bypass_console_login', fallback='False').lower() == 'true'

        if bypass_login:
            # If bypass is enabled, open the console directly
            if not self.admin_console or not self.admin_console.isVisible():
                self.admin_console = AdminConsole(main_window_ref=self)
            self.admin_console.show()
            self.admin_console.activateWindow()
        else:
            # If bypass is disabled, require login
            login_dialog = AdminLoginWindow(self, auth_only=True, force_local_auth=True)
            if login_dialog.exec():
                if not self.admin_console or not self.admin_console.isVisible():
                    self.admin_console = AdminConsole(main_window_ref=self)
                self.admin_console.show()
                self.admin_console.activateWindow()

    def open_income_dashboard_from_console(self):
        """Opens the income dashboard, preferring an active admin panel."""
        # Check if a remote admin panel is open and use its context
        if self.remote_admin_panel and self.remote_admin_panel.isVisible():
            self.remote_admin_panel.open_income_dashboard()
            return

        # Otherwise, check for a local admin panel
        if self.local_admin_panel and self.local_admin_panel.isVisible():
            self.local_admin_panel.open_income_dashboard()
            return

        # If no admin panel is open, inform the user.
        CustomMessageBox.show(self, CustomMessageBox.Information, "เปิด Admin Panel ก่อน", "กรุณาเปิด Admin Panel (F2 หรือ F3) ก่อนเรียกใช้หน้ารายรับ")

    def find_available_cameras(self) -> list[int]:
        """
        Scans for available camera devices and returns a list of their indices.
        This should be called from the main GUI thread to avoid issues.
        """
        available_cameras = []
        # Check a reasonable number of potential camera indices (e.g., 0 to 9)
        for i in range(10):
            # Use CAP_DSHOW for more reliable probing on Windows
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                available_cameras.append(i)
                cap.release()
        return available_cameras

    def on_payment_status_updated(self, user_id: int):
        """Slot to refresh UI elements when a payment status changes globally."""
        if self.current_user and self.current_user['id'] == user_id:
            self.check_pending_payments()

    @pyqtSlot(str)
    def on_data_changed(self, table_name: str):
        """Slot to refresh UI when data changes in the database."""
        print(f"MainWindow received data_changed signal for table: {table_name}")
        if table_name == 'items':
            self.load_items()
            # When an item is returned, it can create a pending payment, so we need to check both.
            self.check_pending_payments()
            self.check_current_rentals()
        elif table_name == 'users':
            # Refresh current user data if a profile window is open or after edits
            if self.current_user:
                self.current_user = self._get_db_instance_for_refresh().get_user_by_id(self.current_user['id'])
                self.update_user_status()

    def execute_test_command(self, command: str, args: list, config_source=None) -> str:
        """
        Executes a test command from the admin console.
        This acts as a bridge between the console UI and the application's logic.
        Returns a result string to be displayed in the console.
        """
        command = command.lower() # sourcery skip: move-assign-in-block
        
        if command == "test.scb":
            from app_payment.scb_api_handler import SCBApiHandler
            handler = SCBApiHandler(debug=True, config_source=config_source)
            return handler.test_authentication()

        elif command == "test.ktb":
            from app_payment.ktb_api_handler import KTBApiHandler
            handler = KTBApiHandler(config_source=config_source)
            return handler.test_authentication()

        elif command == "test.slipok":
            from app_payment.slipok_api_handler import SlipOKApiHandler
            handler = SlipOKApiHandler(debug=True, config_source=config_source)
            return handler.test_authentication()

        elif command == "test.slipok_qr":
            if not args:
                return "Usage: test.slipok_qr <amount>"
            try:
                amount = float(args[0])
                from app_payment.slipok_api_handler import SlipOKApiHandler
                import uuid
                handler = SlipOKApiHandler(debug=True, config_source=config_source)
                test_ref = f"CONSOLE-TEST-{str(uuid.uuid4())[:4]}"
                qr_b64, error = handler.generate_qr_code(amount, test_ref)
                if qr_b64:
                    return f"SlipOK QR generation successful for amount {amount:.2f}!"
                else:
                    return f"SlipOK QR generation failed: {error}"
            except ValueError:
                return "Invalid amount. Please provide a number."
            except Exception as e:
                return f"An error occurred: {e}"

        return f"Unknown test command: '{command}'"

    def open_admin_panel(self, mode: str):
        """
        Opens the Admin Panel in the specified mode ('local' or 'remote').
        """
        if mode not in ['local', 'remote']:
            return

        is_remote_mode = (mode == 'remote')
        
        # For local mode called from the console, we skip the login dialog
        # because the console itself is already authenticated for local actions.
        # For remote mode, we now always require a login, even if the app is in server mode.
        db_instance_for_panel = None
        if mode == 'remote':
            # The login dialog will create a dedicated connection for this session.
            login_dialog = AdminLoginWindow(self, auth_only=True, force_remote_auth=True)
            if not login_dialog.exec():
                return # Exit if login fails
            # IMPORTANT: Use the instance that was successfully created and authenticated by the login dialog.
            db_instance_for_panel = login_dialog.db_instance
            current_admin_user = login_dialog.user # Get the authenticated admin user

        # Select the correct panel instance and create if it doesn't exist
        if is_remote_mode:
            # Crucial Fix: If the panel doesn't exist, create it WITH the new db_instance.
            # If it does exist (somehow), we must still update its db_instance to the new one.
            if not self.remote_admin_panel or not self.remote_admin_panel.isVisible():
                # Pass the established DB instance to the new panel.
                self.remote_admin_panel = AdminPanel(self, is_remote=True, db_instance=db_instance_for_panel, current_admin_user=current_admin_user)
            else:
                # This ensures that even if the panel object survived, it gets the new, valid connection.
                self.remote_admin_panel.db_instance = db_instance_for_panel
                self.remote_admin_panel.initialize_panel()
            target_panel = self.remote_admin_panel
        else: # local mode
            panel_instance = self.local_admin_panel
            if not panel_instance or not panel_instance.isVisible():
                self.local_admin_panel = AdminPanel(self, is_remote=False)
            target_panel = self.local_admin_panel

        target_panel.show()
        target_panel.activateWindow()

    def shutdown_child_windows(self):
        """
        Explicitly closes child windows like the Admin Console before the main app quits.
        This helps ensure resources like stdout/stderr redirection are restored properly.
        """
        # --- Close windows that SHOULD close with the main window ---
        for win in self.open_detail_windows.values():
            if win: win.close()
        if self.user_profile_window: self.user_profile_window.close()
        if self.my_rentals_window: self.my_rentals_window.close()
        if self.payment_history_window: self.payment_history_window.close()
        if self.about_dialog: self.about_dialog.close()

        # --- Close windows that are managed by MainWindow but should persist if possible ---
        # This is called by app.aboutToQuit, so we close everything.
        if self.admin_console and self.admin_console.isVisible():
            self.admin_console.close()
        if self.local_admin_panel and self.local_admin_panel.isVisible():
            self.local_admin_panel.close()
        if self.remote_admin_panel and self.remote_admin_panel.isVisible():
            self.remote_admin_panel.close()

    def closeEvent(self, event):
        """Ensure child windows are closed before the main window."""
        # --- Only close windows that are logically dependent on MainWindow ---
        # Do NOT close AdminConsole or AdminPanel here, as they are now independent.
        # This allows the app to stay open if they are visible.
        for win in self.open_detail_windows.values():
            if win: win.close()
        if self.user_profile_window: self.user_profile_window.close()
        if self.my_rentals_window: self.my_rentals_window.close()
        if self.payment_history_window: self.payment_history_window.close()
        if self.about_dialog: self.about_dialog.close()

        super().closeEvent(event)

    def reset_auto_logout_timer(self):
        """Resets the auto-logout timer if the feature is enabled and a user is logged in."""
        if not self.current_user:
            self.auto_logout_timer.stop()
            return

        timeout_minutes = app_config.getint('UI', 'auto_logout_minutes', fallback=0)
        if timeout_minutes > 0:
            self.auto_logout_timer.start(timeout_minutes * 60 * 1000) # Convert minutes to milliseconds

    def auto_logout(self):
        """Logs out the user due to inactivity."""
        if self.current_user:
            username = self.current_user['username']
            self.current_user = None
            self.update_user_status()
            self.load_items()
            CustomMessageBox.show(self, CustomMessageBox.Information, "ออกจากระบบอัตโนมัติ",
                                  f"ผู้ใช้ '{username}' ถูกออกจากระบบเนื่องจากไม่มีการใช้งาน")

    def show_main_sort_menu(self):
        """Displays a menu to sort items on the main window."""
        menu = QMenu(self.sort_button)

        # --- REVISED: The default action now has its own handler to set 'is_active' to False ---
        menu.addAction("ค่าเริ่มต้น (เรียงตามชื่อ)").triggered.connect(self.reset_main_sort)
        menu.addSeparator()

        sort_options = {
            "ราคาเริ่มต้น (น้อยไปมาก)": ('fixed_fee', 'ASC'),
            "ราคาเริ่มต้น (มากไปน้อย)": ('fixed_fee', 'DESC'),
            "ค่าปรับ (น้อยไปมาก)": ('price_per_minute', 'ASC'),
            "ค่าปรับ (มากไปน้อย)": ('price_per_minute', 'DESC'),
            "--- ": None, # Separator
            "รายการ (ใหม่สุด)": ('id', 'DESC'),
            "รายการ (เก่าสุด)": ('id', 'ASC'),
        }

        for text, criteria in sort_options.items():
            if criteria:
                action = menu.addAction(text)
                # --- REVISED: All explicit sort actions will set 'is_active' to True ---
                action.triggered.connect(lambda checked=False, by=criteria[0], order=criteria[1]: self.apply_main_sort(by, order, is_active=True)) # type: ignore
            else:
                menu.addSeparator()

        menu.exec(self.sort_button.mapToGlobal(self.sort_button.rect().bottomLeft()))

    def reset_main_sort(self):
        """Resets the sorting to the default state."""
        # This specifically calls apply_main_sort with is_active=False
        self.apply_main_sort('name', 'ASC', is_active=False)
