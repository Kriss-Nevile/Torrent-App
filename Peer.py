from threading import Thread, Condition, Lock
import select
import socket
import time
import http
import requests
import struct
from enum import Enum
import json

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




class State(Enum):
    am_choking = 0 # this client is choking the peer
    am_interested = 1 # this client is interested in the peer
    peer_choking = 2 # peer is choking this client
    peer_interested = 3 # peer is interested in this client


# A class to store all information about the neighbour peer

class Neighbour_Peer:
    def __init__(self, IP, port, ID):
        self.IP = IP
        self.port = port
        self.ID = ID
        self.send_staus = State.am_choking
        self.recveive_status = State.peer_choking
        self.available_chunks = []
        self.is_alive = True  #a non alive neighbour peer would be removed from the peer list 


class Peer:

    def __init__(self, port):
        self.max_peer_number = 20
        self.counter_lock = Lock()
        self.current_peer_number = 0
        self.port = port
        self.condition = Condition() # this is to halt the accepting socket if the number of socket have reached 
        # the maximum --> might remove this feature in the future
        self.primary_accept_socket = None
        self.alive = True
        self.peer_id = 100
        self.info_hash = 100
        self.peer_list = [Neighbour_Peer]
        self.uploaded = 0
        self.downloaded = 100    # used to store a list of downloaded chunks
        self.left = 100
        self.URL = 'https://simple-like-torrent-application.vercel.app/'
        #self.block_all = False ( might use later idk )

    def Main(self):
        self.Connect_torrent(self.URL)

    
    def Accepting_request(self):
        accept_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        accept_socket.bind('0.0.0.0', self.port)
        accept_socket.listen(20)

        self.primary_accept_socket = accept_socket

        while self.alive:
            readable, _, _ = select([accept_socket], [], [], 0.2)
            if readable:

                neigbour_peer_socket = accept_socket.accept()
                with self.condition:
                    sub_thread = Thread(target=self.Handle_Neighbour_Peer, args=[neigbour_peer_socket,]).start()
                    self.condition.wait()






    #Function to read a torrent file and initilaizes the variable
    def Read_Torrent(self): 
        pass

    # Check if the peer request are from the same torrent
    def Check_Peer_Request(self):
        pass


    def Handle_Neighbour_Peer(self, peer_socket: socket.socket):
        message = peer_socket.recv(68)
        # do some checking to see if the peer is requesting correctly
        # else kill the connection
        if not self.Check_Peer_Request():
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
        id = None

        new_neighbour = Neighbour_Peer(IP, port, id)

        self.peer_list.append(new_neighbour)

        while new_neighbour.is_alive: 
            pass #do something

        #set block_all to False, when current_peer_number < max_peer_number
        #After we're done with the neighbour decrease the count variable 
        with self.counter_lock:
            self.current_peer_number -= 1 
            if self.current_peer_number < self.max_peer_number:
                with self.condition:
                    self.condition.notify()
         


        
        



    def Connect_torrent(self, URL):
        try:
            params = {
            "info_hash": self.info_hash,
            "peer_id": self.peer_id,
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
                print("Failed to connect to tracker")

        except Exception as e:
            print('Error connecting to the server', e)


    def parse_tracker_response(self, response):
        peers = []
        
        # Parse the JSON response
        try:
            response_data = json.loads(response)
            
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
        
        except json.JSONDecodeError:
            print("Failed to decode JSON response")
        except Exception as e:
            print("An error occurred while parsing the tracker response:", e)





    # Before connecting peers must perform a handshake protocol
    # The handshake process, and the exchange of information is not final

    # May change in the future
    def connect_to_peers(self):
        for instance in self.peer_list:
            try:
                peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                peer_socket.connect((instance.IP, instance.port))
                avai_chunks = self.perform_handshake(peer_socket)

                instance.available_chunks = avai_chunks
            except Exception as e:
                print(f"Failed to connect to peer {instance.IP}:{instance.port} - {e}")



    # Handshake between 2 peers
        
    def perform_handshake(self, peer_socket):
        pstrlen = 19
        pstr = b"BitTorrent protocol"
        reserved = b"\x00" * 8
        handshake = struct.pack("B", pstrlen) + pstr + reserved + self.info_hash + self.peer_id
        
        peer_socket.send(handshake)
        response = peer_socket.recv(68)
        
        if response[:20] == handshake[:20]:
            print("Handshake successful")
        else:
            print("Handshake failed")


        

a = Peer(1121)
a.Main()

