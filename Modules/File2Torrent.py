import hashlib
import os
import json

from config import PEICE_SIZE

def generate_magnet_text(metainfo_file):
    with open(metainfo_file, "rb") as file:
        metainfo_hash = hashlib.sha256(file.read()).hexdigest()
    
    tracker_url = "your-tracker-portal.local"  # Replace with actual tracker portal URL or IP
    magnet_text = f"magnet:?xt=urn:sha256:{metainfo_hash}&dn={metainfo_file}&tr={tracker_url}"
    
    return magnet_text

def generate_pieces(file_path, piece_size=PEICE_SIZE*1024):
    pieces = []
    file_size = os.path.getsize(file_path)
    total_pieces = (file_size + piece_size - 1) // piece_size  # Calculate the total number of pieces

    with open(file_path, 'rb') as file:
        for piece_index in range(total_pieces):
            piece_data = file.read(piece_size)  # Read piece_size bytes from file
            piece_hash = hashlib.sha1(piece_data).hexdigest()  # Calculate SHA-1 hash of the piece
            pieces.append({
                "index": piece_index,
                "hash": piece_hash,
            })

    return pieces

def generate_torrent_json(directory, piece_length=PEICE_SIZE):
    torrent_data = {
        "tracker": "your-tracker-portal.local",
        "info": {
            "name": os.path.basename(directory),
            "piece length": piece_length,
            "files": [],
        }
    }

    if os.path.isfile(directory):  # For a single file
        file_path = directory
        file_size = os.path.getsize(file_path)
        relative_path = [os.path.basename(file_path)]
        pieces = generate_pieces(file_path, piece_length)
        torrent_data["info"]["files"].append({
            "length": file_size,
            "path": relative_path,
            "pieces": pieces
        })
    else:  # Recursively walk through directory to get all file
        for root, _, files in os.walk(directory):
            for filename in files:
                file_path = os.path.join(root, filename)
                file_size = os.path.getsize(file_path)

                # Relative path from the root directory
                relative_path = os.path.relpath(file_path, directory).split(os.sep)
                pieces = generate_pieces(file_path, PEICE_SIZE)
                torrent_data["info"]["files"].append({
                    "length": file_size,
                    "path": relative_path,
                    "pieces": pieces
                })

    return torrent_data

def save_torrent_json(directory, output_filename):
    torrent_metadata = generate_torrent_json(directory)
    with open(output_filename, "w") as f:
        json.dump(torrent_metadata, f, indent=3)
    print(f"Torrent JSON saved as '{output_filename}'")


# Example usage:
directory = "../data"
file_name = os.path.basename(directory)
save_torrent_json(directory, f"{file_name}.torrent.json")