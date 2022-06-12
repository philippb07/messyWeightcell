import asyncio
import websockets
import json
import RPi.GPIO as GPIO
from hx711 import HX711

RELAY_URL = "wss://messy.wilms.ninja/api"
TOKEN = "test"

async def listen(ws):
    while True:
        try:
            message = await asyncio.wait_for(ws.recv(), timeout=10)
            print(f"\r{message}")
            messageDict = json.loads(message)
            if messageDict["event_name"] == "fillIngredient":
                ingredient = messageDict["ingredient_name"]
                goalValue = messageDict["amount"]
                measuredStart = scaleStart()
                measuredValue = measuredStart
                fillingLevel = calcFillingLevel(measuredStart, goalValue, measuredValue)

                while measuredValue != goalValue:
                    ####Zeitliche Abfrage fehlt, weiß nicht welchen Intervall du gewählt hast####
                    #measuredValue = hx.getMeasure()
                    measuredValue  += 5 # zu Testzwecken damit Füllstand erreicht wird
                    fillingLevel = calcFillingLevel(measuredStart, goalValue, measuredValue)
                    print() #für Displayausgabe

                    while True:
                        send(ws, "filling", ingredient, fillingLevel)
                    
                while True:
                    send(ws, "filled", ingredient)

            else:
                pass
        except asyncio.exceptions.TimeoutError:
            pass


async def send(*param):
    await param[0].send(json.dumps({
        "event_name": "cupAuth",
        "sender": "CUP",
        "token": TOKEN
    }))

    while True:
        if param[1] == "filled":
            await param[0].send(json.dumps({
                    "event_name": "filledIngredient",
                    "sender": "CUP",
                    "token": "test",
                    "ingredient_name": param[2],
                }))
            print("Zutat hinzugefügt")
        elif param[1] == "filling":
            await param[0].send(json.dumps({
                    "event_name": "fillingLevel",
                    "sender": "CUP",
                    "token": "test",
                    "ingredient_name": param[2],
                    "filling_level": param[3],
                }))
        else:
                await asyncio.sleep(2)
        await asyncio.sleep(1)


####Erster Versuch als extra Functions, hab es versucht in eine Function zu implementieren####
#async def sendFilled(ws, ingredient):
#    await ws.send(json.dumps({
#                    "event_name": "filledIngredient",
#                    "sender": "CUP",
#                    "token": "test",
#                    "ingredient_name": ingredient,
#    }))
#    print("Zutat hinzugefügt")

#async def sendFilling(ws, ingredient, level):
#    await ws.send(json.dumps({
#        "event_name": "fillingLevel",
#        "sender": "CUP",
#        "token" : "test",
#        "ingredient_name": ingredient,
#        "filling_level": level,
#    }))


def scaleStart():
    hx = HX711(dout=5, pd_sck=6)
    #hx.setReferenceUnit(..)
    hx.reset()
    hx.tare()
    #measuredValue = hx.getMeasure()
    measuredValue = 200.0
    return measuredValue


def calcFillingLevel(startWeight, goalValue, measuredValue):
    goalWeight = startWeight + goalValue
    fillingLevel = (measuredValue / goalWeight)*100
    return fillingLevel


async def main():
    print("Open Connection")
    async with websockets.connect(RELAY_URL) as websocket:
        print("Connection established")

        await asyncio.gather(
            send(websocket),
            listen(websocket)
        )
    

asyncio.run(main())
