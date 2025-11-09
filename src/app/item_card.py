from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtGui import QPixmap, QPainter, QColor, QIcon, QLinearGradient, QPainterPath, QPen, QPainterPath
from PyQt6.QtWidgets import QStyleOption, QStyle, QGraphicsDropShadowEffect
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QDateTime, QPropertyAnimation, QEasingCurve, QPoint, QParallelAnimationGroup, QRectF, QPointF, QEvent
from app_config import app_config
from .utils import set_image_on_label
class ImageContainer(QWidget):
    """A custom widget to display and clip a pixmap."""
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self.pixmap = pixmap

    def setPixmap(self, pixmap):
        self.pixmap = pixmap
        self.update() # Trigger a repaint

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        widget_rect = self.rect()

        # Create a rounded rectangle path to clip the drawing
        path = QPainterPath()
        path.addRoundedRect(QRectF(widget_rect), 8, 8)
        painter.setClipPath(path)

        if not self.pixmap.isNull():
            # Scale the pixmap to fit inside the widget while keeping aspect ratio
            scaled_pixmap = self.pixmap.scaled(widget_rect.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            
            # Calculate the top-left position to center the scaled pixmap
            x = (widget_rect.width() - scaled_pixmap.width()) / 2
            y = (widget_rect.height() - scaled_pixmap.height()) / 2
            
            # Draw the centered and scaled pixmap
            painter.drawPixmap(QPointF(x, y), scaled_pixmap)

class ItemCard(QWidget):
    """
    การ์ดสำหรับแสดงข้อมูล item แต่ละชิ้นใน Grid
    """
    clicked = pyqtSignal(int)
    doubleClicked = pyqtSignal(int)

    def __init__(self, item_data, parent=None):
        super().__init__(parent)
        self.item_id = item_data['id']
        self.item_data = item_data
        self.setFixedSize(200, 280)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # This is required for the custom paintEvent to work with stylesheets
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        # Set margins to provide some padding around the card content
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Image Container ---
        # สร้าง container เพื่อจัดรูปภาพให้อยู่ตรงกลางในแนวนอน
        image_container = QWidget()
        image_layout = QHBoxLayout(image_container)
        image_layout.setContentsMargins(0, 10, 0, 5) # เพิ่มระยะห่างบน-ล่าง
        
        # สร้าง QPixmap จากข้อมูล BLOB
        pixmap = QPixmap()
        image_data_blob = item_data.get('image_path')
        if image_data_blob:
            pixmap.loadFromData(image_data_blob)
        
        # if pixmap.isNull():
        #     pixmap = QPixmap(180, 180)
        #     pixmap.fill(Qt.GlobalColor.transparent)
        self.image_label = ImageContainer(pixmap)
        self.image_label.setFixedSize(180, 180)
        
        image_layout.addWidget(self.image_label)
        self.image_label.setMouseTracking(True) # Ensure mouse events are tracked

        # --- Text Info Widget ---
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(10, 5, 10, 10)
        info_layout.setSpacing(3)

        self.name_label = QLabel(item_data['name'])
        self.name_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(True)

        self.brand_label = QLabel(item_data['brand'] or "N/A")
        self.brand_label.setProperty("class", "secondary-text")
        self.brand_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.brand_label.setWordWrap(True)

        self.renter_info_label = QLabel()
        self.renter_info_label.setStyleSheet("font-size: 8pt;")
        self.renter_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.renter_info_label.setWordWrap(True)
        self.renter_info_label.setVisible(False)
        
        # --- NEW: Improved Price Display Logic ---
        price_per_minute = float(item_data.get('price_per_minute', 0.0))
        price_unit = item_data.get('price_unit', 'ต่อวัน')
        price_model = item_data.get('price_model', 'per_minute')
        fixed_fee = float(item_data.get('fixed_fee', 0.0))
        minimum_charge = float(item_data.get('minimum_charge', 0.0))
        grace_period_minutes = int(item_data.get('grace_period_minutes', 0))

        # --- Build Main Price Text (for status label) ---
        main_price_text = ""
        if (price_model == 'fixed_fee_only' or price_model == 'fixed_plus_overdue') and fixed_fee > 0:
            main_price_text = f"{fixed_fee:.2f} บ./ครั้ง"
        
        if (price_model == 'fixed_plus_overdue' or price_model == 'per_minute') and price_per_minute > 0:
            prefix = " +ค่าปรับ " if price_model == 'fixed_plus_overdue' and main_price_text else ""
            if price_unit == "ต่อวัน":
                main_price_text += f"{prefix}{price_per_minute * 1440:.2f} บ./วัน"
            elif price_unit == "ต่อชั่วโมง":
                main_price_text += f"{prefix}{price_per_minute * 60:.2f} บ./ชม."
            else: # ต่อนาที
                main_price_text += f"{prefix}{price_per_minute:.2f} บ./นาที"

        # --- FIX: If no price text is generated, check for minimum charge before declaring it "Free" ---
        if not main_price_text and price_model == 'per_minute' and minimum_charge > 0:
            main_price_text = f"ขั้นต่ำ {minimum_charge:.2f} บ."
        elif not main_price_text:
            main_price_text = "ฟรี"

        # --- Build Price Details Text (for the new label) ---
        details_parts = []
        if price_model == 'per_minute' and minimum_charge > 0:
            details_parts.append(f"ขั้นต่ำ {minimum_charge:.2f} บ.")
        
        if price_model == 'fixed_plus_overdue' and grace_period_minutes > 0:
            grace_text = self._format_grace_period(grace_period_minutes)
            details_parts.append(f"ได้ไม่เกิน {grace_text}")

        price_details_text = " | ".join(details_parts)

        self.price_details_label = QLabel(price_details_text)
        self.price_details_label.setObjectName("PriceDetailsLabel")
        self.price_details_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.price_details_label.setWordWrap(True)
        # Hide if there are no details to show
        if not price_details_text:
            self.price_details_label.setVisible(False)
        # --- END NEW ---

        # --- NEW: Combine Price and Status Display ---
        status_text = item_data['status'].capitalize()
        # If the item is available, show the price in the status label.
        if item_data['status'] == 'available':
            status_text = main_price_text
        self.status_label = QLabel(status_text)
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True) # Allow text to wrap
        self.status_label.setProperty("status", item_data['status'])

        info_layout.addWidget(self.name_label)
        info_layout.addWidget(self.brand_label)
        info_layout.addWidget(self.renter_info_label)
        info_layout.addStretch(1)
        info_layout.addWidget(self.price_details_label)
        info_layout.addWidget(self.status_label)

        layout.addWidget(image_container)
        layout.addWidget(info_widget)

        if self.item_data['status'] == 'rented':
            self.update_renter_info()
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.update_renter_info)
            self.timer.start(60000)

    def update_renter_info(self):
        renter = self.item_data.get('renter_username', 'N/A')
        rent_date = self.item_data.get('rent_date')
        if rent_date:
            now = QDateTime.currentDateTime()
            # The datetime from SQLite is a string, so we must parse it.
            # The format is 'yyyy-MM-dd HH:mm:ss'. We also specify it's in UTC.
            rent_datetime = QDateTime.fromString(str(rent_date).split('.')[0], "yyyy-MM-dd HH:mm:ss")
            rent_datetime.setTimeSpec(Qt.TimeSpec.UTC)

            offset_hours = app_config.getint('TIME', 'utc_offset_hours', fallback=7)
            offset_seconds = offset_hours * 3600
            local_rent_datetime = rent_datetime.toOffsetFromUtc(offset_seconds)

            days = local_rent_datetime.daysTo(now)
            hours = (local_rent_datetime.secsTo(now) // 3600) % 24
            minutes = (local_rent_datetime.secsTo(now) // 60) % 60
            
            duration_str = f"{days}d {hours}h {minutes}m"
            self.renter_info_label.setText(f"<b>ผู้เช่า-ยืม:</b> {renter or 'N/A'}")
            self.renter_info_label.setVisible(True)

    def mousePressEvent(self, event):
        self.clicked.emit(self.item_id)
        # --- FIX: Pass the event to the parent widget (the scroll area) ---
        # This allows the SwipeGestureWidget to handle dragging even when the press starts on a card.
        super().mousePressEvent(event)
        # We must ignore the event so it propagates up to the parent (SwipeGestureWidget)
        # so it can handle the drag-to-scroll gesture.
        event.ignore()

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit(self.item_id)

    def _format_grace_period(self, total_minutes: int) -> str:
        """Formats total minutes into a human-readable string (days, hours, minutes)."""
        if total_minutes <= 0:
            return ""
        
        days = total_minutes // 1440
        hours = (total_minutes % 1440) // 60
        minutes = total_minutes % 60
        
        parts = []
        if days > 0: parts.append(f"{days}วัน")
        if hours > 0: parts.append(f"{hours}ชม.")
        return " ".join(parts) if parts else f"{minutes}นาที"

    def paintEvent(self, event):
        # This is necessary to allow stylesheets to work on a custom QWidget.
        opt = QStyleOption()
        opt.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, painter, self)
