import serial
import pynmea2
import json
import pyrebase
import socket
from datetime import datetime, timedelta

# Initialize Firebase with your project credentials
config = {
     "apiKey": "AIzaSyB4BUJG2t94v1ho9m8h-kDIlxvwE5Wvo2g",
      "authDomain": "atdxt3.firebaseapp.com",
      "databaseURL": "https://atdxt3-default-rtdb.firebaseio.com",
      "projectId": "atdxt3",
      "storageBucket": "atdxt3.appspot.com",
      "messagingSenderId": "721302049985",
      "appId": "1:721302049985:web:dfd2e914f6d3a62900b040"
    # Your Firebase configuration
}

firebase = pyrebase.initialize_app(config)
storage = firebase.storage()

# Function to check internet connection
def check_internet_connection():
    try:
        socket.create_connection(("www.google.com", 80))
        return True
    except OSError:
        pass
    return False

# Function to parse GPRMC data
def parse_gprmc(data_str):
    msg = pynmea2.parse(data_str)
    if isinstance(msg, pynmea2.types.talker.RMC) and (msg.latitude != 0 and msg.longitude != 0):
        latitude = msg.latitude
        longitude = msg.longitude
        speed = msg.spd_over_grnd
        timestamp = msg.datetime.strftime("%Y-%m-%d %H:%M:%S")

        location_data = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [latitude, longitude]
            },
            "properties": {
                "speed": speed,
                "timestamp": timestamp
            }
        }

        return location_data, latitude, longitude
    else:
        return None, None, None

# Function to get the current date as a string
def get_current_date():
    return datetime.now().strftime("%Y%m%d")

# Function to get the current time as a string
def get_current_time():
    return datetime.now().strftime("%H:%M:%S")

# Function to initialize or retrieve the GeoJSON file for the day
def get_geojson_file():
    current_date = get_current_date()
    file_name = f"data_{current_date}.json"
    
    try:
        # Try to download the existing GeoJSON file
        storage.child(file_name).download(file_name)
        print(f"GeoJSON file {file_name} downloaded from Firebase Storage.")
    except:
        # If the file doesn't exist, create an empty one
        with open(file_name, "w") as geojson_file:
            geojson_file.write('{"type": "FeatureCollection", "features": []}')
        print(f"GeoJSON file {file_name} created.")
    
    return file_name

# Function to upload GeoJSON file to Firebase Storage
def upload_to_firebase(file_name):
    storage.child(file_name).put(file_name)
    print(f"GeoJSON file {file_name} uploaded to Firebase Storage")

# Function to append data to the GeoJSON file
def append_data_to_file(data, file_name):
    with open(file_name, "a") as geojson_file:
        json.dump(data, geojson_file)
        geojson_file.write('\n')

# Main function
def main():
    ser = serial.Serial('/dev/serial0', baudrate=9600, timeout=1.0)
    ct = 0
    geojson_file_name = get_geojson_file()

    print(f"Waiting for GPS connection. Writing to file: {geojson_file_name}")

    try:
        while True:
            try:
                data = ser.readline().decode('utf-8')
                if data.startswith('$GPRMC'):
                    location_data, latitude, longitude = parse_gprmc(data)
                    if location_data:
                        append_data_to_file(location_data, geojson_file_name)
                        print("Location data saved in GeoJSON file")
                        print(f"Latitude: {latitude}, Longitude: {longitude}")
                        print(ct)

                        if ct == 10:
                            if check_internet_connection():
                                upload_to_firebase(geojson_file_name)
                                print(f"{geojson_file_name} has been uploaded.")
                                # Remove the local file after uploading
                                os.remove(geojson_file_name)
                                print(f"{geojson_file_name} has been erased.")
                                # Get a new GeoJSON file for the next day
                                geojson_file_name = get_geojson_file()
                                ct=(ct + 1) % 11
                            else:
                                ct = (ct + 1) % 11

                        else:
                            ct = (ct + 1) % 11

            except KeyboardInterrupt:
                ser.close()
                break
            except Exception as e:
                print("Error:", str(e))

    except serial.serialutil.SerialException:
        print("GPS connection established.")

if __name__ == "__main__":
    main()
