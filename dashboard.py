import config
from time import time

if config.IN_CAR:
    import RPi.GPIO as GPIO

import multiprocessing

import canbus
import web

BUTTON_DEBOUNCE_TIME = 50 # ms
BUTTON_SEND_INTERVAL = 50  # ms

if __name__ == "__main__":
    if config.IN_CAR:
        # Set up GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(config.BMS_LED_GPIO, GPIO.OUT)
        GPIO.setup(config.IMD_LED_GPIO, GPIO.OUT)
        GPIO.setup(config.CAN_NRST_GPIO, GPIO.OUT)
        GPIO.setup(config.CAN_STBY_GPIO, GPIO.OUT)
        GPIO.setup(config.DRIVE_BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(config.DRIVE_LED_GPIO, GPIO.OUT)
        GPIO.setup(config.NEUTRAL_BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(config.NEUTRAL_LED_GPIO, GPIO.OUT)
        GPIO.setup(config.REVERSE_BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(config.REVERSE_LED_GPIO, GPIO.OUT)

    drive_button_state = False
    neutral_button_state = False
    reverse_button_state = False

    rx_queue = multiprocessing.Queue()
    tx_queue = multiprocessing.Queue()

    manager = multiprocessing.Manager()

    # Create a shared dictionary to store the data
    # Contains last known vehicle state, should never be used for vehicle control
    state = manager.dict()

    state["bot"] = False
    state["brb"] = False
    state["imd"] = False
    state["bms"] = False
    state["tsms"] = False
    state["drive_state"] = "NEUTRAL"
    state["acctemp"] = 0.0
    state["leftinvtemp"] = 0.0
    state["rightinvtemp"] = 0.0
    state["throttle_position"] = 0.0
    state["rpm"] = 0.0
    state["speed"] = 0.0
    state["lap"] = 0
    state["laptime"] = 0.0
    state["battery_percentage"] = 0.0
    state["accumulator_voltage"] = 0.0
    state["LV_voltage"] = 0.0
    state["accumulator_current"] = 0.0
    state["accumulator_temperature"] = 0.0
    state["estimated_range"] = 0.0
    state["tractioncontrol"] = False
    state["mileage"] = 0.0
    state["temperaturesok"] = False
    state["canconnected"] = False

    web_process = multiprocessing.Process(target=web.run, args=(state,), daemon=True)
    can_process = multiprocessing.Process(
        target=canbus.run,
        args=(
            rx_queue,
            tx_queue,
            state,
        ),
        daemon=True,
    )

    web_process.start()
    if config.IN_CAR:
        can_process.start()

    last_button_send = 0
    last_drive_button_state = False
    last_neutral_button_state = False
    last_reverse_button_state = False
    drive_press_time = 0
    neutral_press_time = 0
    reverse_press_time = 0
    while True:
        # Send button states every BUTTON_UPDATE_INTERVAL ms
        if config.IN_CAR:
            # Check button states
            drive_button_state = False
            neutral_button_state = False
            reverse_button_state = False
            drive_button = False
            neutral_button = False
            reverse_button = False
            if GPIO.input(config.DRIVE_BUTTON_GPIO) == 0:
                drive_button_state = True
            if GPIO.input(config.NEUTRAL_BUTTON_GPIO) == 0:
                neutral_button_state = True
            if GPIO.input(config.REVERSE_BUTTON_GPIO) == 0:
                reverse_button_state = True

            if drive_button_state != last_drive_button_state:
                drive_press_time = time()
            if neutral_button_state != last_neutral_button_state:
                neutral_press_time = time()
            if reverse_button_state != last_reverse_button_state:
                reverse_press_time = time()

            now = time()
            if (now - drive_press_time) > BUTTON_DEBOUNCE_TIME:
                drive_button = drive_button_state
                last_drive_button_state = drive_button_state
            if (now - neutral_press_time) > BUTTON_DEBOUNCE_TIME:
                neutral_button = neutral_button_state
                last_neutral_button_state = neutral_button_state
            if (now - reverse_press_time) > BUTTON_DEBOUNCE_TIME:
                reverse_button = reverse_button_state
                last_reverse_button_state = reverse_button_state

            if drive_button or neutral_button or reverse_button and (now - last_button_send) * 1000 > BUTTON_SEND_INTERVAL:
                # Build CAN message
                msg = canbus.build_button_message(drive_button, neutral_button, reverse_button)
                # Add status message to the TX queue
                tx_queue.put(msg)

            print(F"Drive: {drive_button}, Neutral: {neutral_button}, Reverse: {reverse_button}")

            last_button_send = time()

        if config.IN_CAR:
            if state["imd"]:
                GPIO.output(config.IMD_LED_GPIO, GPIO.LOW)
            else:
                GPIO.output(config.IMD_LED_GPIO, GPIO.HIGH)

            if state["bms"]:
                GPIO.output(config.BMS_LED_GPIO, GPIO.LOW)
            else:
                GPIO.output(config.BMS_LED_GPIO, GPIO.HIGH)

            drive_state = state["drive_state"]
            if drive_state == "NEUTRAL":
                GPIO.output(config.DRIVE_LED_GPIO, GPIO.LOW)
                GPIO.output(config.NEUTRAL_LED_GPIO, GPIO.HIGH)
                GPIO.output(config.REVERSE_LED_GPIO, GPIO.LOW)
            elif drive_state == "DRIVE":
                GPIO.output(config.DRIVE_LED_GPIO, GPIO.HIGH)
                GPIO.output(config.NEUTRAL_LED_GPIO, GPIO.LOW)
                GPIO.output(config.REVERSE_LED_GPIO, GPIO.LOW)
            elif drive_state == "REVERSE":
                GPIO.output(config.DRIVE_LED_GPIO, GPIO.LOW)
                GPIO.output(config.NEUTRAL_LED_GPIO, GPIO.LOW)
                GPIO.output(config.REVERSE_LED_GPIO, GPIO.HIGH)


        # Process RX queue messages
        while not rx_queue.empty():
            msg = rx_queue.get()
            if msg is None:
                continue

            if msg.is_extended_id:
                pass
            else:
                if msg.arbitration_id == config.CAN_BASE_ID:
                    state["bms"] = msg.data[0]
                    state["imd"] = msg.data[1]
                    drive_state = msg.data[2]
                    if drive_state == 0:
                        state["drive_state"] = "NEUTRAL"
                    elif drive_state == 1:
                        state["drive_state"] = "DRIVE"
                    elif drive_state == 2:
                        state["drive_state"] = "REVERSE"

    # Wait for processes to finish
    web_process.join()
    if config.IN_CAR:
        can_process.join()
