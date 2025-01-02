import os
import re
import json
import shutil
import zipfile
import requests
import hashlib
import time
from urllib.parse import urlparse
import configparser
from typing import Dict, Any
from gui import start_gui
from config import load_config


# List of directories that should be extracted into the main modpack directory (not in /mods/)
non_mod_folders = [
    "forge", "asm", "bin", "cache", "config", "coremods", "customnpcs",
    "Illegal_Clients","journeymap", "logs", "resourcepacks", "resources",
    "saves", "schematics","screenshots", "scripts", "shaderpacks", "betterfps",
    "minetweaker", "options", "optionsof", "optionsshaders", "servers",
    "usernamecache", "settings"
]
non_mod_files = [item.lower() + "-zip" if item.lower() != "forge" else item.lower() for item in non_mod_folders]
# print(f"Non-mod files: {non_mod_files}")

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
        print(f"Error fetching modpack info: {response.status_code}")
        return None

def fetch_build_details(build_version):
    """Fetch build details (mod files) for the specified build version."""
    try:
        build_url = f"{SOLDER_API_URL}{MODPACK_NAME}/{build_version}?include=mods"
        response = requests.get(build_url)
        
        if response.status_code == 200:
            build_data = response.json()
            if 'error' in build_data and build_data['error'] == 'Build does not exist':
                print(f"Build {build_version} does not exist.")
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
            print(f"Error: Unable to fetch build details for version {build_version}.")
            return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

def fetch_mod_list(build_details):
    """Fetch the mod list from the build details."""
    mod_list = []
    for mod in build_details.get("mods", []):
        mod_list.append({
            "name": mod["name"],
            "pretty_name": mod.get("pretty_name", mod["name"]),
            "url": mod["url"],
            "md5": mod["md5"],
            "version": mod.get("version", "unknown"),  # Add version key with a default value
            "author": mod.get("author", "unknown"),
            "link": mod.get("link", "")
        })

    # # Print all mod names in one message
    # mod_names = [mod["name"] for mod in mod_list]
    # print("Mod names:", ", ".join(mod_names))

    return mod_list

def calculate_md5(file_path):
    """Calculate the MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def fetch_existing_mods(mods_folder_path):
    """Fetch existing mods and their MD5 hashes from the mods folder."""
    existing_mods = {}
    if os.path.exists(mods_folder_path):
        for filename in os.listdir(mods_folder_path):
            filepath = os.path.join(mods_folder_path, filename)
            if os.path.isfile(filepath):
                file_md5 = calculate_md5(filepath)
                existing_mods[filename] = file_md5
    return existing_mods

def compare_mods(existing_mods, mod_list, downloads_dir):
    """Compare existing mods+files with the mod list from Solder."""
    mods_to_download = []
    mods_to_remove = []
    up_to_date_count = 0

    for mod in mod_list:
        filename = sanitize_filename(mod['url'])
        file_path = os.path.join(downloads_dir, filename)
        
        # Skip Forge installer files
        if "forge-10-13-4-1614.zip" in filename.lower():
            continue

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

    for filename in existing_mods:
        if filename not in [sanitize_filename(mod['url']) for mod in mod_list]:
            mods_to_remove.append(filename)

    # Exclude Forge installer files from the total count
    total_mods = len([mod for mod in mod_list if "forge-10-13-4-1614.zip" not in sanitize_filename(mod['url']).lower()])

    print(f"{up_to_date_count}/{total_mods} files are up to date.")
    if mods_to_download:
        print(f"{len(mods_to_download)} files need to be downloaded:")
        for mod in mods_to_download:
            print(f"  - {sanitize_filename(mod['url'])}")

    return mods_to_download, mods_to_remove

def download_mods(mod_list, downloads_dir):
    """Download mods from the provided mod list."""
    total_mods = len(mod_list)
    downloaded_count = 0
    downloaded_files = []

    for i, mod in enumerate(mod_list, 1):
        mod_url = mod.get("url")
        expected_md5 = mod.get("md5")
        if mod_url and expected_md5:
            # Sanitize the filename to avoid issues with invalid characters
            filename = sanitize_filename(mod_url)
            file_path = os.path.join(downloads_dir, filename)

            # Skip Forge installer files
            if "forge-10-13-4-1614.zip" in filename.lower():
                continue

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
                print(f"Error downloading {mod_url}: {e}")
        else:
            print(f"Missing URL or MD5 for mod: {mod}")

    return downloaded_files

def extract_files(downloaded_files, minecraft_dir):
    """Extract special files (config.zip, resources.zip, etc.) into the main directory."""
    if not downloaded_files:
        print("No new files to extract.")
        return

    print(f"Extracting {len(downloaded_files)} files...")

    for file_path in downloaded_files:
        filename = os.path.basename(file_path)
        item = filename.replace(".zip", "").lower()

        if item in non_mod_files:
            print(f"Extracting {filename}...")
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                # Extract to the main directory for all files
                zip_ref.extractall(minecraft_dir)

    # Extract any zip files that might be inside the mods folder
    mod_zips = [f for f in downloaded_files if f.endswith(".zip")]
    total_mod_zips = len(mod_zips)
    extracted_count = 0

    for mod_zip in mod_zips:
        extracted_count += 1
        print(f"Extracting mod zip {extracted_count}/{total_mod_zips}: {mod_zip}")
        with zipfile.ZipFile(mod_zip, 'r') as zip_ref:
            # Extract to the main directory
            zip_ref.extractall(minecraft_dir)

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

@rate_limited(3)  # Limit to 3 requests per second
def fetch_mod_details(slug, use_backup=False):
    """Fetch mod details from the primary API using the mod slug."""
    primary_api_url = f"https://api.cfwidget.com/minecraft/mc-mods/{slug}"
    backup_api_url = f"https://www.cflookup.com/minecraft/mc-mods/{slug}.json"
    
    try:
        response = requests.get(backup_api_url if use_backup else primary_api_url)
        if response.status_code == 200:
            data = response.json()
            if use_backup:
                data = {
                    "id": data["id"],
                    "files": data["latestFilesIndexes"]
                }
            # Commenting out the print statements for response details
            # if slug in ["project-red-core", "project-red-illumination"]:
            #     print(f"Fetched details for {slug} from {'backup' if use_backup else 'primary'} API: {json.dumps(data, indent=2)}")
            return data, "backup" if use_backup else "primary"
        elif response.status_code == 404:
            # Only print error for 404 responses
            if not use_backup:  # Only print for primary API
                print(f"Error fetching mod details for slug: {slug} - Status Code: {response.status_code}")
    except requests.exceptions.RequestException:
        pass
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
        if mod_name in non_mod_files:
            # print(f"Excluding non-mod file: {mod_name}")
            continue

        total_mods += 1
        mod_link = mod.get("link")
        if mod_link and "curseforge.com" in mod_link:
            slug = extract_slug_from_url(mod_link)
            if slug:
                slugs[mod["name"]] = slug
        else:
            print(f"{mod['name']} isn't from CurseForge. Link: {mod_link}")

    print(f"Slugs extracted: {len(slugs)}/{total_mods}")
    return slugs

def find_closest_version(mod_version, available_versions):
    """Find the closest matching version from the available versions."""
    from difflib import get_close_matches
    closest_matches = get_close_matches(mod_version, available_versions, n=1, cutoff=0.1)
    return closest_matches[0] if closest_matches else None

def backup_check_mod_availability(slugs, mod_list, minecraft_version):
    """Check mod availability using the backup API."""
    available_mods = []
    unavailable_mods = []
    total_mods = 0

    for mod in mod_list:
        mod_name = mod["name"].lower()

        # Exclude non_mod_files and forge from the total mod counts
        if mod_name in non_mod_files:
            print(f"Excluding non-mod file: {mod_name}")
            continue

        total_mods += 1

        slug = slugs.get(mod["name"])

        # Skip slugs with "-zip" or "forge"
        if slug and ("-zip" in slug or slug == "forge"):
            continue

        if not slug:
            unavailable_mods.append(mod["name"])
            continue

        mod_details, api_source = fetch_mod_details(slug, use_backup=True)
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
                        available_mods.append(mod)
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
                    available_mods.append(mod)
                    found = True
                    print(f"Using closest matching version for {mod['name']}: {closest_version['filename']} (mod_version: {mod['version']}, minecraft_version: {minecraft_version}, selected file: {closest_version['filename']}, versions: {closest_version.get('gameVersions', [])})")
                if not found:
                    unavailable_mods.append(mod["name"])
                    print(f"No matching files found for {mod['name']} (slug: {slug}, version: {mod['version']})")
                    print(f"Checked files: {[file['filename'] for file in files]}")
                    print(f"File versions: {[file.get('gameVersions', []) for file in files]}")
        else:
            unavailable_mods.append(mod["name"])
            print(f"Mod details not found for {mod['name']} (slug: {slug})")

    return available_mods, unavailable_mods

def check_mod_availability(slugs, mod_list, minecraft_version):
    """Check if the mods are available on CurseForge by checking their slugs."""
    print("Checking mod availability...")
    available_mods = []
    unavailable_mods = []
    total_mods = 0

    for mod in mod_list:
        mod_name = mod["name"].lower()

        # Exclude non_mod_files and forge from the total mod counts
        if mod_name in non_mod_files:
            continue
        
        total_mods += 1
        slug = slugs.get(mod["name"])
        
        # Skip slugs with "-zip" or "forge"
        if slug and ("-zip" in slug or slug == "forge"):
            continue
        
        if not slug:
            unavailable_mods.append(mod["name"])
            continue
        
        # Now Redundant with the nearest version checks working correctly, left in code for reference if other special cases are needed.
        # # Special case for fpsplus-lagfixes (1.7.10 minecraft, no version name to check against)
        # if mod_name == "fps":
        #     mod["projectID"] = 66016  # Replace with the actual project ID
        #     mod["fileID"] = 2211275  # Replace with the actual file ID for 1.7.10
        #     available_mods.append(mod)
        #     print(f"Applied fallback for {mod['name']}")
        #     continue

        mod_details, api_source = fetch_mod_details(slug)
        
        if not mod_details:
            if api_source == "primary":
                unavailable_mods.append(mod["name"])
            continue

        project_id = mod_details.get("id")
        files = mod_details.get("files", [])

        found = False
        for file in files:
            file_versions = file["versions"]
            if isinstance(file_versions, list) and minecraft_version in file_versions:
                file_display_version = file["display"].strip().lower()
                file_name_version = file["name"].strip().lower()
                mod_version = mod["version"].strip().lower()

                if mod_version in file_display_version or mod_version in file_name_version:
                    mod["projectID"] = project_id
                    mod["fileID"] = file["id"]
                    available_mods.append(mod)
                    found = True
                    break

        if not found:
            # Try to find the closest matching version
            closest_version = None
            for file in files:
                file_versions = file["versions"]
                file_display_version = file["display"].strip().lower()
                file_name_version = file["name"].strip().lower()
                if mod_version in file_display_version or mod_version in file_name_version:
                    closest_version = file
                    break

            if not closest_version:
                for file in files:
                    file_versions = file["versions"]
                    if minecraft_version in file_versions:
                        closest_version = file
                        break

            if closest_version:
                mod["projectID"] = project_id
                mod["fileID"] = closest_version["id"]
                available_mods.append(mod)
                found = True
                print(f"Using closest matching version for {mod['name']}: {closest_version['display']} (mod_version: {mod['version']}, minecraft_version: {minecraft_version}, selected file: {closest_version['name']}, versions: {closest_version['versions']})")
            if not found:
                unavailable_mods.append(mod["name"])
                print(f"No matching files found for {mod['name']} (slug: {slug}, version: {mod['version']})")
                print(f"Checked files: {[file['name'] for file in files]}")
                print(f"File versions: {[file['versions'] for file in files]}")
    return available_mods, unavailable_mods

def generate_modlist_html(mod_list, output_path, available_mods):
    """Generate modlist.html file."""
    print("Generating modlist.html...")

    html_content = "<ul>\n"
    for mod in available_mods:
        html_content += f'    <li><a href="{mod["link"]}">{mod["pretty_name"]} (by {mod["author"]})</a></li>\n'
    html_content += "</ul>\n"

    with open(output_path, "w") as f:
        f.write(html_content)

def create_curseforge_structure(mod_list, modpack_dir, available_mods, minecraft_version, forge_version, downloads_dir, build_version):
    """Create the CurseForge file structure with the correct manifest."""
    print("Creating CurseForge structure...")
    curseforge_dir = os.path.join(modpack_dir, "curseforge")
    overrides_dir = os.path.join(curseforge_dir, "overrides")
    overrides_mods_dir = os.path.join(overrides_dir, "mods")

    # Clean up existing directories first
    if os.path.exists(curseforge_dir):
        shutil.rmtree(curseforge_dir)

    # Create necessary directories
    for directory in [curseforge_dir, overrides_dir, overrides_mods_dir]:
        os.makedirs(directory)

    # Handle non-mod folders (config, resources, etc.)
    for folder in non_mod_folders:
        folder_zip = folder.lower() + "-zip" if folder.lower() != "forge" else folder.lower()
        zip_path = None
        
        for mod in mod_list:
            if mod["name"].lower() == folder_zip:
                filename = sanitize_filename(mod["url"])
                zip_path = os.path.join(downloads_dir, filename)
                break
        
        if zip_path and os.path.exists(zip_path):
            print(f"Extracting {folder} to overrides...")
            try:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(overrides_dir)
            except Exception as e:
                print(f"Error extracting {folder}: {str(e)}")

    # Handle unavailable mods (copy to overrides/mods and extract if needed)
    available_mod_names = [mod["name"] for mod in available_mods]
    for mod in mod_list:
        if mod["name"] not in available_mod_names and mod["name"].lower() not in non_mod_files:
            filename = sanitize_filename(mod["url"])
            src_path = os.path.join(downloads_dir, filename)
            if os.path.exists(src_path):
                print(f"Processing override mod: {filename}")
                dst_path = os.path.join(overrides_mods_dir, filename)
                temp_extract_dir = os.path.join(overrides_mods_dir, "temp_extract_" + os.path.splitext(filename)[0])
                
                try:
                    # Extract to temporary directory first
                    if filename.lower().endswith('.zip'):
                        print(f"Extracting {filename} to temporary directory...")
                        os.makedirs(temp_extract_dir, exist_ok=True)
                        
                        with zipfile.ZipFile(src_path, 'r') as zip_ref:
                            zip_ref.extractall(temp_extract_dir)
                        
                        # Handle potential nested structure
                        nested_mods_dir = os.path.join(temp_extract_dir, "mods")
                        if os.path.exists(nested_mods_dir):
                            # Move contents from nested mods directory
                            for item in os.listdir(nested_mods_dir):
                                src = os.path.join(nested_mods_dir, item)
                                dst = os.path.join(overrides_mods_dir, item)
                                if os.path.exists(dst):
                                    if os.path.isdir(dst):
                                        shutil.rmtree(dst)
                                    else:
                                        os.remove(dst)
                                shutil.move(src, dst)
                        else:
                            # Move all contents if no nested mods directory
                            for item in os.listdir(temp_extract_dir):
                                src = os.path.join(temp_extract_dir, item)
                                dst = os.path.join(overrides_mods_dir, item)
                                if os.path.exists(dst):
                                    if os.path.isdir(dst):
                                        shutil.rmtree(dst)
                                    else:
                                        os.remove(dst)
                                shutil.move(src, dst)
                    else:
                        # Just copy non-zip files
                        shutil.copy2(src_path, dst_path)
                
                except Exception as e:
                    print(f"Error processing {filename}: {str(e)}")
                    continue
                
                finally:
                    # Clean up temporary directory
                    if os.path.exists(temp_extract_dir):
                        try:
                            shutil.rmtree(temp_extract_dir)
                        except Exception as e:
                            print(f"Error cleaning up temporary directory: {str(e)}")

    # Create manifest.json
    manifest = {
        "minecraft": {
            "version": minecraft_version,
            "modLoaders": [
                {
                    "id": f"forge-{forge_version}",
                    "primary": True
                }
            ]
        },
        "manifestType": "minecraftModpack",
        "manifestVersion": 1,
        "name": MODPACK_NAME,
        "version": build_version,
        "author": "Wargames",
        "files": [],
        "overrides": "overrides"
    }

    # Add available mods to manifest
    for mod in available_mods:
        project_id = mod.get("projectID")
        file_id = mod.get("fileID")
        if project_id and file_id:
            manifest["files"].append({
                "projectID": project_id,
                "fileID": file_id,
                "required": True
            })

    # Write manifest.json
    manifest_path = os.path.join(curseforge_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Generate modlist.html
    generate_modlist_html(mod_list, os.path.join(curseforge_dir, "modlist.html"), available_mods)

def zip_curseforge_modpack(modpack_dir, modpack_name, build_version):
    """Zip the CurseForge directory into a modpack file."""
    print("Zipping CurseForge modpack...")
    curseforge_dir = os.path.join(modpack_dir, "curseforge")
    modpack_zip = os.path.join(modpack_dir, f"{modpack_name}-{build_version}.zip")

    shutil.make_archive(modpack_zip.replace('.zip', ''), 'zip', curseforge_dir)
    print(f"Modpack zipped successfully at {modpack_zip}")

def sort_mod_list(mod_list):
    """Sort the mod list with non-mod files first and mods in alphabetical order."""
    non_mod_files_sorted = []
    mods_sorted = []

    # Extract non-mod files and sort them based on the order in non_mod_folders
    for folder in non_mod_folders:
        non_mod_file = folder.lower() + "-zip" if folder.lower() != "forge" else folder.lower()
        for mod in mod_list:
            if mod["name"].lower() == non_mod_file:
                non_mod_files_sorted.append(mod)
                break

    # Extract and sort the remaining mods alphabetically
    mods_sorted = sorted(
        [mod for mod in mod_list if mod["name"].lower() not in non_mod_files],
        key=lambda x: x["name"].lower()
    )

    # Combine the sorted non-mod files and mods
    sorted_mod_list = non_mod_files_sorted + mods_sorted
    return sorted_mod_list

def main():
    """Main function to handle modpack download and CurseForge packaging."""
    # Load configuration
    config = load_config()
    
    # If config is None, exit the script
    if config is None:
        return
    
    # Update global variables with config values
    global SOLDER_API_URL, MODPACK_NAME
    SOLDER_API_URL = config['SOLDER_API_URL']
    MODPACK_NAME = config['MODPACK_NAME']
    builds_dir = config['BUILDS_DIR']
    
    print(f"Fetching available builds for {MODPACK_NAME}...")
    
    # 1. Fetch modpack info and build details
    modpack_info = fetch_modpack_info()
    if not modpack_info:
        print("Failed to fetch modpack info.")
        return

    build_version = config['BUILD_VERSION']
    if build_version.lower() == 'latest':
        build_version = modpack_info.get("recommended", "")
    
    # Create modpack-specific directory structure
    modpack_dir = os.path.join(builds_dir, f"{MODPACK_NAME}-{build_version}")
    if not os.path.exists(modpack_dir):
        os.makedirs(modpack_dir)
    
    # Update paths for this specific modpack version
    downloads_dir = os.path.join(modpack_dir, "Downloads")
    minecraft_dir = os.path.join(modpack_dir, "minecraft")
    curseforge_dir = os.path.join(modpack_dir, "curseforge")
    
    # Create necessary directories
    for directory in [downloads_dir, minecraft_dir, curseforge_dir]:
        if not os.path.exists(directory):
            os.makedirs(directory)

if __name__ == "__main__":
    from gui import start_gui
    start_gui(main)