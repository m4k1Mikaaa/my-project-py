from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QScroller, QLineEdit,
    QMenu
)
import qtawesome as qta
from app.base_dialog import BaseDialog
from app_config import app_config
from theme import PALETTES
from app_db.db_management import get_db_instance, db_signals
from PyQt6.QtCore import QModelIndex, Qt, QDateTime
from app_payment.payment_history_dialog import PaymentHistoryDialog
from app_user.profile import UserProfileWindow
from app.custom_message_box import CustomMessageBox
class UserManagementDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        # This dialog should always use the db_instance from its parent (AdminPanel)
        self.db_instance = parent.db_instance if parent and hasattr(parent, 'db_instance') else get_db_instance()
        self.current_admin_user = parent.current_admin_user if parent and hasattr(parent, 'current_admin_user') else None
        self.is_remote = parent.is_remote if parent and hasattr(parent, 'is_remote') else False
        # --- Window Management ---
        self.edit_user_dialog = None
        self.payment_history_dialogs = {} # {user_id: window_instance}

        self.setWindowTitle("จัดการบัญชีผู้ใช้งาน")
        self.setMinimumSize(950, 600)

        layout = QVBoxLayout(self)

        # --- Toolbar Widget ---
        toolbar_widget = QWidget()
        toolbar_widget.setObjectName("ToolbarWidget")
        button_layout = QHBoxLayout(toolbar_widget)
        button_layout.setContentsMargins(8, 8, 8, 8)
        button_layout.setSpacing(8)

        self.add_user_button = QPushButton(" เพิ่มผู้ใช้ใหม่")
        self.edit_user_button = QPushButton(" แก้ไขผู้ใช้")
        self.delete_user_button = QPushButton(" ลบผู้ใช้")
        
        self.add_user_button.clicked.connect(self.add_user)
        self.edit_user_button.clicked.connect(self.edit_user)
        self.delete_user_button.clicked.connect(self.delete_user)
        
        button_layout.addWidget(self.add_user_button)
        button_layout.addWidget(self.edit_user_button)
        button_layout.addWidget(self.delete_user_button)

        # --- Search Input ---
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("ค้นหาจาก ID, Username, ชื่อ, อีเมล, เบอร์โทร...")
        self.search_input.textChanged.connect(self.filter_users)        
        button_layout.addStretch()
        button_layout.addWidget(self.search_input, 1) # Add search input, stretchable
        layout.addWidget(toolbar_widget)

        # --- User Table ---
        self.user_table = QTableWidget()
        self.user_table.setColumnCount(7)
        self.user_table.setHorizontalHeaderLabels(["ID", "Username", "ชื่อ", "อีเมล", "เบอร์โทร", "Role", "สถานะชำระเงิน"])
        
        header = self.user_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # ID
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)     # Username
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)     # ชื่อ
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)         # อีเมล
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)     # เบอร์โทร
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents) # Role
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents) # สถานะชำระเงิน

        self.user_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.user_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.user_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # เปลี่ยนกลับไปใช้ doubleClicked เพื่อเปิดหน้าต่างรายละเอียด
        self.user_table.doubleClicked.connect(self.handle_double_click)
        # Enable context menu for right-clicking
        self.user_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.user_table.customContextMenuRequested.connect(self.show_user_context_menu)

        # เปิดใช้งาน Smooth Scrolling สำหรับ Touch
        QScroller.grabGesture(self.user_table.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)

        layout.addWidget(self.user_table)

        self.update_icons()
        self.load_users()
        # Connect to the global signal to refresh when a payment is made anywhere
        db_signals.data_changed.connect(self.on_data_changed)

        self.adjust_and_center()

    def update_icons(self):
        """Sets or updates icons for all buttons based on the current theme."""
        current_theme_name = app_config.get('UI', 'theme', fallback='light')
        icon_color = PALETTES[current_theme_name]['text']

        buttons_with_icons = {
            self.add_user_button: ('fa5s.user-plus', 'white'),
            self.edit_user_button: ('fa5s.user-edit', 'white'),
            self.delete_user_button: ('fa5s.user-minus', 'white'),
        }
        for button, (icon_name, color) in buttons_with_icons.items():
            button.setIcon(qta.icon(icon_name, color=color))

    def load_users(self): # sourcery skip: extract-method
        # In remote mode, get_all_users_for_management filters out the super admin.
        # In local mode, it returns all users. This simplifies the logic here.
        users = self.db_instance.get_all_users_for_management(is_remote=self.is_remote)

        self.user_table.setRowCount(len(users))

        for row, user in enumerate(users):
            self.user_table.setItem(row, 0, QTableWidgetItem(str(user['id'])))
            self.user_table.setItem(row, 1, QTableWidgetItem(user['username']))
            full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
            self.user_table.setItem(row, 2, QTableWidgetItem(full_name))
            self.user_table.setItem(row, 3, QTableWidgetItem(user.get('email', '')))
            self.user_table.setItem(row, 4, QTableWidgetItem(user.get('phone', '')))
            self.user_table.setItem(row, 5, QTableWidgetItem(user.get('role', 'user')))

            # Check for pending payments
            if self.db_instance.has_pending_payments(user['id']):
                pending_item = QTableWidgetItem(" ⚠ ค้างชำระ")
                pending_item.setIcon(qta.icon('fa5s.exclamation-circle', color=PALETTES[app_config.get('UI', 'theme', fallback='light')]['warning']))
                self.user_table.setItem(row, 6, pending_item)
            else:
                # Clear the cell if there are no pending payments
                self.user_table.setItem(row, 6, QTableWidgetItem(""))

    def filter_users(self):
        """Filters the user table based on the search input text."""
        filter_text = self.search_input.text().lower().strip()
        for row in range(self.user_table.rowCount()):
            should_show = False
            if not filter_text:
                should_show = True
            else:
                # Iterate through all columns to check for a match
                for col in range(self.user_table.columnCount()):
                    item = self.user_table.item(row, col)
                    if item and filter_text in item.text().lower():
                        should_show = True
                        break
            self.user_table.setRowHidden(row, not should_show)

    def show_user_context_menu(self, pos):
        """Shows a context menu on right-click, only for Super Admin."""
        is_super_admin = self.current_admin_user and self.current_admin_user.get('id') == 1
        if not is_super_admin:
            return

        selected_item = self.user_table.itemAt(pos)
        if not selected_item:
            return

        user_id = int(self.user_table.item(selected_item.row(), 0).text())
        current_role = self.user_table.item(selected_item.row(), 5).text()

        menu = QMenu(self)
        menu.addSection(f"User ID: {user_id}")

        change_to_admin_action = menu.addAction("Set Role to 'admin'")
        change_to_user_action = menu.addAction("Set Role to 'user'")

        change_to_admin_action.setEnabled(current_role != 'admin')
        change_to_user_action.setEnabled(current_role != 'user')

        action = menu.exec(self.user_table.viewport().mapToGlobal(pos))

        if action: # Check if an action was actually selected
            if action == change_to_admin_action:
                self.change_user_role(user_id, 'admin')
            elif action == change_to_user_action:
                self.change_user_role(user_id, 'user')

    def change_user_role(self, user_id, new_role):
        """Updates the user's role in the database."""
        self.db_instance.update_user_role(user_id, new_role)
        CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", f"เปลี่ยน Role ของผู้ใช้ ID: {user_id} เป็น '{new_role}' เรียบร้อยแล้ว")
        self.load_users()

    def get_selected_user_id(self):
        selected_items = self.user_table.selectedItems()
        if not selected_items:
            return None
        # แก้ไข: ดึงข้อมูลจากแถวที่เลือก ไม่ใช่จากเซลล์ที่คลิกโดยตรง
        # เพื่อให้แน่ใจว่าจะได้ ID เสมอ
        selected_row = selected_items[0].row()
        id_item = self.user_table.item(selected_row, 0)
        if id_item:
            return int(id_item.text())
        return None

    def add_user(self):
        # ใช้ UserProfileWindow ในโหมด "เพิ่ม" (โดยไม่ส่ง user_data)
        if self.edit_user_dialog and self.edit_user_dialog.isVisible():
            self.edit_user_dialog.activateWindow()
            self.edit_user_dialog.raise_()
            CustomMessageBox.show(self, CustomMessageBox.Information, "เปิดอยู่แล้ว", "กรุณาปิดหน้าต่างเพิ่ม/แก้ไขผู้ใช้ก่อนเปิดหน้าต่างใหม่")
            return

        self.edit_user_dialog = UserProfileWindow(user_data=None, parent=self, db_instance=self.db_instance)
        self.edit_user_dialog.open()

    def edit_user(self):
        user_id = self.get_selected_user_id()
        if user_id is None:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ไม่ได้เลือก", "กรุณาเลือกผู้ใช้ที่ต้องการแก้ไข")
            return

        # --- FIX: Prevent editing of super admin (ID=1) only in remote mode ---
        if self.is_remote and user_id == 1:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ไม่ได้รับอนุญาต", "ไม่สามารถแก้ไขบัญชี Super Admin ได้จากหน้านี้\nกรุณาไปที่ 'ตั้งค่าระบบ (Server)' > 'บัญชี Super Admin'")
            return

        user_data = self.db_instance.get_user_by_id(user_id)
        if not user_data:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", "ไม่พบข้อมูลผู้ใช้")
            return

        if self.edit_user_dialog and self.edit_user_dialog.isVisible():
            self.edit_user_dialog.activateWindow()
            self.edit_user_dialog.raise_()
            CustomMessageBox.show(self, CustomMessageBox.Information, "เปิดอยู่แล้ว", "กรุณาปิดหน้าต่างเพิ่ม/แก้ไขผู้ใช้ก่อนเปิดหน้าต่างใหม่")
            return

        self.edit_user_dialog = UserProfileWindow(user_data=user_data, parent=self, is_admin_edit=True)
        self.edit_user_dialog.open()

    def handle_double_click(self, index: QModelIndex):
        """Handles double-clicking on a user row to open their payment history."""
        user_id = int(self.user_table.item(index.row(), 0).text())
        user_data = self.db_instance.get_user_by_id(user_id)
        if user_data:
            # --- Non-Modal Logic ---
            if user_id in self.payment_history_dialogs and self.payment_history_dialogs[user_id]:
                win = self.payment_history_dialogs[user_id]
                win.show()
                win.activateWindow()
                win.raise_()
            else:
                win = PaymentHistoryDialog(user_data, is_admin_view=True, parent=None, db_instance=self.db_instance)
                win.finished.connect(lambda: self.on_child_window_closed('payment_history', user_id))
                self.payment_history_dialogs[user_id] = win
                win.show()
            # --- End Non-Modal Logic ---

    def delete_user(self):
        user_id = self.get_selected_user_id()
        if user_id is None:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ไม่ได้เลือก", "กรุณาเลือกผู้ใช้ที่ต้องการลบ")
            return

        # --- FIX: Prevent deletion of super admin (ID=1) only in remote mode ---
        if self.is_remote and user_id == 1:
            CustomMessageBox.show(self, CustomMessageBox.Critical, "ไม่ได้รับอนุญาต", "ไม่สามารถลบบัญชี Super Admin (ID: 1) ได้")
            return

        # ป้องกันการลบ Admin คนปัจจุบัน (ถ้ามี logic นั้น)
        # ในที่นี้จะอนุญาตให้ลบได้ทั้งหมด

        user_data = self.db_instance.get_user_by_id(user_id)
        if not user_data:
            return

        reply = CustomMessageBox.show(
            self,
            CustomMessageBox.Question,
            "ยืนยันการลบ",
            f"คุณต้องการลบผู้ใช้ '{user_data['username']}' ใช่หรือไม่?\nการกระทำนี้ไม่สามารถย้อนกลับได้",
            buttons=CustomMessageBox.Yes | CustomMessageBox.No
        )

        if reply == CustomMessageBox.Yes:
            # --- NEW: Prevent deletion of the last admin user ---
            if user_data.get('role') == 'admin':
                admin_count = self.db_instance.get_admin_user_count()
                if admin_count <= 1:
                    CustomMessageBox.show(self, CustomMessageBox.Critical, "ไม่ได้รับอนุญาต", "ไม่สามารถลบบัญชี Admin คนสุดท้ายของระบบได้")
                    return
            if self.db_instance.delete_user(user_id):
                # The delete_user method in DB does not emit a signal, so we do it manually or refresh here.
                CustomMessageBox.show(self, CustomMessageBox.Information, "สำเร็จ", "ลบผู้ใช้เรียบร้อยแล้ว")
                self.load_users()
            else:
                CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", "ไม่สามารถลบผู้ใช้ได้ อาจมีข้อมูลการยืม-คืนที่เกี่ยวข้อง")

    def on_data_changed(self, table_name: str):
        if table_name == 'users' or table_name == 'items': # Items can affect payment status
            self.load_users()

    def on_child_window_closed(self, window_type: str, key=None):
        if window_type == 'payment_history' and key in self.payment_history_dialogs:
            self.payment_history_dialogs[key] = None

    def closeEvent(self, event):
        """Disconnect signals when the dialog is closed to prevent errors."""
        try:
            db_signals.data_changed.disconnect(self.on_data_changed)
        except TypeError: # Signal was not connected or already disconnected
            pass
        super().closeEvent(event)