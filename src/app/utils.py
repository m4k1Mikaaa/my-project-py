import sys
import os
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt

def get_base_path():
    """
    Gets the base path for resources.
    - In a PyInstaller bundle, this is the _MEIPASS temporary folder.
    - In a development environment, this is the project's 'src' directory.
    """
    if hasattr(sys, '_MEIPASS'):
        # Running in a PyInstaller bundle
        return sys._MEIPASS
    
    # Running in a development environment
    # We need to find the project's 'src' directory.
    # This handles running from the project root (e.g., `python src/main.py`)
    # or from within the src directory (e.g., `cd src; python main.py`).
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def resource_path(relative_path: str) -> str:
    """
    Get the absolute path to a resource, works for dev and for PyInstaller.
    """
    base_path = get_base_path()
    return os.path.join(base_path, relative_path)

def get_icon(icon_filename: str) -> QIcon:
    """
    Creates a QIcon from a filename in the 'app_images' directory.
    """
    return QIcon(resource_path(icon_filename))

def set_image_on_label(label: QLabel, image_data: bytes | None, fallback_text: str = "No Image"):
    """
    Loads image data (bytes) onto a QLabel, scaling it to fit while maintaining aspect ratio.
    
    Args:
        label (QLabel): The label to display the image on.
        image_data (bytes | None): The image data in bytes.
        fallback_text (str): Text to display if image_data is None or invalid.
    """
    pixmap = QPixmap()
    if image_data and pixmap.loadFromData(image_data):
        # Scale the pixmap to fit the label's size, keeping aspect ratio.
        # The aspectRatioMode and transformationMode are not attributes of QLabel.
        # We should use the Qt enums directly.
        scaled_pixmap = pixmap.scaled(
            label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        label.setPixmap(scaled_pixmap)
    else:
        label.setText(fallback_text)