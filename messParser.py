import struct

def construct_keep_alive():
    return struct.pack('!I', 0)

def construct_choke(_id=0):
    return struct.pack('!IB', 1, _id)

def construct_unchoke(_id=1):
    return struct.pack('!IB', 1, _id)

def construct_interested(_id=2):
    return struct.pack('!IB', 1, _id)

def construct_not_interested(_id=3):
    return struct.pack('!IB', 1, _id)

# def construct_have(piece_index):
#     return struct.pack('!IBI', 5, 4, piece_index)

# def construct_request(piece_index):     # parameters: payload['filepath'], payload['piece_index']
#     return struct.pack('!IBI', 9, 6, piece_index)

# def construct_piece(piece_index):       # parameters: payload['filepath'], payload['piece_index'], payload['piece_data']
#     return struct.pack('!IBI', 9, 7, piece_index)

def construct_have(filepath, piece_index, _id=4):
    filepath_bytes = filepath.encode('utf-8')
    filepath_length = len(filepath_bytes)
    # Format: [length (4 bytes)][id (1 byte)][filepath length (4 bytes)][filepath (variable)][piece_index (4 bytes)]
    return struct.pack(f'!IBI{filepath_length}sI', 5 + filepath_length + 4, _id, filepath_length, filepath_bytes, piece_index)

def construct_request(filepath, piece_index, _id=6):
    filepath_bytes = filepath.encode('utf-8')
    filepath_length = len(filepath_bytes)
    # Format: [length (4 bytes)][id (1 byte)][filepath length (4 bytes)][filepath (variable)][piece_index (4 bytes)]
    return struct.pack(f'!IBI{filepath_length}sI', 5 + filepath_length + 4, _id, filepath_length, filepath_bytes, piece_index)

def construct_piece(filepath, piece_index, chunk_data, _id=7):
    filepath_bytes = filepath.encode('utf-8')
    filepath_length = len(filepath_bytes)
    chunk_length = len(chunk_data)
    # Format: [length (4 bytes)][id (1 byte)][filepath length (4 bytes)][filepath (variable)][piece_index (4 bytes)][chunk_data (variable)]
    return struct.pack(f'!IBI{filepath_length}sI{chunk_length}s', 5 + filepath_length + 4 + chunk_length, _id, filepath_length, filepath_bytes, piece_index, chunk_data)


# def construct_piece(piece_index, begin, block):
#     length = len(block)
#     return struct.pack('!IBII' + str(length) + 's', 9 + length, 7, piece_index, begin, block)
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
        filepath_length = struct.unpack('!I', message[5:9])[0]
        filepath = message[9:9 + filepath_length].decode('utf-8')
        piece_index = struct.unpack('!I', message[9 + filepath_length:9 + filepath_length + 4])[0]
        return 'have', {'filepath': filepath, 'piece_index': piece_index}
    
    elif message_id == 6:
        filepath_length = struct.unpack('!I', message[5:9])[0]
        filepath = message[9:9 + filepath_length].decode('utf-8')
        piece_index = struct.unpack('!I', message[9 + filepath_length:9 + filepath_length + 4])[0]
        return 'request', {'filepath': filepath, 'piece_index': piece_index}
    
    elif message_id == 7:
        filepath_length = struct.unpack('!I', message[5:9])[0]
        filepath = message[9:9 + filepath_length].decode('utf-8')
        piece_index = struct.unpack('!I', message[9 + filepath_length:9 + filepath_length + 4])[0]
        chunk_data = message[9 + filepath_length + 4:]
        return 'piece', {'filepath': filepath, 'piece_index': piece_index, 'chunk_data': chunk_data}
    
    else:
        return 'unknown', None