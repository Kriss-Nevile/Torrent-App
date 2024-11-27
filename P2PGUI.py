import threading
import select
from Peer import Peer
import tkinter as tk
import os
import File2Torrent
import random
import config
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image
import pywinstyles

# Assuming File2Torrent, Peer, config, and other components are implemented elsewhere.
used_ports = set()
used_ports.add(1121)
def wrap_text(text, width):
    """Wrap text at a specified character width."""
    return '\n'.join([text[i:i+width] for i in range(0, len(text), width)])

def rgb_to_hex(rgb):
    return '#%02x%02x%02x' % rgb

def generate_random_port():
    return random.randint(1024, 65535)

def get_unique_port():
    while True:
        port = generate_random_port()
        if port not in used_ports:
            used_ports.add(port)
            return port

class TorrentGUI:
    def __init__(self, root):
        self.width = 1000
        self.height = 600
        self.root = root
        self.root.title("Torrent Client GUI")
        self.root.geometry(f"{self.width}x{self.height}")  # Optional: Adjust window size
        self.root.resizable(False, False)
        ctk.set_appearance_mode("dark")  # Set dark mode
        ctk.set_default_color_theme("blue")  # Use a blue color theme

        # current_path = os.path.dirname(os.path.realpath(__file__))
        # bg_image_path = os.path.join(current_path, "IMG", "BG.jpg")
        # self.bg_image = ctk.CTkImage(Image.open(bg_image_path), size=(self.width, self.height))
        # self.bg_image_label = ctk.CTkLabel(self.root, image=self.bg_image)
        # self.bg_image_label.place(x=0, y=0, relwidth=1, relheight=1)
    

        self.torrent_array = []  # Store torrent paths
        self.torrent_peer = {}   # Store torrent-peer mapping

        # Frame to hold the buttons horizontally
        button_frame_row1 = ctk.CTkFrame(root, fg_color="transparent", bg_color="transparent")
        button_frame_row2 = ctk.CTkFrame(root, fg_color="transparent", bg_color="transparent")


        # Pack the frames
        button_frame_row1.pack(pady=(50, 10))
        button_frame_row2.pack(pady=10)
        button_config = {"fg_color": rgb_to_hex((13,136,198)), "text_color": "white", "bg_color": "transparent"}
        

        # Add buttons to the first row
        ctk.CTkButton(button_frame_row1, text="Create Torrent", command=self.create_torrent, **button_config).pack(side="left", padx=5)
        ctk.CTkButton(button_frame_row1, text="Select Torrent", command=self.select_torrent, **button_config).pack(side="left", padx=5)
        ctk.CTkButton(button_frame_row1, text="Connect", command=self.connect_torrent, **button_config).pack(side="left", padx=5)
        ctk.CTkButton(button_frame_row1, text="Config", command=self.configure, **button_config).pack(side="left", padx=5)
        # Add buttons to the second row
        ctk.CTkButton(button_frame_row2, text="Exit Torrent", command=self.exit_torrent, **button_config).pack(side="left", padx=5)
        ctk.CTkButton(button_frame_row2, text="Show Statistics", command=self.show_statistics, **button_config).pack(side="left", padx=5)
        ctk.CTkButton(button_frame_row2, text="Clear Screen", command=self.clear_screen, **button_config).pack(side="left", padx=5)
        ctk.CTkButton(button_frame_row2, text="Exit Program", command=self.exit_program, **button_config, hover_color="red").pack(side="left", padx=5)

        # Output area
        self.output = ctk.CTkTextbox(self.root, height=400, width=700, fg_color=rgb_to_hex((25,25,25)), text_color="white", font=("Arial", 14 , "bold"), corner_radius=30, bg_color="transparent")
        self.output.pack(pady=10)
        self.output.configure(state="disabled")

    def log(self, message):
        """Display message in the output area."""
        self.output.configure(state="normal")
        self.output.insert("end", message + "\n")
        self.output.configure(state="disabled")

    def ask_peer_type(self, torrent_name):
        """Display a custom dialog to ask for peer type."""
        peer_type = None

        def set_peer_type(value):
            nonlocal peer_type
            peer_type = value
            dialog.destroy()

        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Peer Type")
        dialog.geometry("400x150")
        dialog.resizable(False, False)

        label = ctk.CTkLabel(dialog, text=wrap_text(f"Is this a seeder for torrent {torrent_name}? (Only choose Yes if you already have the file)", 50))
        label.pack(pady=20)

        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(pady=10)

        yes_button = ctk.CTkButton(button_frame, text="Yes", command=lambda: set_peer_type("yes"), hover_color="orange")
        yes_button.pack(side="left", padx=10)

        no_button = ctk.CTkButton(button_frame, text="No", command=lambda: set_peer_type("no"))
        no_button.pack(side="left", padx=10)

        self.root.wait_window(dialog)
        return peer_type

    def create_torrent(self):
        """Handle torrent creation."""

        choice = "none"

        def Update_Choice(new_choice):
            nonlocal choice
            choice = new_choice
            dialog.destroy()

        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Create a Torrent for a File or Directory?")
        
        # Set the window size (optional)
        dialog.geometry("300x100")
        dialog.resizable(False, False)

        dialog.lift()
        dialog.grab_set()

        # File button
        file_button = ctk.CTkButton(dialog, text="File", command=lambda: Update_Choice('file'), width=60)
        file_button.pack(side=tk.LEFT, padx=10)

        # Folder button
        folder_button = ctk.CTkButton(dialog, text="Folder", command=lambda: Update_Choice('folder'), width=60)
        folder_button.pack(side=tk.LEFT, padx=40)

        cancel_button = ctk.CTkButton(dialog, text="Cancel", command=dialog.destroy, width=60, hover_color="red")
        cancel_button.pack(side=tk.RIGHT, padx=10)

        self.root.wait_window(dialog)
        # Apply styles to buttons

        if choice == 'file':
            path = filedialog.askopenfilename(title="Select File or Directory")
            if not path:
                self.log("No file selected for torrent creation.")
                return
        elif choice == 'folder':
            path = filedialog.askdirectory(title="Select Directory")
            if not path:
                self.log("No directory selected for torrent creation.")
                return
        else:
            self.log("No path selected for torrent creation.")
            return
        # output_filename = filedialog.asksaveasfilename(title="Save Torrent As", defaultextension=".json") we dont need an output file_name
        # if not output_filename:
        #     self.log("No output filename provided.")
        #     return
        filename = os.path.basename(path)
        output_filename = f"torrents/{filename}.torrent.json"
        File2Torrent.save_torrent_json(path, output_filename)
        self.log(f"Torrent created: {output_filename}")


    def select_torrent(self):
        """Select a torrent file."""
        path = filedialog.askopenfilename(title="Select Torrent File", filetypes=[("Torrent Files", "*.json")])
        if not path:
            self.log("No torrent file selected.")
            return
        if os.path.exists(path):
            #check if path already exists in the array
            if path in self.torrent_array:
                self.log("NOTE: Torrent already selected.")
                return
            
            self.torrent_array.append(path)
            self.log(f"Torrent selected: {path}")
        else:
            self.log("File does not exist.")

    def connect_torrent(self):
        """Connect to a torrent."""
        if not self.torrent_array:
            self.log("No torrents available. Please select one first.")
            return

        torrent_index = self.select_from_list(self.torrent_array, "Select a Torrent")
        if not torrent_index:
            self.log("No torrent selected.")
            return
        for index in torrent_index:
            torrent = self.torrent_array[index]
            peer_type = self.ask_peer_type(torrent)

            # Validate the response
            if peer_type is None:  # User canceled the dialog
                self.log("UNEXPECTED: Torrent connection canceled.")
                return


            port = get_unique_port()
            
            # Determine the peer type
            if peer_type == 'yes':
                peer = Peer(port, torrent, True)
            else:
                peer = Peer(port, torrent, False)

        # Store the peer and start its thread
            self.torrent_peer[torrent] = peer
            threading.Thread(target=peer.Main).start()
            self.log(f"Connected to torrent: {torrent}")

    def configure(self):
        """View or modify configurations."""
        config_window = ctk.CTkToplevel(self.root)
        config_window.title("Configurations")

        # Display current configurations
        PIECE_SIZE, OUTPUT_DIR, TRACKER_URL = config.read_config()
        tk.Label(config_window, text=f"PIECE_SIZE: {PIECE_SIZE}").pack()
        tk.Label(config_window, text=f"OUTPUT_DIR: {OUTPUT_DIR}").pack()
        tk.Label(config_window, text=f"TRACKER_URL: {TRACKER_URL}").pack()

        def update_config(option, label):
            value = tk.simpledialog.askstring("Update Config", f"Enter new value for {label}:")
            if value:
                config.write_config(option, value)
                self.log(f"Updated {label} to {value}")

        tk.Button(config_window, text="Update PIECE_SIZE", command=lambda: update_config(1, "PIECE_SIZE")).pack(pady=3)
        tk.Button(config_window, text="Update OUTPUT_DIR", command=lambda: update_config(2, "OUTPUT_DIR")).pack(pady=3)
        tk.Button(config_window, text="Update TRACKER_URL", command=lambda: update_config(3, "TRACKER_URL")).pack(pady=3)

    def exit_torrent(self):
        """Stop a torrent."""
        if not self.torrent_array:
            self.log("No torrents available to stop.")
            return

        torrent_index = self.select_from_list(self.torrent_array, "Select a Torrent to Stop")
        if torrent_index is None:
            self.log("No torrent selected.")
            return

        for torrent in torrent_index:
            torrent_path = self.torrent_array[torrent]
            peer = self.torrent_peer.get(torrent_path)
            if peer:
                peer.Turn_off()
                del self.torrent_peer[torrent_path]
                self.log(f"Torrent stopped: {torrent_path} removed from torrent list.")
            else:
                self.log(f"Torrent {torrent_path} is not active. Remove from torrent list.")

    def show_statistics(self):
        """Show statistics for a torrent."""
        if not self.torrent_array:
            self.log("No torrents available.")
            return

        torrent_index = self.select_from_list(self.torrent_array, "Select a Torrent for Statistics")
        if torrent_index is None:
            self.log("No torrent selected.")
            return

        torrent = self.torrent_array[torrent_index]
        peer = self.torrent_peer.get(torrent)
        if peer:
            peer.Get_Peer_Speed_Info()
        else:
            self.log("Torrent is not active.")

    def clear_screen(self):
        """Clear the output area."""
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")


    def exit_program(self):
        """Exit the application."""
        for torrent, peer in self.torrent_peer.items():
            peer.Turn_off()
        self.root.destroy()

    def select_from_list(self, options, title):
        """Display a selection dialog and return the selected index."""
        if not options:
            return None

        # Create the Toplevel window
        selection_window = ctk.CTkToplevel(self.root)
        selection_window.title(title)
        selection_window.geometry("500x300")  # Set window size
        selection_window.maxsize(500, 600)  # Set maximum window size
        selection_window.resizable(False, False)  # Allow vertical resizing
        selection_window.attributes("-topmost", True)  # Keep the window on top
        selection_window.focus_force()

        selected = []

        def toggle_selection(value):
            if value in selected:
                selected.remove(value)
            else:
                selected.append(value)

        # Main frame to hold canvas and scrollbar
        main_frame = ctk.CTkFrame(selection_window)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Canvas for scrolling
        canvas = ctk.CTkCanvas(main_frame, highlightthickness=0)
        canvas.configure(bg="gray17")
        canvas.pack(side="left", fill="both", expand=True)

        # Scrollbar for the canvas
        scrollbar = ctk.CTkScrollbar(main_frame, orientation="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Frame inside the canvas to hold the checkboxes
        scrollable_frame = ctk.CTkFrame(canvas)
        scrollable_frame_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        # Update canvas scroll region whenever the frame resizes
        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        scrollable_frame.bind("<Configure>", on_frame_configure)

        # Ensure the canvas resizes horizontally with the window
        def on_canvas_resize(event):
            canvas.itemconfig(scrollable_frame_id, width=event.width)

        canvas.bind("<Configure>", on_canvas_resize)

        # Add checkboxes to the scrollable frame
        for i, option in enumerate(options):
            var = ctk.IntVar()
            checkbox = ctk.CTkCheckBox(
                scrollable_frame, text=wrap_text(option, 60), variable=var, command=lambda v=i: toggle_selection(v)
            )
            checkbox.pack(anchor="w", pady=(5, 0), padx=(10, 0))

        # Confirm and Cancel buttons
        def confirm():
            selection_window.destroy()

        def cancel():
            selected.clear()
            selection_window.destroy()

        # Button frame at the bottom
        button_frame = ctk.CTkFrame(selection_window, fg_color="transparent")
        button_frame.pack(pady=10)

        ctk.CTkButton(button_frame, text="Cancel", command=cancel, hover_color="red").pack(side="left", padx=10)
        ctk.CTkButton(button_frame, text="Confirm", command=confirm).pack(side="left", padx=10)

        # Wait for the selection window to close
        self.root.wait_window(selection_window)
        return selected

# Create the main window
if __name__ == "__main__":
    root = ctk.CTk()
    app = TorrentGUI(root)
    root.mainloop()
