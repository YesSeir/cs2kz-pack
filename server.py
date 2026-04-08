from common import *
import shutil
import psutil

def is_cs2_running():
    """Check if CS2 process is running (but not our server)."""
    current_pid = os.getpid()
    
    for proc in psutil.process_iter(['name', 'pid', 'exe']):
        try:
            proc_name = proc.info['name'] or ""
            proc_pid = proc.info['pid']
            
            # Пропускаем текущий процесс
            if proc_pid == current_pid:
                continue
            
            # Ищем именно cs2.exe (не cs2kz.exe и не другие)
            if proc_name.lower() == 'cs2.exe':
                return True
                
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    return False

if __name__ == '__main__':
    # Проверяем, не запущена ли уже CS2
    if is_cs2_running():
        print("=" * 60)
        print("ERROR: Counter-Strike 2 is already running!")
        print("=" * 60)
        print("Please close the game before starting the server.")
        print("Check Task Manager for cs2.exe processes.")
        print("=" * 60)
        time.sleep(5)
        exit(1)
    
    path = get_cs2_path()
    if path is None:
        print('Failed to get CS2 path. Closing in 3 seconds...')
        time.sleep(3)
        exit()
    
    # Пути к exe файлам
    cs2_original = os.path.join(path, 'game', 'bin', 'win64', 'cs2.exe')
    cs2_kz = os.path.join(path, 'game', 'bin', 'win64', 'server.exe')
    
    # Проверяем и создаём cs2kz.exe если его нет
    if not os.path.exists(cs2_kz):
        if os.path.exists(cs2_original):
            print(f"Creating cs2kz.exe copy from cs2.exe...")
            shutil.copy2(cs2_original, cs2_kz)
            print(f"Created: {cs2_kz}")
        else:
            print(f"Error: cs2.exe not found at {cs2_original}")
            time.sleep(3)
            exit()
    else:
        print(f"Using existing cs2kz.exe")
    
    gameinfo_path, backup_path, core_gameinfo_path, core_backup_path = backup_files(path)
    
    try:
        modify_gameinfo(gameinfo_path, core_gameinfo_path)
    except PermissionError as e:
        print("=" * 60)
        print("ERROR: Cannot modify game files!")
        print("=" * 60)
        print("Details: Permission denied when writing to gameinfo.gi")
        print("Possible causes:")
        print("  - CS2 is running (check Task Manager)")
        print("  - File is locked by another program")
        print("  - Antivirus is blocking access")
        print("=" * 60)
        
        # Восстанавливаем файлы если что-то пошло не так
        try:
            restore_files(backup_path, gameinfo_path, core_backup_path, core_gameinfo_path)
        except:
            pass
            
        time.sleep(5)
        exit(1)
    
    modify_gameinfo_p2p(gameinfo_path)
    
    print(f"Launching CS2 dedicated server from '{cs2_kz}'...")
    process = subprocess.Popen([cs2_kz, '-dedicated', '+map de_nuke', '-insecure'])

    time.sleep(1)

    restore_files(backup_path, gameinfo_path, core_backup_path, core_gameinfo_path)
    try:
        if os.path.exists('steam_appid.txt'):
            os.remove('steam_appid.txt')
    except:
        pass
