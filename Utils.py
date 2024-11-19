from enum import Enum
import socket
import time
from threading import Thread, Lock, Condition




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
        self.timer_stop = False
        self.send_status = State.am_choking #start condition
        self.receive_status = State.peer_choking #start condition
        self.available_chunks = []
        self.request_queue = []  #maximum 100 pending requests
        self.is_alive = True  #a non alive neighbour peer would be removed from the peer list 
        self.last_message_time = time.time()
        self.live_lock = Lock()
        self.time_lock = Lock()
        self.send_lock = Lock()
        self.receive_lock = Lock()
        self.queue_lock = Lock()
        #self.noted = False
        self.sock = sock


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
            return self.recveive_status == State.peer_interested

    def update_receive_status(self, status):
        with self.receive_lock:
            self.receive_status = status    
    
    def update_time(self):
        with self.live_lock:
            self.last_message_time = time.time()
    
    def get_time(self):
        with self.time_lock:
            return self.last_message_time
    
    def Set_sock(self, sock):
        self.sock = sock



def reassemble_file(pieces):
    # Sort pieces by their index
    sorted_pieces = sorted(pieces, key=lambda x: x[0])
    # Concatenate the blocks in order
    file_data = b''.join(block for _, block in sorted_pieces)
    return file_data





def Time_out(neighbour_peer: Neighbour_Peer):
    while neighbour_peer.Check_alive():
        if neighbour_peer.timer_stop:
            neighbour_peer.update_time
        elif time.time() - neighbour_peer.last_message_time > 60:
            with neighbour_peer.live_lock:
                neighbour_peer.is_alive = False
                print('Time out for peer with ID: ', neighbour_peer.ID, 'waiting for shutdown')
                break
        time.sleep(1)


#These are not used yet
def Download_rate(neighbour_peer):
    while neighbour_peer.is_alive:
        time.sleep(1)
        with neighbour_peer.live_lock:
            if neighbour_peer.is_alive:
                print('Download rate for peer with ID: ', neighbour_peer.ID, 'is: ', len(neighbour_peer.send_track))
                neighbour_peer.send_track = []
            else:
                break


def Upload_rate(neighbour_peer):
    while neighbour_peer.is_alive:
        time.sleep(1)
        with neighbour_peer.live_lock:
            if neighbour_peer.is_alive:
                print('Upload rate for peer with ID: ', neighbour_peer.ID, 'is: ', len(neighbour_peer.request_queue))
            else:
                break