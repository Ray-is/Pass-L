# This python script is run on startup
# By the pico's MicroPython interpreter.
# This script will STOP running
# if you open the MicroPython REPL on serial
# via thonny or a VSCode extension.
from time import sleep
from machine import Pin
from mfrc522 import MFRC522

# Constants for keypad
KEYPAD_ENTER_KEY = "*"
KEYPAD_PASSWORD = "123"

# Keypad pins (initialized on creation)
# If we fail to initialize the pins, hang and print the error forever
try:
    KEYPAD_ROWS = [
        Pin(2, Pin.OPEN_DRAIN, 1),
        Pin(3, Pin.OPEN_DRAIN, 1),
        Pin(4, Pin.OPEN_DRAIN, 1),
        Pin(5, Pin.OPEN_DRAIN, 1)
    ]
    KEYPAD_COLS = [
        Pin(6, Pin.IN, Pin.PULL_UP),
        Pin(7, Pin.IN, Pin.PULL_UP),
        Pin(8, Pin.IN, Pin.PULL_UP),
        Pin(9, Pin.IN, Pin.PULL_UP)
    ]
except BaseException as e:
    while True:
        print(f"ERROR initializing keypad pins: {e}")
        sleep(5)

# RFID pin numbers (fed to third-party RFID class)
RFID_SCK = 18
RFID_MOSI = 19
RFID_MISO = 16
RFID_CS = 17
RFID_RST = 20

# Main safe class definition
class Safe:
    def __init__(self):
        self.passwordBuffer = ""
        self.keyboardAuthenticated = False
        self.safeOpen = False
        self.heldKey = None
        
        # If we fail to initialize the RFID, hand and print the error forever
        try:
            self.rdr = MFRC522(RFID_SCK, RFID_MOSI, RFID_MISO, RFID_CS, RFID_RST)
        except BaseException as e:
            while True:
                print(f"ERROR initializing rfid: {e}")
                sleep(5)
        
        
    def get_keypad_input(self):
        """
        Scans the keypad a single time and returns the key the user last pressed.
        Will not return the same key twice; only returns one key for each press/release cycle.
        Does not implement debouncing.
        Undefined behavior for multiple keys pressed at a time.
        
        returns None if no key is being pressed, or a single-char string if the user pressed a new key
        """
        KEYPAD_PINS_2_KEYS = {  # (row, col) : key
            (0, 0): '1',
            (0, 1): '2',
            (0, 2): '3',
            (0, 3): 'A',
            (1, 0): '4',
            (1, 1): '5',
            (1, 2): '6',
            (1, 3): 'B',
            (2, 0): '7',
            (2, 1): '8',
            (2, 2): '9',
            (2, 3): 'C',
            (3, 0): '*',
            (3, 1): '0',
            (3, 2): '#',
            (3, 3): 'D'
        }
        
        for row, rowPin in enumerate(KEYPAD_ROWS):
            rowPin.value(0)
            for col, colPin in enumerate(KEYPAD_COLS):
                if colPin.value() == 0: # Key pulled down by row wire
                    rowPin.value(1)
                    key = KEYPAD_PINS_2_KEYS[(row, col)]
                    if key != self.heldKey:
                        self.heldKey = key
                        return key
            rowPin.value(1)
        return None
    
    
    def loop(self):
        
        # Keyboard system
        key = self.get_keypad_input()
        if key is not None:
            if key == KEYPAD_ENTER_KEY:
                if self.passwordBuffer != KEYPAD_PASSWORD:
                    self.keypadAuthenticated = False
                    pass # TODO: notify user of incorrect password
                else:
                    self.keypadAuthenticated = True
                self.passwordBuffer = ""
            else:
                self.passwordBuffer += key
                
    # RFID system
    def test_rfid(self):
        while True:
            (stat, tag_type) = self.rdr.request(self.rdr.REQIDL)
            print(stat)

            if stat == self.rdr.OK:

                (stat, raw_uid) = self.rdr.anticoll()

                if stat == self.rdr.OK:
                    print("New card detected")
                    print("  - tag type: 0x%02x" % tag_type)
                    print("  - uid	 : 0x%02x%02x%02x%02x" % (raw_uid[0], raw_uid[1], raw_uid[2], raw_uid[3]))
                    print("")

                    if self.rdr.select_tag(raw_uid) == self.rdr.OK:

                        key = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]

                        if self.rdr.auth(self.rdr.AUTHENT1A, 8, key, raw_uid) == self.rdr.OK:
                            print("Address 8 data: %s" % self.rdr.read(8))
                            self.rdr.stop_crypto1()
                        else:
                            print("Authentication error")
                    else:
                        print("Failed to select tag")

        

        
                


safe = Safe()
safe.test_rfid()
"""
while True:
    sleep(0.1)
    safe.loop()
        
"""


        
    
    

