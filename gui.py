import customtkinter as ctk
from tkinter import messagebox, filedialog
from config import load_config, save_config
import main as main_module
import threading
import queue
import sys

class ThreadSafeConsole:
    def __init__(self, textbox, queue):
        self.textbox = textbox
        self.queue = queue

    def write(self, message):
        self.queue.put(message)

    def flush(self):
        pass

def process_console_queue(console_output, message_queue, root):
    """Process messages in the queue and update the console"""
    try:
        while True:
            message = message_queue.get_nowait()
            console_output.insert(ctk.END, message)
            console_output.see(ctk.END)
            root.update_idletasks()
    except queue.Empty:
        root.after(100, process_console_queue, console_output, message_queue, root)

def run_update_process(entries, console_output, start_button, stop_button, message_queue, update_running):
    """Run the update process in a separate thread"""
    try:
        # Update config with GUI values
        config = load_config()
        if config:
            # Convert entries to strings before saving to config
            config['SOLDER_API_URL'] = str(entries['solder_api_url'].get())
            config['MODPACK_NAME'] = str(entries['modpack_name'].get())
            config['BUILD_VERSION'] = str(entries['build_version'].get())
            config['AUTHOR'] = str(entries['author'].get())
            config['BUILDS_DIR'] = str(entries['builds_dir'].get())
            
            save_config(config)
            
            try:
                # Run the main update function with update_running flag
                main_module.main(update_running)
            except Exception as e:
                if str(e).startswith("[ERROR"):
                    messagebox.showerror(str(e).split(":")[0], str(e))
                else:
                    error_message = f"Error in update process: {str(e)}"
                    messagebox.showerror("[ERROR 007]:", error_message)
                print(error_message)
    finally:
        # Re-enable start button and hide stop button
        start_button.configure(state="normal")
        stop_button.grid_remove()

def start_update(entries, console_output, start_button, stop_button, root, update_running):
    """Start the modpack update process."""
    # Clear the console output
    console_output.delete(1.0, ctk.END)
    
    # Disable the start button and show stop button while updating
    start_button.configure(state="disabled")
    stop_button.grid()  # Show the stop button
    
    # Set the update running flag
    update_running.set()
    
    # Create a queue for thread-safe console output
    message_queue = queue.Queue()
    
    # Redirect stdout and stderr to the thread-safe console
    sys.stdout = ThreadSafeConsole(console_output, message_queue)
    sys.stderr = ThreadSafeConsole(console_output, message_queue)
    
    # Start processing the console queue
    process_console_queue(console_output, message_queue, root)
    
    # Start the update process in a separate thread
    update_thread = threading.Thread(
        target=run_update_process,
        args=(entries, console_output, start_button, stop_button, message_queue, update_running)
    )
    update_thread.daemon = True
    update_thread.start()

def stop_update(stop_button, update_running):
    """Handle stopping the update process"""
    if messagebox.askyesno("Stop Update", "Are you sure you want to stop the current update?\nThis will cancel the operation."):
        update_running.clear()
        stop_button.grid_remove()  # Hide the stop button

def select_directory(entry):
    """Open a dialog to select the builds directory."""
    directory = filedialog.askdirectory()
    if directory:
        entry.delete(0, ctk.END)
        entry.insert(0, directory)

# def on_closing(root, update_running=False):
#     """Handle window closing event"""
#     if update_running:
#         if messagebox.askyesno("Quit", "An update is in progress. Are you sure you want to quit?\nThis will cancel the current operation."):
#             root.destroy()
#     else:
#         root.destroy()

def start_gui(main_func):
    try:
        # Create the main window
        root = ctk.CTk()
        root.title("Modpack Auto-Updater")
        root.geometry("720x600")
        
        # Variable to track if update is running
        update_running = threading.Event()

        def handle_close():
            if update_running.is_set():
                if messagebox.askyesno("Quit", "An update is in progress. Are you sure you want to quit?\nThis will cancel the current operation."):
                    root.destroy()
            else:
                root.destroy()

        # Bind the closing protocol directly
        root.protocol("WM_DELETE_WINDOW", handle_close)

        # Configure grid layout
        root.grid_columnconfigure(1, weight=1)
        root.grid_columnconfigure(2, weight=0)
        root.grid_rowconfigure(6, weight=1)

        # Create and place widgets with adjusted sizes and padding
        ctk.CTkLabel(root, text="Solder API URL:").grid(row=0, column=0, sticky=ctk.W, padx=10, pady=(10,5))
        solder_api_url_entry = ctk.CTkEntry(root, width=500)
        solder_api_url_entry.grid(row=0, column=1, columnspan=2, padx=10, pady=(10,5), sticky=ctk.W+ctk.E)

        ctk.CTkLabel(root, text="Modpack Name:").grid(row=1, column=0, sticky=ctk.W, padx=10, pady=5)
        modpack_name_entry = ctk.CTkEntry(root, width=300)
        modpack_name_entry.grid(row=1, column=1, columnspan=2, padx=10, pady=5, sticky=ctk.W+ctk.E)

        ctk.CTkLabel(root, text="Build Version:").grid(row=2, column=0, sticky=ctk.W, padx=10, pady=5)
        build_version_entry = ctk.CTkEntry(root, width=100)
        build_version_entry.grid(row=2, column=1, columnspan=2, padx=10, pady=5, sticky=ctk.W+ctk.E)

        ctk.CTkLabel(root, text="Author:").grid(row=3, column=0, sticky=ctk.W, padx=10, pady=5)
        author_entry = ctk.CTkEntry(root, width=300)
        author_entry.grid(row=3, column=1, columnspan=2, padx=10, pady=5, sticky=ctk.W+ctk.E)

        ctk.CTkLabel(root, text="Builds Directory:").grid(row=4, column=0, sticky=ctk.W, padx=10, pady=5)
        builds_dir_entry = ctk.CTkEntry(root, width=300)
        builds_dir_entry.grid(row=4, column=1, padx=10, pady=5, sticky=ctk.W+ctk.E)
        
        browse_button = ctk.CTkButton(
            root, 
            text="Browse...", 
            command=lambda: select_directory(builds_dir_entry),
            width=80
        )
        browse_button.grid(row=4, column=2, padx=(10, 10), pady=5, sticky=ctk.W)

        # Create Start and Stop buttons
        button_frame = ctk.CTkFrame(root)
        button_frame.grid(row=5, column=1, pady=10)

        start_button = ctk.CTkButton(
            button_frame, 
            text="Start Update", 
            command=lambda: start_update({
                'solder_api_url': solder_api_url_entry,
                'modpack_name': modpack_name_entry,
                'build_version': build_version_entry,
                'author': author_entry,
                'builds_dir': builds_dir_entry
            }, console_output, start_button, stop_button, root, update_running),
            width=100
        )
        start_button.grid(row=0, column=0, padx=5)

        stop_button = ctk.CTkButton(
            button_frame,
            text="■",  # Square symbol
            command=lambda: stop_update(stop_button, update_running),
            width=40,
            fg_color="orange",
            hover_color="darkorange"
        )
        stop_button.grid(row=0, column=1, padx=5)
        stop_button.grid_remove()  # Initially hidden

        # Load initial config values
        config = load_config()
        if config:
            solder_api_url_entry.insert(0, config['SOLDER_API_URL'])
            modpack_name_entry.insert(0, config['MODPACK_NAME'])
            build_version_entry.insert(0, config['BUILD_VERSION'])
            author_entry.insert(0, config['AUTHOR'])
            builds_dir_entry.insert(0, config['BUILDS_DIR'])

        # Add console output window
        console_output = ctk.CTkTextbox(
            root, 
            width=700,
            height=300,
            font=("Courier", 12)  # Monospace font for better readability
        )
        console_output.grid(row=6, column=0, columnspan=3, padx=10, pady=(5,10), sticky=ctk.W+ctk.E+ctk.N+ctk.S)

        # Add a label above the console
        console_label = ctk.CTkLabel(root, text="Console Output:")
        console_label.grid(row=5, column=0, sticky=ctk.W, padx=10, pady=(10,0))

        # Center the window on the screen
        root.update_idletasks()
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = (screen_width - root.winfo_width()) // 2
        y = (screen_height - root.winfo_height()) // 2
        root.geometry(f"+{x}+{y}")

        # Start the main event loop
        root.mainloop()
        
    except Exception as e:
        # Use ERROR 000 for GUI startup errors
        error_message = f"Error opening the program GUI: {str(e)}"
        messagebox.showerror("[ERROR 000]:", error_message)
        raise SystemExit(1)

if __name__ == "__main__":
    start_gui(main_module.main)