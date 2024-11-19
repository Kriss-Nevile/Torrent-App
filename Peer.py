from threading import Thread, Condition, Lock, Event
import select
import socket
import time
import http
import random
import requests
from urllib.parse import urlencode
import struct
import json
from datetime import datetime
import messParser
from Utils import State, Neighbour_Peer, Time_out
import os
import hashlib


# Import Configuration

from config import PEICE_SIZE, OUTPUT_DIR, TRACKER_URL
from config import timestamped_print as print


#currently the implementation doesnt drop any connections, and will simply stop when it reaches the maimum number of peers

#The handshake process, if the recipient receive a hash info that it currently does not serve
#it has to drop the connection

# keep-alive: <len=0000>
# The keep-alive message is a message with zero bytes, specified with the length prefix set to zero. There is no message ID and no payload. Peers may close a connection if they receive no messages (keep-alive or any other message) for a certain period of time, so a keep-alive message must be sent to maintain the connection alive if no command have been sent for a given amount of time. This amount of time is generally two minutes.

# choke: <len=0001><id=0>
# The choke message is fixed-length and has no payload.

# unchoke: <len=0001><id=1>
# The unchoke message is fixed-length and has no payload.

# interested: <len=0001><id=2>
# The interested message is fixed-length and has no payload.

# not interested: <len=0001><id=3>
# The not interested message is fixed-length and has no payload.

# request: <len=0013><id=6><index><begin><length>
# The request message is fixed length, and is used to request a block. The payload contains the following information:





# Currently the peer supports up to 20 neighbouring peers
class File:
    def __init__(self, filepath, pieces_list, output_directory = OUTPUT_DIR):
        self.filepath = filepath
        self.pieces_list = pieces_list 
        '''
            [
                {
                    "index": 0,
                    "hash": "8664b465fb20620c7e29fde5cb1f0f58de3760b4"
                }
            ]
        '''
        self.verified_pieces_data = [None] * len(pieces_list)
        self.output_directory = output_directory

    def is_complete(self):
        return all(piece_data is not None for piece_data in self.verified_pieces_data)

    def write_full_file_to_local(self, output_directory):
        local_file_path = os.path.join(output_directory, self.filepath)
        os.makedirs(os.path.dirname(local_file_path), exist_ok=True)

        with open(local_file_path, 'wb') as out_file:
            for i in range(len(self.pieces_list)):
                chunk_data = self.verified_pieces_data[i]
                if(chunk_data is not None and isinstance(chunk_data, str)):
                    piece_path = local_file_path + f'_{i}'
                    with open(piece_path, 'rb') as chunk_file:
                        out_file.write(chunk_file.read()) 
                    os.remove(piece_path)  # Remove the chunk file after loading
                else:
                    out_file.write(chunk_data) 

        print(f"INFO - File '{self.filepath}' successfully reconstructed and saved to '{local_file_path}'.")





class Peer:

    def __init__(self, port, torrent_file="", seeder=False):
        self.timer_stop = False
        self.seeder = seeder
        self.max_peer_number = 20
        self.counter_lock = Lock()
        #self.live_lock = Lock() Deprecated, may not used
        self.current_peer_number = 0
        self.port = port
        self.queue_lock = Lock()
        self.time_lock = Lock()
        self.stop_event = Event()
        # self.have_lock = Lock()
        self.have_queue = []
        self.general_update_lock = Lock()
        self.max_councurrent_request = 100
        self.condition = Condition() # this is to halt the accepting socket if the number of socket have reached 
        # the maximum --> might remove this feature in the future
        self.primary_accept_socket = None
        self.alive = True
        self.peer_id = self.peer_id = datetime.now().strftime("%H%M%S%f") + str(random.randint(10000000, 99999999)) #generate a unique peer id
        self.info_hash = '12345678901234567890' #20 bytes
        self.peer_list = []
        self.top_four_peer = []
        #self.peer_list.append(Neighbour_Peer('localhost', self.port, 'self_peer')) #for testing purposes
        self.uploaded = 0
        self.downloaded = 0 #number of bytes downloaded
        self.chunks_downloaded = []   # used to keep track of the chunks downloaded, we if need to get size, we can use len(downloaded)
        self.left = 0
        self.chunks_left = []
        self.duplicate = 0
        self.duplicate_lock = Lock()
        self.URL = 'https://simple-like-torrent-application.vercel.app/'
        self.previous_downloaded = 0
        self.previous_time = time.time()
        self.count = {}

        self.local_storage = []

        # Torrent data:
        self.piece_length = PEICE_SIZE  # default
        self.URL = TRACKER_URL             # default

        if torrent_file != "":
            self.Read_Torrent(torrent_file)


    def Check_alive(self):
        with self.live_lock:
            return self.alive


    #if a peer has available chunks, send an interested message
    #if a peer has no available chunks, send a not interested message
    def Check_available_peers(self, socket: socket.socket, peer_obj: Neighbour_Peer):
        while peer_obj.Check_alive():
            with self.general_update_lock:
                try:
                    if peer_obj.receive_status == State.peer_choking and peer_obj.available_chunks:
                        interested_message = messParser.construct_interested()
                        self.send_all(socket, interested_message)
                        peer_obj.update_time()
                        print('sent interested message to peer with ID:', peer_obj.ID)
                    elif peer_obj.receive_status == State.peer_interested and not peer_obj.available_chunks:
                        not_interested_message = messParser.construct_not_interested()
                        self.send_all(socket, not_interested_message)
                        peer_obj.update_time()
                        print('peer status:', peer_obj.receive_status)
                        print('sent not interested message to peer with ID:', peer_obj.ID)

                except Exception as e:
                    print(f"Connection has been closed: {e}")

            time.sleep(3)



    #should be system wide
    # def Have_thread(self):
    #     while self.alive:
    #         with self.general_update_lock:
    #             for tupled in reversed(self.have_queue):
    #                 have_message = messParser.construct_have(tupled[0])
    #                 for peer in self.peer_list:
    #                     if peer.sock is not None and tupled[1] != peer.ID:
    #                         self.send_all(peer.sock, have_message)
    #                 #print(f"SEND: Sent have message for piece index {tupled[0]} to all peers")
    #                 self.have_queue.remove(tupled)
    #                 # The have message doesnt update the time
            
    #         time.sleep(1) #notify every 1 seconds



    #Function to send data
    def Send_(self, peer_socket, peer_obj: Neighbour_Peer):

        check_thread = Thread(target=self.Check_available_peers, args=(peer_socket, peer_obj))
        check_thread.start()

        while peer_obj.Check_alive():
            try:
                #Send keep-alive message if no other message is sent for a certain period
                with self.general_update_lock:
                    if time.time() - peer_obj.get_time() > 20 and peer_obj.send_status == State.am_choking and len(peer_obj.available_chunks) != 0:
                        keep_alive_message = messParser.construct_keep_alive()
                        self.send_all(peer_socket, keep_alive_message)
                        print("SEND: Sent keep-alive message for peer with ID:", peer_obj.ID, "with available chunks", peer_obj.available_chunks)
                        peer_obj.update_time()

                # with self.general_update_lock:
                #     if not peer_obj.noted and self.left == 0:
                #         not_interested_message = messParser.construct_not_interested()
                #         self.send_all(peer_socket, not_interested_message)
                #         peer_obj.noted = True
                #         peer_obj.update_time()
                
                with self.general_update_lock:
                    with peer_obj.receive_lock:

                        if self.left != 0 and peer_obj.receive_status == State.peer_interested:
                            unique_pieces = random.sample(peer_obj.available_chunks, min(self.max_councurrent_request, len(peer_obj.available_chunks)))

                            for payload in unique_pieces:
                                if payload in self.chunks_downloaded:
                                    with peer_obj.receive_lock:
                                        peer_obj.available_chunks.remove(payload)
                                    continue
                                try:
                                    request_message = messParser.construct_request(payload['filepath'], payload['piece_index'])
                                    self.send_all(peer_socket, request_message)
                                    print(f"SEND: Sent request message for file {payload['filepath']} with piece index {payload['piece_index']}")
                                    peer_obj.update_time()
                                except Exception as e:
                                    print(f"Error handling payload {payload}: {e}")

                            # for piece_index in unique_pieces:
                            #     if piece_index in self.chunks_downloaded:
                            #         peer_obj.available_chunks.remove(piece_index)
                            #         continue
                            #     request_message = messParser.construct_request(piece_index)
                            #     self.send_all(peer_socket, request_message)
                            #     #print(f"SEND: Sent request message for piece index {piece_index}")
                            #     peer_obj.update_time()



                # Send messages based on peer state
                if peer_obj.Check_send_status():
                    # Handle requests from the request queue
                    with peer_obj.queue_lock:
                        print(f"INFO - Peer {peer_obj.ID}: Request queue:", peer_obj.request_queue)

                        # Format of a request payload in queue: {"filepath": path/name, "piece_index": }
                        for request in reversed(peer_obj.request_queue):
                            try:
                                # Validate request structure
                                # if 'filepath' not in request or 'piece_index' not in request:
                                #     print(f"ERROR: Invalid request format: {request}")
                                #     continue

                                filepath = request['filepath']
                                piece_index = request['piece_index']
                                chunk_data = None

                                # Check if the chunk is in local storage
                                file_obj = next((f for f in self.local_storage if f.filepath == filepath), None)
                                if file_obj:
                                    if 0 <= piece_index < len(file_obj.verified_pieces_data):
                                        piece_path = file_obj.verified_pieces_data[piece_index]
                                        chunk_data = None
                                        if piece_path is not None and isinstance(chunk_data, str):
                                            piece_path = os.path.join(file_obj.output_directory, piece_path)
                                            with open(piece_path, 'rb') as chunk_file:
                                                chunk_data = chunk_file.read()

                                        if chunk_data is None:
                                            print(f"INFO: Chunk for file '{filepath}', index {piece_index} not yet verified in local storage from {peer_obj.ID}")
                                    else:
                                        print(f"ERROR: Invalid piece index {piece_index} for file '{filepath}' in local storage.")
                                else:
                                    print(f"INFO: File '{filepath}' not found in local storage. Reading directly from file.")

                                # If not found or verified in local storage, read directly from file
                                if chunk_data is None:
                                    chunk_data = self.read_chunk(filepath, piece_index)
                                    if chunk_data is None:
                                        print(f"ERROR: Failed to read chunk data for file '{filepath}', index {piece_index}.")
                                        continue
                                
                                # Create and send data to source peer
                                # Format of send data message:  {"filepath": path/name, "piece_index": , "chunk_data": binary-data}
                                piece_message = messParser.construct_piece(filepath, piece_index, chunk_data)
                                self.send_all(peer_socket, piece_message)
                                print(f"SEND: Sent piece message for file {filepath}, index {piece_index}")
                                
                                peer_obj.request_queue.remove(request)
                                peer_obj.update_time()
                            except Exception as e:
                                print(f"ERROR: Exception while processing request {request}: {e}")

                
                with self.general_update_lock:
                    for tupled in reversed(self.have_queue):
                        have_message = messParser.construct_have(tupled[0]['filepath'], tupled[0]['piece_index'])
                        for peer in self.peer_list:
                            if peer.sock is not None and tupled[1] != peer.ID:
                                self.send_all(peer.sock, have_message)
                        #print(f"SEND: Sent have message for piece index {tupled[0]} to all peers")
                        self.have_queue.remove(tupled)
                        # The have message doesnt update the time


                time.sleep(1)  # Sleep to avoid busy waiting

            except Exception as e:
                with peer_obj.live_lock:
                    peer_obj.is_alive = False
                print(f"Error sending message: {e}")
                break
        
        check_thread.join()
        print("SEND: Send closed for peer with ID:", peer_obj.ID, '\n')




    # def Measure_download_speed(self):
    #     while self.alive:
    #         with self.general_update_lock:
    #             download_speed = (self.downloaded - self.previous_downloaded) / (time.time() - self.previous_time)
    #             self.previous_downloaded = self.downloaded
    #             self.previous_time = time.time()

    #             if self.update_stats_callback:
    #                 self.update_stats_callback(download_speed, self.downloaded / 30, len(self.peer_list), 0)

    #         time.sleep(1)





    
    #Function to receive data
    def Receive_(self, peer_socket, peer_obj: Neighbour_Peer):
        print('start receiving from peer with ID:', peer_obj.ID,'\n')
        peer_obj.last_message_time = time.time()
        time_out_thread = Thread(target=Time_out, args=(peer_obj,)).start()
        while peer_obj.Check_alive():
            readable, _, _ = select.select([peer_socket], [], [], 0.2)  # Check if the socket is readable
            if readable:
                try:
                    message = self.receive_all(peer_socket)
                    #check if the connection is still alive
                    if message is None:
                        with peer_obj.live_lock:
                            peer_obj.is_alive = False
                        break
                    peer_obj.last_message_time = time.time() # Update the last message time regardless of the message type
                    # Process the message
                    message_type, payload = messParser.parse_message(message)
                    if message_type == 'keep-alive':
                        print("REC: Received keep-alive message")
                    elif message_type == 'choke':
                        print("REC: Received choke message")
                        peer_obj.update_receive_status(State.peer_choking)
                    elif message_type == 'unchoke':
                        print("REC: Received unchoke message")
                        peer_obj.update_receive_status(State.peer_interested)
                    elif message_type == 'interested':
                        print("REC: Received interested message")
                        if True: #temporarily set to true
                            unchoke_message = messParser.construct_unchoke()
                            self.send_all(peer_socket, unchoke_message)
                            print('sent unchoke message')
                            peer_obj.update_send_status(State.am_interested)
                    elif message_type == 'not interested':
                        print("REC: Received not interested message")
                        peer_obj.update_send_status(State.am_choking)
                        choke_message = messParser.construct_choke()
                        self.send_all(peer_socket, choke_message)
                        print('sent choke message')
                    elif message_type == 'have':
                        if self.left == 0: continue
                        #print(f"REC: Received have message for piece index {payload}")
                        # with self.general_update_lock:
                        #     if payload in self.chunks_left:
                        #         peer_obj.available_chunks.append(payload)
                        try:
                            filepath = payload.get('filepath')
                            piece_index = payload.get('piece_index')
                            print(f"REC: Received have message for file {filepath} with piece index {piece_index}")
                            if filepath and piece_index is not None and payload in self.chunks_left:
                                peer_obj.available_chunks.append(payload)
                        except Exception as e:
                            print(f"ERROR: Failed to process have message: {e}")

                    elif message_type == 'request':
                        #print(f"REC: Received request message for piece index {payload}")
                        # with peer_obj.queue_lock:
                        #     if payload not in peer_obj.request_queue and len(peer_obj.request_queue) < self.max_councurrent_request:
                        #         peer_obj.request_queue.append(payload)
                        
                        try:
                            # Validate payload format
                            if not isinstance(payload, dict) or 'filepath' not in payload or 'piece_index' not in payload:
                                print("ERROR: Invalid payload format received.")
                                return  # Ignore invalid payloads
                            print(f"REC: Received request message for file {payload.get('filepath')} with piece index {payload.get('piece_index')}")

                            with peer_obj.queue_lock:
                                # Add to queue if not already present and queue limit not exceeded
                                if payload not in peer_obj.request_queue and len(peer_obj.request_queue) < self.max_councurrent_request:
                                    peer_obj.request_queue.append(payload)
                                    print(f"INFO - Peer {peer_obj.ID}: Added request to queue. Current queue size: {len(peer_obj.request_queue)}")
                                else:
                                    print(f"INFO - Peer {peer_obj.ID}: Request ignored. Either already in queue or queue is full. Current queue size: {len(peer_obj.request_queue)}")
                        except Exception as e:
                            print(f"ERROR: Exception while processing request: {e}")

                    elif message_type == 'piece':
                        #print("REC: Received message for piece index", payload, "from peer with ID:", peer_obj.ID)
                        filepath = payload['filepath']
                        piece_index = payload['piece_index']
                        chunk_data = payload['chunk_data']

                        if chunk_data is None or chunk_data == b'':
                            continue

                        # Get payload info
                        chunk_metadata = {key: payload[key] for key in ['filepath', 'piece_index']}

                        with self.general_update_lock:
                            # might use this later
                            # for neighbour_peer in self.peer_list:
                            #     if payload in neighbour_peer.available_chunks:
                            #         neighbour_peer.available_chunks.remove(payload)

                            if chunk_metadata in self.chunks_left:

                                self.save_chunk_to_local_storage(filepath, piece_index, chunk_data)
                                
                                self.downloaded += 1 #here we download the whole piece
                                self.chunks_downloaded.append(chunk_metadata)
                                self.left -= 1
                                self.chunks_left.remove(chunk_metadata)

                                if peer_obj.ID not in self.count:
                                    self.count[peer_obj.ID] = 1
                                else:
                                    self.count[peer_obj.ID] += 1


                                self.have_queue.append((chunk_metadata, peer_obj.ID))

                                for neighbour_peer in self.peer_list:
                                    if chunk_metadata in neighbour_peer.available_chunks:
                                        neighbour_peer.available_chunks.remove(chunk_metadata) 

                                if self.left == 0:
                                    print("REC: Download complete")
                                    #Make a HTTP GET request to the tracker with the event 'completed'

                                    params = {
                                    "info_hash": self.info_hash,
                                    "ip": "127.0.0.1",  # Your IP address
                                    "peer_id": self.peer_id,  #Assign a unique peer ID
                                    "port": self.port,  # Port your client listens on for incoming peer connections
                                    "downloaded": self.downloaded,
                                    # "downloaded": self.downloaded,
                                    "left": self.left,  # Placeholder for the amount left to download
                                    # "compact": 1, #reserved for future use
                                    "event": "completed"
                                    }
                                    
                                    response = requests.get(self.URL, params=params)
                                    self.chunks_downloaded.sort(key=lambda x: x['piece_index'])
                                    print(f"Downloaded pieces: {len(self.chunks_downloaded)}, duplicates: {self.duplicate}")
                                    #print('sorted Downloaded:', self.chunks_downloaded, 'length:', len(self.chunks_downloaded))
                                    print('number of pieces for each peer:', self.count)
                                    for peer in self.peer_list:
                                        print("available chunks for peer with ID:", peer.ID," ", peer.available_chunks)
                                    
                                    time.sleep(1)
        
                            else:
                                #print("REC: Received duplicate piece message")
                                with self.duplicate_lock:
                                    self.duplicate += 1
                            
                            #break
                    else:
                        print("REC: Received unknown message", message)
                except Exception as e:
                    with peer_obj.live_lock:
                        peer_obj.is_alive = False
                    print(f"Error receiving message: {e}")
                    break

        print("REC: Receive closed for peer with ID:", peer_obj.ID,'\n')
                


            

            

    
    def Accepting_request(self):
        accept_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        accept_socket.bind(('localhost', self.port))
        accept_socket.listen(20)

        self.primary_accept_socket = accept_socket

        print(f"Listening on port {self.port}")

        while self.alive:
            readable, _, _ = select.select([accept_socket], [], [], 0.2) # Check if the socket is readable
            if readable:

                neighbour_peer_socket, addr = accept_socket.accept()
                with self.condition:
                    sub_thread = Thread(target=self.Handle_Neighbour_Peer, args=(neighbour_peer_socket,)).start()
                    self.condition.wait()






    #Function to read a torrent file and initilaizes the variable
    def Read_Torrent(self, torrent_file):
        if self.seeder:
            try:
                
                with open(torrent_file, "r") as file:
                    torrent_data = json.load(file)

                    # Extract the base folder or file name
                    base_name = torrent_data['info']['name']

                    if len(torrent_data['info']['files']) == 1 and base_name == torrent_data['info']['files'][0]['path'][0]:
                        # Single-file torrent
                        file_info = torrent_data["info"]["files"][0]
                        filepath = base_name
                        pieces = file_info["pieces"]
                        
                        # Add payload: {"filepath": path/name, "piece_index": } to chunk_left
                        for piece in pieces:
                            if {"filepath": filepath, "piece_index": piece["index"]} not in self.chunks_left:
                                self.chunks_downloaded.append({"filepath": filepath, "piece_index": piece["index"]})
                    else:
                        # Multi-file torrent (folder with files)
                        for file_info in torrent_data["info"]["files"]:
                            filepath = os.path.join(base_name, *file_info["path"])
                            pieces = file_info["pieces"]

                            # Add payload: {"filepath": path/name, "piece_index": } to chunk_left
                            for piece in pieces:
                                if {"filepath": filepath, "piece_index": piece["index"]} not in self.chunks_left:
                                    self.chunks_downloaded.append({"filepath": filepath, "piece_index": piece["index"]})
            except Exception as e:
                print(f"ERRROR: Seeder failed to load torrent file: {e}")
                return False
        else:
            try:
                with open(torrent_file, "r") as file:
                    torrent_data = json.load(file)

                    self.piece_length = torrent_data["info"]["piece length"]
                    self.URL = torrent_data["tracker"]

                    # Extract the base folder or file name
                    base_name = torrent_data['info']['name']

                    if len(torrent_data['info']['files']) == 1 and base_name == torrent_data['info']['files'][0]['path'][0]:
                        # Single-file torrent
                        file_info = torrent_data["info"]["files"][0]
                        filepath = base_name
                        pieces = file_info["pieces"]
                        self.add_file(filepath, pieces)                         # Add file to the client's local temp storage
                        
                        # Add payload: {"filepath": path/name, "piece_index": } to chunk_left
                        for piece in pieces:
                            if {"filepath": filepath, "piece_index": piece["index"]} not in self.chunks_left:
                                self.chunks_left.append({"filepath": filepath, "piece_index": piece["index"]})
                    else:
                        # Multi-file torrent (folder with files)
                        for file_info in torrent_data["info"]["files"]:
                            filepath = os.path.join(base_name, *file_info["path"])
                            pieces = file_info["pieces"]
                            self.add_file(filepath, pieces)     # Add file to the client's local temp storage

                            # Add payload: {"filepath": path/name, "piece_index": } to chunk_left
                            for piece in pieces:
                                if {"filepath": filepath, "piece_index": piece["index"]} not in self.chunks_left:
                                    self.chunks_left.append({"filepath": filepath, "piece_index": piece["index"]})
                    
                    self.left = len(self.chunks_left)
                    print(f"INFO: Total chunks to download: {self.left}.")
                    return True

            except Exception as e:
                print(f"ERRROR: Failed to load torrent file: {e}")
                return False
            

    def read_chunk(self, filepath, piece_index):
        try:
            # Check if the file exists
            if not os.path.exists(filepath):
                print(f"ERROR: File {filepath} does not exist.")
                return None
            
            # Get the size of the file
            file_length = os.path.getsize(filepath)
            
            # Calculate the start position and size of the chunk
            piece_start = piece_index * self.piece_length
            piece_size = min(self.piece_length, file_length - piece_start)

            # Validate the piece index and size
            if piece_start >= file_length or piece_size <= 0:
                print(f"ERROR: Invalid piece index {piece_index} for file {filepath}.")
                return None

            # Open the file and read the chunk
            with open(filepath, 'rb') as f:
                f.seek(piece_start)  # Move to the start of the chunk
                chunk_data = f.read(piece_size)  # Read the chunk data

            print(f"INFO: Successfully read chunk from {filepath} (index: {piece_index}, size: {piece_size} bytes).")
            return chunk_data

        except Exception as e:
            print(f"ERROR: Exception while reading chunk from {filepath}: {e}")
            return None
    

    def add_file(self, filepath, pieces_list):
        new_file = File(filepath, pieces_list)
        self.local_storage.append(new_file)


    def save_chunk_to_local_storage(self, filepath, piece_index, chunk_data):
        file = next((f for f in self.local_storage if f.filepath == filepath), None)
        if file:
            expected_hash = file.pieces_list[piece_index]['hash']
            piece_hash = hashlib.sha1(chunk_data).hexdigest()

            if piece_hash == expected_hash:
                local_file_path = os.path.join(file.output_directory, file.filepath)
                os.makedirs(os.path.dirname(local_file_path), exist_ok=True)

                piece_path = local_file_path + f'_{piece_index}'
                with open(piece_path, 'wb') as out_file:
                    out_file.write(chunk_data)

                file.verified_pieces_data[piece_index] = filepath + f'_{piece_index}'

                print(f"INFO - Piece {piece_index} for file '{file.filepath}' verified and stored.")
                
                # If all pieces are verified, write out the file
                if file.is_complete():
                    with self.time_lock:
                        for peer in self.peer_list:
                            peer.timer_stop = True
                    file.write_full_file_to_local(file.output_directory)
                    print(f"INFO - All pieces for file '{file.filepath}' are verified. File written to output.")
                    with self.time_lock:
                        for peer in self.peer_list:
                            peer.timer_stop = False
            else:
                print(f"ERRO: Hash mismatch for piece {piece_index} of file '{file.filepath}'.")
        else:
            print(f"ERROR: File {filepath} does not exist in local temporary storage.")


    # Check if the peer request are from the same torrent
    def Check_Peer_Request(self, message):
        #return True if message has the same info hash
        if message[28:48].decode('utf-8') == self.info_hash:
            return True
        return False
    
    def send_all(self, sock, data):
        # First send the size of the data
        if sock is None or sock.fileno() == -1:
            return
        data_size = len(data)

        sock.sendall(struct.pack('!I', data_size) + data)  #might add + data


    def receive_all(self, sock):
        # First receive the size of the data
        data = sock.recv(4)
        if not data:
            print('socket has closed connection\n')
            return None
        data_size = struct.unpack('!I', data)[0]
        # Then receive the actual data
        data = b''
        while len(data) < data_size:
            part = sock.recv(data_size - len(data))
            if not part:
                raise Exception("Socket connection broken, failed to retrieve data")
            data += part
        return data


    #This function is handle the intial handshake process
    def Handle_Neighbour_Peer(self, peer_socket: socket.socket):
        message = self.receive_all(peer_socket)
        # do some checking to see if the peer is requesting correctly
        # else kill the connection
        if not self.Check_Peer_Request(message):
            print("Invalid request")
            peer_socket.shutdown()
            with self.condition:
                self.condition.notify()
            return
        
        with self.counter_lock:
            self.current_peer_number += 1
            if self.current_peer_number < self.max_peer_number: 
                with self.condition:
                    self.condition.notify()    #Allow the accept thread to continue, if the limit is not reached

        IP = None
        port = None
        print(message)
        id = message[48:68].decode('utf-8')
        print(f"Accept connect from peer {IP}:{port} with ID: {id}")

        new_neighbour = Neighbour_Peer(IP, port, id, peer_socket)

        with self.general_update_lock: #to synchronize the chunks_downloaded with have messages
            self.peer_list.append(new_neighbour)

            #send available chunks along with protocol message
            # pstrlen = 19                #The same signature for the protocol
            # pstr = b"BitTorrent protocol"
            # reserved = b"\x00" * 8
            # send_data = struct.pack("!B", pstrlen) + pstr + reserved + str(self.info_hash).encode() + struct.pack(f'!{len(self.chunks_downloaded)}I', *self.chunks_downloaded)
            # self.send_all(peer_socket, send_data)

            packed_data = b''
            for payload in self.chunks_downloaded:
                filepath_bytes = payload['filepath'].encode('utf-8')
                filepath_length = len(filepath_bytes)
                piece_index = payload['piece_index']

                # Format: [filepath length (4 bytes)][filepath (variable)][piece_index (4 bytes)]
                packed_data += struct.pack(f'!I{filepath_length}sI', filepath_length, filepath_bytes, piece_index)

            # Add protocol string and send the packed message
            pstrlen = 19  # The protocol string length
            pstr = b"BitTorrent protocol"
            reserved = b"\x00" * 8
            # Final message includes protocol info and packed piece info
            send_data = struct.pack("!B", pstrlen) + pstr + reserved + str(self.info_hash).encode() + packed_data
            print(f"SEND DATA: {send_data}")
            self.send_all(peer_socket, send_data)

        #receive the available chunks from the peer
        data = self.receive_all(peer_socket)
        if self.Check_Peer_Request(data):
            print(f"Received handshake response. Total length: {len(data)} bytes.")
            response = data[48:]

            # Unpacking the data
            available_chunks = []
            offset = 0
            while offset < len(response):
                # Extract filepath length
                filepath_length = struct.unpack('!I', response[offset:offset + 4])[0]
                offset += 4

                # Extract filepath
                filepath = response[offset:offset + filepath_length].decode('utf-8')
                offset += filepath_length

                # Extract piece index
                piece_index = struct.unpack('!I', response[offset:offset + 4])[0]
                offset += 4

                # Add the extracted payload to available_chunks
                available_chunks.append({"filepath": filepath, "piece_index": piece_index})

            # print(f"INFO: Unpacked available chunks: {available_chunks}")
            # downloaded_unpacked = list(struct.unpack(f'!{len(response) // 4}I', response))

            # print(f"Unpacked downloaded: {downloaded_unpacked}")
            
            with self.general_update_lock:
                new_neighbour.available_chunks = [chunk for chunk in available_chunks if chunk not in self.chunks_downloaded]
        
       

        #after this handle the message from the peer 

        #includes keep-alive, choke, unchoke, interested, not interested, have, bitfield, request, piece, cancel

        send_thread = Thread(target=self.Send_, args=(peer_socket, new_neighbour))
        receive_thread = Thread(target=self.Receive_, args=(peer_socket, new_neighbour))

        send_thread.start()
        receive_thread.start()

        send_thread.join()
        receive_thread.join()


        #After we're done with the neighbour decrease the count variable 
        with self.counter_lock:
            peer_socket.close()
            self.current_peer_number -= 1 
            if self.current_peer_number < self.max_peer_number:
                with self.condition:
                    self.condition.notify()
         


    def announce_to_tracker(self, ip, event=None):
        """
        :param event: The event type ('started', 'completed', 'stopped') or None.
        """
        try:
            params = {
                "info_hash": self.info_hash,
                "ip": ip,
                "peer_id": self.peer_id,
                "port": self.port,
                "uploaded": self.uploaded,
                "downloaded": self.downloaded,
                "left": self.left,
                "event": event
            }
            response = requests.get(self.URL, params=params)
            if response.status_code == 200:
                print(f"INFO: Successfully announced to tracker with event '{event}'.")
            else:
                print(f"ERROR: Failed to announce to tracker with event '{event}', HTTP {response.status_code}.")
        except Exception as e:
            print(f"ERROR: Exception during tracker announcement: {e}")
        



    def Connect_torrent(self):
        try:
            params = {
            "info_hash": self.info_hash,
            "ip": "127.0.0.1",  # Your IP address
            "peer_id": self.peer_id,  #Assign a unique peer ID
            "port": self.port,  # Port your client listens on for incoming peer connections
            "downloaded": self.downloaded,
            # "downloaded": self.downloaded,
            "left": self.left,  # Placeholder for the amount left to download
            # "compact": 1, #reserved for future use
            "event": "started"
            }
            
            response = requests.get(self.URL, params=params)
            
            if response.status_code == 200 and len(response.content) >= 2:
                self.parse_tracker_response(response.content)
            else:
                print("Failed to connect to tracker", response)

        except Exception as e:
            print('Error connecting to the server', e)


    def parse_tracker_response(self, response):
        peers = []
        # Parse the JSON response
        try:
            response_data = json.loads(response)
            print(response_data)
            
            # Extract the peer list
            if "peer_list" in response_data:
                for peer_info in response_data["peer_list"]:
                    # Assuming each peer_info dict contains 'ip' and 'port'
                    ip = peer_info.get('ip')  # Extracting IP address
                    port = peer_info.get('port')  # Extracting port number
                    id = peer_info.get('peer_id')  # Extracting ID
                    print(f'Receieve info: {ip}, {port}, {id}')
                    
                    if ip and port is not None:  # Ensure both IP and port are available
                        peers.append(Neighbour_Peer(ip, port, id))

            with self.general_update_lock:
                self.peer_list = peers
                self.top_four_peer = peers[:4]  # Keep the top 4 peers
        
        except json.JSONDecodeError:
            print("Failed to decode JSON response")
        except Exception as e:
            print("An error occurred while parsing the tracker response:", e)



    def save_local_storage(self):
        for file_obj in self.local_storage:
            try:
                # Construct the full file path
                file_path = os.path.join(file_obj.output_directory, file_obj.filepath)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)

                # Save each chunk separately
                for i, piece_path in enumerate(file_obj.verified_pieces_data):
                    # if piece_path is not None and isinstance(piece_path, str):
                    #     file_obj.verified_pieces_data[i] = None
                    if piece_path is not None and not isinstance(piece_path, str):
                        chunk_data = piece_path
                        piece_path = file_path + f'_{i}'
                        with open(piece_path, 'wb') as out_file:
                            out_file.write(chunk_data)
                        file_obj.verified_pieces_data[i] = None
                        print(f"INFO: Chunk {i} of file '{file_obj.filepath}' saved to '{piece_path}'.")
                    # else:
                    #     print(f"WARNING: Chunk {i} of file '{file_obj.filepath}' is missing. Skipping.")
                    
                print(f"INFO: File '{file_obj.filepath}' saved to '{file_obj.output_directory}'.")
            except Exception as e:
                print(f"ERROR: Failed to save file '{file_obj.filepath}': {e}")



    # Load all binary chunk files into local storage and remove the chunk files afterward.
    def load_local_storage(self):
        for file_obj in self.local_storage:
            try:
                # Construct the base file path
                file_path = os.path.join(file_obj.output_directory, file_obj.filepath)

                # Load chunks from saved files
                for i in range(len(file_obj.pieces_list)):
                    piece_path = file_path + f'_{i}'
                    if os.path.exists(piece_path):
                        # with open(piece_path, 'rb') as chunk_file:
                        file_obj.verified_pieces_data[i] = str(piece_path)
                        # os.remove(piece_path)  # Remove the chunk file after loading
                        print(f"INFO: Loaded chunk {i} of file '{file_obj.filepath}' from '{piece_path}'.")
                    # else:
                    #     print(f"WARNING: Chunk file '{piece_path}' not found. Assuming missing chunk.")
                    
                # Check if all pieces are now verified
                if file_obj.is_complete():
                    print(f"INFO: File '{file_obj.filepath}' is fully loaded and complete.")
                else:
                    print(f"INFO: File '{file_obj.filepath}' loaded but still incomplete.")
            except Exception as e:
                print(f"ERROR: Failed to load file '{file_obj.filepath}': {e}")






    # Before connecting peers must perform a handshake protocol
    # The handshake process, and the exchange of information is not final

    # May change in the future
    def connect_to_peers(self):
        threads_and_sock = []
        for instance in reversed(self.peer_list):
            try:
                peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                peer_socket.connect((instance.IP, instance.port))


                print(f"Connected to peer {instance.IP}:{instance.port}")
                
                try:
                    response = self.perform_handshake(peer_socket)
                    print(f"Received handshake response. Total length: {len(response)} bytes.")

                    # Unpacking the data
                    available_chunks = []
                    offset = 0
                    while offset < len(response):
                        # Extract filepath length
                        filepath_length = struct.unpack('!I', response[offset:offset + 4])[0]
                        offset += 4

                        # Extract filepath
                        filepath = response[offset:offset + filepath_length].decode('utf-8')
                        offset += filepath_length

                        # Extract piece index
                        piece_index = struct.unpack('!I', response[offset:offset + 4])[0]
                        offset += 4

                        # Add the extracted payload to available_chunks
                        available_chunks.append({"filepath": filepath, "piece_index": piece_index})

                    # print(f"INFO: Unpacked available chunks: {available_chunks}")
                    # downloaded_unpacked = list(struct.unpack(f'!{len(response) // 4}I', response))

                    # print(f"Unpacked downloaded: {downloaded_unpacked}")
                    
                    with self.general_update_lock:
                        instance.available_chunks = [chunk for chunk in available_chunks if chunk not in self.chunks_downloaded]
                    #Here we only consider the chunks that is useful to us


                    #Start the send and receive threads
                    interested_message = messParser.construct_interested()
                    self.send_all(peer_socket, interested_message)
                    send_thread = Thread(target=self.Send_, args=(peer_socket, instance))
                    receive_thread = Thread(target=self.Receive_, args=(peer_socket, instance))

                    send_thread.start()
                    receive_thread.start()
                    
                    with self.general_update_lock:
                        instance.Set_sock(peer_socket)  #apply the socket to the peer

                    threads_and_sock.append((send_thread, receive_thread, peer_socket))

                except Exception as e:
                    print(f"Failed to perform handshake with peer {instance.IP}:{instance.port} - {e}\n\n")
                    self.peer_list.remove(instance)
                    peer_socket.close()
                    

            except Exception as e:
                print(f"Failed to connect to peer {instance.IP}:{instance.port} - {e}\n\n")
                #delete the failed peer
                self.peer_list.remove(instance)
                
                # new_thread = Thread(target=self.handling_peer, args=(peer_socket, instance))
                # new_thread.start()


        # for instance in self.peer_list:      #debugging
        #     print(instance.available_chunks)

        for thread in threads_and_sock:
            thread[0].join()
            thread[1].join()
            thread[2].close()
        


    # Handshake between 2 peers
        
    def perform_handshake(self, peer_socket):
        pstrlen = 19
        pstr = b"BitTorrent protocol"
        reserved = b"\x00" * 8
        handshake = struct.pack("!B", pstrlen) + pstr + reserved + str(self.info_hash).encode() + self.peer_id.encode()
        
        self.send_all(peer_socket, handshake)
        response = self.receive_all(peer_socket)
        
        if self.Check_Peer_Request(response): # Check if they have the protocol string
            print("Handshake successful")
            #inform the peer of our own available chunks
            packed_data = b''
            for payload in self.chunks_downloaded:
                filepath_bytes = payload['filepath'].encode('utf-8')
                filepath_length = len(filepath_bytes)
                piece_index = payload['piece_index']

                # Format: [filepath length (4 bytes)][filepath (variable)][piece_index (4 bytes)]
                packed_data += struct.pack(f'!I{filepath_length}sI', filepath_length, filepath_bytes, piece_index)

            # Add protocol string and send the packed message
            pstrlen = 19  # The protocol string length
            pstr = b"BitTorrent protocol"
            reserved = b"\x00" * 8
            # Final message includes protocol info and packed piece info
            send_data = struct.pack("!B", pstrlen) + pstr + reserved + str(self.info_hash).encode() + packed_data
            print(f"SEND DATA: {send_data}")
            self.send_all(peer_socket, send_data)
            # with self.general_update_lock:
            #     send_data = struct.pack("!B", pstrlen) + pstr + reserved + str(self.info_hash).encode() + struct.pack(f'!{len(self.chunks_downloaded)}I', *self.chunks_downloaded)
            #     self.send_all(peer_socket, send_data)

            return response[48:]  # Return the available chunks
        else:
            print("Handshake failed")


    
    def Main(self):
        message = input('server or client ')
        if message == 'seeder':
            print(f"INFO: Seeder initialized with {len(self.chunks_downloaded)} pieces.")
            self.Accepting_request()
        elif message == 'client1':
            print(f"INFO: Client initialized with {len(self.chunks_left)} remaining chunks.")

            # Connect to the tracker and peers
            print(f"INFO: Connecting to tracker at {self.URL}...")
            self.Connect_torrent()

            # Connect to peers if the peer list is populated
            if self.peer_list:
                print(f"INFO: Connecting to peers from the tracker...")
                self.connect_to_peers()
            else:
                print(f"ERROR: No peers found from the tracker.")
        elif message == 'client2':
            self.downloaded = 0
            self.left = 3000
            self.chunks_left = [i for i in range(3000)]
            self.chunks_downloaded = []
            accept_thread = Thread(target=self.Accepting_request).start()    #This should start as a thread
            self.Connect_torrent(self.URL) 
            self.connect_to_peers()
        elif message == 'client3':
            self.downloaded = 0
            self.left = 3000
            self.chunks_left = [i for i in range(3000)]
            self.chunks_downloaded = []
            print(self.port)
            #measurement_thread = Thread(target=self.Measure_download_speed).start()
            self.Connect_torrent(self.URL)
            #after we have obtained peer_list, we can connect to the peers
            if self.peer_list:
                self.connect_to_peers()
        # go = input('go ')
        # if go == 'server':
        #     self.Accepting_request()
        # elif go == 'client':
        #     self.connect_to_peers()
        input('exit')

port = input('port ')    

a = Peer(int(port), 'torrents/ubuntu-22.04.4-desktop-amd64.iso.torrent.json', seeder=False)
a.Main()






















#note the main peer doesnt have a live lock yet, may cause issues