from PyQt6.QtWidgets import QDialog, QWidget, QApplication
from PyQt6.QtGui import QCursor

class BaseDialog(QDialog):
    """
    A base dialog class that provides common functionality like
    automatic centering and screen-aware resizing.
    """
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)

    def center_on_screen(self):
        """Centers the dialog on the current active screen."""
        parent = self.parent()
        current_screen = None

        if parent and parent.screen():
            current_screen = parent.screen()
        else:
            # Fallback to the screen with the mouse cursor if no parent
            current_screen = QApplication.screenAt(QCursor.pos())
        
        if not current_screen:
            current_screen = QApplication.primaryScreen()

        screen_geometry = current_screen.geometry()
        self.move(screen_geometry.center() - self.frameGeometry().center())

    def adjust_and_center(self):
        """Adjusts the dialog size to fit its contents and then centers it."""
        self.adjustSize()
        self.center_on_screen()