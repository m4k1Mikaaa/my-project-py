from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget
)
from PyQt6.QtCore import Qt
import qtawesome as qta
from app_config import app_config
from theme import PALETTES
from .base_dialog import BaseDialog

class CustomMessageBox(BaseDialog):
    # กำหนดค่าคงที่สำหรับประเภทของกล่องข้อความ
    Information = 1
    Warning = 2
    Critical = 3
    Question = 4

    # กำหนดค่าคงที่สำหรับปุ่ม
    Ok = 0x00000400
    Yes = 0x00004000
    No = 0x00010000

    def __init__(self, icon_type, title, text, buttons, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setObjectName("CustomMessageBox")
        self.setMinimumWidth(400)

        # Set a default result, especially important for Question dialogs
        # If the user closes the dialog without clicking a button, it defaults to 'No'
        self.result = self.No if buttons & self.No else self.Ok

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # --- Icon ---
        icon_label = QLabel()
        icon_label.setObjectName("iconLabel")

        current_theme = app_config.get('UI', 'theme', fallback='light')
        palette = PALETTES[current_theme]

        icon_map = {
            self.Information: ('fa5s.info-circle', palette['info']),
            self.Warning: ('fa5s.exclamation-triangle', palette['warning']),
            self.Critical: ('fa5s.times-circle', palette['danger']),
            self.Question: ('fa5s.question-circle', palette['info']) # Using info color for question
        }
        icon_name, icon_color_hex = icon_map.get(icon_type, ('fa5s.info-circle', palette['info']))
        icon_label.setPixmap(qta.icon(icon_name, color=icon_color_hex).pixmap(48, 48))
        main_layout.addWidget(icon_label)

        # --- Text Content ---
        text_layout = QVBoxLayout()
        
        title_label = QLabel(title)
        title_label.setObjectName("titleLabel")
        title_label.setWordWrap(True)
        text_layout.addWidget(title_label)

        message_label = QLabel(text)
        message_label.setObjectName("messageLabel")
        message_label.setWordWrap(True)
        text_layout.addWidget(message_label)
        
        main_layout.addLayout(text_layout)

        # --- Buttons ---
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 15, 0, 0)
        button_layout.addStretch()

        if buttons & self.Yes:
            yes_button = QPushButton("ใช่")
            yes_button.clicked.connect(self.on_yes)
            button_layout.addWidget(yes_button)
        
        if buttons & self.No:
            no_button = QPushButton("ไม่ใช่")
            no_button.clicked.connect(self.on_no)
            button_layout.addWidget(no_button)

        if buttons & self.Ok:
            ok_button = QPushButton("ตกลง")
            ok_button.clicked.connect(self.on_ok)
            button_layout.addWidget(ok_button)

        text_layout.addWidget(button_container)

        self.adjust_and_center()

    def on_ok(self):
        self.result = self.Ok
        self.accept()

    def on_yes(self):
        self.result = self.Yes
        self.accept()

    def on_no(self):
        self.result = self.No
        self.reject()

    @staticmethod
    def show(parent, icon_type, title, text, buttons=Ok, block_console=True):
        dialog = CustomMessageBox(icon_type, title, text, buttons, parent)
        # If called from a context that should not block (like the console), use open()
        if block_console:
            dialog.exec()
        else:
            dialog.open()
        return dialog.result