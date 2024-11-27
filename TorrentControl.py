import threading
import select
from Peer import Peer
import tkinter as tk
import os
import File2Torrent
import random
import config


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


def display_download_bar(no_chunks_downloaded, total_chunks, download_speed):
    bar_length = 50  # Length of the progress bar
    progress = no_chunks_downloaded / total_chunks
    blocks = int(bar_length * progress)
    percent = int(progress * 100)
    
    # Build the progress bar string
    bar = f"[{'#' * blocks}{'.' * (bar_length - blocks)}] {percent}%"
    
    # Print the bar with statistics
    print(f"\r{bar} | Speed: {download_speed:.2f} MB/s", end='', flush=True)


torrent_array = []
#dict to map torrent to peer
torrent_peer = {}


# CLI for input
def CLI():
    os.system('cls' if os.name == 'nt' else 'clear')
    while True:
        command = input('>>>> ')
        if command == 'exit' or command == '/e': break
        if command == 'create':
            print('Enter the path of the file or directory to create a torrent (Relative):')
            path = input('>>>> ')
            print('Enter the output filename:')
            output_filename = input('>>>> ')
            File2Torrent.save_torrent_json(path, output_filename)
        elif command == 'select':
            print('Enter the path of the torrent file: (Relative)')
            path = input('>>>> ')
            #check if file exists
            if os.path.exists(path):
                torrent_array.append(path) #In the GUI each torrent will have a number associated with it
            else:
                print('File does not exist')
        elif command == 'connect':
            print('Select the torrent to connect to: (Enter the number)')
            for i, torrent in enumerate(torrent_array):
                print(f'{i + 1}: {torrent}')
            torrent_index = int(input('>>>> ')) - 1
            if torrent_index >= len(torrent_array) or torrent_index < 0:
                print('Invalid torrent number')
                continue
            torrent = torrent_array[torrent_index]
            #extract file name from torrent json
            print('Is this a seeder or a normal peer? (s/n)')
            peer_type = input('>>>> ')
            #create a random port for the peer
            port = get_unique_port()
            if peer_type == 's':
                #Create a peer object and start seeding
                peer = Peer(port, torrent, True)
                torrent_peer[torrent] = peer
                main_thread = threading.Thread(target=peer.Main).start()
            elif peer_type == 'n':
                #Create a peer object and start downloading
                peer = Peer(port, torrent, False)
                torrent_peer[torrent] = peer
                main_thread = threading.Thread(target=peer.Main).start()
            else:
                print('Invalid input')
        elif command == 'config':
            print('SEE CONFIG: 1, CHANGE CONFIG: 2')
            config_option = input('>>>> ')
            if config_option == '1':
                PIECE_SIZE, OUTPUT_DIR, TRACKER_URL = config.read_config()
                print(f'PIECE_SIZE  =  {PIECE_SIZE}     # Bytes --- Used in creating torrent')
                print(f'OUTPUT_DIR  = {OUTPUT_DIR}     # Output directory --- Default output directory for downloaded files')
                print(f'TRACKER_URL = {TRACKER_URL}     # Default tracker link')
            elif config_option == '2':
                print('In config mode, select the option to change: PIECE_SIZE: 1, OUTPUT_DIR: 2, TRACKER_URL: 3 or exit')
                while True:
                    choice = input('>>>> ')
                    if choice == '1':
                        print('Enter the new piece size in bytes:')
                        value = input('>>>> ')
                        config.write_config(1, value)
                    elif choice == '2':
                        print('Enter the new output directory:')
                        value = input('>>>> ')
                        config.write_config(2, value)
                    elif choice == '3':
                        print('Enter the new tracker URL:')
                        value = input('>>>> ')
                        config.write_config(3, value)
                    elif choice == 'exit':
                        os.system('cls' if os.name == 'nt' else 'clear')
                        break
                    else:
                        print('Invalid choice')
        elif command == 'exitT': #exit torrent
            print('Select the torrent to exit: (Enter the number)')
            for i, torrent in enumerate(torrent_array):
                print(f'{i + 1}: {torrent}')
            torrent_index = int(input('>>>> ')) - 1
            if torrent_index >= len(torrent_array) or torrent_index < 0:
                print('Invalid torrent number')
                continue
            torrent = torrent_array[torrent_index]
            peer = torrent_peer[torrent]
            peer.Turn_off()
            del torrent_peer[torrent]
        elif command == 'show': #show statistics for selected torrent
            print('Select the torrent to show statistics: (Enter the number)')
            for i, torrent in enumerate(torrent_array):
                print(f'{i + 1}: {torrent}')
            torrent_index = int(input('>>>> ')) - 1
            if torrent_index >= len(torrent_array) or torrent_index < 0:
                print('Invalid torrent number')
                continue
            torrent = torrent_array[torrent_index]
            peer = torrent_peer.get(torrent, None)
            if peer is None:
                print('Torrent loaded, but havent started yet')
                continue
            else:
                peer.Get_Peer_Speed_Info()
        elif command == 'clear':
            os.system('cls' if os.name == 'nt' else 'clear')
        elif command == 'exitP': #exit program
            #turn off all torrent in the system
            for torrent in torrent_array:
                peer = torrent_peer.get(torrent, None)
                if peer is not None:
                    peer.Turn_off()
            os.system('cls' if os.name == 'nt' else 'clear')


cli = threading.Thread(target=CLI).start()



