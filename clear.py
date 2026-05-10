import os
import shutil
import tempfile
from common import get_cs2_path

def clear_addons_keep_db():
    cs2_dir = get_cs2_path()
    if cs2_dir is None:
        print("Failed to get CS2 path.")
        return False

    addons_path = os.path.join(cs2_dir, "game", "csgo", "addons")
    db_file_path = os.path.join(addons_path, "cs2kz", "data", "cs2kz.sqlite3")

    if not os.path.exists(addons_path):
        print(f"Folder not found: {addons_path}")
        return False

    # Если база данных существует – сохраняем её во временную папку
    temp_db_path = None
    if os.path.exists(db_file_path):
        try:
            # Создаём временный файл
            temp_fd, temp_db_path = tempfile.mkstemp(suffix=".sqlite3")
            os.close(temp_fd)
            shutil.copy2(db_file_path, temp_db_path)
            print(f"Database backed up to temporary file: {temp_db_path}")
        except Exception as e:
            print(f"Failed to backup database: {e}")
            return False
    else:
        print("Database file not found, will only delete addons folder (no restore needed).")

    # Удаляем всю папку addons
    try:
        shutil.rmtree(addons_path)
        print(f"Deleted: {addons_path}")
    except Exception as e:
        print(f"Failed to delete addons folder: {e}")
        return False

    # Если была база данных – восстанавливаем её на новое место
    if temp_db_path and os.path.exists(temp_db_path):
        try:
            # Воссоздаём структуру папок
            target_dir = os.path.dirname(db_file_path)
            os.makedirs(target_dir, exist_ok=True)
            # Копируем обратно
            shutil.copy2(temp_db_path, db_file_path)
            print(f"Database restored to: {db_file_path}")
            # Удаляем временный файл
            os.unlink(temp_db_path)
        except Exception as e:
            print(f"Failed to restore database: {e}")
            return False
    else:
        print("No database to restore.")

    print("Cleanup completed successfully.")
    return True

if __name__ == "__main__":
    clear_addons_keep_db()