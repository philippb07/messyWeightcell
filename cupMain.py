import asyncio
import websockets
import json

import board
# pip3 install adafruit-circuitpython-ssd1306
import adafruit_ssd1306
import digitalio
from PIL import Image, ImageDraw, ImageFont
import time
import RPi.GPIO as GPIO
# https://github.com/tatobari/hx711py
#from hx711 import HX711
import tqdm
import statistics

import argparse

RELAY_URL: str = "wss://messy.wilms.ninja/api"
RELAY_HOME = "ws://localhost:8765"

TOKEN: str = "test"

#from https://github.com/dcrystalj/hx711py3/blob/master/hx711.py
class HX711:
    def __init__(self, dout=5, pd_sck=6, gain=128, bitsToRead=24):
        self.PD_SCK = pd_sck
        self.DOUT = dout

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.PD_SCK, GPIO.OUT)
        GPIO.setup(self.DOUT, GPIO.IN)

        # The value returned by the hx711 that corresponds to your
        # reference unit AFTER dividing by the SCALE.
        self.REFERENCE_UNIT = 1

        self.GAIN = 0
        self.OFFSET = 1
        self.lastVal = 0
        self.bitsToRead = bitsToRead
        self.twosComplementThreshold = 1 << (bitsToRead-1)
        self.twosComplementOffset = -(1 << (bitsToRead))
        self.setGain(gain)
        self.read()

    def isReady(self):
        return GPIO.input(self.DOUT) == 0

    def setGain(self, gain):
        if gain == 128:
            self.GAIN = 1
        elif gain == 64:
            self.GAIN = 3
        elif gain == 32:
            self.GAIN = 2

        GPIO.output(self.PD_SCK, False)
        self.read()

    def waitForReady(self):
        while not self.isReady():
            pass

    def correctTwosComplement(self, unsignedValue):
        if unsignedValue >= self.twosComplementThreshold:
            return unsignedValue + self.twosComplementOffset
        else:
            return unsignedValue

    def read(self):
        self.waitForReady()

        unsignedValue = 0
        for i in range(0, self.bitsToRead):
            GPIO.output(self.PD_SCK, True)
            bitValue = GPIO.input(self.DOUT)
            GPIO.output(self.PD_SCK, False)
            unsignedValue = unsignedValue << 1
            unsignedValue = unsignedValue | bitValue

        # set channel and gain factor for next reading
        for i in range(self.GAIN):
            GPIO.output(self.PD_SCK, True)
            GPIO.output(self.PD_SCK, False)

        return self.correctTwosComplement(unsignedValue)

    def getValue(self):
        return self.read() - self.OFFSET

    def getWeight(self):
        value = self.getValue()
        value /= self.REFERENCE_UNIT
        return value

    def tare(self, times=25):
        reference_unit = self.REFERENCE_UNIT
        self.setReferenceUnit(1)

        # remove spikes
        cut = times//5
        values = sorted([self.read() for i in range(times)])[cut:-cut]
        offset = statistics.mean(values)

        self.setOffset(offset)

        self.setReferenceUnit(reference_unit)

    def setOffset(self, offset):
        self.OFFSET = offset

    def setReferenceUnit(self, reference_unit):
        self.REFERENCE_UNIT = reference_unit

    # HX711 datasheet states that setting the PDA_CLOCK pin on high
    # for a more than 60 microseconds would power off the chip.
    # I used 100 microseconds, just in case.
    # I've found it is good practice to reset the hx711 if it wasn't used
    # for more than a few seconds.
    def powerDown(self):
        GPIO.output(self.PD_SCK, False)
        GPIO.output(self.PD_SCK, True)
        time.sleep(0.0001)

    def powerUp(self):
        GPIO.output(self.PD_SCK, False)
        time.sleep(0.0001)

    def reset(self):
        self.powerDown()
        self.powerUp()

BORDER = 5
BAR = 2

def init_display():
    oled_reset = digitalio.DigitalInOut(board.D4)
    i2c = board.I2C()
    oled = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c, #addr=0x3d, 
                                        reset=oled_reset)
    clear(oled)
    return oled

def clear(oled):
    # Clear display.
    oled.fill(0)
    oled.show()

def draw(oled, current, target, unit):
    #if current > target:
        #raise Exception("Current bigger than target")

    # Create blank image for drawing.
    # Make sure to create image with mode '1' for 1-bit color.
    image = Image.new("1", (oled.width, oled.height))

    # Get drawing object to draw on image.
    draw = ImageDraw.Draw(image)

    # Draw a white background
    draw.rectangle((0, 0, oled.width, oled.height), outline=255, fill=255)

    # Draw a smaller inner rectangle
    draw.rectangle(
        (BORDER, BORDER, oled.width - BORDER - 1, oled.height - BORDER - 1),
        outline=0,
        fill=0,
    )
    
    #draw progress rectangle
    progress = current/target
    if progress > 1:
        progress = 1
    if progress > 0.01:
        draw.rectangle(
            (BORDER+BAR, BORDER+BAR, max(oled.width * progress - BORDER - 1 - BAR, BORDER+BAR), oled.height - BORDER - 1 - BAR),
            outline=255,
            fill=0
        )

    # Load default font.
    font = ImageFont.load_default()


    text = f"{current}{unit}"
    (font_width, font_height) = font.getsize(text)
    draw.text(
        (oled.width // 2 - font_width // 2, oled.height // 2 - font_height // 2),
        text,
        font=font,
        fill=255,
    )

    # Display image
    oled.image(image)
    oled.show()


running_task = set()


async def event_scheduler(message, websocket) -> None:
    messageDict = json.loads(message)
    try:
    # mach was
        event_name = messageDict["event_name"]
        if event_name == "fillIngredient":
            if len(running_task) == 0:
                print(f"Starting Task {event_name} with ingredient {messageDict['ingredient_name']}")

            else:
                print(f"Closing currently running Task and starting new Task {event_name} with ingredient {messageDict['ingredient_name']}")
                _t = running_task.pop()
                _t.cancel()

            task = asyncio.create_task(handle_fill_ingredient(messageDict, websocket))
            running_task.add(task)
            task.add_done_callback(running_task.discard)


    except KeyError:
        print(f"Event name {messageDict} ist nicht vorhanden")
async def handle_fill_ingredient(message, websocket):
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", type=int, default=1000)
    parser.add_argument("-c", type=float, default=2)
    parser.add_argument("-p", type=float, default=0.001)

    args = parser.parse_args()

    hx = HX711(5, 6)
    #hx.set_reading_format("MSB", "MSB")
    #hx.set_reference_unit(1)
    hx.reset()
    hx.tare()
    oled = init_display()

    #vals = list()
    keep = 5
    hist = list()
    try:
        name_ingredient = message["ingredient_name"]
        amount = float(message["amount"])

        while True:
            val = hx.getWeight()
            hist.append(val)
            current = max(0, round(statistics.median(hist)/1000) * args.c)
            hist = hist[-keep:]
            print(f"{current}/{args.t}")
            draw(oled, current, args.t, "g")
            time.sleep(args.p)
            #measuredValue = 200.0
            fillingLevel = (current / amount) * 100
            if fillingLevel < 100:
                event = await make_event(event_name="fillingLevel", filling_level=fillingLevel,
                                   ingredient_name=name_ingredient)
                await websocket.send(json.dumps(event))
            else:
                event = await make_event(event_name="filledIngredient", ingredient_name=name_ingredient)
                await websocket.send(json.dumps(event))
                clear(oled)
                GPIO.cleanup()
                break

            await asyncio.sleep(1)
    except KeyError:
        print("Ein Key ist nicht vorhanden")


async def make_event(event_name: str, ingredient_name: str, filling_level: float = 0):
    if event_name == "fillingLevel":
        return {
            "event_name": "fillingLevel",
            "sender": "CUP",
            "token": TOKEN,
            "ingredient_name": ingredient_name,
            "filling_level": filling_level
        }
    elif event_name == "filledIngredient":
        return {
            "event_name": "filledIngredient",
            "sender": "CUP",
            "token": TOKEN,
            "ingredient_name": ingredient_name
        }
    else:
        print(f"Event {event_name} existiert nicht")


async def main():
    print("Open Connection")
    async with websockets.connect(RELAY_HOME) as websocket:
        print("Connection established")
        await websocket.send(json.dumps({
            "event_name": "cupAuth",
            "sender": "CUP",
            "token": TOKEN
        }))
        while True:
            message = await websocket.recv()
            await event_scheduler(message, websocket)


if __name__ == "__main__":
    asyncio.run(main())

