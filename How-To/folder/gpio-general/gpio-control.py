import RPi.GPIO as GPIO
import time

# Define the GPIO pin number using the BCM (Broadcom SOC channel) numbering scheme.
# GPIO24 corresponds to physical pin 18 on the Raspberry Pi header.
GPIO_PIN = 24

def main():
    """
    Main function to set up GPIO and blink the LED.
    """
    # Set the GPIO mode to BCM. This refers to the Broadcom SOC channel numbers,
    # which are the numbers after "GPIO" (e.g., GPIO24 is just 24).
    # Alternatively, GPIO.BOARD refers to the physical pin numbers on the header.
    GPIO.setmode(GPIO.BCM)

    # Set up GPIO_PIN as an output pin.
    # The initial_state=GPIO.LOW ensures the pin starts in the OFF state.
    GPIO.setup(GPIO_PIN, GPIO.OUT, initial=GPIO.LOW)

    print(f"GPIO {GPIO_PIN} (Physical Pin 18) will now blink every second.")
    print("Press Ctrl+C to stop the script.")

    try:
        while True:
            # Turn the GPIO pin ON (HIGH)
            GPIO.output(GPIO_PIN, GPIO.HIGH)
            print(f"GPIO {GPIO_PIN} is ON")
            time.sleep(1)  # Wait for 1 second

            # Turn the GPIO pin OFF (LOW)
            GPIO.output(GPIO_PIN, GPIO.LOW)
            print(f"GPIO {GPIO_PIN} is OFF")
            time.sleep(1)  # Wait for 1 second

    except KeyboardInterrupt:
        # This block is executed when Ctrl+C is pressed.
        print("\nScript stopped by user.")
    finally:
        # This ensures that GPIO pins are reset to a safe state (inputs)
        # regardless of how the script exits. This is very important!
        GPIO.cleanup()
        print("GPIO cleanup complete.")

if __name__ == "__main__":
    main()
