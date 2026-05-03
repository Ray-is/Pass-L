# This python script is run on startup
# By the pico's MicroPython interpreter.
# This script will STOP running
# if you open the MicroPython REPL on serial
# via thonny or a VSCode extension.
from time import sleep, time
from machine import Pin, PWM
from mfrc522 import MFRC522
import urequests
import network


# Constants for keypad
KEYPAD_ENTER_KEY = "*"
KEYPAD_PASSWORD = "123"


# Keypad pin objects (initialized on creation). If we fail to initialize the pins, hang and print the error forever.
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
        print(f"FATAL ERROR: could not initialize keypad pins: {e}")
        sleep(5)


# RFID pin numbers (fed to third-party RFID class)
RFID_SCK = 18
RFID_MOSI = 19
RFID_MISO = 16
RFID_CS = 17
RFID_RST = 20


# RFID accepted UIDs
# Each fob stores a "password", and these are the passwords the safe accepts. This dict also stores the name of the fob holder
RFID_ACCEPTED_UIDS = {
    "[0x6F, 0xF3, 0x86, 0xC2]": "Ray",
    # Add more here as needed
}


# Self explanatory
PRINT_ALL_TELEGRAM_TO_CONSOLE = True


# RFID status constants. Micropython has no Enum implementation, so here we are
RFID_NO_FOB_DETECTED = 1   # Fob not close enough to the reader
RFID_FOB_AUTH_FAILURE = 2  # Detected but failed to authenticate (wrong fob)
RFID_ERROR = 3             # Any error


WIFI_CONNECT_MAX_TIMEOUT = 10.0
WIFI_MESSAGE_MAX_TIMEOUT = 10.0

AUTH_EXPIRE_TIME = 10.0

# LED pin objects (initialized on creation). If we fail to initialize the pins, hang and print the error forever.
try:
    GREEN_LED = Pin(10, Pin.OUT, 0)
    RED_LED = Pin(11, Pin.OUT, 0)
    YELLOW_LED = Pin(12, Pin.OUT, 0)
    RED_LED.value(0)
except BaseException as e:
    while True:
        print(f"FATAL ERROR: could not initialize LED pins: {e}")
        sleep(5)


def flash_led(led, durationS):
    """
    Turns the LED on, waits durationS seconds, then turns it off.
    """
    led.value(1)
    sleep(durationS)
    led.value(0)


# Main safe class definition
class Safe:
    def __init__(self):        
        # Internal state variables
        self.passwordBuffer = ""
        self.keypadAuthenticated = False
        self.rfidAuthenticated = False
        self.safeOpen = False  # assume safe is closed on power-on
        self.heldKey = None
        self.queuedTelegramMsg = []
        self.authTime = None # For expiring authentication
        
        # Servo setup
        self.servo = PWM(Pin(27))
        self.servo.freq(50)
        self._set_servo_angle(14)
        
        # If we fail to initialize the RFID, hang and print the error forever
        try:
            self.rfidreader = MFRC522(spi_id=0, sck=RFID_SCK, miso=RFID_MISO, mosi=RFID_MOSI, cs=RFID_CS, rst=RFID_RST)
        except BaseException as e:
            while True:
                print(f"FATAL ERROR: could not initialize rfid: {e}")
                sleep(5)
                
        # If we fail to connect to the wifi, print the error and continue
        RED_LED.value(1)
        self.wirelesshandler = WirelessHandler()
        self.wirelesshandler.connect_wifi()
        if not self.wirelesshandler.isconnected():
            print(f"WARN: Could not connect to wifi. Continuing with all telegram/wireless functionality disabled.")
        RED_LED.value(0)

    def _set_servo_angle(self, angle):
        pulse_us = 500 + (angle / 180) * 1900
        self.servo.duty_u16(int((pulse_us / 20000) * 65535))

    def unlock_safe(self):
        """
        Uses the servo to unlock the safe if it isn't already unlocked.
        Sweeps from 15 to 75 degrees to open the latch.
        """
        if self.safeOpen:
            return
        for angle in range(15, 77, 1):
            self._set_servo_angle(angle)
            sleep(0.01)
        self.safeOpen = True
        print("Safe unlocked")

    def lock_safe(self):
        """
        Uses the servo to close the safe if it isn't already locked.
        Sweeps from 76 back to 15 degrees to close the latch.
        """
        if not self.safeOpen:
            return
        for angle in range(76, 14, -1):
            self._set_servo_angle(angle)
            sleep(0.01)
        self.safeOpen = False
        print("Safe locked")
        
        
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
        Function to poll the RFID reader for authentication.
        If successful, returns the name of the card holder from the RFID_ACCEPTED_UIDS dictionary.
        If unsuccessful, returns an RFID status constant (See definitions above).
        """
        self.rfidreader.init()
        
        (stat, tag_type) = self.rfidreader.request(self.rfidreader.REQIDL)
        if stat != self.rfidreader.OK:
            return RFID_NO_FOB_DETECTED
        
        (stat, uid) = self.rfidreader.SelectTagSN()
        if stat != self.rfidreader.OK:
            return RFID_ERROR
        
        # Loop through all accepted UIDs and return success if there is a match
        readUid = self.rfidreader.tohexstring(uid)
        try:
            return RFID_ACCEPTED_UIDS[readUid]
        except KeyError:
            return RFID_FOB_AUTH_FAILURE
    
    
    def loop(self):
        """
        Main loop.
        This should be called repeatedly after creating the Safe object.
        """
        
        # Keypad system
        if not self.keypadAuthenticated:
            key = self.get_keypad_input()
            if key is not None:
                if key == KEYPAD_ENTER_KEY:
                    if self.passwordBuffer != KEYPAD_PASSWORD:
                        self.keypadAuthenticated = False
                        self.queuedTelegramMsg.append(f"Incorrect password \"{self.passwordBuffer}\"")
                        for i in range(5):
                            flash_led(RED_LED, 0.05)
                            sleep(0.05)
                    else:
                        self.keypadAuthenticated = True
                        if not self.rfidAuthenticated:
                            self.authTime = time()
                    self.passwordBuffer = ""
                else:
                    self.passwordBuffer += key
                    flash_led(GREEN_LED, 0.1)
                    print(key)
        
        # RFID system
        if not self.rfidAuthenticated:
            rfidStatus = self.get_rfid_status()
            if isinstance(rfidStatus, str):
                self.rfidAuthenticated = True
                if not self.keypadAuthenticated:
                    self.authTime = time()
            elif (rfidStatus == RFID_NO_FOB_DETECTED):
                pass # ignore
            elif (rfidStatus == RFID_FOB_AUTH_FAILURE):
                self.rfidAuthenticated = False
                for i in range(5):
                    flash_led(RED_LED, 0.05)
                    sleep(0.05)
                self.queuedTelegramMsg.append(f"Incorrect RFID Keyfob; you have the wrong one.")
            elif (rfidStatus == RFID_ERROR):
                self.rfidAuthenticated = False
                for i in range(5):
                    flash_led(RED_LED, 0.05)
                    sleep(0.05)
                self.queuedTelegramMsg.append(f"ERROR reading RFID keyfob. Try again.")
        else:
            sleep(0.4)
            
            
        # If one method is passed, expire the other one after a delay
        if self.keypadAuthenticated ^ self.rfidAuthenticated:
            if (time() - self.authTime) > AUTH_EXPIRE_TIME:
                self.keypadAuthenticated = False
                self.rfidAuthenticated = False
            else:
                pass #self.authTime = time()
                
        
        # Logic for when both auth methods are passed
        # If the safe isn't open yet, open it.
        # If it's already open, wait for the user to press a key. Once they do, lock it.
        if (self.rfidAuthenticated and self.keypadAuthenticated):
            if not self.safeOpen:
                YELLOW_LED.value(1)
                GREEN_LED.value(1)
                self.unlock_safe()
                self.queuedTelegramMsg.append(f"Safe unlocked!")
            else:
                key = self.get_keypad_input()
                if key == '#':
                    YELLOW_LED.value(0)
                    GREEN_LED.value(0)
                    self.lock_safe()
                    self.keypadAuthenticated = False
                    self.rfidAuthenticated = False
                    self.queuedTelegramMsg.append(f"Safe locked.")
        
        # LED handling
        if self.rfidAuthenticated:
            YELLOW_LED.value(1)
        else:
            YELLOW_LED.value(0)
        if self.keypadAuthenticated:
            GREEN_LED.value(1)
        else:
            GREEN_LED.value(0)
        
        # Send all messages generated in this loop
        # This happens after everything else important has already happened
        if len(self.queuedTelegramMsg) != 0:
            for msg in self.queuedTelegramMsg:
                self.wirelesshandler.send_push_notification(msg)
            self.queuedTelegramMsg = []


# Push Notif section, Developed by Felix Garita
class WirelessHandler:
    def __init__(self):
        self.BOT_TOKEN = "8742345323:AAFM3KLYQbaCfmAG6VlIARD_PFceZ72pDH0"
        self.CHAT_ID = 8787048379
        self.SSID = "Foo"
        self.WPASSWORD = "Bar"
        self.connected = False
        
        self.wlan = network.WLAN(network.STA_IF)

    def connect_wifi(self):
        """
        Function to connect to wifi.
        """
        self.wlan.active(True)
        self.wlan.connect(self.SSID, self.WPASSWORD)

        print("Connecting to WiFi...")
        timeout = WIFI_CONNECT_MAX_TIMEOUT

        while not self.wlan.isconnected() and timeout > 0:
            print(".", end="")
            sleep(1)
            timeout -= 1

        if self.wlan.isconnected():
            print("\nConnected:", self.wlan.ifconfig())
        else:
            print("\nWifi failed to connect.")


    def send_push_notification(self, msg: str):
        """
        Function to send a push notification to the telegram API.
        """
        if not self.isconnected():
            print(f"WARN: Cannot send push notif, not connected to wifi. Attempted to send \"{msg}\"")
            return False
        elif PRINT_ALL_TELEGRAM_TO_CONSOLE:
            print("Telegram: ", msg)
        
        RED_LED.value(1)
        try:
            url = "https://api.telegram.org/bot{}/sendMessage".format(self.BOT_TOKEN)
            data = "chat_id={}&text={}".format(self.CHAT_ID, msg)
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            response = urequests.post(url, data=data, headers=headers, timeout=WIFI_MESSAGE_MAX_TIMEOUT)
            print("Telegram status:", response.status_code)
            print("Response:", response.text)
            response.close()
            RED_LED.value(0)
            return True
        except OSError as e:
            print("Telegram timeout/network error:", e)
            RED_LED.value(0)
            flash_led(RED_LED, 0.05)
            return False
        except Exception as e:
            print("Telegram error:", e)
            RED_LED.value(0)
            flash_led(RED_LED, 0.05)
            return False
        
    
    def isconnected(self):
        return self.wlan.isconnected()


# Entry point. This is the first code that runs
safe = Safe()  # calls safe.__init__
#safe._set_servo_angle(14)
while True:
    safe.loop()
