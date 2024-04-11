import os
import serial
import shutil
import psutil
import pynmea2
import json
import socket
import psycopg2
from adafruit_ds3231 import DS3231
import board
import busio
from datetime import datetime
from datetime import timedelta

def setup_led(led_pin):
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(led_pin, GPIO.OUT)
    return led_pin



# declaring credentials for local host
local_db_name = "atdxtrv"
local_db_user = "atdxt"
local_db_password = "1234"

# AWS RDS database credentials
aws_db_endpoint = "demo.coccpvzcn43y.ap-southeast-1.rds.amazonaws.com"
aws_db_name = "postgres"
aws_db_user = "postgres"
aws_db_password = "rvce1234"


def connect_to_db():
    try:
        connection = psycopg2.connect(
            user="atdxt",
            password="1234",
            host="localhost",
            port=5432,
            database="atdxtrv",
        )
        return connection
    except (Exception, psycopg2.Error) as error:
        print("Error while connecting to PostgreSQL:", error)


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


def update_local_database(your_table_name, vehicle_id, latitude, longitude, speed, timestamp, threshold_sq):
    # Connect to the local database
    local_connection = psycopg2.connect(
        database=local_db_name,
        user=local_db_user,
        password=local_db_password,
        host="localhost",
        port=5432,  # Default PostgreSQL port
    )
    
    try:
        cursor = local_connection.cursor()

        # Check if the difference between successive latitude and longitude is greater than the threshold
        select_query = f"""
            SELECT latitude, longitude
            FROM {your_table_name}
            ORDER BY timestamp DESC
            LIMIT 1
        """
        cursor.execute(select_query)
        last_lat, last_lon = cursor.fetchone() if cursor.rowcount > 0 else (None, None)

        if last_lat is None or last_lon is None or ((latitude - last_lat)*2 + (longitude - last_lon)*2 > threshold_sq):
            # If the difference is greater than the threshold, insert the data
            insert_query = f"""
                INSERT INTO {your_table_name} (vehicle_id, latitude, longitude, speed, timestamp)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(insert_query, (vehicle_id, latitude, longitude, speed, timestamp))
            local_connection.commit()
            print("Data inserted successfully.")
        else:
            print("Skipping data insertion due to proximity to the previous point.")

    except (Exception, psycopg2.Error) as error:
        print("Error inserting data:", error)
    finally:
        # Close the connection
        local_connection.close()

def sync_data_to_aws(your_table_name):
    # Connect to the local and AWS RDS databases
    local_connection = psycopg2.connect(
        database=local_db_name,
        user=local_db_user,
        password=local_db_password,
        host="localhost",
        port=5432,  # Default PostgreSQL port
    )
    aws_connection = psycopg2.connect(
        database=aws_db_name,
        user=aws_db_user,
        password=aws_db_password,
        host=aws_db_endpoint,
        port=5432,  # Default PostgreSQL port
    )

    local_cursor = local_connection.cursor()
    aws_cursor = aws_connection.cursor()
    local_cursor.execute("SET TIME ZONE 'Asia/Kolkata'")


    create_table(aws_connection, your_table_name)
    aws_cursor.execute("SET TIME ZONE 'Asia/Kolkata'")


    try:
        # Fetch data from the local and AWS RDS databases
        local_cursor.execute(f"SELECT * FROM {your_table_name}")
        local_data = local_cursor.fetchall()

        aws_cursor.execute(f"SELECT * FROM {your_table_name}")
        aws_data = aws_cursor.fetchall()

        # Identify extra data in the local database
        local_ids = set(row[0] for row in local_data)  # Assuming id is at index 0
        aws_ids = set(row[0] for row in aws_data)  # Assuming id is at index 0

        extra_data = [row for row in local_data if row[0] not in aws_ids]

        # Append extra data to the AWS RDS database
        for row in extra_data:
            adjusted_timestamp = row[5] + timedelta(hours=5, minutes=30)


            aws_cursor.execute(
                f"INSERT INTO {your_table_name} (vehicle_id, latitude, longitude, speed, timestamp) VALUES (%s, %s, %s, %s, %s)",
                (row[1], row[2], row[3], row[4], adjusted_timestamp),  # Assuming the order of values in the row tuple
            )

        # Commit changes
        aws_connection.commit()

        print("Extra data appended to the AWS RDS database.")

    finally:
        # Close connections
        local_cursor.close()
        aws_cursor.close()
        local_connection.close()
        aws_connection.close()


# ... (rest of your code)


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
            "geometry": {"type": "LineString", "coordinates": [latitude, longitude]},
            "properties": {"speed": speed, "timestamp": f"{date_str} {time_str}"},
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
        geojson_file.write("\n")

# Function to get the current disk usage in percentage and gigabytes
def get_disk_usage():
    disk_usage = psutil.disk_usage('/')
    total_gb = round(disk_usage.total / (1024 ** 3), 2)
    used_gb = round(disk_usage.used / (1024 ** 3), 2)
    percent_used = disk_usage.percent
    return percent_used, used_gb, total_gb

# Function to delete older files in the specified folder based on percentage usage
def delete_older_files(folder_path, threshold_high=80, threshold_low=75):
    percent_used, used_gb, total_gb = get_disk_usage()

    #print(f"Current disk usage: {percent_used}% ({used_gb} GB used out of {total_gb} GB")

    if percent_used >= threshold_high:
        print(f"Disk usage exceeds {threshold_high}%. Deleting older files to free up space.")

        files = os.listdir(folder_path)
        files.sort(key=lambda x: os.path.getctime(os.path.join(folder_path, x)))

        while percent_used >= threshold_low and files:
            file_to_delete = files.pop(0)
            file_path = os.path.join(folder_path, file_to_delete)

            try:
                os.remove(file_path)
                print(f"Deleted: {file_to_delete}")
            except Exception as e:
                print(f"Error deleting {file_to_delete}: {str(e)}")

            percent_used, _, _ = get_disk_usage()

        print(f"Deletion complete. Current disk usage: {percent_used}% ({used_gb} GB used out of {total_gb} GB)")


def check_table_exists(connection, table_name):
    try:
        cursor = connection.cursor()
        cursor.execute(f"SELECT * FROM information_schema.tables WHERE table_name = '{table_name}'")
        return cursor.fetchone() is not None
    except (Exception, psycopg2.Error) as error:
        print(f"Error checking table existence for '{table_name}':", error)


def sync_and_delete_previous_table(previous_table_name):
    # Connect to the local and AWS RDS databases
    local_connection = connect_to_db()
    aws_connection = psycopg2.connect(
        database=aws_db_name,
        user=aws_db_user,
        password=aws_db_password,
        host=aws_db_endpoint,
        port=5432,  # Default PostgreSQL port
    )

    local_cursor = local_connection.cursor()
    aws_cursor = aws_connection.cursor()

    create_table(aws_connection, previous_table_name)

    try:
        # Fetch data from the local and AWS RDS databases
        local_cursor.execute(f"SELECT * FROM {previous_table_name}")
        local_data = local_cursor.fetchall()

        aws_cursor.execute(f"SELECT * FROM {previous_table_name}")
        aws_data = aws_cursor.fetchall()

        # Identify extra data in the local database
        local_ids = set(row[0] for row in local_data)  # Assuming id is at index 0
        aws_ids = set(row[0] for row in aws_data)  # Assuming id is at index 0

        extra_data = [row for row in local_data if row[0] not in aws_ids]

        # Append extra data to the AWS RDS database
        for row in extra_data:
            aws_cursor.execute(
                f"INSERT INTO {previous_table_name} (vehicle_id, latitude, longitude, speed, timestamp) VALUES (%s, %s, %s, %s, %s)",
                row,
            )

        # Commit changes
        aws_connection.commit()

        print(f"Previous date's data appended to the AWS RDS database. Table: {previous_table_name}")

        # Delete the table from the local database
        local_cursor.execute(f"DROP TABLE IF EXISTS {previous_table_name}")
        local_connection.commit()

        print(f"Table '{previous_table_name}' deleted from the local database.")

    finally:
        # Close connections
        local_cursor.close()
        aws_cursor.close()
        local_connection.close()
        aws_connection.close()


# Main function
def main():
    ser = serial.Serial('/dev/ttyUSB0', baudrate=9600, timeout=1.0)
    ct = 0
    id="12"
    
    led_pin=setup_led(7)
    GPIO.output(led_pin,GPIO.HIGH)
    # Set your folder path here
    folder_path = "/home/atdxt/Documents/jso"
    geojson_file_path = get_geojson_file_path(folder_path)
    display_counter=0

    print(f"Waiting for GPS connection. Writing to file: {geojson_file_path}")

    try:
        # Check and sync the previous day's data at the start
        previous_date = (datetime.now() - timedelta(days=1)).strftime("%Y_%m_%d")
        previous_table_name = f"vehicle_{id}_{previous_date}"

        local_connection = connect_to_db()
        if check_table_exists(local_connection, previous_table_name):
            sync_and_delete_previous_table(previous_table_name)
        
        while True:
            try:
                delete_older_files(folder_path)
                
                display_counter += 1

                if display_counter % 300 == 0:
                    percent_used, used_gb, total_gb = get_disk_usage()
                    print(f"Current disk usage: {percent_used}% ({used_gb} GB used out of {total_gb})")
                    
                    # Reset display_counter after displaying information
                    display_counter = 0
                    
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
                            today = read_rtc()[0]
                            table_name = f"vehicle_{id}_{today}"  # Assuming vehicle ID is 12, adjust as needed

                            connection = connect_to_db()
                            create_table(connection, table_name)
                            update_local_database(
                                table_name,
                                id,
                                latitude,
                                longitude,
                                location_data["properties"]["speed"],
                                location_data["properties"]["timestamp"],
                                threshold_sq=0.000001,
                            )

                            if check_internet_connection():
                                # Assuming vehicle ID is 12, adjust as needed
                                sync_data_to_aws(
                                    table_name
                                    
                                )
                                print(f"Data uploaded to database for {today}")

                                # Reset the counter after successful upload
                                ct = (ct + 1) % 11
                            else:
                                print("No internet connection. Data will be uploaded on the next attempt.")
                                connection = connect_to_db()
                                create_table(connection, table_name)
                                update_local_database(
                                    table_name,
                                    12,
                                    latitude,
                                    longitude,
                                    location_data["properties"]["speed"],
                                    location_data["properties"]["timestamp"],
                                    threshold_sq=0.000001,
                                )
                                ct = (ct + 1) % 11
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
