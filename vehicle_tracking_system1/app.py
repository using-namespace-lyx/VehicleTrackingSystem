from flask import Flask, render_template, jsonify, request
import psycopg2
import json
import traceback

app = Flask(__name__)

# Function to convert JSONB array data to a list of dictionaries
def convert_jsonb_to_list(jsonb_array_data):
    json_data = json.loads(json.dumps(jsonb_array_data))
    return json_data

# Flask route to render the firstpage.html
@app.route('/')
def index():
    return render_template('firstpage.html')

# Flask route to fetch locations from the database
@app.route('/get_locations', methods=['POST'])
def get_locations():
    try:
        # Connect to PostgreSQL database
        with psycopg2.connect(
                user="postgres",
                password="rvce1234",
                host="database-1.cnco44k2w5r9.ap-south-1.rds.amazonaws.com",
                port=5432,
                database="postgres"
        ) as connection:
            with connection.cursor() as cursor:
                vehicle_id = request.form.get('vehicle_id')
                # Using the primary key 'date' for querying the table
                cursor.execute("SELECT location_data FROM {}".format(vehicle_id))
                records = cursor.fetchall()
                converted_data = convert_jsonb_to_list(records[0])
        return jsonify(converted_data)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "Internal Server Error"}), 500

# Flask route to handle form submission
@app.route('/map', methods=['GET', 'POST'])
def map():
    try:
        vehicle_id = request.form.get('vehicle_id')
        return render_template('map.html', vehicle_id=vehicle_id)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "Internal Server Error"}), 500

if __name__ == '__main__':
    app.run(debug=True)
