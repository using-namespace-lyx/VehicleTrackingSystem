import os
import serial
import pynmea2
import json
import socket
import psycopg2
from adafruit_ds3231 import DS3231
import board
import busio
from datetime import datetime

# Create I2C bus
i2c = busio.I2C(board.SCL, board.SDA)

# Create the DS3231 object
rtc = DS3231(i2c)

# Function to check internet connection
def check_internet_connection():
    try:
        socket.create_connection(("www.google.com", 80))
        return True
    except OSError:
        pass
    return False

# Function to parse GNRMC data
def parse_gnrmc(data_str):
    msg = pynmea2.parse(data_str)
    if isinstance(msg, pynmea2.types.talker.RMC) and (msg.latitude != 0 and msg.longitude != 0):
        latitude = round(msg.latitude, 6)
        longitude = round(msg.longitude, 6)
        speed = msg.spd_over_grnd
        date_str, time_str = read_rtc()

        location_data = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [latitude, longitude]
            },
            "properties": {
                "speed": speed,
                "timestamp": f"{date_str} {time_str}"
            }
        }
        return location_data, latitude, longitude
    else:
        return None, None, None

# Function to get the date and time from RTC
def read_rtc():
    # Read the current time from the RTC
    now = rtc.datetime

    # Add 5 hours and 30 minutes to the current time
    hour = now.tm_hour + 5
    minute = now.tm_min + 30

    # Correct for overflow (e.g., if adding 30 minutes goes beyond 59 minutes)
    if minute >= 60:
        hour += minute // 60
        minute %= 60

    # Format the adjusted time
    date_str = f"{now.tm_year:02}_{now.tm_mon:02}_{now.tm_mday:02}"
    time_str = f"{hour:02}:{minute:02}:{now.tm_sec:02}"

    return date_str, time_str

# Function to get the GeoJSON file path
def get_geojson_file_path(folder_path):
    date_str = read_rtc()[0]
    file_name = f"{date_str}.geojson"
    return os.path.join(folder_path, file_name)

# Function to append data to the GeoJSON file
def append_data_to_file(data, file_path):
    with open(file_path, "a") as geojson_file:
        json.dump(data, geojson_file)
        geojson_file.write('\n')

# Function to connect to PostgreSQL
def connect_to_db():
    try:
        connection = psycopg2.connect(
            user="postgres",
            password="rvce1234",
            host="demo.coccpvzcn43y.ap-southeast-1.rds.amazonaws.com",
            port=5432,
            database="postgres"
        )
        return connection
    except (Exception, psycopg2.Error) as error:
        print("Error while connecting to PostgreSQL:", error)

# Function to create a new table for each day per vehicle
# Function to create a new table for each day per vehicle
# Function to insert vehicle data into the specified table
def insert_data(connection, table_name, vehicle_id, latitude, longitude, speed, timestamp):
    try:
        cursor = connection.cursor()
        insert_query = f"""
            INSERT INTO {table_name} (vehicle_id, latitude, longitude, speed, timestamp)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (vehicle_id, latitude, longitude, speed, timestamp))
        connection.commit()
        print("Data inserted successfully.")
    except (Exception, psycopg2.Error) as error:
        print("Error inserting data:", error)
# Function to create a new table for each day per vehicle
def create_table(connection, table_name):
    try:
        cursor = connection.cursor()
        create_table_query = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id SERIAL PRIMARY KEY,
                vehicle_id INTEGER,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                speed DOUBLE PRECISION,
                timestamp TIMESTAMPTZ
            )
        """
        cursor.execute(create_table_query)
        connection.commit()
        print(f"Table '{table_name}' created successfully.")
    except (Exception, psycopg2.Error) as error:
        print(f"Error creating table '{table_name}':", error)

# Main function
def main():
    ser = serial.Serial('/dev/ttyUSB0', baudrate=9600, timeout=1.0)
    ct = 0

    # Set your folder path here
    folder_path = "/home/atdxt/Documents/jso"
    geojson_file_path = get_geojson_file_path(folder_path)

    print(f"Waiting for GPS connection. Writing to file: {geojson_file_path}")

    try:
        while True:
            try:
                data = ser.readline().decode('utf-8')
                if data.startswith('$GNRMC'):
                    location_data, latitude, longitude = parse_gnrmc(data)
                    if location_data:
                     
                        
                        print(f"Latitude: {latitude}, Longitude: {longitude}")
                        print(ct)
                        if ct == 10:
                            # Append data to file when ct=10
                            append_data_to_file(location_data, geojson_file_path)
                            print(f"Location data appended to GeoJSON file at ct={ct}")

                            if check_internet_connection():
                                connection = connect_to_db()

                                # Get the current date for creating a table
                                today = read_rtc()[0]
                                table_name = f"vehicle_13_{today}"  # Assuming vehicle ID is 12, adjust as needed

                                create_table(connection, table_name)
                                insert_data(connection, table_name, 12, latitude, longitude, location_data["properties"]["speed"], location_data["properties"]["timestamp"])

                                connection.close()

                                print(f"Data uploaded to database for {today}")

                                # Reset the counter after successful upload
                                ct = 0
                            else:
                                print("No internet connection. Data will be uploaded on the next attempt.")
                                ct=(ct+1)%11
                            # Reset the counter after every 10 iterations
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
