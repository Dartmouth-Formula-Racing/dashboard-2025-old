import config
from time import time, sleep
import os

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

        GPIO.output(config.DRIVE_LED_GPIO, GPIO.HIGH)
        GPIO.output(config.NEUTRAL_LED_GPIO, GPIO.HIGH)
        GPIO.output(config.REVERSE_LED_GPIO, GPIO.HIGH)
        GPIO.output(config.BMS_LED_GPIO, GPIO.HIGH)
        GPIO.output(config.IMD_LED_GPIO, GPIO.HIGH)

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
    state["dcdc"] = False
    state["drive_state"] = "NEUTRAL"
    state["vehicle_state"] = "Loading..."
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
    state["cvc_overflow"] = False
    state["cvc_time"] = 0

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
    drive_update_time = 0
    neutral_update_time = 0
    reverse_update_time = 0

    sleep(1) # Wait a second for web process to start
    os.system("chromium-browser localhost:5000 --start-maximized --start-fullscreen")

    while True:
        # Send button states every BUTTON_UPDATE_INTERVAL ms
        if config.IN_CAR:
            # Check button states
            drive_button = False
            neutral_button = False
            reverse_button = False
            if GPIO.input(config.DRIVE_BUTTON_GPIO) == 0:
                drive_button = True
            if GPIO.input(config.NEUTRAL_BUTTON_GPIO) == 0:
                neutral_button = True
            if GPIO.input(config.REVERSE_BUTTON_GPIO) == 0:
                reverse_button = True

            if (drive_button or neutral_button or reverse_button) and ((time() - last_button_send) * 1000 > BUTTON_SEND_INTERVAL):
                # Build CAN message
                msg = canbus.build_button_message(drive_button, neutral_button, reverse_button)
                # Add status message to the TX queue
                tx_queue.put(msg)
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
                if msg.arbitration_id == config.CAN_INVERTER1_BASE + 0: # Inverter 1 temperatures 1
                    module_A_temp = (msg.data[1] << 8) | msg.data[0]
                    module_A_temp = module_A_temp - 32768 if module_A_temp > 32767 else module_A_temp # Convert to signed int
                    module_A_temp = module_A_temp / 10
                    module_B_temp = (msg.data[3] << 8) | msg.data[2]
                    module_B_temp = module_B_temp - 32768 if module_B_temp > 32767 else module_B_temp
                    module_B_temp = module_B_temp / 10
                    module_C_temp = (msg.data[5] << 8) | msg.data[4]
                    module_C_temp = module_C_temp - 32768 if module_C_temp > 32767 else module_C_temp
                    module_C_temp = module_C_temp / 10
                    state["leftinvtemp"] = max(module_A_temp, module_B_temp, module_C_temp)
                elif msg.arbitration_id == config.CAN_INVERTER2_BASE + 0: # Inverter 2 temperatures 1
                    module_A_temp = (msg.data[1] << 8) | msg.data[0]
                    module_A_temp = module_A_temp - 32768 if module_A_temp > 32767 else module_A_temp
                    module_A_temp = module_A_temp / 10
                    module_B_temp = (msg.data[3] << 8) | msg.data[2]
                    module_B_temp = module_B_temp - 32768 if module_B_temp > 32767 else module_B_temp
                    module_B_temp = module_B_temp / 10
                    module_C_temp = (msg.data[5] << 8) | msg.data[4]
                    module_C_temp = module_C_temp - 32768 if module_C_temp > 32767 else module_C_temp
                    module_C_temp = module_C_temp / 10
                    state["rightinvtemp"] = max(module_A_temp, module_B_temp, module_C_temp)
            else:
                if msg.arbitration_id == config.CAN_BASE_ID + 1: # Vehicle state
                    state["bms"] = msg.data[0]
                    state["imd"] = msg.data[1]
                    drive_state = msg.data[2]
                    vehicle_state = msg.data[3]
                    state["bot"] = msg.data[4]
                    state["brb"] = msg.data[5]
                    state["cvc_overflow"] = msg.data[6]
                    state["cvc_time"] = msg.data[7]

                    if drive_state == 0:
                        state["drive_state"] = "NEUTRAL"
                    elif drive_state == 1:
                        state["drive_state"] = "DRIVE"
                    elif drive_state == 2:
                        state["drive_state"] = "REVERSE"

                    if vehicle_state == 0:
                        state["vehicle_state"] = "Initial"
                    elif vehicle_state == 1:
                        state["vehicle_state"] = "Voltage Check"
                    elif vehicle_state == 2:
                        state["vehicle_state"] = "Wait for Precharge"
                    elif vehicle_state == 3:
                        state["vehicle_state"] = "Precharge Stage 1"
                    elif vehicle_state == 4:
                        state["vehicle_state"] = "Precharge Stage 2"
                    elif vehicle_state == 5:
                        state["vehicle_state"] = "Precharge Stage 3"
                    elif vehicle_state == 6:
                        state["vehicle_state"] = "Not Ready to Drive"
                    elif vehicle_state == 7:
                        state["vehicle_state"] = "Buzzer"
                    elif vehicle_state == 8:
                        state["vehicle_state"] = "Ready to Drive"
                    elif vehicle_state == 9:
                        state["vehicle_state"] = "Charging"
                elif msg.arbitration_id == config.CAN_BASE_ID + 2: # Driving data
                    state["throttle_position"] = ((msg.data[0] << 8) | msg.data[1])
                    rpm = (msg.data[2] << 8) | msg.data[3]
                    state["rpm"] = rpm
                    speed = (rpm * 60 * config.WHEEL_DIAMETER * 3.1415926535)/(12 * 5280 * config.TRANSMISSION_RATIO)
                    state["speed"] = speed
                elif msg.arbitration_id == config.CAN_BMS_BASE + 1: # BMS pack voltage
                    state["accumulator_voltage"] = ((msg.data[5] << 24) | (msg.data[6] << 16) | (msg.data[3] << 8) | msg.data[4]) / 100
                elif msg.arbitration_id == config.CAN_BMS_BASE + 5: # BMS state of charge
                    state["battery_percentage"] = ((msg.data[5] << 8) | msg.data[6]) / 100
                    current_bytes = (msg.data[0] << 8) | msg.data[1]
                    current_value = current_bytes - 65535 if current_bytes > 32767 else current_bytes # Convert to signed int
                    state["accumulator_current"] = current_value / 10
                elif msg.arbitration_id == config.CAN_BMS_BASE + 8: # BMS cell temperatures
                    # state["acctemp"] = (msg.data[1] - 100) * (9/5) + 32 # Convert to F
                    state["acctemp"] = msg.data[1] - 100 # in C

    # Wait for processes to finish
    web_process.join()
    if config.IN_CAR:
        can_process.join()
