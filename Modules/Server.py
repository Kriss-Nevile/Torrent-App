import socket
import struct

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # AF_INET = IP, SOCK_STREAM = TCP
server.bind(('localhost', 1002))
server.listen()

client_socket, client_address = server.accept()
print(f"[NEW CONNECTION] {client_address} connected.")

# Receive 4 bytes indicating the length of the filename
# It is enough for the integer that represents the filename length.
filename_length = struct.unpack("I", client_socket.recv(4))[0]

# Receive the filename based on the specified length
filename = client_socket.recv(filename_length).decode()
print(f"[RECV] Filename: {filename}.")

# Receive and write the file data
try:
    with open(filename, "wb") as file:
        while True:
            data_chunk = client_socket.recv(2048)  # Match client buffer size
            if not data_chunk:
                break
            file.write(data_chunk)
except Exception as e:
    print(f"[ERROR] An error occurred while writing to file: {e}")
finally:
    print(f"[DISCONNECTED] {client_address} disconnected. File transfer complete.")
    client_socket.close()
