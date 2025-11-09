from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QApplication,
    QPushButton, QFileDialog, QMessageBox, QTextEdit, QComboBox, QFormLayout, QWidget, QGridLayout, QSpinBox,
    QGroupBox, QScrollArea, QFrame
)
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtCore import Qt, QBuffer
import qtawesome as qta
from app.base_dialog import BaseDialog
from app_db.db_management import get_db_instance
from app_config import app_config
from theme import PALETTES
from app.utils import set_image_on_label
from app.image_cropper_dialog import ImageCropperDialog
from app.image_viewer import ImageViewerDialog
from app.rental_history import RentalHistoryDialog
from app.custom_message_box import CustomMessageBox
from validators import sanitize_input, is_valid_image_data

class ItemDialog(BaseDialog):
    def __init__(self, parent=None, item_id=None, db_instance=None):
        super().__init__(parent)
        self.item_id = item_id
        # This dialog should always use the db_instance from its parent (AdminPanel)
        self.db_instance = parent.db_instance if parent and hasattr(parent, 'db_instance') else get_db_instance()
        
        if self.item_id:
            self.setWindowTitle("แก้ไขข้อมูลรายการ")
        else:
            self.setWindowTitle("เพิ่มรายการใหม่")

        self.image_data = None # เก็บข้อมูลรูปภาพเป็น bytes
        
        main_layout = QGridLayout(self)
        main_layout.setColumnStretch(0, 1) # Image column
        main_layout.setColumnStretch(1, 2) # Form column

        # --- Left Panel (Image) ---
        left_panel = QVBoxLayout()
        left_panel.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.image_preview_label = QLabel("ไม่มีรูปภาพ")
        self.image_preview_label.setFixedSize(250, 250)
        self.image_preview_label.setStyleSheet("border: 1px solid #cccccc; background-color: #f0f0f0;")
        self.image_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview_label.setToolTip("ดับเบิลคลิกเพื่อดูภาพขนาดเต็ม")
        self.image_preview_label.mouseDoubleClickEvent = self.view_full_image
        self.browse_button = QPushButton("เลือกไฟล์รูปภาพ")
        self.browse_button.clicked.connect(self.browse_image)
        self.crop_button = QPushButton("ตัดรูปภาพ (Crop)")
        self.crop_button.clicked.connect(self.crop_image)
        self.crop_button.setEnabled(False) # Initially disabled
        
        self.history_button = QPushButton("ดูประวัติการยืม-คืน")
        self.history_button.clicked.connect(self.show_history)
        self.history_button.setEnabled(False)

        left_panel.addWidget(self.image_preview_label)
        left_panel.addWidget(self.browse_button)
        left_panel.addWidget(self.crop_button)
        left_panel.addWidget(self.history_button)
        left_panel.addStretch() # Add stretch to keep buttons at the top

        # --- Right Panel (Form) ---
        right_widget = QWidget()
        right_panel_layout = QVBoxLayout(right_widget)
        right_panel_layout.setSpacing(20)

        # --- Group 1: General Info ---
        general_group = QGroupBox("ข้อมูลทั่วไป")
        general_layout = QFormLayout(general_group)
        general_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        general_layout.setSpacing(10)
        self.name_input = QLineEdit()
        general_layout.addRow("ชื่อ:", self.name_input)
        self.brand_input = QLineEdit()
        general_layout.addRow("ยี่ห้อ/รุ่น:", self.brand_input)
        self.desc_input = QTextEdit()
        self.desc_input.setMinimumHeight(80)
        general_layout.addRow("รายละเอียด:", self.desc_input)
        self.status_combo = QComboBox() # Items will be added in load_item_data
        general_layout.addRow("สถานะ:", self.status_combo)
        right_panel_layout.addWidget(general_group)

        # --- Group 2: Pricing Settings ---
        pricing_group = QGroupBox("การตั้งค่าราคา")
        pricing_layout = QFormLayout(pricing_group)
        pricing_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        pricing_layout.setSpacing(10)

        self.minimum_charge_input = QLineEdit("0.00")
        self.minimum_charge_input.setValidator(QDoubleValidator(0.00, 999999.99, 2))
        pricing_layout.addRow("ค่าบริการขั้นต่ำ:", self.minimum_charge_input)

        self.price_model_combo = QComboBox()
        self.price_model_combo.addItems(["คิดตามเวลา", "คิดเป็นรายครั้ง (คงที่)", "คิดเป็นรายครั้ง + ค่าปรับ"])
        self.price_model_combo.currentIndexChanged.connect(self.on_price_model_changed)
        pricing_layout.addRow("รูปแบบราคา:", self.price_model_combo)

        self.fixed_fee_input = QLineEdit("0.00")
        self.fixed_fee_input.setValidator(QDoubleValidator(0.00, 999999.99, 2))
        self.fixed_fee_label = QLabel("ค่าบริการรายครั้ง:")
        pricing_layout.addRow(self.fixed_fee_label, self.fixed_fee_input)

        grace_period_layout = QHBoxLayout()
        self.grace_period_input = QSpinBox()
        self.grace_period_input.setRange(0, 99999)
        self.grace_period_unit_combo = QComboBox()
        self.grace_period_unit_combo.addItems(["นาที", "ชั่วโมง", "วัน"])
        grace_period_layout.addWidget(self.grace_period_input)
        grace_period_layout.addWidget(self.grace_period_unit_combo)
        grace_period_layout.addStretch()
        self.grace_period_label = QLabel("ระยะเวลาที่อนุญาต:")
        pricing_layout.addRow(self.grace_period_label, grace_period_layout)

        self.time_price_label = QLabel("ราคาเช่า:")
        price_layout = QHBoxLayout()
        self.price_input = QLineEdit("0.00")
        self.price_input.setMinimumWidth(150)
        self.price_input.setValidator(QDoubleValidator(0.00, 999999.99, 2))
        self.period_combo = QComboBox()
        self.period_combo.addItems(["ต่อวัน", "ต่อชั่วโมง", "ต่อนาที"])
        self.period_combo.currentIndexChanged.connect(self.on_period_changed)
        self.previous_period_text = self.period_combo.currentText()
        price_layout.addWidget(self.price_input)
        price_layout.addWidget(self.period_combo)
        price_layout.addStretch()
        pricing_layout.addRow(self.time_price_label, price_layout)
        right_panel_layout.addWidget(pricing_group)

        # --- Bottom Buttons ---
        right_panel_layout.addStretch()
        # Separator before save/cancel
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        right_panel_layout.addWidget(separator)

        # Save/Cancel buttons
        button_box = QHBoxLayout()
        save_button = QPushButton("บันทึก/ปิด")
        save_button.clicked.connect(self.save_item)
        cancel_button = QPushButton("ยกเลิก")
        cancel_button.clicked.connect(self.reject)
        button_box.addStretch()
        button_box.addWidget(save_button)
        button_box.addWidget(cancel_button)
        right_panel_layout.addLayout(button_box)

        main_layout.addLayout(left_panel, 0, 0)
        main_layout.addWidget(right_widget, 0, 1)

        if self.item_id:
            self.load_item_data()

        # Set initial visibility based on the default price model
        self.on_price_model_changed()

        # ปรับขนาดหน้าต่างให้พอดีกับเนื้อหาและจัดกลาง
        self.adjust_and_center()

    def load_item_data(self):
        item = self.db_instance.get_item_by_id(self.item_id)
        if item:
            self.name_input.setText(item.get('name', ''))
            self.brand_input.setText(item.get('brand', ''))
            self.desc_input.setPlainText(item.get('description'))
            
            # --- REVISED: Status ComboBox Logic ---
            # Populate the combo box with relevant statuses
            self.status_combo.clear()
            self.status_combo.addItems(["available", "suspended"])

            current_status = item.get('status')
            # If the current status is not in the standard list, add it
            if current_status not in ["available", "suspended"]:
                self.status_combo.addItem(current_status)
            
            self.status_combo.setCurrentText(current_status)

            # Disable status changes for items that are currently rented or pending return
            if current_status in ['rented', 'pending_return']:
                self.status_combo.setEnabled(False)

            # --- Load new pricing model data ---
            self.minimum_charge_input.setText(f"{item.get('minimum_charge', 0.0):.2f}")

            price_model = item.get('price_model', 'per_minute')
            if price_model == 'fixed_fee_only':
                self.price_model_combo.setCurrentText("คิดเป็นรายครั้ง (คงที่)")
            elif price_model == 'fixed_plus_overdue':
                self.price_model_combo.setCurrentText("คิดเป็นรายครั้ง + ค่าปรับ")
            else:
                self.price_model_combo.setCurrentText("คิดตามเวลา")
            
            self.fixed_fee_input.setText(f"{item.get('fixed_fee', 0.0):.2f}")
            
            grace_minutes = item.get('grace_period_minutes', 0)
            if grace_minutes >= 1440 and grace_minutes % 1440 == 0:
                self.grace_period_input.setValue(grace_minutes // 1440)
                self.grace_period_unit_combo.setCurrentText("วัน")
            elif grace_minutes >= 60 and grace_minutes % 60 == 0:
                self.grace_period_input.setValue(grace_minutes // 60)
                self.grace_period_unit_combo.setCurrentText("ชั่วโมง")
            else:
                self.grace_period_input.setValue(grace_minutes)
                self.grace_period_unit_combo.setCurrentText("นาที")

            # --- End loading new pricing model data ---


            # --- Load and display price ---
            price_per_minute = float(item.get('price_per_minute', 0.0))
            if price_per_minute > 0:
                # Display as per-day if it's a clean multiple
                if price_per_minute * 1440 >= 1:
                    self.price_input.setText(f"{price_per_minute * 1440:.2f}")
                    self.period_combo.setCurrentText("ต่อวัน")
                elif price_per_minute * 60 >= 0.01:
                    self.price_input.setText(f"{price_per_minute * 60:.2f}")
                    self.period_combo.setCurrentText("ต่อชั่วโมง")
                else:
                    self.price_input.setText(f"{price_per_minute:.2f}")
                    self.period_combo.setCurrentText("ต่อนาที")

            self.image_data = item.get('image_path')
            if self.image_data:
                set_image_on_label(self.image_preview_label, self.image_data)
                self.crop_button.setEnabled(True)
            
            self.history_button.setEnabled(True)

            # Load price unit
            self.period_combo.setCurrentText(item.get('price_unit', 'ต่อวัน'))
        
        self.previous_period_text = self.period_combo.currentText()

    def browse_image(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "เลือกรูปภาพ", "", "Image Files (*.png *.jpg *.jpeg)")
        if file_name:
            try:
                with open(file_name, 'rb') as f:
                    image_bytes = f.read()
                
                if not is_valid_image_data(image_bytes):
                    CustomMessageBox.show(self, CustomMessageBox.Warning, "ไฟล์ไม่ถูกต้อง", "กรุณาเลือกไฟล์รูปภาพประเภท .png หรือ .jpg เท่านั้น")
                    return

                self.image_data = image_bytes
                set_image_on_label(self.image_preview_label, self.image_data)
                self.crop_button.setEnabled(True)
            except IOError as e:
                CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", f"ไม่สามารถอ่านไฟล์รูปภาพได้: {e}")
                self.image_data = None
                self.crop_button.setEnabled(False)

    def crop_image(self):
        if not self.image_data:
            return

        cropped_pixmap = ImageCropperDialog.crop_from_data(self.image_data, self)
        if cropped_pixmap:
            buffer = QBuffer()
            buffer.open(QBuffer.OpenModeFlag.WriteOnly)
            cropped_pixmap.save(buffer, "PNG")
            self.image_data = buffer.data().data()
            set_image_on_label(self.image_preview_label, self.image_data)

    def view_full_image(self, event=None):
        if self.image_data:
            dialog = ImageViewerDialog(self.image_data, self)
            dialog.exec()

    def show_history(self):
        if self.item_id:
            item_name = self.name_input.text()
            dialog = RentalHistoryDialog(self.item_id, item_name, self)
            dialog.exec()

    def on_price_model_changed(self):
        """Shows or hides fields based on the selected pricing model."""
        selected_model = self.price_model_combo.currentText()

        is_fixed_fee_only = selected_model == "คิดเป็นรายครั้ง (คงที่)"
        is_fixed_plus_overdue = selected_model == "คิดเป็นรายครั้ง + ค่าปรับ"

        # Visibility for Fixed Fee
        self.fixed_fee_label.setVisible(is_fixed_fee_only or is_fixed_plus_overdue)
        self.fixed_fee_input.setVisible(is_fixed_fee_only or is_fixed_plus_overdue)

        # Visibility for Grace Period
        self.grace_period_label.setVisible(is_fixed_plus_overdue)
        self.grace_period_input.setVisible(is_fixed_plus_overdue)
        self.grace_period_unit_combo.setVisible(is_fixed_plus_overdue)

        # Visibility and Label for Time-based Price
        self.time_price_label.setVisible(not is_fixed_fee_only)
        self.price_input.setVisible(not is_fixed_fee_only)
        self.period_combo.setVisible(not is_fixed_fee_only)

        if is_fixed_plus_overdue:
            self.time_price_label.setText("ค่าปรับ (เมื่อเกินเวลา):")
        else:
            self.time_price_label.setText("ราคาเช่า:")

        # Adjust the dialog size to fit the new content
        self.adjustSize()

    def on_period_changed(self):
        """Automatically converts the price when the period (day/hour/minute) is changed."""
        try:
            price = float(self.price_input.text())
        except ValueError:
            return # Do nothing if the input is not a valid number

        new_period_text = self.period_combo.currentText()

        # 1. Convert the current price to a base price_per_minute
        price_per_minute = 0.0
        if self.previous_period_text == "ต่อวัน":
            price_per_minute = price / 1440
        elif self.previous_period_text == "ต่อชั่วโมง":
            price_per_minute = price / 60
        else: # ต่อนาที
            price_per_minute = price

        # 2. Convert price_per_minute to the new period's price
        new_price = 0.0
        if new_period_text == "ต่อวัน":
            new_price = price_per_minute * 1440
        elif new_period_text == "ต่อชั่วโมง":
            new_price = price_per_minute * 60
        else: # ต่อนาที
            new_price = price_per_minute

        # 3. Update the input field and store the new period for the next change
        # Block signals to prevent recursive calls while setting text
        self.price_input.setText(f"{new_price:.2f}")
        self.previous_period_text = new_period_text

    def save_item(self):
        name = sanitize_input(self.name_input.text())
        brand = sanitize_input(self.brand_input.text())
        description = sanitize_input(self.desc_input.toPlainText())
        status = self.status_combo.currentText()

        minimum_charge = float(self.minimum_charge_input.text() or 0.0)

        # --- Get new pricing model data ---
        price_model_text = self.price_model_combo.currentText()
        if price_model_text == "คิดเป็นรายครั้ง (คงที่)":
            price_model = 'fixed_fee_only'
        elif price_model_text == "คิดเป็นรายครั้ง + ค่าปรับ":
            price_model = 'fixed_plus_overdue'
        else:
            price_model = 'per_minute'

        fixed_fee = float(self.fixed_fee_input.text() or 0.0)
        
        grace_value = self.grace_period_input.value()
        grace_unit = self.grace_period_unit_combo.currentText()
        grace_period_minutes = grace_value * 1440 if grace_unit == "วัน" else (grace_value * 60 if grace_unit == "ชั่วโมง" else grace_value)

        # --- End get new pricing model data ---
        
        # --- Calculate price_per_minute ---
        price = float(self.price_input.text() or 0.0)
        period = self.period_combo.currentText()
        price_per_minute = 0.0
        if price > 0:
            if period == "ต่อวัน":
                price_per_minute = price / 1440
            elif period == "ต่อชั่วโมง":
                price_per_minute = price / 60
            else: # ต่อนาที
                price_per_minute = price

        if not name:
            CustomMessageBox.show(self, CustomMessageBox.Warning, "ข้อมูลไม่ครบ", "กรุณาใส่ชื่อ")
            return

        if self.item_id:
            self.db_instance.update_item(self.item_id, name, description, self.image_data, brand, status, price_per_minute, period, price_model, fixed_fee, grace_period_minutes, minimum_charge)
        else:
            self.db_instance.add_item(name, description, self.image_data, brand, price_per_minute, period, price_model, fixed_fee, grace_period_minutes, minimum_charge)
        
        # The data_changed signal will be emitted by the DB function.
        # The AdminPanel will catch this and reload.
        # We just need to close this dialog.
        self.accept() # Close the dialog on successful save.
