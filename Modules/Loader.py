import json
import hashlib
import os
import random      

def load_metainfo(torrent_file):
    with open(torrent_file, "r") as file:
        metainfo = json.load(file)
    return metainfo

def download_file_from_local_torrent(torrent_file):
    # Step 1: Load metainfo from the .torrent.json file
    metainfo = load_metainfo(torrent_file)
    source_file = metainfo["file_name"]  # Original file path
    file_size = metainfo["file_size"]
    piece_size = metainfo["piece_size"]
    pieces = metainfo["pieces"]

    # Step 2: Reassemble the file using pieces
    output_file = f"downloaded_{source_file}"
    
    # Ensure the source file exists
    filepath = '../data/'
    if not os.path.exists(filepath + source_file):
        print(f"Source file '{filepath + source_file}' not found.")
        return
    
    # Shuffle the list of pieces
    random.shuffle(pieces)

    # Create a list to store the verified piece data
    verified_pieces = [None] * len(pieces)

    with open(filepath + source_file, "rb") as src_file:
        for piece in pieces:
            piece_index = piece["index"]
            expected_hash = piece["hash"]
            
            # Read the piece data
            src_file.seek(piece_index * piece_size)
            piece_data = src_file.read(piece["size"])
            
            # Verify the piece data
            piece_hash = hashlib.sha1(piece_data).hexdigest()
            if piece_hash == expected_hash:
                print(f"Piece {piece_index} verified.")
                verified_pieces[piece_index] = piece_data  # Store the verified piece data by index
            else:
                print(f"Piece {piece_index} failed verification. Hash mismatch.")
                return

    # Write the verified pieces in the correct order
    with open(output_file, "wb") as out_file:
        for piece in verified_pieces:
            if piece is not None:  # Ensure only verified pieces are written
                out_file.write(piece)

    print(f"Download and reconstruction of '{source_file}' complete as '{output_file}'.")

# torrent_file = "../Model/video_1.mkv.torrent.json"
# download_file_from_local_torrent(torrent_file)
    
#------------------------------------------------------------------------------------------
#------------------------------------------------------------------------------------------
    
def write_to_output(piece_length, file_length, pieces, out_path, source_file_path):
    # Open the output file for writing
    print("Out path: ", out_path)
    print("Source path: ", source_file_path)
    with open(out_path, "wb") as out_file:
        for piece in pieces:
            piece_index = piece["index"]
            expected_hash = bytes.fromhex(piece["hash"])

            # Calculate byte range for the piece
            piece_start = piece_index * piece_length
            piece_size = min(piece_length, file_length - piece_start)

            # Read piece data from source file
            piece_data = read_piece_from_source(source_file_path, piece_start, piece_size)
            
            # Verify the piece’s hash
            piece_hash = hashlib.sha1(piece_data).digest()
            if piece_hash != expected_hash:
                print(f"Hash mismatch for piece {piece_index} of {out_path}")
                return False

            # Write piece data to the output file
            out_file.write(piece_data)
            print(f"Piece {piece_index} of {out_path} verified and written.")

    return True

def download_from_torrent(torrent_file, output_directory):
    # Load torrent metadata
    torrent_data = load_metainfo(torrent_file)
    
    piece_length = torrent_data["info"]["piece length"]
    fileroot = torrent_data["info"]["name"]

    if os.path.isfile(fileroot):
        file_info = torrent_data["info"]["files"][0]
        out_path = os.path.join(output_directory, *file_info["path"])
        os.makedirs(os.path.dirname(out_path), exist_ok=True) # Ensure output directory structure
        print(out_path)
        source_file_path = fileroot
        if(write_to_output(piece_length, file_info["length"], file_info["pieces"], out_path, source_file_path)):
            print(f"Download and reconstruction of '{file_info['path']}' complete.")
    else:
        for file_info in torrent_data["info"]["files"]:
            out_path = os.path.join(output_directory, *file_info["path"])
            os.makedirs(os.path.dirname(out_path), exist_ok=True) # Ensure output directory structure
            
            source_file_path = os.path.join('..\\'+fileroot, *file_info["path"]) 
            if(write_to_output(piece_length, file_info["length"], file_info["pieces"], out_path, source_file_path)):
                print(f"Download and reconstruction of '{file_info['path']}' complete.")

def read_piece_from_source(file_path, start, size):
    with open(file_path, "rb") as f:
        f.seek(start)
        return f.read(size)

# # Example usage:
# torrent_file = "Assignment 1-Network Application P2P File Sharing.pdf.torrent.json"
# output_directory = "downloaded"
# download_from_torrent(torrent_file, output_directory)