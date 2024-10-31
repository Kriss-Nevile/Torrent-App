import hashlib
import os

class File:
    def __init__(self, filepath, filename, pieces_list):
        self. filepath = filepath
        self.filename = filename
        self.pieces_list = pieces_list
        self.verified_pieces_data = [None] * len(pieces_list)

    def is_complete(self):
        return all(piece_data is not None for piece_data in self.verified_pieces_data)

    def write_to_file(self, output_directory):
        file_path = os.path.join(output_directory, self.filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, 'wb') as out_file:
            for i in range(len(self.pieces_list)):
                out_file.write(self.verified_pieces_data[i]) 

        print(f"File '{self.filename}' successfully reconstructed and saved to '{file_path}'.")


class Client:
    def __init__(self, output_directory):
        self.files = []
        self.output_directory = output_directory

    def add_file(self, filepath, filename, pieces_list):
        new_file = File(filepath, filename, pieces_list)
        self.files.append(new_file)

    def verify_and_store_piece(self, filepath, filename, piece_index, piece_data, expected_hash):
        file = next((f for f in self.files if f.filepath == filepath and f.filename == filename), None)
        if file:
            piece_hash = hashlib.sha1(piece_data).hexdigest()
            if piece_hash == expected_hash:
                file.verified_pieces_data[piece_index] = piece_data
                print(f"Piece {piece_index} for file '{file.filename}' verified and stored.")
                
                # If all pieces are verified, write out the file
                if file.is_complete():
                    file.write_to_file(self.output_directory)
                    print(f"All pieces for file '{file.filename}' are verified. File written to output.")
            else:
                print(f"Hash mismatch for piece {piece_index} of file '{file.filename}'.")


# Sample torrent data structure
torrent_data = {
   "tracker": "your-tracker-portal.local",
   "info": {
      "name": "example_files",
      "piece length": 524288,  # Piece size of 512 KB
      "files": [
         {
            "length": 1024,  # File size in bytes
            "path": ["file1.txt"],
            "pieces": [
               {"index": 0, "hash": "a54d88e06612d820bc3be72877c74f257b561b19"},
            ]
         },
         {
            "length": 2048,
            "path": ["file2.txt"],
            "pieces": [
               {"index": 0, "hash": "e5af1c6ab5d7e5b04d8fbbfd1f57e6ed1f9b5da1"},
               {"index": 1, "hash": "da39a3ee5e6b4b0d3255bfef95601890afd80709"}
            ]
         }
      ]
   }
}

# Mock function to read piece data (simulating data fetch from a peer or file source)
def read_piece_from_source(filepath, piece_index, piece_length):
    # This would actually be implemented to read from a file or peer
    # Here, it’s just mock data for testing
    if filepath == "file1.txt":
        return b"Hello World! " * 10  # Simulated 120 bytes piece data
    elif filepath == "file2.txt":
        if piece_index == 0:
            return b"A" * piece_length  # 512 KB data filled with 'A'
        elif piece_index == 1:
            return b""  # Empty string for testing purposes

# Initialize client with an output directory
output_directory = "output_directory"
client = Client(output_directory)

# Add files to the client and start downloading pieces
for file_info in torrent_data["info"]["files"]:
    filename = file_info["path"][0]
    filepath = os.path.join(*file_info["path"])
    pieces = file_info["pieces"]

    # Add file to the client's download list
    client.add_file(filepath, filename, pieces)

    # Simulate downloading each piece for the file
    for piece in pieces:
        piece_index = piece["index"]
        expected_hash = piece["hash"]
        
        # Simulated fetching of piece data
        piece_data = read_piece_from_source(filename, piece_index, torrent_data["info"]["piece length"])
        
        # Verify and store the piece
        client.verify_and_store_piece(filepath, filename, piece_index, piece_data, expected_hash)


for file in client.files:
    print(file.filepath + '/' + file.filename)
    for pieces_data in file.verified_pieces_data:
        print(pieces_data)