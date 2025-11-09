import sys
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QEvent
from PyQt6.QtGui import QImage, QPixmap
import cv2
import qtawesome as qta
from app.base_dialog import BaseDialog
from app_config import app_config
from app.custom_message_box import CustomMessageBox

class CameraCaptureDialog(BaseDialog):
    """
    A dialog for capturing an image from a webcam.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ถ่ายภาพสลิป")
        self.setMinimumSize(640, 520)

        self.capture = None
        self.timer = QTimer(self)
        self.captured_image_bytes = None
        self.is_moving = False # Flag to track if the window is being moved/resized

        # --- Layouts ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        self.image_label = QLabel("กำลังเปิดกล้อง...")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: black; border-radius: 8px;")
        main_layout.addWidget(self.image_label)

        button_layout = QHBoxLayout()
        self.capture_button = QPushButton(qta.icon('fa5s.camera', color='white'), " ถ่ายภาพ")
        self.retake_button = QPushButton(qta.icon('fa5s.sync-alt', color='white'), " ถ่ายใหม่")
        self.confirm_button = QPushButton(qta.icon('fa5s.check', color='white'), " ยืนยัน")
        self.cancel_button = QPushButton(qta.icon('fa5s.times', color='white'), " ยกเลิก")

        self.capture_button.clicked.connect(self.capture_image)
        self.retake_button.clicked.connect(self.start_camera)
        self.confirm_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(self.capture_button)
        button_layout.addWidget(self.retake_button)
        button_layout.addWidget(self.confirm_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        self.timer.timeout.connect(self.update_frame)

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
                resolution_str = app_config.get('CAMERA', 'resolution', fallback='1280x720')
                try:
                    width, height = map(int, resolution_str.split('x'))
                    self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                    self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

                    # Set FPS from config
                    fps = app_config.getint('CAMERA', 'fps', fallback=30)
                    self.capture.set(cv2.CAP_PROP_FPS, float(fps))

                except (ValueError, IndexError):
                    # Fallback to a default resolution if the config value is invalid
                    self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                    self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

                if not self.capture or not self.capture.isOpened():
                    # This error message is more user-friendly.
                    self.capture = None # Ensure it's None on failure
                    raise IOError(f"ไม่สามารถเปิดกล้อง Index {device_index} ได้\nอาจมีโปรแกรมอื่นกำลังใช้งานอยู่ หรือไม่ได้เชื่อมต่อ")
            except Exception as e:
                self.show_error_and_close(f"ไม่สามารถเปิดกล้องได้: {e}")
                return

        self.timer.start(30)  # Update frame every ~30ms
        self.capture_button.setVisible(True)
        self.retake_button.setVisible(False)
        self.confirm_button.setVisible(False)
        self.image_label.setText("กำลังเปิดกล้อง...")

    def update_frame(self):
        """Reads a frame from the camera and displays it."""
        if not self.capture or not self.capture.isOpened() or self.is_moving:
            return

        ret, frame = self.capture.read()
        if ret:
            # Convert the captured frame to RGB
            rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) # Keep this for QImage
            h, w, ch = frame.shape
            bytes_per_line = ch * w
            
            # Create QImage and QPixmap to display
            qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_image)

            # --- Adjust label size to match video aspect ratio ---
            # This prevents the image from being distorted.
            label_width = self.image_label.width()
            scaled_height = int(label_width * (h / w))
            self.image_label.setFixedHeight(scaled_height)
            
            # Scale pixmap to fit the label while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(self.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.image_label.setPixmap(scaled_pixmap)

    def capture_image(self):
        """Captures the current frame and stops the camera feed."""
        if not self.capture or not self.capture.isOpened():
            return

        self.timer.stop()
        ret, frame = self.capture.read()
        if ret:
            self.release_camera() # Release camera immediately after capture
            # Encode the captured frame to JPEG format in memory
            is_success, buffer = cv2.imencode(".jpg", frame)
            if is_success:
                self.captured_image_bytes = buffer.tobytes()

                # Display the captured frame
                pixmap = QPixmap()
                pixmap.loadFromData(self.captured_image_bytes)
                scaled_pixmap = pixmap.scaled(self.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.image_label.setPixmap(scaled_pixmap)

                # Update button visibility
                self.capture_button.setVisible(False)
                self.retake_button.setVisible(True)
                self.confirm_button.setVisible(True)
            else:
                self.show_error_and_close("ไม่สามารถบันทึกภาพได้")

    def get_captured_image_bytes(self) -> bytes | None:
        """Returns the captured image as bytes."""
        return self.captured_image_bytes

    def show_error_and_close(self, message):
        """Shows an error message and then closes the dialog."""
        CustomMessageBox.show(self, CustomMessageBox.Critical, "ผิดพลาด", message)
        # Use QTimer to close the dialog after the message box is closed
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
        if self.timer and self.timer.isActive():
            self.timer.stop()
        if self.capture and self.capture.isOpened():
            self.capture.release()
            print("CameraCaptureDialog: Camera hardware released.")
        self.capture = None