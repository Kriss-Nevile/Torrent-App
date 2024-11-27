import json

CONFIG_PATH = 'config.json' #this is in the same directory as the main file

def read_config():
    with open(CONFIG_PATH, 'r') as file:
        config_data = json.load(file)
    PIECE_SIZE = config_data['PIECE_SIZE']
    TRACKER_URL = config_data['TRACKER_URL']
    OUTPUT_DIR = config_data['OUTPUT_DIR']
    
    return (PIECE_SIZE, OUTPUT_DIR, TRACKER_URL)

def write_config(choice, value):
  if choice == 1: #Update piece size
      #check if value is a number string
      if not value.isdigit():
          print("Invalid value for PIECE_SIZE. It should be a number.")
          return
      
      with open(CONFIG_PATH, 'r') as file:
          config_data = json.load(file)
      config_data['PIECE_SIZE'] = int(value)
      with open(CONFIG_PATH, 'w') as file:
          json.dump(config_data, file)

      print("Piece size updated")

  elif choice == 2: #Update output directory
      #check if value is a string
      with open(CONFIG_PATH, 'r') as file:
          config_data = json.load(file)
      config_data['OUTPUT_DIR'] = value
      with open(CONFIG_PATH, 'w') as file:
          json.dump(config_data, file)

      print("Output directory updated")

  elif choice == 3: #Update tracker url
      with open(CONFIG_PATH, 'r') as file:
          config_data = json.load(file)
      config_data['TRACKER_URL'] = value
      with open(CONFIG_PATH, 'w') as file:
          json.dump(config_data, file)
        
      print("Tracker URL updated")
    



# Logging configuration
from datetime import datetime

old_print = print

def timestamped_print(*args, **kwargs):
  old_print(f"<{datetime.now()}> || ", *args, **kwargs)