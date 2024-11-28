from threading import Thread, Condition, Lock, Event
import select
import socket
import time
import random
import requests
from urllib.parse import urlencode
import struct 
import json
from datetime import datetime
import messParser
from Utils import State, Neighbour_Peer, Time_out, Get_IP, Download_rate
import os
import hashlib


# Import Configuration
import config
from config import timestamped_print as print


PIECE_SIZE, OUTPUT_DIR, TRACKER_URL = config.read_config()
# OUTPUT_DIR = 'downloadeds' 


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


#Avoid nested locks at all costs --> if it is inevitable, always lock in the same order
#A Problem i called phantom dependency --> a send lock shouldnt be in the recive lock



class Peer:

    def __init__(self, port, torrent_file="", seeder=False):
        #self.timer_stop = False   deprecated, I dont even remember what this was for
        self.torrent_file = torrent_file
        self.seeder = seeder
        self.max_peer_number = 20
        self.counter_lock = Lock()
        #self.live_lock = Lock() Deprecated, may not used
        self.current_peer_number = 0 
        self.port = port
        self.queue_lock = Lock()
        self.time_lock = Lock()
        self.piece_thread_lock = Lock()
        self.live_lock = Lock()
        self.stop_event = Event()
        self.interested_but_blocked = []
        # self.have_lock = Lock()
        #self.have_queue = []
        self.general_update_lock = Lock()
        self.completed = seeder
        self.max_councurrent_request = 20
        self.condition = Condition() # this is to halt the accepting socket if the number of socket have reached 
        # the maximum --> might remove this feature in the future
        self.primary_accept_socket = None
        self.alive = True
        self.peer_id = datetime.now().strftime("%H%M%S%f") + str(random.randint(10000000, 99999999)) #generate a unique peer id
        self.info_hash = None #20 bytes
        self.max_unchoked_peers = 4 #doesnt include the random one
        self.peer_list = []
        self.unchoked_peer = [] #we're implementing 4 + 1 algorithm
        #self.peer_list.append(Neighbour_Peer('localhost', self.port, 'self_peer')) #for testing purposes
        self.uploaded = 0
        self.downloaded = 0 #number of bytes downloaded
        self.chunks_downloaded = []   # used to keep track of the chunks downloaded, we if need to get size, we can use len(downloaded)
        self.left = 0
        self.chunks_left = []
        self.duplicate = 0
        self.duplicate_lock = Lock()
        self.URL = None
        self.upload_speed = 0 #in MB/s
        self.uploaded = 0
        self.previous_time = time.time()
        self.stats_lock = Lock() #use for download and upload speed, currently only upload speed is implemented
        self.count = {}
        self.piece_thread = 0
        self.send_track = set()
        self.send_track_lock = Lock()
        self.local_storage = []
        self.start_time = time.time() #track total execution time
        self.total_execution_time = 0
        # self.is_paused = False
        # Torrent data:
        self.piece_length = PIECE_SIZE  # default
        #self.URL = TRACKER_URL             # default
        self.IP = Get_IP()

        if torrent_file != "":
            self.Read_Torrent(torrent_file)

    def add_to_set(self, piece_index):
        with self.send_track_lock:
            self.send_track.add(piece_index)

    def In_set(self, piece_index):
        with self.send_track_lock:
            return piece_index in self.send_track
        
    def clear_set(self, piece_index):
        with self.send_track_lock:
            self.send_track.clear()

    def Check_alive(self):
        with self.live_lock:
            return self.alive
    
    def Turn_off(self):
        with self.live_lock:
            self.alive = False
    
    def Update_chunks_uploaded(self):
        with self.stats_lock:
            self.uploaded += 1
    

    def Upload_rate(self):
        with self.stats_lock:
            self.upload_speed = self.uploaded * PIECE_SIZE / ((time.time() - self.previous_time) * (1024 * 1024))
            self.uploaded = 0
            self.previous_time = time.time()

    
    def Get_Peer_Speed_Info(self):
        download_percent = 0
        download_array = []
        current_upload_speed = self.Upload_rate()
            # print(f"General Upload speed: {current_upload_speed:.2f} MB/s")
        with self.general_update_lock:
            for peer in self.peer_list:
                Download_rate = peer.current_download_rate()
                download_array.append((peer.ID, Download_rate))
                # print(f"Downloaded speed for peer with ID {peer.ID}: {Download_rate:.2f} MB/s")
            download_percent = (self.downloaded / (self.downloaded + self.left)) * 100
        
        return current_upload_speed, download_percent, download_array

    #if a peer has available chunks, send an interested message
    #if a peer has no available chunks, send a not interested message
    def Check_available_peers(self, socket: socket.socket, peer_obj: Neighbour_Peer):
        while peer_obj.Check_alive():
            # print('length of available chunks:', len(peer_obj.available_chunks), 'for peer with ID:', peer_obj.ID)
            try:
                if not peer_obj.Check_receive_status() and peer_obj.has_chunks():
                    interested_message = messParser.construct_interested()
                    with peer_obj.queue_send_lock:
                        peer_obj.control_queue.append(interested_message)
                    #print('sent interested message to peer with ID:', peer_obj.ID)
                elif peer_obj.Check_receive_status() and not peer_obj.has_chunks():
                    not_interested_message = messParser.construct_not_interested()
                    with peer_obj.queue_send_lock:
                        peer_obj.control_queue.append(not_interested_message) 
                    #print('peer status:', peer_obj.receive_status)
                    #print('sent not interested message to peer with ID:', peer_obj.ID)

            except Exception as e:
                print(f"Connection has been closed: {e}")

            time.sleep(3) #sending a few choke message more than necessary is not a big deal
        print('Check available peers closed for peer with ID:', peer_obj.ID,'\n')

    
    def Keep_alive(self, peer_socket, peer_obj: Neighbour_Peer):
        while peer_obj.Check_alive():
            if time.time() - peer_obj.get_time() > 20 and not peer_obj.Check_send_status() and peer_obj.has_chunks():
                keep_alive_message = messParser.construct_keep_alive()
                with peer_obj.queue_send_lock:
                    peer_obj.control_queue.append(keep_alive_message)
            time.sleep(20)
        print('Keep alive closed for peer with ID:', peer_obj.ID,'\n')

    
    def Request_thread(self, peer_socket, peer_obj: Neighbour_Peer):
        while peer_obj.Check_alive():

            if self.left != 0 and peer_obj.Check_receive_status():
                length = 0
                with peer_obj.available_lock:
                    length = len(peer_obj.available_chunks)
                    requests = random.sample(peer_obj.available_chunks, min(self.max_councurrent_request, length))

                stop = True
                for request in requests:
                    if self.In_set((request['piece_index'], request['filepath'])): continue
                    stop = False
                    request_message = messParser.construct_request(request['filepath'], request['piece_index'])
                    with peer_obj.queue_send_lock:
                        peer_obj.request_queue.append(request_message)
                    self.add_to_set((request['piece_index'], request['filepath']))
                    
                # if not stop: print('request for peer with ID:', peer_obj.ID,' was sent') 

                #     time.sleep(0.05 * length) #if all the chunks are already in the set, wait for 5 seconds
                #     with self.send_track_lock:
                #         self.send_track.clear()

            time.sleep(0.5)
        
        print('Request thread closed for peer with ID:', peer_obj.ID,'\n')



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


    #implement 4 + 1 peer selection algorithm
    def Tit_for_tat(self): 
        while self.Check_alive():
            # Sort peers based on the number of pieces they have sent
            remove = []
            with self.general_update_lock: 
                if len(self.peer_list) > self.max_unchoked_peers + 1:
                    for peer in self.peer_list: peer.toggle_modifying()

                    self.peer_list.sort(reverse=True)
                    new_peers = self.peer_list[:self.max_unchoked_peers]
                    if self.peer_list[self.max_unchoked_peers:]:
                        new_peers += random.sample(self.peer_list[self.max_unchoked_peers:], 1)
                    for peers in self.unchoked_peer:
                        if peers not in new_peers:
                            remove.append(peers)

                    self.unchoked_peer = new_peers
                    #move 4 top peers to back of list
                    self.peer_list = self.peer_list[self.max_unchoked_peers:] + self.peer_list[:self.max_unchoked_peers]
                    #to avoid extreme cases where new peers are not selected

                    for peer in self.peer_list: peer.toggle_modifying()  
                    print('new unchoked peers after tit for tat', self.unchoked_peer)
            
            for peer in remove:
                peer.update_send_status(State.am_choking)
                with peer.queue_send_lock:
                    peer.control_queue.append(messParser.construct_choke())

            time.sleep(15)  # Re-evaluate every 15 seconds
        


    #Function to send data
    def Send_(self, peer_socket, peer_obj: Neighbour_Peer):
        print('start sending to peer with ID:', peer_obj.ID,'\n')

        check_thread = Thread(target=self.Check_available_peers, args=(peer_socket, peer_obj))
        keep_alive_thread = Thread(target=self.Keep_alive, args=(peer_socket, peer_obj))
        request_thread = Thread(target=self.Request_thread, args=(peer_socket, peer_obj))
        download_speed_thread = Thread(target=Download_rate, args=(peer_obj,))

        check_thread.start()
        keep_alive_thread.start()
        request_thread.start()
        download_speed_thread.start()
        
        while peer_obj.Check_alive():
            with peer_obj.queue_send_lock:
                if peer_obj.control_queue:
                    for control in reversed(peer_obj.control_queue):
                        self.send_all(peer_socket, control)
                        peer_obj.control_queue.remove(control)
                    #print('sent', control[1], 'message to peer with ID:', peer_obj.ID)
                    peer_obj.update_time()
            # time.sleep(0.5)
            # with peer_obj.queue_send_lock:
                if peer_obj.have_queue:
                    for have in reversed(peer_obj.have_queue):
                        self.send_all(peer_socket, have)
                        peer_obj.have_queue.remove(have)
                        #print('sent have message for index', have, 'to peer with ID:', peer_obj.ID)
                    peer_obj.update_time()
            # time.sleep(0.5)
            # with peer_obj.queue_send_lock:
                if peer_obj.request_queue:      
                    for request in reversed(peer_obj.request_queue):
                        self.send_all(peer_socket, request)
                        peer_obj.request_queue.remove(request)
                    peer_obj.update_time()
                    # print('request sent to peer with ID:', peer_obj.ID)
            # time.sleep(0.5)
            # with peer_obj.queue_send_lock:
                if peer_obj.piece_queue:
                    for piece in reversed(peer_obj.piece_queue):
                        data = self.handle_request(piece[0], piece[1])    
                        if data is not None: self.send_all(peer_socket, data)
                        peer_obj.piece_queue.remove(piece) 
                        self.Update_chunks_uploaded()
                    # print('sending piece to peer with ID:', peer_obj.ID)
                    peer_obj.update_time()


            time.sleep(1)
        
        while not peer_obj.send_closes:
            time.sleep(1)
        
        peer_socket.close()
            # if peer_obj in self.unchoked_peer:
            #     self.unchoked_peer.remove(peer_obj)
            #     filtered = [peer for peer in self.peer_list if peer not in self.unchoked_peer]
            #     if filtered: self.unchoked_peer.append(random.choice(filtered))

        check_thread.join()
        keep_alive_thread.join()    
        request_thread.join()
        download_speed_thread.join()

        with self.general_update_lock:
            self.peer_list.remove(peer_obj)


        print("SEND: Cleared peer object and Send closed for peer with ID:", peer_obj.ID,'\n')





    def Measure_upload_speed(self):
        while self.Check_alive():
            with self.stats_lock:
                upload_speed = self.uploaded * 0.512 / (time.time() - self.previous_time)
                self.uploaded = 0
                self.previous_time = time.time()
                print(f"INFO: Upload speed: {upload_speed:.2f} MB/s")
            time.sleep(3)


    def handle_request(self, filepath, piece_index):
        try:
            chunk_data = None

                    # Check if the chunk is in local storage
            file_obj = next((f for f in self.local_storage if f.filepath == filepath), None)
            if file_obj:
                if 0 <= piece_index < len(file_obj.verified_pieces_data):
                    piece_path = file_obj.verified_pieces_data[piece_index]
                    chunk_data = None
                    if piece_path is not None:
                        piece_path = os.path.join(file_obj.output_directory, piece_path)
                        if os.path.exists(piece_path):
                            with open(piece_path, 'rb') as chunk_file:
                                chunk_data = chunk_file.read()

                    if chunk_data is None: pass
                        #print(f"INFO: Chunk for file '{filepath}', index {piece_index} not yet verified in local storage from")
                else:
                    print(f"ERROR: Invalid piece index {piece_index} for file '{filepath}' in local storage.")
            else: pass
                #print(f"INFO: File '{filepath}' not found in local storage. Reading directly from file.")

            # If not found or verified in local storage, read directly from file
            if chunk_data is None:
                #print('start reading chunks')
                chunk_data = self.read_chunk(filepath, piece_index)
                #print('Reading done')
            
            if chunk_data is not None:        
                piece_message = messParser.construct_piece(filepath, piece_index, chunk_data)
                return piece_message
            else:
                return None

        except Exception as e:
            print(f"ERROR: Exception while processing request: {e}")


    # def Putting_pieces(self, payload, filepath, piece_index, peer_obj: Neighbour_Peer):
    #     chunk_data = self.handle_request(payload, filepath, piece_index)
    #     if chunk_data is not None:        
    #         #with peer_obj.queue_lock:
    #             # Add to queue if not already present and queue limit not exceeded
    #             #if payload not in peer_obj.request_queue and peer_obj.request_queue.qsize() < self.max_councurrent_request:
    #                 piece_message = messParser.construct_piece(filepath, piece_index, chunk_data)
    #                 peer_obj.request_queue.put(piece_message)
    #                 #print('putting piece message to queue (now has size)', peer_obj.request_queue.qsize())


    def receive_queue(self, peer_socket, peer_obj: Neighbour_Peer):
        print('start receive Queue from peer with ID:', peer_obj.ID,'\n')

        time_out_thread = Thread(target=Time_out, args=(peer_obj,)).start()

        while peer_obj.Check_alive():
            readable, _, _ = select.select([peer_socket], [], [], 0.01)
            if readable:
                try:
                    message = self.receive_all(peer_socket)
                    if message is None:
                        with peer_obj.live_lock:
                            peer_obj.is_alive = False
                        break
                    peer_obj.update_time()
                    message_type, payload = messParser.parse_message(message)
                    with peer_obj.queue_receive_lock:
                        if message_type == 'request':
                            peer_obj.receive_request_queue.append(payload)
                        elif message_type == 'have':   
                            peer_obj.receive_have_queue.append(payload)
                        elif message_type == 'piece':
                            peer_obj.receive_piece_queue.append(payload)
                        else:
                            peer_obj.receive_control_queue.append((payload, message_type))

                except Exception as e:
                    with peer_obj.live_lock:
                        peer_obj.is_alive = False
                    print(f"Error receiving message: {e}")
                    break

        print("REC: Receive Queue closed for peer with ID:", peer_obj.ID,'\n')

                
    
    #Function to receive data
    def Receive_(self, peer_socket, peer_obj: Neighbour_Peer):
        receive_queue_thread = Thread(target=self.receive_queue, args=(peer_socket, peer_obj)).start()
        
        message_queue = []
        meta_data_list = []

        while peer_obj.Check_alive():
            with peer_obj.session_lock:
                with peer_obj.queue_receive_lock:
                    # print('piece queue for peer with ID:', peer_obj.ID, 'have size:', len(peer_obj.receive_piece_queue))
                    while peer_obj.receive_control_queue:
                        payload, message_type = peer_obj.receive_control_queue.pop()
                        # print('received', message_type, 'message from peer with ID:', peer_obj.ID)
                        if message_type == 'keep-alive': pass
                        elif message_type == 'choke':
                            # print('REC: Received choke message from peer with ID:', peer_obj.ID)
                            peer_obj.update_receive_status(State.peer_choking)
                        elif message_type == 'unchoke':
                            peer_obj.update_receive_status(State.peer_interested)
                            # print('REC: Received unchoke message from peer with ID:', peer_obj.ID)
                        elif peer_obj in self.unchoked_peer and message_type == 'interested':
                            # print('REC: Received interested message from peer with ID:', peer_obj.ID)
                            unchoke_message = messParser.construct_unchoke()
                            message_queue.append(unchoke_message)
                            peer_obj.update_send_status(State.am_interested)
                        else:
                            # print('REC: Received not interested message from peer with ID:', peer_obj.ID)
                            choke_message = messParser.construct_choke()
                            message_queue.append(choke_message)
                            peer_obj.update_send_status(State.am_choking)

                with peer_obj.queue_send_lock:
                    peer_obj.control_queue += message_queue
                    message_queue.clear()

                with peer_obj.queue_receive_lock:
                    while peer_obj.receive_have_queue:
                        payload = peer_obj.receive_have_queue.pop()
                        if self.left == 0: continue
                        try:
                            filepath = payload.get('filepath')
                            piece_index = payload.get('piece_index')
                            # print(f"REC: Received have message for file {filepath} with piece index {piece_index} from peer with ID: {peer_obj.ID}")
                            if filepath and piece_index is not None and payload in self.chunks_left:
                                peer_obj.add_chunk(payload)
                        except Exception as e:
                            print(f"ERROR: Failed to process have message: {e}")
                with peer_obj.queue_receive_lock:
                    while peer_obj.receive_request_queue:
                        payload = peer_obj.receive_request_queue.pop()
                        if not isinstance(payload, dict) or 'filepath' not in payload or 'piece_index' not in payload:
                            print("ERROR: Invalid payload format received.")
                            # Ignore invalid payloads
                        else:
                            #print(f"REC: Received request message for file {payload.get('filepath')} with piece index {payload.get('piece_index')}")
                            filepath = payload.get('filepath')
                            piece_index = payload.get('piece_index')
                            message_queue.append((filepath, piece_index))

                with peer_obj.queue_send_lock:    
                    peer_obj.piece_queue += message_queue
                    message_queue.clear()

                with peer_obj.queue_receive_lock:
                    while peer_obj.receive_piece_queue:
                        payload = peer_obj.receive_piece_queue.pop()               
                        filepath = payload['filepath']
                        piece_index = payload['piece_index']
                        chunk_data = payload['chunk_data']
                        #print("REC: Received message for piece index", piece_index, "from peer with ID:", peer_obj.ID)
                        if chunk_data is None or chunk_data == b'':
                            continue

                        # Get payload info
                        chunk_metadata = {key: payload[key] for key in ['filepath', 'piece_index']}
                        have = False
                        with self.general_update_lock:
                            if chunk_metadata in self.chunks_left:
                                have = True
                                self.save_chunk_to_local_storage(filepath, piece_index, chunk_data)
                                
                                self.downloaded += 1 #here we download the whole piece
                                self.chunks_downloaded.append(chunk_metadata)
                                self.left -= 1
                                self.chunks_left.remove(chunk_metadata)

                        if have:
                            if peer_obj.ID not in self.count:  #doesnt need a lock since it is only accessed by this thread
                                self.count[peer_obj.ID] = 1
                            else:
                                self.count[peer_obj.ID] += 1

                            have_message = messParser.construct_have(filepath, piece_index)
                            message_queue.append(have_message)
                            meta_data_list.append(chunk_metadata)

                            peer_obj.Update_chunks_downloaded()

                            # for neighbour_peer in self.peer_list:
                            #     with neighbour_peer.available_lock:
                            #         if chunk_metadata in neighbour_peer.available_chunks:
                            #             neighbour_peer.available_chunks.remove(chunk_metadata)
                                
                        else:
                            with self.duplicate_lock:
                                self.duplicate += 1
            
            with self.general_update_lock:
                peer_copy = self.peer_list #reference to the peer list, because update is to be reflected in the peer list

            for peer in peer_copy:
                with peer.session_lock:
                    if peer.sock is not None and peer_obj.ID != peer.ID:
                        with peer.queue_send_lock:
                            peer.have_queue += message_queue  # Send have message to all peers except the sender
                    set_meta_data = {frozenset(d.items()) for d in meta_data_list}
                    with peer.available_lock:
                        peer.available_chunks = [
                            x for x in peer.available_chunks if frozenset(x.items()) not in set_meta_data
                        ]
            
            with self.general_update_lock:
                if not self.completed and self.left == 0:
                    self.completed = True
                    self.total_execution_time = time.time() - self.start_time
                    print("DOWNLOAD COMPLETED -- NOW SEEDING")
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
            
            message_queue.clear()
            meta_data_list.clear()


                # else:       been here a long time
                #     print("REC: Received unknown message", payload)
            
            time.sleep(1)
        peer_obj.send_closes = True #to notify the send thread that the receive thread has closed
        print("REC: Receive closed for peer with ID:", peer_obj.ID,'\n')
            
            

            

    
    def Accepting_request(self):
        accept_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        accept_socket.bind(('0.0.0.0', self.port))
        accept_socket.listen(20)

        self.primary_accept_socket = accept_socket

        print(f"Listening on port {self.port}")

        while self.Check_alive():
            readable, _, _ = select.select([accept_socket], [], [], 0) # Check if the socket is readable
            if readable:

                neighbour_peer_socket, addr = accept_socket.accept()
                with self.condition:
                    sub_thread = Thread(target=self.Handle_Neighbour_Peer, args=(neighbour_peer_socket,)).start()
                    self.condition.wait()

        #release the socket
        accept_socket.close()
        print("Accepting request closed\n")






    #Function to read a torrent file and initilaizes the variable
    def Read_Torrent(self, torrent_file):
        with open(torrent_file, "r") as file:
            torrent_data = json.load(file)

        self.URL = torrent_data['tracker']

        # Extract the base folder or file name
        base_name = torrent_data['info']['name']
        self.info_hash = hashlib.sha1(json.dumps(torrent_data['info']).encode()).hexdigest()
        
        if self.seeder:
            try:

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
                            
                    self.downloaded = len(self.chunks_downloaded)
            except Exception as e:
                print(f"ERRROR: Seeder failed to load torrent file: {e}")
                return False
        else:
            try:
                    # self.piece_length = torrent_data["info"]["piece length"]

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
                    
                    
                    
                    self.load_local_storage()
                    print('----------------------------------------------------')
                    for file in self.local_storage:
                        print(file.filepath)
                    print('----------------------------------------------------')
                    print(self.chunks_left)
                    print('----------------------------------------------------')
                    print(self.chunks_downloaded)
                    print('----------------------------------------------------')
                    print(len(self.chunks_downloaded))
                    print('----------------------------------------------------')

                    self.downloaded = len(self.chunks_downloaded)
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

            #print(f"INFO: Successfully read chunk from {filepath} (index: {piece_index}, size: {piece_size} bytes).")
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

                #print(f"INFO - Piece {piece_index} for file '{file.filepath}' verified and stored.")
                
                # If all pieces are verified, write out the file
                if file.is_complete():
                    write_thread = Thread(target=file.write_full_file_to_local, args=(file.output_directory,))
                    write_thread.start()
                    #print(f"INFO - All pieces for file '{file.filepath}' are verified. File written to output.")
            else:
                print(f"ERRO: Hash mismatch for piece {piece_index} of file '{file.filepath}'.")
        else:
            print(f"ERROR: File {filepath} does not exist in local temporary storage.")


    # Check if the peer request are from the same torrent
    def Check_Peer_Request(self, message):
        #return True if message has the same info hash 40 bytes now
        if message[28:68].decode('utf-8') == self.info_hash:
            return True
        return False
    
    def send_all(self, sock: socket.socket, data):
        # First send the size of the data
        try:
            # First send the size of the data
            if sock is None or sock.fileno() == -1:
                print("Socket is not connected or already closed")
                return

            data_size = len(data)
            packed_data = struct.pack('!I', data_size) + data


            # Set the socket to non-blocking mode
            sock.setblocking(False)

            total_sent = 0
            while total_sent < len(packed_data):
                try:
                    sent = sock.send(packed_data[total_sent:])
                    if sent == 0:
                        raise RuntimeError("Socket connection broken")
                    total_sent += sent
                except BlockingIOError:
                    # If the socket is non-blocking and the send would block, wait a bit and try again
                    time.sleep(0.01)
        except socket.error as e:
            print(f"Socket error occurred: {e}")
        except Exception as e:
            print(f"Unexpected error occurred: {e}")
        finally:
            # Set the socket back to blocking mode
            sock.setblocking(True)

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
            try:
                part = sock.recv(data_size - len(data))
                if not part:
                    raise Exception("Socket connection broken, failed to retrieve data")
                data += part
            except socket.error as e:
                if e.errno == 10035:  # WSAEWOULDBLOCK
                    continue
                else:
                    raise
        return data


    #This function is handle the intial handshake process
    def Handle_Neighbour_Peer(self, peer_socket: socket.socket):
        message = self.receive_all(peer_socket)
        # do some checking to see if the peer is requesting correctly
        # else kill the connection
        if not self.Check_Peer_Request(message):
            print("Invalid request")
            peer_socket.close()
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
        id = message[68:88].decode('utf-8')
        print(f"Accept connect from peer {IP}:{port} with ID: {id}")

        new_neighbour = Neighbour_Peer(IP, port, id, peer_socket)

        with self.general_update_lock: #to synchronize the chunks_downloaded with have messages
            self.peer_list.append(new_neighbour)
            if len(self.unchoked_peer) <= self.max_unchoked_peers:  #account for the extra unchoked peer
                self.unchoked_peer.append(new_neighbour)

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
            response = data[68:]

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
            "ip": self.IP,  # Your IP address
            "peer_id": self.peer_id,  #Assign a unique peer ID
            "port": self.port,  # Port your client listens on for incoming peer connections
            "downloaded": self.downloaded,
            # "downloaded": self.downloaded,
            "left": self.left,  # Placeholder for the amount left to download
            # "compact": 1, #reserved for future use
            "event": "started"
            }
            
            response = requests.get(self.URL, params=params) #useful when peer is not a seeder 
            if self.left != 0:
                if response.status_code == 200 and len(response.content) >= 2:
                    self.parse_tracker_response(response.content)
                else:
                    print("Failed to connect to tracker", response)
            else:
                print('already have the file')
                params = {
                "info_hash": self.info_hash,
                "ip": self.IP,  # Your IP address
                "peer_id": self.peer_id,  #Assign a unique peer ID
                "port": self.port,  # Port your client listens on for incoming peer connections
                "downloaded": self.downloaded,
                # "downloaded": self.downloaded,
                "left": self.left,  # Placeholder for the amount left to download
                # "compact": 1, #reserved for future use
                "event": "completed"
                }
                requests.get(self.URL, params=params)  #doesnt need to parse the response

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
                print('Got list,', self.peer_list)
                self.unchoked_peer = self.peer_list[:min(self.max_unchoked_peers + 1, len(self.peer_list))] 
        
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

                if os.path.exists(file_path):
                    # Load chunks from saved files
                    for i in range(len(file_obj.pieces_list)):
                        piece_path = file_path + f'_{i}'
                        file_obj.verified_pieces_data[i] = str(piece_path)
                        # Remove payloay if exists in chunk_left
                        if {"filepath": file_obj.filepath, "piece_index": i} in self.chunks_left:
                            self.chunks_left.remove({"filepath": file_obj.filepath, "piece_index": i})
                            self.chunks_downloaded.append({"filepath": file_obj.filepath, "piece_index": i})
                    print(f"INFO: Loaded file '{file_obj.filepath}' from {file_path}.")
                else:
                    # Load chunks from saved pieces
                    for i in range(len(file_obj.pieces_list)):
                        piece_path = file_path + f'_{i}'

                        if os.path.exists(piece_path):
                            file_obj.verified_pieces_data[i] = str(piece_path)
                            # Remove payloay if exists in chunk_left
                            if {"filepath": file_obj.filepath, "piece_index": i} in self.chunks_left:
                                self.chunks_left.remove({"filepath": file_obj.filepath, "piece_index": i})
                                self.chunks_downloaded.append({"filepath": file_obj.filepath, "piece_index": i})
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
        print("Connecting to peers...", self.peer_list)
        threads = []
        self.start_time = time.time() #the start time is when the client starts to connect to the peers
        for instance in reversed(self.peer_list):
            try:
                peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                peer_socket.connect((instance.IP, instance.port))


                print(f"Connected to peer {instance.IP}:{instance.port}")
                
                try:
                    response = self.perform_handshake(peer_socket)
                    if response is None:
                        print(f"Failed to perform handshake with peer {instance.IP}:{instance.port}")
                        self.peer_list.remove(instance)
                        peer_socket.close()
                        continue
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

                    # print('available chunks:', instance.available_chunks)
                    # print('instance chunks:', instance.available_chunks)
                    #Here we only consider the chunks that is useful to us


                    #Start the send and receive threads
                    # interested_message = messParser.construct_interested()
                    # self.send_all(peer_socket, interested_message)
                    with self.general_update_lock:
                        instance.Set_sock(peer_socket)  #apply the socket to the peer



                    send_thread = Thread(target=self.Send_, args=(peer_socket, instance))
                    receive_thread = Thread(target=self.Receive_, args=(peer_socket, instance))

                    send_thread.start()
                    receive_thread.start()
                    


                    threads.append((send_thread, receive_thread))

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

        for thread in threads:
            thread[0].join()
            thread[1].join()
            
        


    # Handshake between 2 peers
        
    def perform_handshake(self, peer_socket):
        pstrlen = 19
        pstr = b"BitTorrent protocol"
        reserved = b"\x00" * 8
        handshake = struct.pack("!B", pstrlen) + pstr + reserved + str(self.info_hash).encode() + self.peer_id.encode()
        
        self.send_all(peer_socket, handshake)
        response = self.receive_all(peer_socket)

        if response is None:
            return None
        
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
            print(f"SEND DATA: {send_data} \n\n\n")
            self.send_all(peer_socket, send_data)
            # with self.general_update_lock:
            #     send_data = struct.pack("!B", pstrlen) + pstr + reserved + str(self.info_hash).encode() + struct.pack(f'!{len(self.chunks_downloaded)}I', *self.chunks_downloaded)
            #     self.send_all(peer_socket, send_data)

            return response[68:]  # Return the available chunks
        else:
            print("Handshake failed")
            return None
    
    # def Pause(self):
    #     with self.general_update_lock:
    #         self.is_paused = True
    #         for peer in self.peer_list:
    #             peer.Turn_off()
        
    #     while True:
    #         with self.general_update_lock:
    #             if self.peer_list: time.sleep(1)  #wait for all the threads to close
    #             else: break
        
    #     print('The torrent is paused')

    # def Resume(self):
    #     good = False
    #     with self.general_update_lock:
    #         if self.is_paused:
    #             self.is_paused = False
    #             good = True
    #         else:
    #             print('The torrent is not paused')
    #     if good:
    #         self.Connect_torrent()  #reconnnect all
    #         self.connect_to_peers()
        

    def Exit_torrent(self):
        if self.completed: print('Exit the torrent gracefully')
        else: print('Exit the torrent without completing the download')

        with self.general_update_lock:
            for peer in self.peer_list:
                peer.Turn_off()  #set is alive to false for all peers
                #delete all the data in it's queue
            
            self.Turn_off()
            #all it's threaa will then turned off automatically
        #send a stopped event to the tracker

        params = {
                "info_hash": self.info_hash,
                "ip": self.IP,  # Your IP address
                "peer_id": self.peer_id,  #Assign a unique peer ID
                "port": self.port,  # Port your client listens on for incoming peer connections
                "downloaded": self.downloaded,
                # "downloaded": self.downloaded,
                "left": self.left,  # Placeholder for the amount left to download
                # "compact": 1, #reserved for future use
                "event": "stopped"
                }
        requests.get(self.URL, params=params)
        


    
    def Main(self):
        print('chunks left:', self.left)
        print('start the peer main thread')
        input('ready?')
        if self.seeder:
            accept_thread = Thread(target=self.Accepting_request)
            accept_thread.start()
            tit_for_tat = Thread(target=self.Tit_for_tat)
            tit_for_tat.start()
            self.Connect_torrent()  # a seeder doesnt need to connect to other peers, i'll also send a completed event to the tracker
            #input('turn off?')
            # self.Exit_torrent()
            accept_thread.join()
            tit_for_tat.join()
        else:
            accept_thread = Thread(target=self.Accepting_request)
            accept_thread.start()
            tit_for_tat = Thread(target=self.Tit_for_tat)
            tit_for_tat.start()
            self.Connect_torrent()
            if self.peer_list:
                self.connect_to_peers()
            else:
                print('No peer available')
            accept_thread.join()
            tit_for_tat.join()
    
        print('The connection to torrent:', self.torrent_file, 'is closed')


# port = input('port ')
# if port == '1122': seeder = True
# else: seeder = False    

# a = Peer(int(port), 'torrents/Multi_Test.torrent.json', seeder)
# a.Main()






















#note the main peer doesnt have a live lock yet, may cause issues