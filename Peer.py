from threading import Thread, Condition, Lock, Event
import select
import socket
import time
import http
import random
import requests
from urllib.parse import urlencode
import struct
from enum import Enum
import json
from typing import List
from datetime import datetime
import messParser
from Utils import State, Neighbour_Peer, Time_out
import asyncio


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




class Peer:

    def __init__(self, port):
        self.max_peer_number = 20
        self.counter_lock = Lock()
        self.current_peer_number = 0
        self.port = port
        self.queue_lock = Lock()
        self.time_lock = Lock()
        self.stop_event = Event()
        self.general_update_lock = Lock()
        self.max_councurrent_request = 100
        self.condition = Condition() # this is to halt the accepting socket if the number of socket have reached 
        # the maximum --> might remove this feature in the future
        self.primary_accept_socket = None
        self.alive = True
        self.peer_id = None
        self.info_hash = '12345678901234567890' #20 bytes
        self.peer_list = []
        self.top_four_peer = []
        self.peer_list.append(Neighbour_Peer('localhost', self.port, 'self_peer')) #for testing purposes
        self.uploaded = 0
        self.downloaded = 10 #number of bytes downloaded
        self.chunks_downloaded = [0,1,2,3,4,5,6,7,8,9]   # used to keep track of the chunks downloaded, we if need to get size, we can use len(downloaded)
        self.left = 1 
        self.chunks_left = []
        self.duplicate = 0
        self.duplicate_lock = Lock()
        self.URL = 'https://simple-like-torrent-application.vercel.app/'
        #self.block_all = False ( might use later idk )
    


    #Function to send data
    def Send_(self, peer_socket, peer_obj: Neighbour_Peer):
        while peer_obj.Check_alive():
            try:
                #Send keep-alive message if no other message is sent for a certain period
                with self.general_update_lock:
                    if time.time() - peer_obj.get_time() > 20 and peer_obj.send_status == State.am_choking and len(peer_obj.available_chunks) != 0:
                        keep_alive_message = messParser.construct_keep_alive()
                        self.send_all(peer_socket, keep_alive_message)
                        print("SEND: Sent keep-alive message")
                        peer_obj.update_time()

                with self.general_update_lock:
                    if not peer_obj.noted and self.left == 0:
                        print('send track', peer_obj.send_track)
                        not_interested_message = messParser.construct_not_interested()
                        self.send_all(peer_socket, not_interested_message)
                        peer_obj.noted = True
                        peer_obj.update_time()
                
                with self.general_update_lock:
                    with peer_obj.receive_lock:

                        if self.left != 0 and peer_obj.receive_status == State.peer_interested:
                            unique_pieces = random.sample(peer_obj.available_chunks, min(self.max_councurrent_request, len(peer_obj.available_chunks)))


                            for piece_index in unique_pieces:
                                if piece_index in self.chunks_downloaded:
                                    peer_obj.available_chunks.remove(piece_index)
                                    continue
                                request_message = messParser.construct_request(piece_index)
                                self.send_all(peer_socket, request_message)
                                print(f"SEND: Sent request message for piece index {piece_index}")
                                peer_obj.update_time()



                # Send messages based on peer state
                if peer_obj.Check_send_status():
                    # Handle requests from the request queue
                    with peer_obj.queue_lock:
                        peer_obj.send_track.append(len(peer_obj.request_queue))
                        print('request queue:', peer_obj.request_queue)
                        for request in reversed(peer_obj.request_queue):
                            piece_message = messParser.construct_piece(request)
                            self.send_all(peer_socket, piece_message)
                            print(f"SEND: Sent piece message for request {request}")
                            peer_obj.request_queue.remove(request)
                            peer_obj.update_time()
                    # else:    #save for later use
                    #     # Send have message for a random piece
                    #     if peer_obj.available_chunks:
                    #         piece_index = random.choice(peer_obj.available_chunks)
                    #         have_message = messParser.construct_have(piece_index)
                    #         self.send_all(peer_socket, have_message)
                    #         print(f"SEND: Sent have message for piece index {piece_index}")
                    #         peer_obj.last_message_time = time.time()
                    #     else:
                    #         # Send not interested message if no pieces are available
                    #         not_interested_message = messParser.construct_not_interested()
                    #         self.send_all(peer_socket, not_interested_message)
                    #         print("SEND: Sent not interested message")
                    #         peer_obj.last_message_time = time.time()
                    #         break

                time.sleep(1)  # Sleep to avoid busy waiting

            except Exception as e:
                with peer_obj.live_lock:
                    peer_obj.is_alive = False
                print(f"Error sending message: {e}")
                break

        print("SEND: Send closed for peer with ID:", peer_obj.ID, '\n')





    
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
                        print('send track', peer_obj.send_track)
                    elif message_type == 'have':
                        print(f"REC: Received have message for piece index {payload}")
                        peer_obj.available_chunks.append(payload)
                    elif message_type == 'request':
                        print(f"REC: Received request message for piece index {payload}")
                        with peer_obj.queue_lock:
                            if payload not in peer_obj.request_queue and len(peer_obj.request_queue) < self.max_councurrent_request:
                                peer_obj.request_queue.append(payload)
                    elif message_type == 'piece':
                        print("REC: Received message for piece index", payload, "from peer with ID:", peer_obj.ID)


                        with self.general_update_lock:
                            # might use this later
                            # for neighbour_peer in self.peer_list:
                            #     if payload in neighbour_peer.available_chunks:
                            #         neighbour_peer.available_chunks.remove(payload)

                            if payload in self.chunks_left:
                                    self.downloaded += 1 #here we download the whole piece
                                    self.chunks_downloaded.append(payload)
                                    self.left -= 1
                                    self.chunks_left.remove(payload)

                                    for neighbour_peer in self.peer_list:
                                        if payload in neighbour_peer.available_chunks:
                                            neighbour_peer.available_chunks.remove(payload) 

                                    if self.left == 0:
                                        print("REC: Download complete and send a not interested message")
                                        self.chunks_downloaded.sort()
                                        print('sorted Downloaded:', self.chunks_downloaded, 'length:', len(self.chunks_downloaded))
                                        print('number of duplicate:', self.duplicate)
            
                            else:
                                print("REC: Received duplicate piece message")
                                with self.duplicate_lock:
                                    self.duplicate += 1
                            
                            #break
                    else:
                        print("REC: Connection closed")
                        break
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
    def Read_Torrent(self): 
        pass

    # Check if the peer request are from the same torrent
    def Check_Peer_Request(self, message):
        #return True if message has the same info hash
        if message[28:48].decode('utf-8') == self.info_hash:
            return True
        return False
    
    def send_all(self, sock, data):
        # First send the size of the data
        data_size = len(data)
        sock.sendall(struct.pack('!I', data_size))
        # Then send the actual data
        sock.sendall(data)


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

        new_neighbour = Neighbour_Peer(IP, port, id)

        self.peer_list.append(new_neighbour)

        #send available chunks along with protocol message
        pstrlen = 19                #The same signature for the protocol
        pstr = b"BitTorrent protocol"
        send_data = struct.pack("!B", pstrlen) + pstr + struct.pack(f'!{len(self.chunks_downloaded)}I', *self.chunks_downloaded)
        self.send_all(peer_socket, send_data)
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
         


        
        



    def Connect_torrent(self, URL):
        try:
            self.peer_id = datetime.now().strftime("%H%M%S%f") + str(random.randint(10000000, 99999999))  # Generate a unique peer ID
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
            
            self.peer_list = peers
            self.top_four_peer = peers[:4]  # Keep the top 4 peers
        
        except json.JSONDecodeError:
            print("Failed to decode JSON response")
        except Exception as e:
            print("An error occurred while parsing the tracker response:", e)





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
                    print(f"Available chunks: {len(response)},  {response}")

                    # Unpacking the data
                    downloaded_unpacked = list(struct.unpack(f'!{len(response) // 4}I', response))

                    print(f"Unpacked downloaded: {downloaded_unpacked}")
                    
                    with self.general_update_lock:
                        instance.available_chunks = instance.available_chunks = [chunk for chunk in downloaded_unpacked if chunk not in self.chunks_downloaded]
                    #Here we only consider the chunks that is useful to us


                    #Start the send and receive threads
                    interested_message = messParser.construct_interested()
                    self.send_all(peer_socket, interested_message)
                    send_thread = Thread(target=self.Send_, args=(peer_socket, instance))
                    receive_thread = Thread(target=self.Receive_, args=(peer_socket, instance))

                    send_thread.start()
                    receive_thread.start()

                    threads_and_sock.append((send_thread, receive_thread, peer_socket))

                except Exception as e:
                    print(f"Failed to perform handshake with peer {instance.IP}:{instance.port} - {e}\n\n")

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
        input()


    def handling_peer(self, peer_socket, peer_obj: Neighbour_Peer):
        pass


    # Handshake between 2 peers
        
    def perform_handshake(self, peer_socket):
        pstrlen = 19
        pstr = b"BitTorrent protocol"
        reserved = b"\x00" * 8
        handshake = struct.pack("!B", pstrlen) + pstr + reserved + str(self.info_hash).encode() + self.peer_id.encode()
        
        self.send_all(peer_socket, handshake)
        response = self.receive_all(peer_socket)
        
        if response[:20] == handshake[:20]: # Check if they have the protocol string
            print("Handshake successful")
            return response[20:]  # Return the available chunks
        else:
            print("Handshake failed")


    
    def Main(self):
        message = input('server or client ')
        if message == 'server1':
            self.chunks_downloaded = [i for i in range(768)]
            self.Accepting_request()
        if message == 'server2':
            self.chunks_downloaded = [i for i in range(689, 1575)]
            self.Accepting_request()
        if message == 'server3':
            self.chunks_downloaded = [i for i in range(1450, 2000)]
            self.Accepting_request()
        elif message == 'client':
            self.downloaded = 0
            self.left = 2000
            self.chunks_left = [i for i in range(2000)]
            self.chunks_downloaded = []
            print(self.port)
            self.Connect_torrent(self.URL)
            #after we have obtained peer_list, we can connect to the peers
            if self.peer_list:
                self.connect_to_peers()
        # go = input('go ')
        # if go == 'server':
        #     self.Accepting_request()
        # elif go == 'client':
        #     self.connect_to_peers()

port = input('port ')    

a = Peer(int(port))
a.Main()

