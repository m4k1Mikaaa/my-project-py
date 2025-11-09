import re
from PIL import Image, UnidentifiedImageError
import io

# Regex for a stricter email validation
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

# Regex for a stricter phone validation (optional '+' at the start, then only digits)
PHONE_REGEX = re.compile(r"^\+?\d{9,}$")

# --- REVISED: Stricter username regex ---
# - Must be 3-20 characters.
# - Can contain letters, numbers, underscore, hyphen.
# - Cannot start or end with an underscore or hyphen.
USERNAME_REGEX = re.compile(r"^(?=[a-zA-Z0-9_-]{3,20}$)(?![-_])(?!.*[-_]{2})[a-zA-Z0-9_-]+(?<![-_])$")

def sanitize_input(text: str) -> str:
    """
    Removes potentially harmful characters from a string to prevent
    basic injection attacks or config file corruption.
    This is a basic sanitization and should not be the only security measure.
    """
    if not isinstance(text, str):
        return ""
    # Remove characters like <, >, {, }, ;, etc.
    return re.sub(r'[<>{};\'"]', '', text)

def is_valid_image_data(data: bytes, allowed_formats: tuple = ('PNG', 'JPEG')) -> bool:
    """
    Validates if the given byte data is a valid image of an allowed format using Pillow.
    This helps prevent uploading malicious files disguised as images.
    """
    if not data:
        return False
    try:
        with Image.open(io.BytesIO(data)) as img:
            # Check if the format is in the allowed list (JPEG is the format name for .jpg files)
            if img.format.upper() not in allowed_formats:
                return False
            # Verify integrity of the image file
            img.verify()
        return True
    except (UnidentifiedImageError, IOError, SyntaxError):
        return False

def is_valid_username(username: str) -> bool:
    """
    Validates a username. It must be 3-20 characters long and can only contain
    alphanumeric characters, underscores, and hyphens.
    """
    if not username:
        return False
    return bool(USERNAME_REGEX.match(username))

def is_valid_password(password: str) -> bool:
    """
    Validates password strength. It must be at least 8 characters long and
    contain at least one letter and one digit.
    """
    if len(password) < 8:
        return False
    if not re.search(r"\d", password): # Must contain at least one digit
        return False
    if not re.search(r"[a-zA-Z]", password): # Must contain at least one letter
        return False
    return True

def is_valid_phone(phone: str) -> bool:
    """
    Validates a phone number. It must contain at least 9 digits.
    """
    if not phone:
        return True # Allow empty phone number
    return bool(PHONE_REGEX.match(phone))

def is_valid_email(email: str) -> bool:
    """
    Validates an email format using regex.
    """
    if not email:
        return False # Email is required
    return bool(EMAIL_REGEX.match(email))

def is_username_taken(username: str, db_instance=None, user_id: int = None) -> bool:
    """
    Checks if the username already exists in the database for another user.
    
    Args:
        username (str): The username to check.
        db_instance: The database management instance to use for the check.
        user_id (int, optional): The ID of the current user, to exclude from the check.
                                 Defaults to None for registration.
    """
    if not db_instance: return True # Fail safe
    return db_instance.username_exists(username, user_id_to_exclude=user_id)

def is_email_taken(email: str, db_instance, user_id: int = None) -> bool:
    """
    Checks if the email already exists in the database for another user.
    
    Args:
        email (str): The email to check.
        db_instance: The database management instance to use for the check.
        user_id (int, optional): The ID of the current user, to exclude from the check.
                                 Defaults to None for registration.
    """
    if not db_instance: return True # Fail safe
    return db_instance.email_exists(email, user_id_to_exclude=user_id)
