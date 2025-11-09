import os
import zipfile
import datetime

# --- Configuration ---
PROJECT_NAME = "Mika_Rental"
EXCLUDE_DIRS = {
    "__pycache__",
    ".git",
    ".venv",
    "build",
    "",
    ".vscode",
    ".pytest_cache",
    "Installer_Output",
}
EXCLUDE_FILES = {
    ".gitignore",
    "app_config.ini",
    "",
    ".mika_key",
    "mika_rental.log"
}
# --- End Configuration ---

def get_project_root():
    """Finds the project root directory."""
    return os.path.dirname(os.path.abspath(__file__))

def create_zip_archive(root_dir, zip_filename):
    """Creates a zip archive of the project, excluding specified files and directories."""
    
    # Also exclude the output zip file itself
    EXCLUDE_FILES.add(os.path.basename(zip_filename))

    print(f"Creating archive: {zip_filename}")
    
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for folder_name, subfolders, filenames in os.walk(root_dir):
            # --- Exclude directories ---
            # Modify subfolders in-place to prevent os.walk from traversing them
            subfolders[:] = [d for d in subfolders if d not in EXCLUDE_DIRS]

            # --- Add files to zip ---
            for filename in filenames:
                if filename in EXCLUDE_FILES:
                    continue
                
                # ไม่รวมไฟล์ทดสอบ (test_*.py)
                if filename.startswith("test_") and filename.endswith(".py"):
                    print(f"  Skipping test file: {filename}")
                    continue

                # ไม่รวมไฟล์ zip ของโปรเจกต์ที่เคยสร้างไว้ก่อนหน้า
                if filename.startswith(f"{PROJECT_NAME}_Source_") and filename.endswith(".zip"):
                    print(f"  Skipping previous archive: {filename}")
                    continue
                
                file_path = os.path.join(folder_name, filename)
                arcname = os.path.relpath(file_path, root_dir)
                
                print(f"  Adding: {arcname}")
                zipf.write(file_path, arcname)
    
    print(f"\nSuccessfully created {zip_filename}")

if __name__ == "__main__":
    project_root = get_project_root()
    
    # Generate a filename with a timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_zip_file = os.path.join(project_root, f"{PROJECT_NAME}_Source_{timestamp}.zip")
    
    create_zip_archive(project_root, output_zip_file)