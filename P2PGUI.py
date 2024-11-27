import threading
import select
from Peer import Peer
import tkinter as tk
import os
import File2Torrent
import random
import config
from tkinter import filedialog, messagebox

# Assuming File2Torrent, Peer, config, and other components are implemented elsewhere.
used_ports = set()
used_ports.add(1121)


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
        self.root = root
        self.root.title("Torrent Client GUI")
        
        self.torrent_array = []  # Store torrent paths
        self.torrent_peer = {}   # Store torrent-peer mapping

        # Frame to hold the buttons horizontally
        button_frame = tk.Frame(root)
        button_frame.pack(pady=40)

        # Buttons for main commands added to the frame
        tk.Button(button_frame, text="Create Torrent", command=self.create_torrent).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Select Torrent", command=self.select_torrent).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Connect", command=self.connect_torrent).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Config", command=self.configure).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Exit Torrent", command=self.exit_torrent).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Show Statistics", command=self.show_statistics).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Clear Screen", command=self.clear_screen).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Exit Program", command=self.exit_program).pack(side=tk.LEFT, padx=5)

        # Output area
        self.output = tk.Text(root, height=25, width=100, state=tk.DISABLED)
        self.output.pack(pady=5)



    def log(self, message):
        """Display message in the output area."""
        self.output.config(state=tk.NORMAL)
        self.output.insert(tk.END, message + "\n")
        self.output.config(state=tk.DISABLED)

    def create_torrent(self):
        """Handle torrent creation."""
        path = filedialog.askdirectory(title="Select File or Directory")
        if not path:
            self.log("No path selected for torrent creation.")
            return
        output_filename = filedialog.asksaveasfilename(title="Save Torrent As", defaultextension=".json")
        if not output_filename:
            self.log("No output filename provided.")
            return
        File2Torrent.save_torrent_json(path, output_filename)
        self.log(f"Torrent created: {output_filename}")

    def select_torrent(self):
        """Select a torrent file."""
        path = filedialog.askopenfilename(title="Select Torrent File", filetypes=[("Torrent Files", "*.json")])
        if not path:
            self.log("No torrent file selected.")
            return
        if os.path.exists(path):
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
        if torrent_index is None:
            self.log("No torrent selected.")
            return

        peer_type = messagebox.askquestion("Peer Type", "Is this a seeder? (Yes for Seeder, No for Peer)")
        port = get_unique_port()
        torrent = self.torrent_array[torrent_index]
        
        if peer_type == 'yes':
            peer = Peer(port, torrent, True)
        else:
            peer = Peer(port, torrent, False)

        self.torrent_peer[torrent] = peer
        threading.Thread(target=peer.Main).start()
        self.log(f"Connected to torrent: {torrent}")

    def configure(self):
        """View or modify configurations."""
        config_window = tk.Toplevel(self.root)
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

        torrent = self.torrent_array[torrent_index]
        peer = self.torrent_peer.get(torrent)
        if peer:
            peer.Turn_off()
            del self.torrent_peer[torrent]
            self.log(f"Torrent stopped: {torrent}")
        else:
            self.log("Torrent is not active.")

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
        self.output.config(state=tk.NORMAL)
        self.output.delete(1.0, tk.END)
        self.output.config(state=tk.DISABLED)

    def exit_program(self):
        """Exit the application."""
        for torrent, peer in self.torrent_peer.items():
            peer.Turn_off()
        self.root.destroy()

    def select_from_list(self, options, title):
        """Display a selection dialog and return the selected index."""
        if not options:
            return None
        selection_window = tk.Toplevel(self.root)
        selection_window.title(title)

        selected = tk.IntVar(value=-1)

        for i, option in enumerate(options):
            tk.Radiobutton(selection_window, text=option, variable=selected, value=i).pack(anchor='w')

        def confirm():
            selection_window.destroy()

        tk.Button(selection_window, text="Confirm", command=confirm).pack()
        self.root.wait_window(selection_window)
        return selected.get()

# Create the main window
if __name__ == "__main__":
    root = tk.Tk()
    app = TorrentGUI(root)
    root.mainloop()
