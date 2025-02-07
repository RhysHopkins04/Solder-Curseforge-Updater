import os
import re
import json
import shutil
import zipfile
import requests
import hashlib
import time
import traceback
from urllib.parse import urlparse
from config import load_config

def sanitize_filename(url):
    """Sanitize the filename to avoid issues with invalid characters."""
    filename = os.path.basename(url)
    filename = filename.split('?')[0]  # Remove query parameters
    return re.sub(r'[<>:"/\\|?*]', '_', filename)

def fetch_modpack_info():
    """Fetch modpack information from the Solder API."""
    url = f"{SOLDER_API_URL}{MODPACK_NAME}/"
    response = requests.get(url)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"[ERROR 011]: Error fetching modpack info: {response.status_code}")
        return None

def fetch_build_details(build_version):
    """Fetch build details (mod files) for the specified build version."""
    try:
        if build_version.lower() == "latest":
            modpack_info = fetch_modpack_info()
            if not modpack_info:
                print("[ERROR 011]: Error fetching modpack information.")
                return None
            build_version = modpack_info.get("recommended", "")
            if not build_version:
                print("[ERROR 012]: No recommended build found for the modpack.")
                return None

        build_url = f"{SOLDER_API_URL}{MODPACK_NAME}/{build_version}?include=mods"
        response = requests.get(build_url)
        
        if response.status_code == 200:
            build_data = response.json()
            if 'error' in build_data and build_data['error'] == 'Build does not exist':
                print(f"[ERROR 012]: Build {build_version} does not exist.")
                return None  # Return None if the build doesn't exist
            else:
                # Extract Forge version from the mods list
                forge_version = None
                for mod in build_data.get("mods", []):
                    if mod["name"].lower() == "forge":
                        forge_version = mod["version"]
                        break
                build_data["forge_version"] = forge_version
                return build_data
        else:
            print(f"[ERROR 012]: Unable to fetch build details for version {build_version}.")
            return None
    except Exception as e:
        print(f"[ERROR 012]: An error occurred: {e}")
        return None

def fetch_mod_list(build_details):
    """Fetch the mod list from the build details."""
    mod_list = []
    non_mod_list = []
    forge_list = []

    for mod in build_details.get("mods", []):
        mod_name = mod["name"].lower()
        mod_url = mod["url"].lower()

        if "forges" in mod_url:
            forge_list.append(mod)
        elif "others" in mod_url:
            non_mod_list.append(mod)
        else:
            mod_list.append({
                "name": mod["name"],
                "pretty_name": mod.get("pretty_name", mod["name"]),
                "url": mod["url"],
                "md5": mod["md5"],
                "version": mod.get("version", "unknown"),
                "author": mod.get("author", "unknown"),
                "link": mod.get("link", "")
            })

    return mod_list, non_mod_list, forge_list

def calculate_md5(file_path):
    """Calculate the MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"[ERROR 014]: Error calculating MD5 hash of file {file_path}: {e}")
        return None

def fetch_existing_mods(mods_folder_path):
    """Fetch existing mods and their MD5 hashes from the mods folder."""
    existing_mods = {}
    try:
        if os.path.exists(mods_folder_path):
            for filename in os.listdir(mods_folder_path):
                filepath = os.path.join(mods_folder_path, filename)
                if os.path.isfile(filepath):
                    file_md5 = calculate_md5(filepath)
                    existing_mods[filename] = file_md5
        return existing_mods
    except Exception as e:
        print(f"[ERROR 015]: Error fetching existing mods from {mods_folder_path}: {e}")
        return None

def compare_mods(existing_mods, mod_list, non_mod_list, downloads_dir):
    mods_to_download = []
    mods_to_remove = []
    up_to_date_count = 0
    invalid_files_removed = 0

    try:
        # First, check and remove any invalid files
        for filename in os.listdir(downloads_dir):
            file_path = os.path.join(downloads_dir, filename)
            is_valid = False
            for mod in mod_list + non_mod_list:
                if filename == sanitize_filename(mod['url']):
                    if calculate_md5(file_path) == mod['md5']:
                        is_valid = True
                        break
            
            if not is_valid:
                print(f"Removing invalid file: {filename}")
                os.remove(file_path)
                invalid_files_removed += 1

        if invalid_files_removed > 0:
            print(f"Cleaned up {invalid_files_removed} invalid or outdated files.")
        else:
            print("No invalid files found in Downloads directory.")

        # Then proceed with normal comparison
        for mod in mod_list + non_mod_list:
            filename = sanitize_filename(mod['url'])
            file_path = os.path.join(downloads_dir, filename)

            # Check if the .zip file exists and has the correct MD5 hash
            if os.path.exists(file_path):
                file_md5 = calculate_md5(file_path)
                if file_md5 != mod['md5']:
                    print(f"MD5 mismatch for {filename}: expected {mod['md5']}, got {file_md5}")
                    mods_to_download.append(mod)
                else:
                    up_to_date_count += 1
            else:
                mods_to_download.append(mod)

        # Calculate mods to remove
        for filename in existing_mods:
            if filename not in [sanitize_filename(mod['url']) for mod in mod_list + non_mod_list]:
                mods_to_remove.append(filename)

        total_mods = len(mod_list + non_mod_list)

        print(f"{up_to_date_count}/{total_mods} files are up to date.")
        if mods_to_download:
            print(f"{len(mods_to_download)} files need to be downloaded:")
            for mod in mods_to_download:
                print(f"  - {sanitize_filename(mod['url'])}")

        return mods_to_download, mods_to_remove
    except Exception as e:
        print(f"[ERROR 016]: Error comparing mods: {e}")
        return None, None

def download_mods(mod_list, downloads_dir):
    """Download mods from the provided mod list."""
    if not mod_list:
        return []  # Return empty list for no mods to download
        
    total_mods = len(mod_list)
    downloaded_count = 0
    downloaded_files = []

    try:
        # Ensure the downloads directory exists
        os.makedirs(downloads_dir, exist_ok=True)

        for i, mod in enumerate(mod_list, 1):
            mod_url = mod.get("url")
            expected_md5 = mod.get("md5")
            if mod_url and expected_md5:
                # Sanitize the filename to avoid issues with invalid characters
                filename = sanitize_filename(mod_url)
                file_path = os.path.join(downloads_dir, filename)

                # Check if the .zip file already exists and has the correct MD5 hash
                if os.path.exists(file_path):
                    existing_md5 = calculate_md5(file_path)
                    if existing_md5 == expected_md5:
                        continue  # Skip download if MD5 matches

                # Download the file
                try:
                    downloaded_count += 1
                    print(f"Downloading {downloaded_count}/{total_mods}: {mod_url}")
                    response = requests.get(mod_url, stream=True)
                    response.raise_for_status()  # Raise an exception for HTTP errors

                    with open(file_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)

                    # Verify the downloaded file's MD5 hash
                    downloaded_md5 = calculate_md5(file_path)
                    if downloaded_md5 != expected_md5:
                        print(f"MD5 mismatch for {filename}, expected {expected_md5}, got {downloaded_md5}")
                        os.remove(file_path)
                    else:
                        downloaded_files.append(file_path)
                except requests.exceptions.RequestException as e:
                    print(f"[ERROR 017]: Error downloading {mod_url}: {e}")
            else:
                print(f"[ERROR 017]: Missing URL or MD5 for mod: {mod}")

        return downloaded_files
    except Exception as e:
        print(f"[ERROR 017]: Error downloading mods: {e}")
        return None  # Return None for actual errors

def extract_files(downloaded_files, minecraft_dir, overrides_dir, is_mod=True):
    if not downloaded_files:
        print("No new files to extract.")
        return

    print(f"Extracting {len(downloaded_files)} files...")

    try:
        for file_path in downloaded_files:
            filename = os.path.basename(file_path)
            item = filename.replace(".zip", "").lower()

            if is_mod:
                print(f"Extracting {filename} to minecraft/mods...")
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    mods_dir = os.path.join(minecraft_dir, "mods")
                    os.makedirs(mods_dir, exist_ok=True)
                    for member in zip_ref.namelist():
                        if member.startswith("mods/"):
                            zip_ref.extract(member, minecraft_dir)
                        else:
                            zip_ref.extract(member, mods_dir)
            else:
                print(f"Extracting {filename} to minecraft...")
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    os.makedirs(minecraft_dir, exist_ok=True)
                    zip_ref.extractall(minecraft_dir)
    except Exception as e:
        print(f"[ERROR 018]: Error extracting files: {e}")

def rate_limited(max_per_second):
    """Decorator to limit the number of requests per second."""
    min_interval = 1.0 / max_per_second
    def decorator(func):
        last_called = [0.0]
        def rate_limited_function(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            left_to_wait = min_interval - elapsed
            if left_to_wait > 0:
                time.sleep(left_to_wait)
            ret = func(*args, **kwargs)
            last_called[0] = time.time()
            return ret
        return rate_limited_function
    return decorator

@rate_limited(5)  # Limit to 5 requests per second
def fetch_mod_details(slug, use_backup=False):
    """Fetch mod details from the primary API using the mod slug."""
    primary_api_url = f"https://api.cfwidget.com/minecraft/mc-mods/{slug}"
    backup_api_url = f"https://www.cflookup.com/minecraft/mc-mods/{slug}.json"
    
    try:
        response = requests.get(backup_api_url if use_backup else primary_api_url)
        if response.status_code == 200:
            data = response.json()
            if use_backup:
                # Transform backup API response to match primary API structure
                data = {
                    "id": data["id"],
                    "files": [{
                        "gameVersions": [file["gameVersion"]],
                        "filename": file.get("name", ""),  # Add filename if available
                        "fileId": file["fileId"]
                    } for file in data["latestFilesIndexes"]]
                }
            return data, "backup" if use_backup else "primary"
        elif response.status_code == 404:
            if use_backup:
                return False, "error"  # Special error return value
            else:
                print(f"[ERROR 021]: Primary API check failed for {slug} - Status Code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching mod details for slug: {slug} - Exception: {e}")
    return None, "backup" if use_backup else "primary"

def extract_slug_from_url(url):
    """Extract the mod slug from the CurseForge URL."""
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.split('/')
    if len(path_parts) > 2 and path_parts[1] == "minecraft" and path_parts[2] == "mc-mods":
        return path_parts[3]
    elif len(path_parts) > 1 and path_parts[1] == "projects":
        return path_parts[2]
    return None

def extract_slugs_from_mod_list(mod_list):
    """Extract slugs from the mod list."""
    print("Extracting slugs from URLs...")
    slugs = {}
    total_mods = 0

    for mod in mod_list:
        mod_name = mod["name"].lower()
        mod_link = mod.get("link")

        total_mods += 1
        if mod_link and "curseforge.com" in mod_link:
            slug = extract_slug_from_url(mod_link)
            if slug:
                slugs[mod["name"]] = slug
            else:
                print(f"[ERROR 019] Could not extract slug for {mod['name']} from link: {mod_link}")
        else:
            print(f"[ERROR 020] {mod['name']} isn't from CurseForge. Link: {mod_link}. Ensure the license allows redistribution.")

    print(f"Slugs extracted: {len(slugs)}/{total_mods}")
    return slugs

def find_closest_version(mod_version, available_versions):
    """Find the closest matching version from the available versions."""
    from difflib import get_close_matches
    closest_matches = get_close_matches(mod_version, available_versions, n=1, cutoff=0.1)
    return closest_matches[0] if closest_matches else None

def backup_check_mod_availability(slugs, unavailable_mods, minecraft_version):
    """Check mod availability using the backup API."""
    still_unavailable = []
    backup_available = []

    for mod in unavailable_mods:
        mod_name = mod["name"].lower()
        
        slug = slugs.get(mod["name"])  # Use mod object structure
        if not slug:
            still_unavailable.append(mod)  # Store full mod object
            continue

        mod_details, api_source = fetch_mod_details(slug, use_backup=True)
        if api_source == "error":  # Check for critical error
            print(f"[ERROR 022]: {slug} has failed to be found on CurseForge. Ensure your link is correct and version {mod['version']} exists.")
            return False, False  # Special error return value

        if mod_details and api_source == "backup":
            project_id = mod_details.get("id")
            files = mod_details.get("files", [])

            found = False
            mod_version = mod["version"].strip().lower()  # Define mod_version here
            for file in files:
                file_versions = file.get("gameVersions", [])
                if isinstance(file_versions, list) and minecraft_version in file_versions:
                    file_name_version = file["filename"].strip().lower()

                    if mod_version in file_name_version:
                        mod["projectID"] = project_id
                        mod["fileID"] = file["fileId"]
                        backup_available.append(mod)
                        found = True
                        break

            if not found:
                # Try to find the closest matching version
                closest_version = None
                for file in files:
                    file_name_version = file["filename"].strip().lower()
                    if mod_version in file_name_version:
                        closest_version = file
                        break

                if not closest_version:
                    for file in files:
                        file_versions = file.get("gameVersions", [])
                        if minecraft_version in file_versions:
                            closest_version = file
                            break

                if closest_version:
                    mod["projectID"] = project_id
                    mod["fileID"] = closest_version["fileId"]
                    backup_available.append(mod)
                    found = True
                    print(f"[ERROR 023] Using closest matching version for {mod['name']}: {closest_version['filename']} (mod_version: {mod['version']}, minecraft_version: {minecraft_version}, selected file: {closest_version['filename']}, versions: {closest_version.get('gameVersions', [])}) Please ensure Compatibility before distribution.")
                if not found:
                    still_unavailable.append(mod)
                    print(f"[ERROR 022] No matching files found for {mod['name']} (slug: {slug}, version: {mod['version']})")
                    return False, False  # Special error return value
                    # print(f"Checked files: {[file['filename'] for file in files]}")
                    # print(f"File versions: {[file.get('gameVersions', []) for file in files]}")
        else:
            still_unavailable.append(mod)
            print(f"[ERROR 022]: Mod details not found for {mod['name']} (slug: {slug})")
            return False, False  # Special error return value

    return backup_available, still_unavailable

def check_mod_availability(slugs, mod_list, minecraft_version):
    """Check if the mods are available on CurseForge by checking their slugs."""
    print("Checking mod availability...")
    available_mods = []
    unavailable_mods = []
    total_mods = 0

    for mod in mod_list:
        mod_name = mod["name"].lower()
        
        total_mods += 1
        slug = slugs.get(mod["name"])
        
        if not slug:
            unavailable_mods.append(mod)  # Store full mod object
            continue

        mod_details, api_source = fetch_mod_details(slug, use_backup=False)
        if not mod_details:
            unavailable_mods.append(mod)  # Store full mod object
            continue

        try:
            project_id = mod_details.get("id")
            files = mod_details.get("files", [])
            found = False
            mod_version = mod["version"].strip().lower()

            # Only try find an exact match for the mod version
            for file in files:
                if isinstance(file, dict):
                    game_versions = file.get("gameVersions", []) or file.get("versions", [])
                    file_name = (file.get("filename") or file.get("name", "")).strip().lower()
                    file_id = file.get("fileId") or file.get("id")
                    
                    if minecraft_version in game_versions:
                        if mod_version in file_name:
                            mod["projectID"] = project_id
                            mod["fileID"] = file_id
                            available_mods.append(mod)
                            found = True
                            break
            
            if not found:
                unavailable_mods.append(mod)
                print(f"[ERROR 021]: Primary API check failed for {mod['name']} - Status Code: Unable to find")
            
        except Exception as e:
            print(f"[ERROR ***]: Error processing mod {mod['name']}: {str(e)}")
            return None, None

    return available_mods, unavailable_mods

def generate_modlist_html(mod_list, output_path, available_mods):
    """Generate modlist.html file."""
    print("Generating modlist.html...")
    
    html_content = "<ul>\n"
    for mod in available_mods:
        html_content += f"<li>{mod['pretty_name']} (v{mod['version']}) - {mod['author']}</li>\n"
    html_content += "</ul>\n"

    with open(output_path, "w") as f:
        f.write(html_content)

def create_curseforge_structure(mod_list, non_mod_list, downloads_dir, overrides_dir, available_mods, minecraft_version):
    print("Creating CurseForge modpack structure...")

    # Create necessary directories
    os.makedirs(overrides_dir, exist_ok=True)
    os.makedirs(os.path.join(overrides_dir, "mods"), exist_ok=True)

    # Copy non-mod files to the overrides directory
    for mod in non_mod_list:
        filename = sanitize_filename(mod["url"])
        src_path = os.path.join(downloads_dir, filename)
        dest_path = os.path.join(overrides_dir, filename)
        print(f"Copying {filename} to overrides...")
        shutil.copy(src_path, dest_path)
        with zipfile.ZipFile(dest_path, 'r') as zip_ref:
            zip_ref.extractall(overrides_dir)
        os.remove(dest_path)

    # Extract unavailable mods to the overrides/mods directory
    for mod in mod_list:
        if mod not in available_mods:
            filename = sanitize_filename(mod["url"])
            src_path = os.path.join(downloads_dir, filename)
            dest_path = os.path.join(overrides_dir, "mods")
            print(f"Extracting {filename} to overrides/mods...")
            with zipfile.ZipFile(src_path, 'r') as zip_ref:
                for member in zip_ref.namelist():
                    if member.startswith("mods/"):
                        zip_ref.extract(member, overrides_dir)
                    else:
                        zip_ref.extract(member, dest_path)

    # Create manifest.json
    manifest = {
        "minecraft": {
            "version": minecraft_version,
            "modLoaders": [
                {
                    "id": "forge",
                    "primary": True
                }
            ]
        },
        "manifestType": "minecraftModpack",
        "manifestVersion": 1,
        "name": MODPACK_NAME,
        "version": BUILD_VERSION,
        "author": "Unknown",
        "files": [
            {
                "projectID": mod["projectID"],
                "fileID": mod["fileID"],
                "required": True
            }
            for mod in available_mods if "projectID" in mod and "fileID" in mod
        ],
        "overrides": "overrides"
    }

    with open(os.path.join(os.path.dirname(overrides_dir), "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=4)

    # Generate modlist.html
    generate_modlist_html(mod_list, os.path.join(os.path.dirname(overrides_dir), "modlist.html"), available_mods)

def zip_curseforge_modpack(curseforge_dir):
    """Zip the CurseForge modpack."""
    print("Zipping CurseForge modpack...")
    
    # Get the parent directory (modpack directory)
    modpack_dir = os.path.dirname(curseforge_dir)
    
    # Create zip in the modpack directory
    zip_filename = os.path.join(modpack_dir, f"{MODPACK_NAME}-{BUILD_VERSION}.zip")
    
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(curseforge_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, curseforge_dir)
                zipf.write(file_path, arcname)

def sort_mod_list(mod_list):
    """Sort the mod list alphabetically by mod name."""
    return sorted(mod_list, key=lambda mod: mod["name"].lower())

def main():
    config = load_config()
    if not config['SOLDER_API_URL'] or not config['MODPACK_NAME']:
        print("[ERROR 001]: Error please fill the required boxes with information.")
        return

    global SOLDER_API_URL, MODPACK_NAME, BUILD_VERSION, BUILDS_DIR
    SOLDER_API_URL = config['SOLDER_API_URL']
    MODPACK_NAME = config['MODPACK_NAME']
    BUILD_VERSION = config['BUILD_VERSION']
    BUILDS_DIR = config['BUILDS_DIR']

    if BUILD_VERSION.lower() == "latest":
        modpack_info = fetch_modpack_info()
        if not modpack_info:
            print("[ERROR 011]: Error fetching modpack information.")
            return
        BUILD_VERSION = modpack_info.get("recommended", "")
        if not BUILD_VERSION:
            print("[ERROR 012]: No recommended build found for the modpack.")
            return

    versioned_name = f"{MODPACK_NAME}-{BUILD_VERSION}"
    modpack_dir = os.path.join(BUILDS_DIR, versioned_name)
    downloads_dir = os.path.join(modpack_dir, "Downloads")
    minecraft_dir = os.path.join(modpack_dir, "minecraft")
    curseforge_dir = os.path.join(modpack_dir, "curseforge")
    overrides_dir = os.path.join(curseforge_dir, "overrides")

    if os.path.exists(modpack_dir):
        for item in os.listdir(modpack_dir):
            item_path = os.path.join(modpack_dir, item)
            if item != "Downloads":
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)

    os.makedirs(downloads_dir, exist_ok=True)
    os.makedirs(minecraft_dir)
    os.makedirs(curseforge_dir)
    os.makedirs(overrides_dir)

    print(f"Starting modpack update process for {versioned_name}...")

    modpack_info = fetch_modpack_info()
    if not modpack_info:
        print("[ERROR 011]: Error fetching modpack information.")
        return

    build_details = fetch_build_details(BUILD_VERSION)
    if not build_details:
        print("[ERROR 012]: Error fetching build details.")
        return

    mod_list, non_mod_list, forge_list = fetch_mod_list(build_details)
    if not mod_list:
        print("[ERROR 013]: Error fetching mod list.")
        return

    existing_mods = fetch_existing_mods(downloads_dir)
    if existing_mods is None:
        print("[ERROR 015]: Error fetching existing mods.")
        return

    mods_to_download, mods_to_remove = compare_mods(existing_mods, mod_list, non_mod_list, downloads_dir)
    if mods_to_download is None or mods_to_remove is None:
        print("[ERROR 016]: Error comparing mods.")
        return

    if mods_to_download:
        downloaded_files = download_mods(mods_to_download, downloads_dir)
        if downloaded_files is None:
            print("[ERROR 017]: Error downloading mods.")
            return

    all_files = [os.path.join(downloads_dir, sanitize_filename(mod['url'])) 
                 for mod in mod_list 
                 if os.path.exists(os.path.join(downloads_dir, sanitize_filename(mod['url'])))]
    
    if not all_files:
        print("[ERROR 017]: No files found in Downloads directory.")
        return
    
    print(f"Extracting all {len(all_files)} files from Downloads directory...")
    extract_files(all_files, minecraft_dir, overrides_dir, is_mod=True)

    non_mod_files = [os.path.join(downloads_dir, sanitize_filename(mod['url'])) 
                     for mod in non_mod_list 
                     if os.path.exists(os.path.join(downloads_dir, sanitize_filename(mod['url'])))]
    
    if non_mod_files:
        print(f"Extracting all {len(non_mod_files)} non-mod files from Downloads directory...")
        extract_files(non_mod_files, minecraft_dir, overrides_dir, is_mod=False)

    try:
        minecraft_version = build_details["minecraft"].get("version") if isinstance(build_details["minecraft"], dict) else build_details["minecraft"]
        if not minecraft_version:
            minecraft_version = "1.7.10"

        slugs = extract_slugs_from_mod_list(mod_list)
        available_mods, unavailable_mods = check_mod_availability(slugs, mod_list, minecraft_version)

        if unavailable_mods:
            print("\nAttempting backup API check for unavailable mods...")
            backup_available, still_unavailable = backup_check_mod_availability(slugs, unavailable_mods, minecraft_version)
            if backup_available is False and still_unavailable is False:
                return
            available_mods.extend(backup_available)
            unavailable_mods = still_unavailable

        total_mods = len(mod_list)
        print(f"\nFound {len(available_mods)}/{total_mods} mods on CurseForge")

        if unavailable_mods:
            print("\nSome mods are unavailable:")
            for mod in unavailable_mods:
                print(f"  - {mod['name']}")

        if not available_mods and unavailable_mods:
            print("[ERROR 021]: No mods could be found through either API, Please ensure the modpack contains mods...")
            return

        try:
            generate_modlist_html(mod_list, os.path.join(curseforge_dir, "modlist.html"), available_mods)
            create_curseforge_structure(mod_list, non_mod_list, downloads_dir, overrides_dir, available_mods, minecraft_version)
            zip_curseforge_modpack(overrides_dir)

            print("Modpack update process completed.")
        except Exception as e:
            print(f"[ERROR ***]: Program fault - please report to developer: {str(e)}\n\nStacktrace:\n{traceback.format_exc()}")
            return
    except Exception as e:
        print(f"[ERROR ***]: Program fault - please report to developer: {str(e)}\n\nStacktrace:\n{traceback.format_exc()}")
        return

if __name__ == "__main__":
    main()