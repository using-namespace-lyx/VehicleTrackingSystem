import time
import serial
import re

i=0

def detect_gsm_port(i):
    # Replace 'GSM' with the identifier in the device name or description
    pattern = re.compile(r'/dev/ttyUSB(\d+)')  # Adjust the pattern based on your system

    try:
        # Try checking up to 10 ports
        port = f'/dev/ttyUSB{i}'
        try:
                with serial.Serial(port, baudrate=9600, timeout=1) as ser:
                    ser.write(b'AT\r\n')
                    time.sleep(1)
                    response = ser.read(ser.in_waiting).decode()
                    if 'OK' in response:
                        return port
        except serial.SerialException:
                pass
    except Exception as e:
        print(f"Error detecting GSM port: {e}")

    return None

def send_command(ser, command, timeout=1):
    ser.write(command.encode() + b'\r\n')
    time.sleep(timeout)
    return ser.read(ser.in_waiting).decode()

def read_sms(ser):
    response = send_command(ser, "AT+CMGF=1")  # Set SMS mode to text
    print(response)

    response = send_command(ser, "AT+CMGL=\"REC UNREAD\"")  # Read unread messages
    print(response)

    messages = response.split("+CMGL: ")[1:]
    return messages

def parse_and_reply(ser, message):
    lines = message.split('\n')
    print("Printing Lines:", lines)

    if len(lines) >= 3:
        sender_line = lines[0].strip().split(",")
        print("Sender Lines: ", sender_line)
        if len(sender_line) >= 2:
            sender = sender_line[2].strip().strip('"')
            print(sender)
            text = lines[1].strip()
            print(text)
            character_count = len(text)

            reply = f"Character count of your message: {character_count}"

            # Reply to the sender
            send_command(ser, f'AT+CMGS="{sender}"', timeout=2)
            send_command(ser, reply + '\x1A', timeout=2)
        else:
            print("Error: Sender information not found in the message.")
    else:
        print("Error: Insufficient lines in the message to parse.")

def main():
    try:
        while True:
            gsm_port = detect_gsm_port(i)
            if gsm_port:
                print(f"GSM module detected on port: {gsm_port}")
                i=0
                ser = serial.Serial(gsm_port, baudrate=9600, timeout=1)

                try:
                    while True:
                        messages = read_sms(ser)

                        if messages:
                            print(messages)
                            most_recent_message = messages[-1]
                            parse_and_reply(ser, most_recent_message)

                        time.sleep(10)  # Adjust the sleep time as needed
                finally:
                    ser.close()
            else:
                print("GSM module not found. Retrying in 60 seconds.")
                i+=1
                
                time.sleep(60)
    except KeyboardInterrupt:
        print("KeyboardInterrupt. Exiting.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
