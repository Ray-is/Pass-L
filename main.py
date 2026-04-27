# This python script is run on startup
# By the pico's MicroPython interpreter.
# This script will STOP running
# if you open the MicroPython REPL on serial
# via thonny or a VSCode extension.
from time import sleep
from machine import Pin
from mfrc522 import MFRC522
import urequests
#import network


# Constants for keypad
KEYPAD_ENTER_KEY = "*"
KEYPAD_PASSWORD = "123"


# Keypad pin objects (initialized on creation)
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


# RFID status constants
# Micropython has no Enum implementation, so here we are
RFID_NO_FOB_DETECTED = 1
RFID_FOB_AUTH_FAILURE = 2  # Detected but failed to authenticate (wrong fob)
RFID_FOB_AUTH_SUCCESS = 3  # Detected and successful
RFID_ERROR = 4


# Main safe class definition
class Safe:
    def __init__(self):        
        # Internal state variables
        self.passwordBuffer = ""
        self.keypadAuthenticated = False
        self.rfidAuthenticated = False
        self.safeOpen = False  # assume safe is closed on power-on
        self.heldKey = None
        
        # If we fail to initialize the RFID, hang and print the error forever
        try:
            self.rdr = MFRC522(RFID_SCK, RFID_MOSI, RFID_MISO, RFID_CS, RFID_RST)
        except BaseException as e:
            while True:
                print(f"ERROR initializing rfid: {e}")
                sleep(5)
                
    def unlock_safe(self):
        """
        TODO - FINISH THIS
        Uses the servo to unlock the safe if it isn't already unlocked.
        This function should not return until the safe is actually unlocked.
        Raahil's job
        """
        if self.safeOpen:
            return
        
        # TODO blocking code to open the safe
        self.safeOpen = True
        
    def lock_safe(self):
        """
        TODO - FINISH THIS
        Uses the servo to close the safe if it isn't already locked.
        This function should not return until the safe is actually locked.
        Raahil's job
        """
        if not self.safeOpen:
            return
        
        # TODO blocking code to close the safe
        self.safeOpen = False
        
        
    def get_keypad_input(self):
        """
        Scans the keypad a single time and returns the key the user last pressed.
        Will not return the same key twice; only returns a non-None value once for each press/release cycle.
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
    
    
    def get_rfid_status(self):
        """
        TODO - FINISH THIS
        Returns an RFID status constant (See definitions above).
        Ray's Job
        """
        return RFID_FOB_AUTH_SUCCESS
    
    
    def loop(self):
        """
        Main loop.
        This should be called repeatedly after creating the Safe object.
        """
        
        # Logic for when both auth methods are passed
        # If the safe isn't open yet, open it.
        # If it's already open, wait for the user to press a key. Once they do, lock it.
        if (self.rfidAuthenticated and self.keypadAuthenticated):
            if not self.safeOpen:
                self.unlock_safe()
                send_push_notification(f"Safe unlocked!")
            if self.safeOpen:
                key = self.get_keypad_input()
                if key is not None:
                    self.lock_safe()
                    self.keypadAuthenticated = False
                    self.rfidAuthenticated = False
                    send_push_notification(f"Safe locked.")
        
        # Keypad system
        # We may want to change the logic to allow the user to re-lock the keypad auth without needing to open and close the safe.
        # Currently, the only way to go from keypadAuthenticated = True to keypadAuthenticated = False is to successfully authenticate the RFID and close the safe again.
        # This is insecure if the user changes their mind after getting the password right.
        # Someone could authenticate with password and immediately leave; it would stay "password-unlocked" forever until it was fully unlocked.
        # We could also have the "one auth successful but still locked" state expire back to the fully locked state after some delay.
        # None of this is essential, so I haven't included it in this code.
        if not self.keypadAuthenticated:
            key = self.get_keypad_input()
            if key is not None:
                if key == KEYPAD_ENTER_KEY:
                    if self.passwordBuffer != KEYPAD_PASSWORD:
                        self.keypadAuthenticated = False
                        send_push_notification(f"Incorrect password \"{self.passwordBuffer}\"")
                    else:
                        self.keypadAuthenticated = True
                        send_push_notification(f"Password correct!")
                    self.passwordBuffer = ""
                else:
                    self.passwordBuffer += key
        
        # RFID system
        # Same issue as the keypad system above.
        # If I authenticate successfully with RFID and leave, another user would only require the password to get in.
        if not self.rfidAuthenticated:
            rfidStatus = self.get_rfid_status()
            if (rfidStatus == RFID_NO_FOB_DETECTED):
                pass # ignore
            elif (rfidStatus == RFID_FOB_AUTH_FAILURE):
                self.rfidAuthenticated = False
                send_push_notification(f"Incorrect RFID Keyfob; you have the wrong one.")
            elif (rfidStatus == RFID_FOB_AUTH_SUCCESS):
                self.rfidAuthenticated = True
                send_push_notification(f"RFID authenticated successfully!")
            elif (rfidStatus == RFID_ERROR):
                pass # ignore (maybe do something else)

        
        
        
# Push Notif section, Developed by Felix Garita
# Telegram Bot constants
BOT_TOKEN = "8742345323:AAFM3KLYQbaCfmAG6VlIARD_PFceZ72pDH0"
CHAT_ID = 8787048379

# Wifi constants
# Possible improvement: have these be lists, so we can configure many networks for it to try and connect to
SSID = "Insert Wifi name here"
WPASSWORD = "Insert Wifi password here"

def connect_wifi():
    """
    Function to connect to wifi.
    """
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, WPASSWORD)

    print("Connecting to WiFi...")
    timeout = 15

    while not wlan.isconnected() and timeout > 0:
        print(".", end="")
        sleep(1)
        timeout -= 1

    if wlan.isconnected():
        print("\nConnected:", wlan.ifconfig())
    else:
        print("\nERROR: WiFi failed to connect. Continuing as normal.")


def send_push_notification(msg: str):
    """
    Function to send a push notification to the telegram API.
    """
    try:
        url = "https://api.telegram.org/bot{}/sendMessage".format(BOT_TOKEN)

        data = "chat_id={}&text={}".format(CHAT_ID, msg)

        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        response = urequests.post(url, data=data, headers=headers, timeout=3)

        print("Telegram status:", response.status_code)
        print("Response:", response.text)

        response.close()

        return True  # need more logic in here, if response.status_code... is an error or unsuccessful, return false
    except OSError as e:
        print("Telegram timeout/network error:", e)
        return False
    except Exception as e:
        print("Telegram error:", e)
        return False

                


# Main
# connect_wifi()

safe = Safe()

while True:
    safe.loop()   


        
    
    

