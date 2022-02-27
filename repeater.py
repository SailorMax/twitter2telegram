"""
Run twitter2telegram.py Z minutes
"""
import sys
import time
import twitter2telegram

# setup pause length
pause_duration = 0
if len(sys.argv) > 1:
    pause_duration = int(sys.argv[1])

if pause_duration <= 0:
    print("Error: Please, define pause duration in minutes in first argument")
    exit(1)
else:
    print("> Found user defined pause duration = " + str(pause_duration) + " minutes")

# loop
while True:
    try:
        twitter2telegram.transfer_newest_tweets()
        time.sleep( pause_duration*60 )
    except Exception as e:
        print(f"!!! Something wrong: {e}")
