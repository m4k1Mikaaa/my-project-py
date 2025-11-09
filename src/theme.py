import sys
import os
from PyQt6.QtGui import QPalette, QColor, QFontDatabase, QFont
from PyQt6.QtWidgets import QApplication
from app.utils import resource_path

# --- Color Palettes ---
PALETTES = {
    "light": {
        "window": "#f0f0f0",
        "window_text": "#000000",
        "base": "#ffffff",
        "alternate_base": "#f0f0f0",
        "tooltip_base": "#ffffff",
        "tooltip_text": "#000000",
        "text": "#000000",
        "button": "#4a4a4a",      # Dark gray background for buttons
        "button_text": "#ffffff", # White text for buttons
        "bright_text": "#ff0000",
        "success": "#27ae60",
        "danger": "#c0392b",
        "warning": "#f39c12",
        "info": "#2980b9",
        "link": "#005cc5",
        "highlight": "#0078d7",
        "highlighted_text": "#ffffff",
        "disabled_text": "#a0a0a0",
        "disabled_button_text": "#a0a0a0",
        "disabled_button_bg": "#d3d3d3",
    },
    "dark": {
        "window": "#353535",
        "window_text": "#ffffff",
        "base": "#2a2a2a",
        "alternate_base": "#353535",
        "tooltip_base": "#000000",
        "tooltip_text": "#ffffff",
        "text": "#ffffff",
        "button": "#5a5a5a",
        "button_text": "#ffffff",
        "bright_text": "#ff0000",
        "success": "#2ecc71",
        "danger": "#e74c3c",
        "warning": "#f1c40f",
        "info": "#3498db",
        "link": "#58a6ff",
        "highlight": "#50a5f5",
        "highlighted_text": "#ffffff",
        "disabled_text": "#808080",
        "disabled_button_text": "#808080",
        "disabled_button_bg": "#454545",
    }
}

# --- Stylesheets ---
STYLESHEETS = {
    "base": """
        QWidget {{
            font-family: "{font_family}";
            font-weight: normal; /* ตั้งค่า Font พื้นฐานเป็นตัวปกติ */
            font-size: 11pt;
        }}
        QMainWindow, QDialog, QMenu {{
            background-color: {window};
        }}
        QLabel {{
            color: {text};
        }}
        #HeaderWidget QLabel#UserNameLabel, QGroupBox::title {{
            font-weight: bold; /* ทำให้ชื่อผู้ใช้และหัวข้อ GroupBox เป็นตัวหนา */
        }}
        QLineEdit, QComboBox, QDateTimeEdit, QSpinBox, QDoubleSpinBox {{
            background-color: {base};
            color: {text};
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 5px;
        }}
        QTextEdit {{
            background-color: {alternate_base}; /* ทำให้พื้นหลังแตกต่างเล็กน้อย */
            border: 1px solid #555555;
        }}
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
            border: 1px solid {highlight};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 20px;
            background-color: transparent;
            border-left-width: 1px;
            border-left-color: {disabled_text};
            border-left-style: solid;
            border-top-right-radius: 3px;
            border-bottom-right-radius: 3px;
        }}
        QComboBox QAbstractItemView {{
            border: 1px solid {disabled_text};
            background-color: {base};
            selection-background-color: {highlight};
        }}
        QDateTimeEdit, QSpinBox, QDoubleSpinBox {{
            padding-right: 15px; /* make room for the arrows */
        }}
        QDateTimeEdit::up-button, QSpinBox::up-button, QDoubleSpinBox::up-button {{
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 16px;
            border-image: url({arrow_up_path});
            background-color: {alternate_base};
            border: 1px solid {disabled_text};
        }}
        QDateTimeEdit::down-button, QSpinBox::down-button, QDoubleSpinBox::down-button {{
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 16px;
            border-image: url({arrow_down_path});
            background-color: {alternate_base};
            border: 1px solid {disabled_text};
        }}

        QPushButton {{
            background-color: {button};
            color: {button_text};
            font-weight: bold; /* ทำให้ข้อความบนปุ่มเป็นตัวหนา */
            border: 1px solid {disabled_text}; /* Use a palette color for border */
            padding: 6px 15px;
            border-radius: 5px;
            line-height: 1.5; /* เพิ่มความสูงของบรรทัดเพื่อรองรับสระภาษาไทย */
            min-height: 22px;
        }}
        #HeaderWidget QPushButton {{
            /* This is for the text-based login button */
            font-size: 12pt;
        }}
        #HeaderWidget QPushButton#IconButton {{
            font-weight: normal; /* ปุ่มไอคอนไม่จำเป็นต้องมี font-weight */
        }}
        QPushButton:pressed {{
            background-color: {highlight};
            color: {highlighted_text};
            border: none; /* เอฟเฟกต์เหมือนปุ่มถูกกดลงไป */
        }}
        QPushButton:disabled {{
            background-color: {disabled_button_bg};
            color: {disabled_button_text};
            border-color: #5a5a5a;
        }}
        /* Special style for icon-only buttons */
        QPushButton#IconButton {{
            background-color: {alternate_base};
            border: 1px solid {disabled_text};
            padding: 5px;
            border-radius: 5px;
        }}
        QPushButton#IconButton:pressed {{
            background-color: {highlight};
            border: 1px solid {highlight};
        }}

        /* Header and Toolbar Styles */
        #HeaderWidget, #ToolbarWidget {{
            background-color: {alternate_base};
            min-height: 40px; /* เพิ่มความสูงขั้นต่ำ */
            border-bottom: 1px solid #cccccc;
        }}
        #HeaderWidget QLineEdit {{
            padding: 12px 10px;
            font-size: 13pt;
        }}
        QGroupBox {{
            background-color: {base};
            border: 1px solid {disabled_text};
            border-radius: 5px;
            margin-top: 10px;
            padding: 10px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top center;
            padding: 0 5px;
            background-color: {window};
            color: {text};
            font-weight: bold;
        }}
        QTableWidget::item:selected {{
            background-color: {highlight};
            color: {highlighted_text};
        }}
        /* Only make the main scroll areas borderless by using their object name */
        QScrollArea#MainScrollArea {{
            border: none;
        }}
        #HistoryScrollContent {{
            background-color: {window};
        }}
        #GridContainer {{
            background-color: {window};
        }}
        /* ItemCard specific styles */
        ItemCard {{
            background-color: {base};
            border-radius: 8px;
            border: 1px solid {disabled_button_bg};
        }}
        ItemCard:hover {{
            border: 1px solid {highlight};
        }}
        ItemCard[selected="true"] {{
            border: 2px solid {highlight}; /* ทำให้เส้นขอบหนาขึ้นเมื่อถูกเลือก */
        }}
        QLabel#status[status="available"] {{
            background-color: {success};
            color: white;
            font-weight: bold;
            padding: 3px 8px;
            border-radius: 10px;
        }}
        QLabel#status[status="rented"] {{
            background-color: {disabled_text};
            color: white;
            font-weight: bold;
            padding: 3px 8px;
            border-radius: 10px;
        }}
        QLabel#status[status="suspended"], QLabel#status[status="pending"], QLabel#status[status="pending_return"] {{
            background-color: {warning};
            color: white;
            font-weight: bold;
            padding: 3px 8px;
            border-radius: 10px;
        }}
        QLabel[class="secondary-text"] {{
            color: {disabled_text};
        }}
        QLabel.avatar-image {{
            border: 1px solid {disabled_text};
            border-radius: 4px;
        }}
        QLabel.avatar-placeholder {{
            border: none;
        }}
        QLabel[class="avatar-label"] {{
            border: 1px solid #cccccc;
            border-radius: 8px;
            background-color: #e0e0e0;
        }}
        /* --- ItemDetailWindow specific styles --- */
        QPushButton#rent_button[status="available"] {{
            background-color: {success};
            color: white;
            border: none;
        }}
        QPushButton#rent_button[status="available"]:hover {{
            background-color: #2ecc71; /* Lighter green */
        }}
        QPushButton#rent_button[status="suspended"] {{
            background-color: {warning};
            color: white;
            border: none;
        }}
        QPushButton#return_button {{
            background-color: {info};
            color: white;
            border: none;
        }}
        QPushButton#return_button:hover {{
            background-color: #5dade2; /* Lighter blue */
        }}
        QMenu {{
            /* background-color is inherited from QWidget */
            color: {text};
            border: 1px solid #555555;
        }}
        QMenu::item {{
            padding: 5px 25px 5px 20px;
        }}
        QMenu::item:selected {{
            background-color: {highlight};
            color: {highlighted_text};
        }}
        QMenu::separator {{
            height: 1px;
            background: #555555;
            margin-left: 10px;
            margin-right: 5px;
        }}
        /* --- CustomMessageBox specific styles --- */
        #CustomMessageBox {{
            background-color: {base};
            border: 1px solid {highlight};
            border-radius: 8px;
        }}
        #CustomMessageBox #titleLabel {{
            font-size: 14pt;
            font-weight: bold;
        }}
        #CustomMessageBox #messageLabel {{
            font-size: 11pt;
            color: {text};
        }}
    """,
    "dark": """
        QLabel[class="secondary-text"] {{
            color: {disabled_text};
        }}
        QLabel.avatar-image {{
            border: 1px solid #666666;
            border-radius: 4px;
        }}
        QLabel.avatar-placeholder {{
            border: none;
        }}
        QLabel[class="avatar-label"] {{
            border: 1px solid #555555;
            border-radius: 8px; /* Changed from circle to rounded square */
            background-color: #404040;
        }}
        #HeaderWidget, #ToolbarWidget {{
            border-bottom: 1px solid #2a2a2a;
        }}
    """
}

_font_family = 'Segoe UI' # ค่าเริ่มต้นของ Font
_font_loaded = False

def _load_fonts_if_needed():
    """Loads custom fonts from the 'fonts' directory on first call."""
    global _font_family, _font_loaded
    if _font_loaded: # โหลดแค่ครั้งเดียว
        return

    medium_font_family = None
    regular_font_family = None
    first_font_family = None

    # ตรวจสอบว่า QApplication ถูกสร้างแล้วหรือยัง
    if QApplication.instance():
        try:
            font_folder = resource_path('fonts')
            font_files = [f for f in os.listdir(font_folder) if f.endswith(('.ttf', '.otf'))]
            if font_files:
                for font_file in font_files:
                    font_path = os.path.join(font_folder, font_file)
                    font_id = QFontDatabase.addApplicationFont(font_path)
                    if font_id != -1:
                        current_family = QFontDatabase.applicationFontFamilies(font_id)[0]
                        if not first_font_family:
                            first_font_family = current_family
                        if 'medium' in font_file.lower():
                            medium_font_family = current_family
                        elif 'regular' in font_file.lower():
                            regular_font_family = current_family
                _font_family = medium_font_family or regular_font_family or first_font_family or _font_family
        except FileNotFoundError:
            print("Warning: 'fonts' directory not found. Using default system font.")
    
    _font_loaded = True

def apply_theme(app: QApplication, theme_name: str):
    """Applies the selected theme to the application."""
    
    _load_fonts_if_needed() # โหลด Font (ถ้ายังไม่ได้โหลด)
    default_font = QFont(_font_family)
    app.setFont(default_font) # Set default for widgets not covered by stylesheet

    palette = QPalette()
    colors = PALETTES[theme_name]
    
    # Set palette colors
    palette.setColor(QPalette.ColorRole.Window, QColor(colors["window"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["window_text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors["base"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["alternate_base"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors["tooltip_base"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(colors["tooltip_text"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors["button"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["button_text"]))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(colors["bright_text"]))
    palette.setColor(QPalette.ColorRole.Link, QColor(colors["link"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["highlight"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(colors["highlighted_text"]))
    
    # Set disabled colors
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(colors["disabled_text"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(colors["disabled_button_text"]))

    app.setPalette(palette)

    # Apply stylesheets
    # Add font_family to the format dictionary
    format_dict = colors.copy()
    format_dict['font_family'] = _font_family
    # --- FIX: Add resource paths for arrow icons, ensuring correct path separators for CSS ---
    arrow_suffix = 'dark' if theme_name == 'dark' else 'light'
    format_dict['arrow_up_path'] = resource_path(f'app_image/ui_icons/arrow_up_{arrow_suffix}.png').replace('\\', '/')
    format_dict['arrow_down_path'] = resource_path(f'app_image/ui_icons/arrow_down_{arrow_suffix}.png').replace('\\', '/')
    base_style = STYLESHEETS["base"].format(**format_dict)
    theme_specific_style = STYLESHEETS.get(theme_name, "").format(**format_dict)
    app.setStyleSheet(base_style + theme_specific_style)

# Create a single instance to be used
theme = sys.modules[__name__]
