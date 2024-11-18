PEICE_SIZE  = 512 * 1024     # Bytes
OUTPUT_DIR  = 'Download'     # Output directory
TRACKER_URL = 'https://simple-like-torrent-application.vercel.app/' # Default tracker


# Logging configuration
from datetime import datetime

old_print = print

def timestamped_print(*args, **kwargs):
  old_print(f"<{datetime.now()}> || ", *args, **kwargs)