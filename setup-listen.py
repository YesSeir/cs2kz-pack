import requests
import zipfile
import os
import shutil
from pathlib import Path
import time
import re
import sys
from common import get_cs2_path

# =======================
# Цвета для консоли
# =======================
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

def print_success(message):
    print(f"{Colors.GREEN}✓ {message}{Colors.END}")

def print_error(message):
    print(f"{Colors.RED}✗ {message}{Colors.END}")

def print_info(message):
    print(f"{Colors.CYAN}➜ {message}{Colors.END}")

def print_warning(message):
    print(f"{Colors.YELLOW}⚠ {message}{Colors.END}")

def print_header(message):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*50}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{message:^50}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*50}{Colors.END}\n")

def print_step(message):
    print(f"{Colors.BOLD}→ {message}{Colors.END}")

def download_with_progress(url, filename, description=""):
    """Скачивает файл с отображением прогресс-бара"""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        block_size = 8192
        downloaded = 0
        
        # Определяем ширину терминала для прогресс-бара
        try:
            terminal_width = os.get_terminal_size().columns
            bar_width = min(40, terminal_width - 30)
        except:
            bar_width = 40
        
        with open(filename, 'wb') as file:
            for chunk in response.iter_content(chunk_size=block_size):
                if chunk:
                    file.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        filled_length = int(bar_width * downloaded // total_size)
                        bar = '█' * filled_length + '░' * (bar_width - filled_length)
                        
                        # Форматируем размеры
                        downloaded_mb = downloaded / (1024 * 1024)
                        total_mb = total_size / (1024 * 1024)
                        
                        sys.stdout.write(f'\r{Colors.CYAN}[{bar}] {percent:.1f}% ({downloaded_mb:.1f}/{total_mb:.1f} MB){Colors.END}')
                        sys.stdout.flush()
        
        if total_size > 0:
            sys.stdout.write('\n')
            sys.stdout.flush()
        
        return True
    except Exception as e:
        print()
        print_error(f"Failed to download: {e}")
        return False

def extract_zip(zip_path: str, extract_to: str):
    """Распаковка без лишнего вывода"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        return True
    except Exception as e:
        print_error(f"Failed to extract: {e}")
        return False

def download_and_extract_metamod(cs2_dir: str):
    print_step("Installing Metamod")
    
    try:
        latest_mm_url = "https://mms.alliedmods.net/mmsdrop/2.0/mmsource-latest-windows"
        response = requests.get(latest_mm_url)
        response.raise_for_status()
        
        mm_filename = response.text.strip()
        mm_download_url = f"https://mms.alliedmods.net/mmsdrop/2.0/{mm_filename}"

        archive_path = Path(os.getcwd()) / mm_filename

        # Скачивание с прогрессом
        if not download_with_progress(mm_download_url, str(archive_path)):
            return False

        output_dir_path = os.path.join(cs2_dir, 'game', 'csgo')
        
        # Распаковка
        if not extract_zip(str(archive_path), output_dir_path):
            return False

        os.remove(archive_path)
        print_success("Metamod installed successfully")

    except Exception as e:
        print_error(f"Failed: {e}")
        return False
    
    return True

def download_cs2kz(cs2_dir: str):
    try:
        config_path = os.path.join(cs2_dir, "game", "csgo", "cfg", "cs2kz-server-config.txt")
        is_upgrade = os.path.exists(config_path)
        
        if is_upgrade:
            zip_name = "cs2kz-windows-master-upgrade.zip"
        else:
            zip_name = "cs2kz-windows-master.zip"
        
        print_step(f"Installing CS2KZ ({'upgrade' if is_upgrade else 'fresh'})")
        
        response = requests.get("https://api.github.com/repos/KZGlobalTeam/cs2kz-metamod/releases/latest")
        if response.status_code != 200:
            raise Exception(f"Failed to fetch release: {response.status_code}")
        
        release_data = response.json()
        
        found = False
        for asset in release_data["assets"]:
            if asset["name"] == zip_name:
                asset_url = asset["browser_download_url"]
                
                # Скачивание с прогрессом
                if not download_with_progress(asset_url, asset["name"]):
                    return False
                
                extract_to = os.path.join(cs2_dir, "game", "csgo")
                
                # Распаковка
                if not extract_zip(asset["name"], extract_to):
                    return False
                
                os.remove(asset["name"])
                found = True
                break
        
        if not found:
            print_warning(f"{zip_name} not found")
            return False
        
        # Модифицируем конфиг только при первой установке
        if not is_upgrade:
            create_or_modify_cs2kz_config(cs2_dir)
        
        # Скачиваем FGD файл (без вывода)
        try:
            response = requests.get("https://raw.githubusercontent.com/KZGlobalTeam/cs2kz-metamod/refs/heads/master/mapping_api/game/csgo_core/csgo_internal.fgd")
            if response.status_code == 200:
                fgd_path = os.path.join(cs2_dir, "game", "csgo_core")
                os.makedirs(fgd_path, exist_ok=True)
                with open(os.path.join(fgd_path, "csgo_internal.fgd"), "wb") as file:
                    file.write(response.content)
        except:
            pass
        
        print_success("CS2KZ installed successfully")
        return True
        
    except Exception as e:
        print_error(f"Failed: {e}")
        return False

def create_or_modify_cs2kz_config(cs2_dir: str):
    """Создание или модификация конфига (без вывода)"""
    config_path = os.path.join(cs2_dir, "game", "csgo", "cfg", "cs2kz-server-config.txt")
    cfg_dir = os.path.dirname(config_path)
    os.makedirs(cfg_dir, exist_ok=True)
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Изменяем настройки
            content = re.sub(r'"defaultTimeLimit"\s+"60\.0"', '"defaultTimeLimit"\t\t\t\t\t"1000.0"', content)
            content = re.sub(r'"tipInterval"\s+"75"', '"tipInterval"\t\t\t\t\t\t"0"', content)
            content = re.sub(r'"defaultJSSoundMinTier"\s+"4"', '"defaultJSSoundMinTier"\t\t\t\t"2"', content)
            content = re.sub(r'"defaultJSMinTier"\s+"2"', '"defaultJSMinTier"\t\t\t\t\t"1"', content)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(content)
        else:
            config_content = '''"KZSettings"
{
    "defaultTimeLimit"\t\t\t\t\t"1000.0"
    "tipInterval"\t\t\t\t\t\t"0"
    "defaultJSSoundMinTier"\t\t\t\t"2"
    "defaultJSMinTier"\t\t\t\t\t"1"
}'''
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(config_content)
        
        return True
    except Exception as e:
        return False

def download_sql_mm(cs2_dir: str):
    print_step("Installing sql_mm")
    
    try:
        response = requests.get("https://api.github.com/repos/zer0k-z/sql_mm/releases/latest")
        if response.status_code != 200:
            raise Exception(f"Failed to fetch release: {response.status_code}")
        
        release_data = response.json()
        
        found = False
        for asset in release_data["assets"]:
            if asset["name"] == "package-windows.zip":
                asset_url = asset["browser_download_url"]
                
                # Скачивание с прогрессом
                if not download_with_progress(asset_url, asset["name"]):
                    return False
                
                extract_to = os.path.join(cs2_dir, "game", "csgo")
                
                # Распаковка
                if not extract_zip(asset["name"], extract_to):
                    return False
                
                os.remove(asset["name"])
                found = True
                print_success("sql_mm installed successfully")
                break
        
        if not found:
            print_warning("package-windows.zip not found")
            return False
        
        return True
        
    except Exception as e:
        print_error(f"Failed: {e}")
        return False

def setup_asset_bin(cs2_dir: str):
    try:
        source = os.path.join(cs2_dir, "game", "csgo", "readonly_tools_asset_info.bin")
        target = os.path.join(cs2_dir, "game", "csgo", "addons", "metamod", "readonly_tools_asset_info.bin")
        
        if os.path.exists(source):
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(source, target)
        return True
    except:
        return False

def setup_metamod_content_path(path: str):
    try:
        os.makedirs(os.path.join(path, 'content', 'csgo', 'addons', 'metamod'), exist_ok=True)
        return True
    except:
        return False

# =======================
# Main
# =======================

def main():
    print_header("CS2KZ Setup")
    
    path = get_cs2_path()
    if path is None:
        print_error("Failed to get CS2 path.")
        input("\nPress Enter to exit...")
        exit(1)
    
    print_info(f"CS2 Path: {path}")
    print()
    
    # Установка Metamod
    download_and_extract_metamod(path)
    
    # Установка CS2KZ
    download_cs2kz(path)
    
    # Установка sql_mm
    download_sql_mm(path)
    
    # Дополнительные настройки (тихо)
    setup_asset_bin(path)
    setup_metamod_content_path(path)
    
    print_success("\n✨ Setup completed! ✨")
    print("\nClosing in 3 seconds...")
    time.sleep(3)

if __name__ == "__main__":
    main()