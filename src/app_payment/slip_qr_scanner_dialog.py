import sys
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QEvent
from PyQt6.QtGui import QImage, QPixmap
import cv2
import qtawesome as qta
from pyzbar.pyzbar import decode, ZBarSymbol
from app.base_dialog import BaseDialog
from app_config import app_config
from app.custom_message_box import CustomMessageBox

class SlipQRScannerDialog(BaseDialog):
    """
    A dialog for scanning a slip's QR code from a webcam feed in real-time.
    """
    qr_code_found = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("สแกน QR Code จากสลิป")
        self.setMinimumSize(640, 520)

        self.capture = None
        self.timer = QTimer(self)
        self.found_qr_data = None
        self.is_moving = False # Flag to track if the window is being moved/resized

        # --- Layouts ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        self.image_label = QLabel("กรุณาแสดง QR Code จากสลิปบนหน้าจอของคุณให้อยู่ในกรอบ")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: black; border-radius: 8px; color: white; font-weight: bold;")
        main_layout.addWidget(self.image_label)

        button_layout = QHBoxLayout()
        self.cancel_button = QPushButton(qta.icon('fa5s.times', color='white'), " ยกเลิก")
        self.cancel_button.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        self.timer.timeout.connect(self.update_and_scan_frame)

        self.adjust_and_center()
        # Install event filter to detect move/resize events
        self.installEventFilter(self)

        self.start_camera()

    def start_camera(self):
        """Initializes and starts the camera feed."""
        if not self.capture or not self.capture.isOpened():
            try:
                device_index = app_config.getint('CAMERA', 'device_index', fallback=0)
                # Use CAP_DSHOW for better compatibility on Windows.
                # It's more stable than the default or CAP_MSMF in many cases.
                self.capture = cv2.VideoCapture(device_index, cv2.CAP_DSHOW)

                # --- Set camera resolution from config ---
                resolution_str = app_config.get('CAMERA', 'resolution', fallback='640x480') # Use a lower default for scanning
                try:
                    width, height = map(int, resolution_str.split('x'))
                    self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                    self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

                    # Set FPS from config
                    fps = app_config.getint('CAMERA', 'fps', fallback=30)
                    self.capture.set(cv2.CAP_PROP_FPS, float(fps))

                except (ValueError, IndexError):
                    # Fallback to a default resolution if the config value is invalid
                    self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

                if not self.capture or not self.capture.isOpened():
                    self.capture = None # Ensure it's None on failure
                    raise IOError(f"ไม่สามารถเปิดกล้อง Index {device_index} ได้\nอาจมีโปรแกรมอื่นกำลังใช้งานอยู่ หรือไม่ได้เชื่อมต่อ")
            except Exception as e:
                self.show_error_and_close(f"ไม่สามารถเปิดกล้องได้: {e}")
                return

        self.timer.start(50)  # Update frame every ~50ms

    def update_and_scan_frame(self):
        """Reads a frame, displays it, and attempts to decode QR codes."""
        if not self.capture or not self.capture.isOpened() or self.is_moving:
            return

        ret, frame = self.capture.read()
        if ret:
            # --- OPTIMIZATION: Decode from a downscaled grayscale image ---
            # Convert to grayscale for faster processing
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Downscale the image to a smaller size for much faster QR code detection
            scale_percent = 50 # 50% of original size
            width = int(gray_frame.shape[1] * scale_percent / 100)
            height = int(gray_frame.shape[0] * scale_percent / 100)
            dim = (width, height)
            resized_frame = cv2.resize(gray_frame, dim, interpolation = cv2.INTER_AREA)

            # Decode QR codes from the smaller, grayscale frame
            decoded_objects = decode(resized_frame, symbols=[ZBarSymbol.QRCODE])
            if decoded_objects:
                # We found a QR code, take the first one
                self.found_qr_data = decoded_objects[0].data.decode('utf-8')
                self.qr_code_found.emit(self.found_qr_data)
                # The accept() call will trigger closeEvent, which releases the camera.
                self.accept() # Close the dialog on success
                return

            # If no QR code found, just display the frame
            rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w
            
            qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_image)
            
            scaled_pixmap = pixmap.scaled(self.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.image_label.setPixmap(scaled_pixmap)

    def show_error_and_close(self, message):
        """Shows an error message and then closes the dialog."""
        CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", message)
        QTimer.singleShot(0, self.reject)

    def eventFilter(self, source, event):
        """Filter events to detect when the window is being moved or resized."""
        if event.type() == QEvent.Type.Move:
            self.is_moving = True
            # Use a timer to reset the flag after movement stops
            QTimer.singleShot(150, self.reset_moving_flag)
        elif event.type() == QEvent.Type.Resize:
            self.is_moving = True
            QTimer.singleShot(150, self.reset_moving_flag)
        
        return super().eventFilter(source, event)

    def reset_moving_flag(self):
        self.is_moving = False

    def closeEvent(self, event):
        """Ensures the camera is released when the dialog is closed."""
        self.release_camera()
        super().closeEvent(event)

    def reject(self):
        """Override reject to ensure camera is released."""
        self.release_camera()
        super().reject()

    def accept(self):
        """Override accept to ensure camera is released."""
        self.release_camera()
        super().accept()

    def release_camera(self):
        """Stops the timer and releases the camera resource."""
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()
        if self.capture and self.capture.isOpened():
            self.capture.release()
            print("SlipQRScannerDialog: Camera hardware released.")
        self.capture = None