import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog
from config import load_config

def load_config_gui():
    """Load configuration from config.ini file using GUI."""
    config = load_config()
    if config is None:
        messagebox.showerror("Error", "Please fill in the required information in config.ini and run the script again.")
    return config

def start_update(main_func):
    """Start the modpack update process."""
    config = load_config_gui()
    if config:
        main_func()

def select_directory(entry):
    """Open a dialog to select the builds directory."""
    directory = filedialog.askdirectory()
    if directory:
        entry.delete(0, tk.END)
        entry.insert(0, directory)

def start_gui(main_func):
    # Create the main window
    root = tk.Tk()
    root.title("Modpack Auto-Updater")

    # Create and place widgets
    tk.Label(root, text="Solder API URL:").grid(row=0, column=0, sticky=tk.W)
    solder_api_url_entry = tk.Entry(root, width=50)
    solder_api_url_entry.grid(row=0, column=1)

    tk.Label(root, text="Modpack Name:").grid(row=1, column=0, sticky=tk.W)
    modpack_name_entry = tk.Entry(root, width=50)
    modpack_name_entry.grid(row=1, column=1)

    tk.Label(root, text="Build Version:").grid(row=2, column=0, sticky=tk.W)
    build_version_entry = tk.Entry(root, width=50)
    build_version_entry.grid(row=2, column=1)

    tk.Label(root, text="Builds Directory:").grid(row=3, column=0, sticky=tk.W)
    builds_dir_entry = tk.Entry(root, width=50)
    builds_dir_entry.grid(row=3, column=1)
    tk.Button(root, text="Browse...", command=lambda: select_directory(builds_dir_entry)).grid(row=3, column=2)

    tk.Button(root, text="Start Update", command=lambda: start_update(main_func)).grid(row=4, column=1, pady=10)

    # Load initial config values
    config = load_config()
    if config:
        solder_api_url_entry.insert(0, config['SOLDER_API_URL'])
        modpack_name_entry.insert(0, config['MODPACK_NAME'])
        build_version_entry.insert(0, config['BUILD_VERSION'])
        builds_dir_entry.insert(0, config['BUILDS_DIR'])

    # Start the main event loop
    root.mainloop()

if __name__ == "__main__":
    from main import main
    start_gui(main)