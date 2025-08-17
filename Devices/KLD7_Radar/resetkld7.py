import serial

ser = serial.Serial(
    port='/dev/ttyUSB0',  # Replace with your actual serial port
    baudrate=115200,
    parity=serial.PARITY_EVEN,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    timeout=1
)

# Set the maximum range to 30 meters (assuming the command for setting range is RRAI with value 2 for 30m)
ser.write(b'RRAI 2\n')
ser.close()

print("Maximum range set to 30 meters.")
