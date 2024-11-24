from enum import Enum
import socket
import time
from threading import Thread, Lock, Condition
from queue import Queue
import psutil



class State(Enum):
    am_choking = 0 # this client is choking the peer
    am_interested = 1 # this client is interested in the peer
    peer_choking = 2 # peer is choking this client
    peer_interested = 3 # peer is interested in this client


# A class to store all information about the neighbour peer

class Neighbour_Peer:
    def __init__(self, IP, port, ID, sock=None):
        self.IP = IP
        self.port = port
        self.ID = ID
        #self.timer_stop = False   what was this for?
        self.send_status = State.am_choking #start condition
        self.receive_status = State.peer_choking #start condition
        self.available_chunks = []
        self.request_queue = []  #maximum 100 pending requests
        self.piece_queue = []
        self.control_queue = []  
        self.receive_control_queue = []  
        self.receive_request_queue = []  
        self.receive_piece_queue = [] 
        self.have_queue = []
        self.receive_have_queue = []
        self.is_alive = True  #a non alive neighbour peer would be removed from the peer list 
        self.last_message_time = time.time()
        self.live_lock = Lock()
        self.time_lock = Lock()
        self.send_lock = Lock()
        self.receive_lock = Lock()
        self.available_lock = Lock()
        self.queue_send_lock = Lock()
        self.queue_receive_lock = Lock()
        self.download_rate_lock = Lock()
        self.is_mod = False
        
        self.send_closes = False

        #self.noted = False
        self.sock = sock
        self.chunks_downloaded = 0
        self.last_time = time.time()
        self.download_rate = 0


    def __repr__(self):
        return self.__str__()
    
    def __str__(self):
        return f"Peer {self.ID}"

    def has_chunks(self):
        with self.available_lock:
            return len(self.available_chunks) > 0
    
    def remove_chunk(self, piece_index):
        with self.available_lock:
            self.available_chunks.remove(piece_index)

    def add_chunk(self, piece_index):
        with self.available_lock:
            self.available_chunks.append(piece_index)
    
    # def implicit_wait(self):
    #     print('enough was sent')
    #     time.sleep(0.3 * self.og_size) #in case some packets are lost, extremely rare
    #     #reset set
    #     self.send_track.clear()
    #     with self.available_lock:
    #         self.og_size = len(self.available_chunks)
    #     print('clear set for peer with ID: ', self.ID)
    
            # size = len(self.send_track)
        
        # with self.available_lock:
        #     chunk_size = len(self.available_chunks)

        # if size >= chunk_size:
        #     print('enough was sent')
        #     time.sleep(10) #in case some packets are lost, extremely rare 1(s) for every megabyte
        #     self.send_track.clear()
        #     print('clear set for peer with ID: ', self.ID)
            # this will block the request thread itself


    def Check_alive(self):
        with self.live_lock:
            return self.is_alive

    def Check_send_status(self):
        with self.send_lock:
            return self.send_status == State.am_interested
        
    def update_send_status(self, status):
        with self.send_lock:
            self.send_status = status
        
    def Check_receive_status(self):
        with self.receive_lock:
            return self.receive_status == State.peer_interested

    def update_receive_status(self, status):
        with self.receive_lock:
            self.receive_status = status    
    
    def update_time(self):
        with self.live_lock:
            self.last_message_time = time.time()
            #print(self.ID, 'time updated')
    
    def get_time(self):
        with self.time_lock:
            return self.last_message_time
    
    def Set_sock(self, sock):
        self.sock = sock

    def Update_chunks_downloaded(self):
        with self.download_rate_lock:
            self.chunks_downloaded += 1

    def toggle_modifying(self):
        with self.download_rate_lock:
            self.is_mod = not self.is_mod

    def is_mofifying(self):
        with self.download_rate_lock:
            return self.is_mod
    
    def __lt__(self, other):
        return self.download_rate < other.download_rate



def reassemble_file(pieces):
    # Sort pieces by their index
    sorted_pieces = sorted(pieces, key=lambda x: x[0])
    # Concatenate the blocks in order
    file_data = b''.join(block for _, block in sorted_pieces)
    return file_data





def Time_out(neighbour_peer: Neighbour_Peer):
    while neighbour_peer.Check_alive():
        if time.time() - neighbour_peer.last_message_time > 60:
            with neighbour_peer.live_lock:
                neighbour_peer.is_alive = False
                print('Time out for peer with ID: ', neighbour_peer.ID, 'waiting for shutdown')
                break
        time.sleep(1)


#used for statistics and implementation of 4 + 1 algorithm
def Download_rate(neighbour_peer: Neighbour_Peer):
    while neighbour_peer.Check_alive():
        while neighbour_peer.is_mofifying():
            time.sleep(0.1)
        with neighbour_peer.download_rate_lock:
            Download_rate = neighbour_peer.chunks_downloaded / (time.time() - neighbour_peer.last_time)
            neighbour_peer.download_rate = Download_rate
            neighbour_peer.last_time = time.time()
            neighbour_peer.chunks_downloaded = 0
        
        print('Download rate for peer with ID: ', neighbour_peer.ID, 'is: ', Download_rate)
        time.sleep(3) #update every 5 seconds
    
    print('Download rate closed for peer with ID: ', neighbour_peer.ID)


def Upload_rate(neighbour_peer):
    while neighbour_peer.is_alive:
        time.sleep(1)
        with neighbour_peer.live_lock:
            if neighbour_peer.is_alive:
                print('Upload rate for peer with ID: ', neighbour_peer.ID, 'is: ', len(neighbour_peer.request_queue))
            else:
                break

def Get_IP():
    net_if_addrs = psutil.net_if_addrs()
    address = None
    # Find the IP address of the Wi-Fi interface (typically 'Wi-Fi' on Windows or 'wlan0' on Linux)
    for interface, addrs_list in net_if_addrs.items():
        if interface == 'Wi-Fi':
            address = addrs_list[1].address
            break
    return address

