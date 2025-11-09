import os
from app.utils import resource_path

def create_icon_if_needed():
    """
    Checks for icon.ico and creates it from pic.png if it doesn't exist.
    This requires the 'Pillow' library.
    """
    try:
        from PIL import Image
    except ImportError:
        print("Warning: 'Pillow' library not found. Cannot automatically create .ico file.")
        print("Please install it using: pip install Pillow")
        return

    try:
        png_path = resource_path('app_image/pic.png')
        ico_path = resource_path('app_image/icon.ico')

        if not os.path.exists(ico_path):
            print(f"'{os.path.basename(ico_path)}' not found. Creating it from '{os.path.basename(png_path)}'...")
            img = Image.open(png_path)
            # Provide multiple sizes for better quality on different displays
            icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
            img.save(ico_path, sizes=icon_sizes)
            print("Successfully created icon.ico.")
    except Exception as e:
        print(f"Error creating .ico file: {e}")