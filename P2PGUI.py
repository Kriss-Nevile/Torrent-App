import tkinter as tk
from tkinter import ttk, filedialog

# Function to handle file browsing
def browse_file():
    file_path = filedialog.askopenfilename()
    if file_path:
        file_label.config(text=file_path)

# Function to display stats for the selected torrent
def display_stats(event):
    try:
        # Get the selected torrent based on the listbox
        selected_index = torrent_listbox.curselection()[0]
        selected_torrent = torrent_listbox.get(selected_index)
        stats_label.config(text=f"Stats for: {selected_torrent}")
    except IndexError:
        pass

# Main application window
root = tk.Tk()
root.title("P2P App")
root.geometry("800x600")

# Top section: File search and browse
search_frame = tk.Frame(root, padx=10, pady=10)
search_frame.pack(fill="x")

search_entry = tk.Entry(search_frame, width=50, font=("Arial", 14))
search_entry.pack(side="left", fill="x", expand=True)

browse_button = tk.Button(search_frame, text="Browse", command=browse_file, font=("Arial", 12))
browse_button.pack(side="left", padx=5)

file_label = tk.Label(root, text="The name of chosen file", font=("Arial", 12), anchor="w")
file_label.pack(fill="x", padx=10, pady=(5, 10))

# Middle section: Torrent list and stats
content_frame = tk.Frame(root, padx=10, pady=10)
content_frame.pack(fill="both", expand=True)

# Left: Torrent list with progress bars
torrent_list_frame = tk.Frame(content_frame)
torrent_list_frame.pack(side="left", fill="y", padx=10, pady=10)

torrent_list_label = tk.Label(torrent_list_frame, text="Torrents in download", font=("Arial", 12))
torrent_list_label.pack(anchor="w")

# Scrollable frame for torrents
torrent_canvas = tk.Canvas(torrent_list_frame)
scrollbar = ttk.Scrollbar(torrent_list_frame, orient="vertical", command=torrent_canvas.yview)
scrollable_frame = tk.Frame(torrent_canvas)

scrollable_frame.bind(
    "<Configure>",
    lambda e: torrent_canvas.configure(scrollregion=torrent_canvas.bbox("all"))
)

torrent_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
torrent_canvas.configure(yscrollcommand=scrollbar.set)

torrent_canvas.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")

# Add torrents with progress bars and make them selectable
torrent_data = {}
torrent_listbox = tk.Listbox(scrollable_frame, height=0)  # Listbox for tracking selections
torrent_listbox.pack_forget()  # Hidden but used to bind selection events

for i in range(1, 11):
    frame = tk.Frame(scrollable_frame, pady=5)
    frame.pack(fill="x", padx=5)

    torrent_label = tk.Label(frame, text=f"Torrent_{i}", font=("Arial", 10), anchor="w")
    torrent_label.pack(side="left", fill="x", expand=True)

    progress = ttk.Progressbar(frame, length=300, mode="determinate")
    progress.pack(side="right", fill="x", expand=True)
    progress["value"] = i * 10  # Dummy progress value
    torrent_data[f"Torrent_{i}"] = progress

    # Add the torrent to the listbox for selection
    torrent_listbox.insert("end", f"Torrent_{i}")
    torrent_label.bind("<Button-1>", lambda e, index=i: select_torrent(index - 1))  # Allow selection on label click

def select_torrent(index):
    torrent_listbox.select_clear(0, "end")
    torrent_listbox.select_set(index)
    torrent_listbox.event_generate("<<ListboxSelect>>")

# Bind listbox selection to the stats display
torrent_listbox.bind("<<ListboxSelect>>", display_stats)

# Right: Stats display
stats_frame = tk.Frame(content_frame, padx=10)
stats_frame.pack(side="right", fill="both", expand=True)

stats_label = tk.Label(stats_frame, text="Stats for selected torrent", font=("Arial", 12), anchor="w", wraplength=200, justify="left")
stats_label.pack(fill="both", expand=True)

# Start the application
root.mainloop()
