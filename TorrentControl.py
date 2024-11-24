import threading
import select
import Peer
import tkinter as tk
import os


def display_download_bar(no_chunks_downloaded, total_chunks, download_speed):
    bar_length = 50  # Length of the progress bar
    progress = no_chunks_downloaded / total_chunks
    blocks = int(bar_length * progress)
    percent = int(progress * 100)
    
    # Build the progress bar string
    bar = f"[{'#' * blocks}{'.' * (bar_length - blocks)}] {percent}%"
    
    # Print the bar with statistics
    print(f"\r{bar} | Speed: {download_speed:.2f} MB/s", end='', flush=True)

# CLI for input
def CLI():
    os.system('cls' if os.name == 'nt' else 'clear')
    while True:
        command = input('>>>> ')
        if command == 'exit' or command == '/e': break
        if command == 'create':
            pass
        elif command == 'connect':
            pass
        elif command == 'deamon':
            pass
        elif command == 'edit':
            pass
        elif command == 'edit':
            pass
        elif command == 'show':
            pass
        elif command == 'clear':
            os.system('cls' if os.name == 'nt' else 'clear')


cli = threading.Thread(target=CLI).start()



