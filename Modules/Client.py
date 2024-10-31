import socket
import os
import struct

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # AF_INET = IP, SOCK_STREAM = TCP
client.connect(('localhost', 1002))  # 127.0.0.1

filepath = 'data/video_1.mkv'
filename = os.path.basename(filepath)
filename_bytes = filename.encode()

# Send filename length as a 4-byte header, followed by the filename
client.send(struct.pack("I", len(filename_bytes)))
client.send(filename_bytes)

# Send file data
with open(filepath, 'rb') as file:
    data_chunk = file.read(2048)
    while data_chunk:
        client.send(data_chunk)
        data_chunk = file.read(2048)

client.close()