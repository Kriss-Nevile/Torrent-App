import threading
import select
import Peer
import os



# CLI for input

def CLI():
    os.system('cls' if os.name == 'nt' else 'clear')
    while True:
        command = input('>>>> ')
        if command == 'exit' or command == '/e': break
        if command == 'create':
            pass
        elif command == 'connect':
            pass
        elif command == 'deamon':
            pass
        elif command == 'edit':
            pass
        elif command == 'edit':
            pass
        elif command == 'show':
            pass
        elif command == 'clear':
            os.system('cls' if os.name == 'nt' else 'clear')


cli = threading.Thread(target=CLI).start()



