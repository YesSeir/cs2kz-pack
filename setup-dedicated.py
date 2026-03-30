import requests
import zipfile
import os
import shutil
from pathlib import Path
import time
import re
import json
import sys
from common import get_cs2_path


# =======================
# Maplist Generator (из maplist.py)
# =======================

STEAM_COLLECTION_API = "https://api.steampowered.com/ISteamRemoteStorage/GetCollectionDetails/v1/"
STEAM_DETAILS_API = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
BATCH_SIZE = 50


def get_collection_item_ids(collection_id):
    print(f"[Maplist] Fetching collection items for ID: {collection_id}...")
    data = {
        "collectioncount": "1",
        "publishedfileids[0]": collection_id
    }
    r = requests.post(STEAM_COLLECTION_API, data=data, timeout=30)
    r.raise_for_status()
    j = r.json()
    items = j["response"]["collectiondetails"][0]["children"]
    print(f"[Maplist] Found {len(items)} items in collection")
    return [c["publishedfileid"] for c in items]


def get_published_file_details(ids):
    result = []
    total = len(ids)
    batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    
    print(f"[Maplist] Fetching details for {total} maps in {batches} batches...")
    
    for i in range(0, total, BATCH_SIZE):
        batch = ids[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"[Maplist] Batch {batch_num}/{batches} ({len(batch)} items)...", end=" ")
        
        data = {"itemcount": str(len(batch))}
        for idx, fid in enumerate(batch):
            data[f"publishedfileids[{idx}]"] = fid

        r = requests.post(STEAM_DETAILS_API, data=data, timeout=30)
        r.raise_for_status()
        batch_result = r.json()["response"]["publishedfiledetails"]
        result.extend(batch_result)
        print(f"OK")
        time.sleep(0.5)

    return result


def generate_maplist(collection_id, output_dir, update_mode=True):
    """
    Generate maplist from Steam collection.
    If update_mode=True, will merge with existing file.
    """
    ids = get_collection_item_ids(collection_id)
    
    if not ids:
        print("[Maplist] No items found in collection!")
        return None
    
    items = get_published_file_details(ids)
    
    print(f"[Maplist] Processing {len(items)} maps...")
    
    # Создаем словарь новых карт
    new_maps = {}
    for item in items:
        title = item.get("title", "").strip()
        fid = item.get("publishedfileid", "")
        if title and fid:
            new_maps[fid] = f"{title}:{fid}"
    
    # Путь к файлу
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "maplist.txt")
    
    # Загружаем существующие карты если нужно
    existing_maps = {}
    if update_mode and os.path.exists(path):
        print(f"[Maplist] Reading existing file to merge...")
        with open(path, 'r', encoding='utf-8') as f:
            for line in f.readlines():
                line = line.strip()
                if line and ':' in line:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        existing_maps[parts[1]] = line
    
    # Объединяем
    if update_mode:
        merged_maps = existing_maps.copy()
        merged_maps.update(new_maps)
        final_maps = sorted(merged_maps.values())
        print(f"[Maplist] Merged: {len(existing_maps)} existing + {len(new_maps)} new = {len(final_maps)} total")
    else:
        final_maps = sorted(new_maps.values())
        print(f"[Maplist] New file: {len(final_maps)} maps")
    
    # Записываем
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(final_maps))
    
    print(f"[Maplist] Done! Saved {len(final_maps)} maps to: {path}")
    return path


# =======================
# Setup Functions
# =======================

def extract_zip(zip_path: str, extract_to: str):
    print(f"Extracting {zip_path} to {extract_to}...")
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    
    print(f"Extraction complete: {extract_to}")


def download_and_extract_metamod(cs2_dir: str):
    try:
        latest_mm_url = "https://mms.alliedmods.net/mmsdrop/2.0/mmsource-latest-windows"
        response = requests.get(latest_mm_url)
        response.raise_for_status()
        
        mm_filename = response.text.strip()
        mm_download_url = f"https://mms.alliedmods.net/mmsdrop/2.0/{mm_filename}"

        archive_path = Path(os.getcwd()) / mm_filename

        print(f"Downloading Metamod from {mm_download_url}...")
        with requests.get(mm_download_url, stream=True) as r:
            r.raise_for_status()
            with open(archive_path, 'wb') as f:
                f.write(r.content)
        print("Download complete.")

        output_dir_path = os.path.join(cs2_dir, 'game', 'csgo')
        print(f"Extracting {archive_path}...")
        
        extract_zip(str(archive_path), output_dir_path)

        print(f"Removing temporary file: {archive_path}")
        os.remove(archive_path)

        print(f"Metamod has been successfully extracted.")

    except requests.exceptions.RequestException as e:
        print(f"Error downloading Metamod: {e}")
    except zipfile.BadZipFile as e:
        print(f"Error extracting Metamod archive: {e}. Ensure the file is a valid ZIP archive.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


def download_cs2kz(cs2_dir: str):
    print(f"Downloading CS2KZ plugin...")
    
    config_path = os.path.join(cs2_dir, "game", "csgo", "cfg", "cs2kz-server-config.txt")
    is_upgrade = os.path.exists(config_path)
    
    if is_upgrade:
        zip_name = "cs2kz-windows-master-upgrade.zip"
        print(f"Detected existing server config, using upgrade package: {zip_name}")
    else:
        zip_name = "cs2kz-windows-master.zip"
        print(f"No existing config found, using full package: {zip_name}")
    
    response = requests.get("https://api.github.com/repos/KZGlobalTeam/cs2kz-metamod/releases/latest")
    if response.status_code != 200:
        raise Exception(f"Failed to fetch latest release: {response.status_code} - {response.text}")

    release_data = response.json()

    if "assets" not in release_data or len(release_data["assets"]) == 0:
        raise Exception("No assets found in the latest release.")
    
    for asset in release_data["assets"]:
        if asset["name"] == zip_name:
            asset_url = asset["browser_download_url"]

            response = requests.get(asset_url)
            if response.status_code != 200:
                raise Exception(f"Failed to download asset: {response.status_code} - {response.text}")

            with open(asset["name"], "wb") as file:
                file.write(response.content)
            
            extract_to = os.path.join(cs2_dir, "game", "csgo")
            extract_zip(asset["name"], extract_to)
            
            os.remove(asset["name"])
            break
    else:
        print(f"Warning: {zip_name} not found in release assets")

    # Модифицируем конфиг ТОЛЬКО при первой установке (не при upgrade)
    if not is_upgrade:
        create_or_modify_cs2kz_config(cs2_dir)
    else:
        print(f"Skipping config modification (upgrade mode - preserving existing config)")

    print(f"Downloading mapping API FGD...")
    response = requests.get("https://raw.githubusercontent.com/KZGlobalTeam/cs2kz-metamod/refs/heads/master/mapping_api/game/csgo_core/csgo_internal.fgd")
    if response.status_code != 200:
        raise Exception(f"Failed to fetch mapping API FGD: {response.status_code} - {response.text}")
    path = os.path.join(cs2_dir, "game", "csgo_core")
    if not os.path.exists(path):
        os.makedirs(path)
    with open(os.path.join(path, "csgo_internal.fgd"), "wb") as file:
        file.write(response.content)

def create_or_modify_cs2kz_config(cs2_dir: str):
    config_path = os.path.join(cs2_dir, "game", "csgo", "cfg", "cs2kz-server-config.txt")
    
    cfg_dir = os.path.dirname(config_path)
    os.makedirs(cfg_dir, exist_ok=True)
    
    if os.path.exists(config_path):
        print(f"Modifying existing cs2kz-server-config.txt...")
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Change defaultTimeLimit from 60.0 to 1000.0
        new_content = re.sub(
            r'"defaultTimeLimit"\s+"60\.0"',
            '"defaultTimeLimit"\t\t\t\t\t"1000.0"',
            content
        )
        
        if new_content == content:
            new_content = content.replace('"defaultTimeLimit"\t\t\t\t\t"60.0"', '"defaultTimeLimit"\t\t\t\t\t"1000.0"')
            new_content = new_content.replace('"defaultTimeLimit" "60.0"', '"defaultTimeLimit"\t\t\t\t\t"1000.0"')
        
        # Change tipInterval from 75 to 0
        new_content = re.sub(
            r'"tipInterval"\s+"75"',
            '"tipInterval"\t\t\t\t\t\t"0"',
            new_content
        )
        
        if '"tipInterval"\t\t\t\t\t\t"75"' in new_content:
            new_content = new_content.replace('"tipInterval"\t\t\t\t\t\t"75"', '"tipInterval"\t\t\t\t\t\t"0"')
        if '"tipInterval" "75"' in new_content:
            new_content = new_content.replace('"tipInterval" "75"', '"tipInterval"\t\t\t\t\t\t"0"')
        
        # Change defaultJSSoundMinTier from 4 to 2
        new_content = re.sub(
            r'"defaultJSSoundMinTier"\s+"4"',
            '"defaultJSSoundMinTier"\t\t\t\t"2"',
            new_content
        )
        
        if '"defaultJSSoundMinTier"\t\t\t\t"4"' in new_content:
            new_content = new_content.replace('"defaultJSSoundMinTier"\t\t\t\t"4"', '"defaultJSSoundMinTier"\t\t\t\t"2"')
        if '"defaultJSSoundMinTier" "4"' in new_content:
            new_content = new_content.replace('"defaultJSSoundMinTier" "4"', '"defaultJSSoundMinTier"\t\t\t\t"2"')
        
        # Change defaultJSMinTier from 2 to 1
        new_content = re.sub(
            r'"defaultJSMinTier"\s+"2"',
            '"defaultJSMinTier"\t\t\t\t\t"1"',
            new_content
        )
        
        if '"defaultJSMinTier"\t\t\t\t\t"2"' in new_content:
            new_content = new_content.replace('"defaultJSMinTier"\t\t\t\t\t"2"', '"defaultJSMinTier"\t\t\t\t\t"1"')
        if '"defaultJSMinTier" "2"' in new_content:
            new_content = new_content.replace('"defaultJSMinTier" "2"', '"defaultJSMinTier"\t\t\t\t\t"1"')
        
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"Updated config settings in {config_path}")
        print(f"  - defaultTimeLimit: 60.0 -> 1000.0")
        print(f"  - tipInterval: 75 -> 0")
        print(f"  - defaultJSSoundMinTier: 4 -> 2")
        print(f"  - defaultJSMinTier: 2 -> 1")
        
    else:
        print(f"Creating cs2kz-server-config.txt with custom settings...")
        config_content = '''"KZSettings"
{
    "defaultTimeLimit"\t\t\t\t\t"1000.0"
    "tipInterval"\t\t\t\t\t\t"0"
    "defaultJSSoundMinTier"\t\t\t\t"2"
    "defaultJSMinTier"\t\t\t\t\t"1"
}'''
        
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(config_content)
        
        print(f"Created cs2kz-server-config.txt: {config_path}")


def download_sql_mm(cs2_dir: str):
    print(f"Downloading sql_mm plugin...")
    response = requests.get("https://api.github.com/repos/zer0k-z/sql_mm/releases/latest")
    if response.status_code != 200:
        raise Exception(f"Failed to fetch latest sql_mm release: {response.status_code} - {response.text}")

    release_data = response.json()

    if "assets" not in release_data or len(release_data["assets"]) == 0:
        raise Exception("No assets found in the latest sql_mm release.")
    
    for asset in release_data["assets"]:
        if asset["name"] == "package-windows.zip":
            asset_url = asset["browser_download_url"]

            response = requests.get(asset_url)
            if response.status_code != 200:
                raise Exception(f"Failed to download sql_mm asset: {response.status_code} - {response.text}")

            with open(asset["name"], "wb") as file:
                file.write(response.content)
            
            extract_to = os.path.join(cs2_dir, "game", "csgo")
            extract_zip(asset["name"], extract_to)
            
            os.remove(asset["name"])
            break
    else:
        print("Warning: package-windows.zip not found in sql_mm release")


def download_multiaddon_manager(cs2_dir: str):
    print(f"Downloading MultiAddonManager...")
    
    try:
        # Получаем информацию о последнем релизе
        response = requests.get("https://api.github.com/repos/Source2ZE/MultiAddonManager/releases/latest")
        if response.status_code != 200:
            raise Exception(f"Failed to fetch latest release: {response.status_code} - {response.text}")

        release_data = response.json()

        if "assets" not in release_data or len(release_data["assets"]) == 0:
            raise Exception("No assets found in the latest MultiAddonManager release.")
        
        # Ищем файл с Windows версией
        found = False
        for asset in release_data["assets"]:
            if "windows" in asset["name"].lower():
                asset_url = asset["browser_download_url"]
                zip_name = asset["name"]

                print(f"Found Windows asset: {zip_name}")
                response = requests.get(asset_url)
                if response.status_code != 200:
                    raise Exception(f"Failed to download MultiAddonManager asset: {response.status_code} - {response.text}")

                with open(zip_name, "wb") as file:
                    file.write(response.content)
                
                extract_to = os.path.join(cs2_dir, "game", "csgo")
                extract_zip(zip_name, extract_to)
                
                os.remove(zip_name)
                found = True
                break
        
        if not found:
            print("Warning: No Windows asset found in MultiAddonManager release")
            return
        
        # Модифицируем конфиг после установки
        modify_multiaddon_manager_config(cs2_dir)
        
    except Exception as e:
        print(f"Warning: Failed to download MultiAddonManager: {e}")
        return

def modify_multiaddon_manager_config(cs2_dir: str):
    config_path = os.path.join(cs2_dir, "game", "csgo", "cfg", "multiaddonmanager", "multiaddonmanager.cfg")
    
    print(f"Modifying {config_path}...")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Change mm_extra_addons
    pattern = r'(mm_extra_addons\s+")([^"]*)(")'
    replacement = r'\g<1>3469155349,3610991685\g<3>'
    
    new_content = re.sub(pattern, replacement, content)
    
    if new_content == content:
        old_line = 'mm_extra_addons 				""'
        new_line = 'mm_extra_addons 				"3469155349,3610991685"'
        new_content = content.replace(old_line, new_line)
    
    # Change mm_extra_addons_timeout from 10 to 3600
    pattern = r'(mm_extra_addons_timeout\s+)(\d+)'
    replacement = r'\g<1>3600'
    
    new_content = re.sub(pattern, replacement, new_content)
    
    if '"mm_extra_addons_timeout" "10"' in new_content:
        new_content = new_content.replace('"mm_extra_addons_timeout" "10"', '"mm_extra_addons_timeout" "3600"')
    if 'mm_extra_addons_timeout 10' in new_content:
        new_content = new_content.replace('mm_extra_addons_timeout 10', 'mm_extra_addons_timeout 3600')
    
    # Change mm_block_disconnect_messages from 0 to 1
    pattern = r'(mm_block_disconnect_messages\s+)(\d+)'
    replacement = r'\g<1>1'
    
    new_content = re.sub(pattern, replacement, new_content)
    
    if '"mm_block_disconnect_messages" "0"' in new_content:
        new_content = new_content.replace('"mm_block_disconnect_messages" "0"', '"mm_block_disconnect_messages" "1"')
    if 'mm_block_disconnect_messages 0' in new_content:
        new_content = new_content.replace('mm_block_disconnect_messages 0', 'mm_block_disconnect_messages 1')
    
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"Updated MultiAddonManager config in {config_path}")
    print(f"  - mm_extra_addons: -> '3469155349,3610991685'")
    print(f"  - mm_extra_addons_timeout: 10 -> 3600")
    print(f"  - mm_block_disconnect_messages: 0 -> 1")


def download_counterstrikesharp(cs2_dir: str):
    print(f"Downloading CounterStrikeSharp...")
    
    dotnet_path = os.path.join(cs2_dir, "game", "csgo", "addons", "counterstrikesharp", "dotnet")
    is_upgrade = os.path.exists(dotnet_path)
    
    if is_upgrade:
        print(f"Detected existing dotnet folder, looking for counterstrikesharp-windows package...")
        search_pattern = "counterstrikesharp-windows"
    else:
        print(f"No existing installation found, looking for runtime-windows package...")
        search_pattern = "runtime-windows"
    
    response = requests.get("https://api.github.com/repos/roflmuffin/CounterStrikeSharp/releases/latest")
    if response.status_code != 200:
        raise Exception(f"Failed to fetch latest CounterStrikeSharp release: {response.status_code} - {response.text}")

    release_data = response.json()

    if "assets" not in release_data or len(release_data["assets"]) == 0:
        raise Exception("No assets found in the latest CounterStrikeSharp release.")
    
    found = False
    for asset in release_data["assets"]:
        if search_pattern in asset["name"]:
            asset_url = asset["browser_download_url"]
            zip_name = asset["name"]

            print(f"Found asset: {zip_name}")
            response = requests.get(asset_url)
            if response.status_code != 200:
                raise Exception(f"Failed to download CounterStrikeSharp asset: {response.status_code} - {response.text}")

            with open(zip_name, "wb") as file:
                file.write(response.content)
            
            extract_to = os.path.join(cs2_dir, "game", "csgo")
            extract_zip(zip_name, extract_to)
            
            os.remove(zip_name)
            found = True
            break
    
    if not found:
        print(f"Warning: No file containing '{search_pattern}' found in CounterStrikeSharp release")
        return
    
    if not is_upgrade:
        create_counterstrikesharp_config(cs2_dir)


def create_counterstrikesharp_config(cs2_dir: str):
    config_dir = os.path.join(cs2_dir, "game", "csgo", "addons", "counterstrikesharp", "configs")
    config_path = os.path.join(config_dir, "core.json")
    
    if os.path.exists(config_path):
        print(f"CounterStrikeSharp config already exists: {config_path}, skipping creation")
        return
    
    os.makedirs(config_dir, exist_ok=True)
    
    config_content = {
        "PublicChatTrigger": ["!"],
        "SilentChatTrigger": ["/"],
        "FollowCS2ServerGuidelines": False,
        "PluginHotReloadEnabled": True,
        "PluginAutoLoadEnabled": True,
        "PluginResolveNugetPackages": False,
        "ServerLanguage": "en",
        "UnlockConCommands": True,
        "UnlockConVars": True,
        "AutoUpdateEnabled": True,
        "AutoUpdateURL": "http://gamedata.cssharp.dev",
        "MaximumFrameTasksExecutedPerTick": 1024
    }
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config_content, f, indent=4)
    
    print(f"Created CounterStrikeSharp config: {config_path}")


def download_asset_by_url(cs2_dir: str, asset_url: str, extract_to: str, description: str = "asset", search_pattern: str = None):
    print(f"Downloading {description} from {asset_url}...")
    
    if search_pattern:
        parts = asset_url.split('/')
        if len(parts) >= 7 and parts[2] == "api.github.com" and parts[3] == "repos":
            owner = parts[4]
            repo = parts[5]
            releases_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
            
            print(f"Fetching release info to find asset matching '{search_pattern}'...")
            response = requests.get(releases_url)
            if response.status_code != 200:
                raise Exception(f"Failed to fetch release info: {response.status_code} - {response.text}")
            
            release_data = response.json()
            if "assets" not in release_data or len(release_data["assets"]) == 0:
                raise Exception("No assets found in the release.")
            
            found_asset = None
            for asset in release_data["assets"]:
                if search_pattern in asset["name"]:
                    found_asset = asset
                    print(f"Found matching asset: {asset['name']}")
                    break
            
            if not found_asset:
                raise Exception(f"No asset containing '{search_pattern}' found in release")
            
            download_url = found_asset["url"]
            zip_name = found_asset["name"]
        else:
            download_url = asset_url
            zip_name = asset_url.split('/')[-1]
            if not zip_name.endswith('.zip'):
                zip_name = f"{description}.zip"
    else:
        download_url = asset_url
        zip_name = asset_url.split('/')[-1]
        if not zip_name.endswith('.zip'):
            zip_name = f"{description}.zip"
    
    try:
        headers = {}
        if "api.github.com" in download_url:
            headers["Accept"] = "application/octet-stream"
        
        response = requests.get(download_url, headers=headers, allow_redirects=True)
        if response.status_code != 200:
            raise Exception(f"Failed to download {description}: {response.status_code}")

        with open(zip_name, "wb") as file:
            file.write(response.content)
        
        print(f"Downloaded {zip_name}, extracting...")
        
        os.makedirs(extract_to, exist_ok=True)
        
        with zipfile.ZipFile(zip_name, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        
        print(f"{description} extracted successfully")
        
        os.remove(zip_name)
        
    except Exception as e:
        print(f"Error downloading {description}: {e}")
        raise


def setup_rockthevote(cs2_dir: str):
    print(f"Setting up RockTheVote...")
    
    asset_url = "https://api.github.com/repos/M-archand/cs2-rockthevote/releases/assets/344433876"
    plugins_path = os.path.join(cs2_dir, "game", "csgo", "addons", "counterstrikesharp", "plugins")
    
    try:
        download_asset_by_url(cs2_dir, asset_url, plugins_path, "RockTheVote", "RockTheVote")
    except Exception as e:
        print(f"Warning: Failed to download RockTheVote: {e}")
        return
    
    # Генерируем maplist.txt через Steam API
    generate_maplist_for_rockthevote(cs2_dir)
    
    config_dir = os.path.join(cs2_dir, "game", "csgo", "addons", "counterstrikesharp", "configs", "plugins", "RockTheVote")
    config_path = os.path.join(config_dir, "RockTheVote.json")
    
    if os.path.exists(config_path):
        print(f"RockTheVote config already exists: {config_path}, skipping creation")
        return
    
    os.makedirs(config_dir, exist_ok=True)
    
    rockthevote_config = {
        "ConfigVersion": 22,
        "Rtv": {
            "Enabled": True,
            "EnabledInWarmup": False,
            "EnablePanorama": False,
            "MinPlayers": 0,
            "MinRounds": 0,
            "ChangeAtRoundEnd": False,
            "MapChangeDelay": 5,
            "SoundEnabled": False,
            "SoundPath": "sounds/vo/announcer/cs2_classic/felix_broken_fang_pick_1_map_tk01.vsnd_c",
            "MapsToShow": 6,
            "AlwaysActive": True,
            "AlwaysActiveReminder": False,
            "ReminderInterval": 180,
            "RtvVoteDuration": 25,
            "MapVoteDuration": 25,
            "CooldownDuration": 10,
            "MapStartDelay": 10,
            "VotePercentage": 51,
            "EnableCountdown": True,
            "CountdownType": "chat",
            "ChatCountdownInterval": 15
        },
        "EndOfMapVote": {
            "Enabled": True,
            "MapsToShow": 6,
            "MenuType": "CenterHtmlMenu",
            "ChangeMapImmediately": True,
            "VoteDuration": 25,
            "SoundEnabled": False,
            "SoundPath": "sounds/vo/announcer/cs2_classic/felix_broken_fang_pick_1_map_tk01.vsnd_c",
            "TriggerSecondsBeforeEnd": 180,
            "TriggerRoundsBeforeEnd": 0,
            "DelayToChangeInTheEnd": 0,
            "IncludeExtendCurrentMap": True,
            "EnableCountdown": True,
            "CountdownType": "hud",
            "ChatCountdownInterval": 30,
            "EnableHint": False,
            "HintType": "GameHint"
        },
        "Nominate": {
            "Enabled": True,
            "EnabledInWarmup": True,
            "MenuType": "CenterHtmlMenu",
            "NominateLimit": 3,
            "Permission": ""
        },
        "Votemap": {
            "Enabled": True,
            "MenuType": "CenterHtmlMenu",
            "VotePercentage": 50,
            "ChangeMapImmediately": True,
            "EnabledInWarmup": False,
            "MinPlayers": 0,
            "MinRounds": 0,
            "Permission": "@css/vip"
        },
        "VoteExtend": {
            "Enabled": True,
            "EnablePanorama": True,
            "VoteDuration": 60,
            "VotePercentage": 50,
            "CooldownDuration": 180,
            "EnableCountdown": True,
            "CountdownType": "chat",
            "ChatCountdownInterval": 15,
            "Permission": "@css/vip"
        },
        "MapChooser": {
            "Command": "mapmenu,mm",
            "MenuType": "WasdMenu",
            "Permission": "@css/changemap"
        },
        "General": {
            "AdminPermission": "@css/root",
            "MaxMapExtensions": 2,
            "RoundTimeExtension": 15,
            "MapsInCoolDown": 0,
            "HideHudAfterVote": True,
            "RandomStartMap": False,
            "IncludeSpectator": True,
            "IncludeAFK": True,
            "AFKCheckInterval": 30,
            "EnableMapValidation": False,
            "SteamApiKey": "",
            "DiscordWebhook": ""
        }
    }
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(rockthevote_config, f, indent=2)
    
    print(f"Created RockTheVote config: {config_path}")


def generate_maplist_for_rockthevote(cs2_dir: str):
    """Generate/update maplist.txt for RockTheVote from Steam collection."""
    collection_id = "3587380938"  # ID коллекции KZ карт
    
    output_dir = os.path.join(cs2_dir, "game", "csgo", "addons", "counterstrikesharp", "plugins", "RockTheVote")
    maplist_path = os.path.join(output_dir, "maplist.txt")
    
    print(f"[Maplist] Generating/updating maplist from collection {collection_id}...")
    
    try:
        # Получаем актуальный список карт из коллекции
        ids = get_collection_item_ids(collection_id)
        
        if not ids:
            print("[Maplist] No items found in collection!")
            return
        
        items = get_published_file_details(ids)
        
        print(f"[Maplist] Processing {len(items)} maps from Steam...")
        
        # Создаем словарь с новыми картами
        new_maps = {}
        for item in items:
            title = item.get("title", "").strip()
            fid = item.get("publishedfileid", "")
            if title and fid:
                new_maps[fid] = f"{title}:{fid}"
        
        # Читаем существующий maplist.txt если есть
        existing_maps = {}
        existing_lines = []
        
        if os.path.exists(maplist_path):
            print(f"[Maplist] Reading existing maplist: {maplist_path}")
            with open(maplist_path, 'r', encoding='utf-8') as f:
                existing_lines = [line.strip() for line in f.readlines() if line.strip()]
            
            # Парсим существующие записи
            for line in existing_lines:
                if ':' in line:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        fid = parts[1]
                        existing_maps[fid] = line
                else:
                    # Обычные карты без workshop ID сохраняем как есть
                    existing_maps[line] = line
        
        # Объединяем существующие и новые карты
        merged_maps = existing_maps.copy()
        
        # Счетчики для статистики
        added_count = 0
        updated_count = 0
        
        for fid, line in new_maps.items():
            if fid not in existing_maps:
                merged_maps[fid] = line
                added_count += 1
                print(f"[Maplist] New map added: {line}")
            elif existing_maps[fid] != line:
                # Если название изменилось (маловероятно, но на всякий случай)
                merged_maps[fid] = line
                updated_count += 1
                print(f"[Maplist] Map updated: {line}")
        
        # Сортируем по названию
        sorted_maps = sorted(merged_maps.values())
        
        # Записываем обновленный файл
        os.makedirs(output_dir, exist_ok=True)
        with open(maplist_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(sorted_maps))
        
        print(f"[Maplist] Done! Statistics:")
        print(f"[Maplist]   - Total maps: {len(sorted_maps)}")
        print(f"[Maplist]   - Added: {added_count}")
        print(f"[Maplist]   - Updated: {updated_count}")
        print(f"[Maplist]   - Existing: {len(existing_maps) - updated_count}")
        print(f"[Maplist] Saved to: {maplist_path}")
        
    except Exception as e:
        print(f"[Maplist] Warning: Failed to generate maplist: {e}")
        # Создаём базовый maplist с дефолтными картами если вообще нет файла
        if not os.path.exists(maplist_path):
            print(f"[Maplist] Creating fallback maplist...")
            os.makedirs(output_dir, exist_ok=True)
            fallback_content = """de_nuke
kz_avalon:3583337319
kz_victoria:3086304337"""
            with open(maplist_path, 'w', encoding='utf-8') as f:
                f.write(fallback_content)
            print(f"[Maplist] Created fallback maplist: {maplist_path}")

def update_maplist(cs2_dir: str):
    """Отдельная функция для обновления maplist без переустановки всего"""
    collection_id = "3587380938"
    output_dir = os.path.join(cs2_dir, "game", "csgo", "addons", "counterstrikesharp", "plugins", "RockTheVote")
    
    print("=" * 50)
    print("Updating maplist.txt...")
    print("=" * 50)
    
    generate_maplist(collection_id, output_dir, update_mode=True)
    
    print("\nMaplist update complete!")

def download_cs2menumanager(cs2_dir: str):
    print(f"Downloading CS2MenuManager...")
    
    asset_url = "https://api.github.com/repos/schwarper/CS2MenuManager/releases/assets/349269061"
    extract_to = os.path.join(cs2_dir, "game", "csgo", "addons", "counterstrikesharp")
    
    try:
        download_asset_by_url(cs2_dir, asset_url, extract_to, "CS2MenuManager", "CS2MenuManager")
    except Exception as e:
        print(f"Warning: Failed to download CS2MenuManager: {e}")


def setup_asset_bin(cs2_dir: str):
    print(f"Setting up asset bin...")
    source = os.path.join(cs2_dir, "game", "csgo", "readonly_tools_asset_info.bin")
    target = os.path.join(cs2_dir, "game", "csgo", "addons", "metamod", "readonly_tools_asset_info.bin")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copyfile(source, target)


def setup_metamod_content_path(path: str):
    print('Creating necessary folder for hammer...')
    os.makedirs(os.path.join(path, 'content', 'csgo', 'addons', 'metamod'), exist_ok=True)


# =======================
# Main
# =======================

path = get_cs2_path()
if path is None:
    print("Failed to get CS2 path.")
    exit(1)

print(f"Setting up CS2KZ in {path}...")

download_and_extract_metamod(path)
download_cs2kz(path)

try:
    download_sql_mm(path)
except Exception as e:
    print(f"Warning: Failed to download sql_mm: {e}")

try:
    download_multiaddon_manager(path)
except Exception as e:
    print(f"Warning: Failed to download MultiAddonManager: {e}")

try:
    download_counterstrikesharp(path)
except Exception as e:
    print(f"Warning: Failed to download CounterStrikeSharp: {e}")

try:
    setup_rockthevote(path)
except Exception as e:
    print(f"Warning: Failed to setup RockTheVote: {e}")

try:
    download_cs2menumanager(path)
except Exception as e:
    print(f"Warning: Failed to download CS2MenuManager: {e}")

try:
    setup_asset_bin(path)
    setup_metamod_content_path(path)
except Exception as e:
    print(f"Warning: Failed to setup asset bin or content path: {e}")
    print("This might be because mapping tools are probably not installed.")

print("Setup complete, closing in 3 seconds...")
time.sleep(3)