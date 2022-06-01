import time
import sys

EMULATE_HX711=False

referenceUnit = 1

if not EMULATE_HX711:
    import RPi.GPIO as GPIO
    from hx711 import HX711
else:
    from emulated_hx711 import HX711

def cleanAndExit():
    print("Cleaning")

    if not EMULATE_HX711:
        GPIO.cleanup()
        
    print("Beendet")
    sys.exit()

hx = HX711(5, 6)


hx.set_reading_format("MSB", "MSB")
#Gibt hier wohl Unstimmigkeiten, bei stark veränderten Werten das Format auf LSB ändern [...("LSB","MSB")]



#Um Waage zu eichen, bekanntes Gewicht (am Besten 2-3kg, evtl. 2 Pack Reis) aufstellen und Wert ablesen
#Wert durch Gewicht dividieren
#Resultat ist Parameter bei Reference Unit
#danach Zeile 36 auskommentieren
#hx.set_reference_unit(113)
hx.set_reference_unit(referenceUnit)

hx.reset()

hx.tare()

print("Tare, jetzt Gewicht aufstellen")


while True:
    try:
        #
        val = hx.get_weight(5)
        print(val)
        #Falls es Probleme beim Format gibt, siehe https://github.com/tatobari/hx711py/blob/master/example.py

        hx.power_down()
        hx.power_up()
        time.sleep(0.1)

    except (KeyboardInterrupt, SystemExit):
        cleanAndExit()
