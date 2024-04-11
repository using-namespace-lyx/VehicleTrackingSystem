import serial
import time
import pynmea2
import re
# Default values
default_phone_number = "+91 1234567890"
default_password = "atdxt"

# def send_at_command(ser, command, expected_response, timeout=1):
#     ser.write(command.encode() + b'\r\n')
#     time.sleep(timeout)
#     response = ser.read(ser.in_waiting).decode()
#     return expected_response in response
def send_at_command(ser, command, expected_response, max_retries=3, timeout=1):
    for _ in range(max_retries):
        try:
            ser.write(command.encode() + b'\r\n')
            time.sleep(timeout)
            if ser.in_waiting:
                response = ser.read(ser.in_waiting).decode()
                if expected_response in response:
                    return True
                else:
                    print(f"Unexpected response: {response}")
            else:
                print("No response received.")
        except Exception as e:
            print(f"Error sending AT command: {e}")

        print(f"Retrying command: {command}")
        time.sleep(timeout)

    print(f"Failed to execute command: {command}")
    return False

def is_sim_card_present(ser):
    try:
        print("Checking SIM card presence...")
        return send_at_command(ser, "AT+CPIN?", "+CPIN: READY")
    except Exception as e:
        print(f"Error checking SIM card presence: {e}")
        return False

def initialize_gsm(ser):
    try:
        if not is_sim_card_present(ser):
            print("No SIM card detected. Exiting.")
            return False

        print("Initializing GSM module...")
        if send_at_command(ser, "AT", "OK"):
            print("GSM module initialized successfully.")
        else:
            print("Error initializing GSM module.")
            return False

        # Set text mode
        if send_at_command(ser, "AT+CMGF=1", "OK"):
            print("Text mode set.")
        else:
            print("Error setting text mode.")
            return False

        return True
    except Exception as e:
        print(f"Error initializing GSM module: {e}")
        return False

def check_network_status(ser):
    try:
        print("Checking network status...")
        if send_at_command(ser, "AT+CREG?", "+CREG: 0,1", timeout=3):
            print("Connected to the network.")
        else:
            print("Not connected to the network.")
            return False
        return True
    except Exception as e:
        print(f"Error checking network status: {e}")
        return False

def send_sms(ser, to_phone_number, message):
    try:
        print(f"Sending SMS to {to_phone_number}...")
        ser.write(f'AT+CMGS="{to_phone_number}"\r\n'.encode())
        time.sleep(1)
        ser.write(f'{message}\r\n'.encode())
        time.sleep(1)
        ser.write(b'\x1A')  # Send CTRL+Z to indicate the end of the message
        time.sleep(5)  # Wait for the message to be sent
        response = ser.read(ser.in_waiting).decode()
        if "+CMGS" in response:
            print("SMS sent successfully.")
        else:
            print("Error sending SMS.")
    except Exception as e:
        print(f"Error sending SMS: {e}")

def extract_sender_number(response):
    # Use regular expression to find the sender's number
    match = re.search(r'\+CMGL: \d+,"(\+91\d{10})",', response)
    if match:
        return match.group(1)
    return None

def receive_sms(ser, from_phone_number):
    try:
        print(f"Receiving SMS from {from_phone_number}...")
        ser.write(f'AT+CMGL="REC UNREAD",1\r\n'.encode())  # 1 for reading SMS index 1
        time.sleep(1)
        response = ser.read(ser.in_waiting).decode()
        
        if "+CMGL" in response:
            print("New unread messages:")
            print(response)

            # Split the response into individual messages
            messages = response.split("+CMGL")[1:]

            # Extract information from each message
            message_info_list = []
            for msg in messages:
                sender_number = extract_sender_number(msg)
                timestamp_match = re.search(r'Date: (\d{2}/\d{2}/\d{2}, \d{2}:\d{2}:\d{2})', msg)
                
                if sender_number and timestamp_match:
                    timestamp_str = timestamp_match.group(1)
                    timestamp = time.strptime(timestamp_str, "%y/%m/%d, %H:%M:%S")
                    message_info_list.append((sender_number, timestamp, msg))

            # Sort messages by timestamp in descending order
            message_info_list.sort(key=lambda x: x[1], reverse=True)

            # Return the most recent message
            if message_info_list:
                return message_info_list[0][2]

        else:
            print("No new unread messages.")
        return None
    except Exception as e:
        print(f"Error receiving SMS: {e}")
        return None

def parse_gps_data(data_str):
    try:
        msg = pynmea2.parse(data_str)
        if isinstance(msg, pynmea2.types.talker.RMC) and (msg.latitude != 0 and msg.longitude != 0):
            latitude = round(msg.latitude,6)
            longitude = round( msg.longitude,6)
            timestamp = msg.datetime.strftime("%Y-%m-%d %H:%M:%S")

            return latitude,longitude,timestamp
       
    except pynmea2.ParseError as e:
        print(f"Error parsing GPS data: {e}")
    return None, None,None

def get_gps_coordinates(serial_gps):
    try:
        while True:
            gps_data = serial_gps.readline().decode()
            latitude, longitude,timestamp = parse_gps_data(gps_data)
            if latitude is not None and longitude is not None and timestamp is not None:
                return latitude, longitude,timestamp
    except Exception as e:
        print(f"Error reading GPS data: {e}")
        return None, None,None
    
def location(ser_gps, ser):
    try:
        send_sms(ser,default_phone_number,"obtaining gps co-ordinates...")
        latitude, longitude,timestamp = get_gps_coordinates(ser_gps)
        if latitude is not None and longitude is not None and timestamp is not None:
            
            google_maps_link = f"https://maps.google.com/maps?q={latitude},{longitude}"
            msg="the  current  vehicle location is \n"+"\nlatitude:"+str(latitude)+"\nlongitude:"+str(longitude)+"\nurl link:"+google_maps_link
            send_sms(ser, default_phone_number, msg)
            print(f"Location sent: {google_maps_link}")
        else:
            send_sms(ser,default_phone_number,"unable to send gps co ordinates")
    except Exception as e:
        print(f"Error getting location: {e}")



def main():
    ser_gps = serial.Serial('/dev/serial0', baudrate=9600, timeout=1.0)
    ser = serial.Serial('/dev/serial1', baudrate=9600, timeout=1.0)
    try:
        while True:
            if is_sim_card_present(ser):
                if initialize_gsm(ser):
                    if check_network_status(ser):
                        receive = receive_sms(ser,"")

                        if receive:
                            sender_number = extract_sender_number(receive)
                            received_upper = receive.upper()
                       
                        

                        if(received_upper=="HI"):
                            msg="enter the password"
                            send_sms(ser,sender_number,msg)
                            check=receive_sms(ser,sender_number)
                            if(check==default_password):
                                send_sms(ser,sender_number,"sending the location ...")
                                location(ser_gps,ser)
                            else:
                                send_sms(ser,sender_number,"incorrect password restart the communication with HI")
                                break;

                        print(f"Received SMS: {receive}")
                    else:
                        print("GSM module is not connected to the network.")
            
            time.sleep(60)  # Adjust the delay according to your needs (e.g., 60 seconds)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        ser.close()

if __name__ == "__main__":
    main()