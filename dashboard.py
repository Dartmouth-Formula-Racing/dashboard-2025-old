import queue
import time

import config

if config.IN_CAR:
    import RPi.GPIO as GPIO
    import smbus2

import multiprocessing

import canbus
import web

BUTTON_DEBOUNCE_TIME = 50  # ms
BUTTON_SEND_INTERVAL = 50  # ms

POT_SEND_INTERVAL = 100  # ms

# ADS1015 Register addresses
ADS1015_REG_POINTER_CONVERT = 0x00
ADS1015_REG_POINTER_CONFIG = 0x01

# ADS1015 Configuration bits
ADS1015_CONFIG_OS_SINGLE = 0x8000  # Start a single conversion (not used in continuous mode)
ADS1015_CONFIG_MUX_SINGLE_0 = 0x4000  # Single-ended AIN0
ADS1015_CONFIG_PGA_4_096V = 0x0200  # +/- 4.096V range (covers 0-3.3V)
ADS1015_CONFIG_MODE_CONTINUOUS = 0x0000  # Continuous conversion mode
ADS1015_CONFIG_DR_1600SPS = 0x0080  # 1600 samples per second
ADS1015_CONFIG_CMODE_TRAD = 0x0000  # Traditional comparator
ADS1015_CONFIG_CPOL_ACTVLOW = 0x0000  # Alert/Rdy active low
ADS1015_CONFIG_CLAT_NONLAT = 0x0000  # Non-latching comparator
ADS1015_CONFIG_CQUE_NONE = 0x0003  # Disable comparator


def configure_adc(i2c_bus):
    """Configure the ADS1015 ADC for continuous reading on channel 0"""
    config_value = (ADS1015_CONFIG_MUX_SINGLE_0 |
                    ADS1015_CONFIG_PGA_4_096V |
                    ADS1015_CONFIG_MODE_CONTINUOUS |
                    ADS1015_CONFIG_DR_1600SPS |
                    ADS1015_CONFIG_CMODE_TRAD |
                    ADS1015_CONFIG_CPOL_ACTVLOW |
                    ADS1015_CONFIG_CLAT_NONLAT |
                    ADS1015_CONFIG_CQUE_NONE)

    # Write config register
    i2c_bus.write_i2c_block_data(config.ADC_I2C_ADDRESS, ADS1015_REG_POINTER_CONFIG,
                                 [(config_value >> 8) & 0xFF, config_value & 0xFF])


def read_adc(i2c_bus):
    """Read ADC value and convert to 0-1000 range"""
    try:
        # Read conversion result (no need to trigger, it's continuously converting)
        data = i2c_bus.read_i2c_block_data(config.ADC_I2C_ADDRESS, ADS1015_REG_POINTER_CONVERT, 2)

        # Convert to 12-bit value (ADS1015 is 12-bit, left-aligned in 16-bit register)
        raw_value = ((data[0] << 8) | data[1]) >> 4

        # ADS1015 with +/- 4.096V range gives us 2mV per bit
        # For 0-3.3V input: 3.3V / 0.002V = 1650 counts max
        # Convert to 0-1000 range
        # Clamp raw_value to positive range (0-2047 for 12-bit)
        if raw_value > 2047:
            raw_value = 0

        # Scale to 0-255 (assuming 3.3V full scale maps to 255)
        # 3.3V at 4.096V range = 3.3/4.096 * 2048 = 1650 counts
        value = int((raw_value / 1650.0) * 255.0)

        # Clamp to 0-255
        value = max(0, min(255, value))

        return value
    except Exception as e:
        print(f"Error reading ADC: {e}")
        return 0


if __name__ == "__main__":
    i2c_bus = None
    if config.IN_CAR:
        # Set up GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(config.BMS_LED_GPIO, GPIO.OUT)
        GPIO.setup(config.IMD_LED_GPIO, GPIO.OUT)
        # GPIO.setup(config.CAN_NRST_GPIO, GPIO.OUT)
        # GPIO.setup(config.CAN_STBY_GPIO, GPIO.OUT)
        GPIO.setup(config.DRIVE_BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(config.DRIVE_LED_GPIO, GPIO.OUT)
        GPIO.setup(config.NEUTRAL_BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(config.NEUTRAL_LED_GPIO, GPIO.OUT)
        GPIO.setup(config.REVERSE_BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(config.REVERSE_LED_GPIO, GPIO.OUT)
        GPIO.setup(config.ACCEL_BUTTON_TOP_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(config.ACCEL_BUTTON_BOTTOM_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        GPIO.output(config.DRIVE_LED_GPIO, GPIO.HIGH)
        GPIO.output(config.NEUTRAL_LED_GPIO, GPIO.HIGH)
        GPIO.output(config.REVERSE_LED_GPIO, GPIO.HIGH)
        GPIO.output(config.BMS_LED_GPIO, GPIO.HIGH)
        GPIO.output(config.IMD_LED_GPIO, GPIO.HIGH)

        # Initialize I2C for ADC
        i2c_bus = smbus2.SMBus(config.ADC_I2C_BUS)
        configure_adc(i2c_bus)

    # drive_button_state = False
    # neutral_button_state = False
    # reverse_button_state = False

    rx_queue = multiprocessing.Queue()
    tx_queue = multiprocessing.Queue(maxsize=1024)

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
    last_pot_send = 0
    last_accel_mode_send = 0

    # last_drive_button_state = False
    # last_neutral_button_state = False
    # last_reverse_button_state = False

    # drive_update_time = 0
    # neutral_update_time = 0
    # reverse_update_time = 0

    while True:
        # Send button states every BUTTON_SEND_INTERVAL ms
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

            accel_button_top = False
            accel_button_bottom = False
            if GPIO.input(config.ACCEL_BUTTON_TOP_GPIO) == 0:
                accel_button_top = True
            if GPIO.input(config.ACCEL_BUTTON_BOTTOM_GPIO) == 0:
                accel_button_bottom = True

            if (accel_button_top or accel_button_bottom) and (
                    (time.monotonic() - last_accel_mode_send) * 1000 > BUTTON_SEND_INTERVAL):
                None

            if (drive_button or neutral_button or reverse_button) and (
                    (time.monotonic() - last_button_send) * 1000 > BUTTON_SEND_INTERVAL):
                # Build CAN message
                msg = canbus.build_button_message(drive_button, neutral_button, reverse_button)
                # Try to add button message to the TX queue without blocking; only update the
                # send timestamp if the message was queued successfully.
                try:
                    tx_queue.put_nowait(msg)
                except queue.Full:
                    # queue is full; drop message
                    pass
                else:
                    last_button_send = time.monotonic()

            if i2c_bus and ((time.monotonic() - last_pot_send) * 1000 > POT_SEND_INTERVAL):
                # Read potentiometer from ADC
                pot_value = read_adc(i2c_bus)

                # Send potentiometer value over CAN
                pot_msg = canbus.build_potentiometer_message(pot_value)
                try:
                    tx_queue.put_nowait(pot_msg)
                except queue.Full:
                    # drop if full
                    pass
                else:
                    last_pot_send = time.monotonic()

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
                if msg.arbitration_id == config.CAN_INVERTER1_BASE + 0:  # Inverter 1 temperatures 1
                    module_A_temp = (msg.data[1] << 8) | msg.data[0]
                    module_A_temp = module_A_temp - 32768 if module_A_temp > 32767 else module_A_temp  # Convert to signed int
                    module_A_temp = module_A_temp / 10
                    module_B_temp = (msg.data[3] << 8) | msg.data[2]
                    module_B_temp = module_B_temp - 32768 if module_B_temp > 32767 else module_B_temp
                    module_B_temp = module_B_temp / 10
                    module_C_temp = (msg.data[5] << 8) | msg.data[4]
                    module_C_temp = module_C_temp - 32768 if module_C_temp > 32767 else module_C_temp
                    module_C_temp = module_C_temp / 10
                    state["leftinvtemp"] = max(module_A_temp, module_B_temp, module_C_temp)
                elif msg.arbitration_id == config.CAN_INVERTER2_BASE + 0:  # Inverter 2 temperatures 1
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
                if msg.arbitration_id == config.CAN_BASE_ID + 1:  # Vehicle state
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
                elif msg.arbitration_id == config.CAN_BASE_ID + 2:  # Driving data
                    state["throttle_position"] = (((msg.data[0] << 8) | msg.data[1])) / 10.0
                    rpm = (msg.data[2] << 8) | msg.data[3]
                    state["rpm"] = rpm
                    speed = (rpm * 60 * config.WHEEL_DIAMETER * 3.1415926535) / (12 * 5280 * config.TRANSMISSION_RATIO)
                    state["speed"] = speed
                    state["mileage"] = ((msg.data[6] << 8) | msg.data[7]) / 1000.0
                elif msg.arbitration_id == config.CAN_BMS_BASE + 1:  # BMS pack voltage
                    state["accumulator_voltage"] = ((msg.data[5] << 24) | (msg.data[6] << 16) | (msg.data[3] << 8) |
                                                    msg.data[4]) / 100
                elif msg.arbitration_id == config.CAN_BMS_BASE + 5:  # BMS state of charge
                    # state["battery_percentage"] = msg.data[6] / 100
                    current_bytes = (msg.data[0] << 8) | msg.data[1]
                    current_value = current_bytes - 65535 if current_bytes > 32767 else current_bytes  # Convert to signed int
                    state["accumulator_current"] = current_value / 10
                elif msg.arbitration_id == config.CAN_BMS_BASE + 16:  # BMS state of charge and health
                    state_of_charge_bytes = (msg.data[2] << 8) | msg.data[3]
                    state["battery_percentage"] = state_of_charge_bytes / 100
                elif msg.arbitration_id == config.CAN_BMS_BASE + 8:  # BMS cell temperatures
                    # state["acctemp"] = (msg.data[1] - 100) * (9/5) + 32 # Convert to F
                    state["acctemp"] = msg.data[1] - 100  # in C
    time.sleep(0.005)
