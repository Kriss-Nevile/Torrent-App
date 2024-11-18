import struct

def construct_keep_alive():
    return struct.pack('!I', 0)

def construct_choke():
    return struct.pack('!IB', 1, 0)

def construct_unchoke():
    return struct.pack('!IB', 1, 1)

def construct_interested():
    return struct.pack('!IB', 1, 2)

def construct_not_interested():
    return struct.pack('!IB', 1, 3)

def construct_have(piece_index):
    return struct.pack('!IBI', 5, 4, piece_index)

def construct_request(piece_index):
    return struct.pack('!IBI', 9, 6, piece_index)

def construct_piece(piece_index):
    return struct.pack('!IBI', 9, 7, piece_index)

def construct_piece_with_data(piece_index,  block):
    length = len(block)
    return struct.pack('!IBI' + str(length) + 's', 9 + length, 7, piece_index, block)
#reserve for later use

def parse_message(message):
    length = struct.unpack('!I', message[:4])[0]
    if length == 0:
        return 'keep-alive', None
    message_id = struct.unpack('!B', message[4:5])[0]
    if message_id == 0:
        return 'choke', None
    elif message_id == 1:
        return 'unchoke', None
    elif message_id == 2:
        return 'interested', None
    elif message_id == 3:
        return 'not interested', None
    elif message_id == 4:
        piece_index = struct.unpack('!I', message[5:])[0]
        return 'have', piece_index
    elif message_id == 6:
        piece_index = struct.unpack('!I', message[5:])[0]
        return 'request', piece_index
    elif message_id == 7:
        piece_index = struct.unpack('!I', message[5:])[0]
        return 'piece', piece_index
    else:
        return 'unknown', None