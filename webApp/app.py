from flask import Flask, json, jsonify, render_template, Response, request, redirect, url_for, session
from flask_cors import CORS
from waitress import serve
import configparser
import os
import psycopg2
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps

from src.get_layer_info import (
    get_feature_data, get_layer_time_bounds, get_meteo_stations_geojson, get_meteostation_month_data,
    get_feature_data_from_lat_lon, get_data_time_bounds, get_data_from_meteostation,
    get_station_time_bounds, get_station_data_from_lat_lon, export_table_to_netcdf, parse_sld_rules
)
from src.import_meteo_csv import import_meteo_csv   

##############################################################################
# CONFIGURATION
##############################################################################

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.ini')
    config = configparser.ConfigParser()
    config.read(config_path)
    return config

def get_key_config(feat):
    config = load_config()
    if feat not in config:
        return {}
    base_url = config['base'].get('base_url', '')
    geoserver_url = config['base'].get('geoserver_url', '')
    return {
        key: config.get(feat, key)
            .replace('{base_url}', base_url)
            .replace('{geoserver_url}', geoserver_url)
        for key in config[feat]
    }

############################################################################### 
# Database connection functions 
###############################################################################

def get_db_connection():
    config = load_config()
    db_config = dict(config.items('database'))
    db_config = {k: v for k, v in db_config.items() if k in ['host', 'port', 'dbname', 'user', 'password']}
    conn = psycopg2.connect(**db_config)
    return conn

def close_db_connection(conn):
    if conn:
        conn.commit()
        conn.close()

###############################################################################
# Admin user management
###############################################################################

def get_admin_user(username):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, password_hash FROM admin_users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    close_db_connection(conn)
    return user

def create_admin_user(username, password):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO admin_users (username, password_hash) VALUES (%s, %s)", 
                (username, generate_password_hash(password)))
    conn.commit()
    cur.close()
    close_db_connection(conn)

def delete_admin_user(username):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM admin_users WHERE username = %s", (username,))
    conn.commit()
    cur.close()
    close_db_connection(conn)

def change_admin_password(username, new_password):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE admin_users SET password_hash = %s WHERE username = %s", 
                (generate_password_hash(new_password), username))
    conn.commit()
    cur.close()
    close_db_connection(conn)

###############################################################################
# Flask app
###############################################################################

app = Flask(__name__)
app.secret_key = 'droughts'  # Change this!
CORS(app)

###############################################################################
# Admin login and protection
###############################################################################

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = get_admin_user(username)
        if user and check_password_hash(user[2], password):
            session['admin_logged_in'] = True
            session['admin_username'] = username
            return redirect(url_for('admin_dashboard'))
        else:
            error = "Invalid username or password"
    return render_template('admin_login.html', error=error)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    return redirect(url_for('main_map'))

@app.route('/admin/config', methods=['GET', 'POST'])
@admin_required
def admin_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.ini')
    message = None

    if request.method == 'POST':
        config_raw = request.form.get('config_raw')
        if config_raw:
            with open(config_path, 'w') as f:
                f.write(config_raw)
            message = "Configuration updated successfully."

    with open(config_path, 'r') as f:
        config_raw = f.read()

    return render_template('admin_config.html', config_raw=config_raw, message=message)

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html', username=session.get('admin_username'))

@app.route('/admin/users', methods=['GET', 'POST'])
@admin_required
def admin_users():
    message = None
    if request.method == 'POST':
        action = request.form['action']
        username = request.form['username']
        password = request.form.get('password')
        if action == 'create':
            create_admin_user(username, password)
            message = f"User {username} created."
        elif action == 'delete':
            delete_admin_user(username)
            message = f"User {username} deleted."
        elif action == 'change_password':
            change_admin_password(username, password)
            message = f"Password for {username} changed."
    return render_template('admin_users.html', message=message)

@app.route('/admin/layer_creation')
@admin_required
def admin_layer_creation():
    return render_template('admin_layer_creation.html')

@app.route('/admin/add_station_data', methods=['GET', 'POST'])
@admin_required
def admin_add_station_data():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    upload_folder = os.path.join(project_root, 'fileExchange', 'uploads')
    csv_files = [f for f in os.listdir(upload_folder) if f.lower().endswith('.csv')]
    message = None

    if request.method == 'POST':
        csv_filename = request.form.get('csv_filename')
        if not csv_filename:
            message = "No CSV file selected."
        else:
            # Call the import service directly
            from src.import_meteo_csv import import_meteo_csv
            config_path = os.path.join(project_root, 'config', 'config.ini')
            sql_path = os.path.join(project_root, 'DB_Scripts', 'meteo_stations.sql')
            csv_file = os.path.join(upload_folder, csv_filename)
            try:
                import_meteo_csv(csv_file, config_path=config_path, sql_path=sql_path)
                message = f"Imported '{csv_filename}' successfully."
            except Exception as e:
                message = f"Error importing: {e}"

    return render_template('admin_add_station_data.html', csv_files=csv_files, message=message)

@app.route('/admin/upload', methods=['GET', 'POST'])
@admin_required
def admin_upload():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    upload_folder = os.path.join(project_root, 'fileExchange', 'uploads')
    print("Uploading to:", upload_folder)  # For debugging
    message = None

    if request.method == 'POST':
        if 'file' not in request.files:
            message = "No file part"
        else:
            file = request.files['file']
            if file.filename == '':
                message = "No selected file"
            else:
                filepath = os.path.join(upload_folder, file.filename)
                file.save(filepath)
                message = f"File '{file.filename}' uploaded successfully."

    return render_template('admin_upload.html', message=message)

@app.route('/admin/download', methods=['GET', 'POST'])
@admin_required
def admin_download():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    download_folder = os.path.join(project_root, 'fileExchange', 'downloads')
    message = None
    files = [f for f in os.listdir(download_folder) if os.path.isfile(os.path.join(download_folder, f))]

    if request.method == 'POST':
        selected_file = request.form.get('selected_file')
        if selected_file and selected_file in files:
            filepath = os.path.join(download_folder, selected_file)
            try:
                with open(filepath, 'rb') as f:
                    response = Response(f.read(), mimetype='application/octet-stream')
                    response.headers.set('Content-Disposition', 'attachment', filename=selected_file)
                os.remove(filepath)
                return response
            except Exception as e:
                message = f"Error downloading file: {e}"
        else:
            message = "No file selected or file does not exist."

    return render_template('admin_download.html', files=files, message=message)

@app.route('/admin/import_meteo_stations', methods=['POST'])
@admin_required
def import_meteo_stations():
    csv_filename = request.form.get('csv_filename')
    if not csv_filename:
        return jsonify({"error": "No CSV filename provided."}), 400

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    csv_file = os.path.join(project_root, 'fileExchange', 'uploads', csv_filename)
    config_path = os.path.join(project_root, 'config', 'config.ini')
    sql_path = os.path.join(project_root, 'DB_Scripts', 'meteo_stations.sql')

    if not os.path.isfile(csv_file):
        return jsonify({"error": f"CSV file '{csv_filename}' not found."}), 404

    # Try to delete existing data, ignore errors if table doesn't exist or is empty
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM meteostation_month_data;")
            conn.commit()
        except Exception as e:
            # Ignore error if table does not exist or is empty
            conn.rollback()
        cur.close()
        close_db_connection(conn)
    except Exception as e:
        # Ignore connection errors for deletion step
        pass

    # Import new data
    try:
        import_meteo_csv(csv_file, config_path=config_path, sql_path=sql_path)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Delete the CSV file after import
    try:
        os.remove(csv_file)
    except Exception as e:
        return jsonify({"error": f"Imported but could not delete CSV file: {e}"}), 500

    return jsonify({"success": True, "message": f"Imported '{csv_filename}' successfully and deleted the file."})

###############################################################################
# Existing routes
###############################################################################

@app.route('/get_data_from_lat_lon/<lat>/<lon>/<yearFrom>/<monthFrom>/<yearTo>/<monthTo>/<layer>')
def get_data_from_latlon(lat, lon, yearFrom, monthFrom, yearTo, monthTo, layer):
    conn = get_db_connection()
    feat_info = get_feature_data_from_lat_lon(layer, lat, lon, int(yearFrom), int(monthFrom), int(yearTo), int(monthTo), conn)
    close_db_connection(conn)
    return jsonify(feat_info)

@app.route('/get_data_station_from_lat_lon/<lat>/<lon>/<yearFrom>/<monthFrom>/<yearTo>/<monthTo>/<layer>/<variable>')
def get_data_station_from_latlon(lat, lon, yearFrom, monthFrom, yearTo, monthTo, layer, variable):
    conn = get_db_connection()
    feat_info = get_station_data_from_lat_lon(layer, variable, lat, lon, int(yearFrom), int(monthFrom), int(yearTo), int(monthTo), conn)
    close_db_connection(conn)
    return jsonify(feat_info)

@app.route('/get_feature_info/<layer>/<lat>/<lon>/<date>')
def get_feature_info(layer, lat, lon, date):
    conn = get_db_connection()
    feat_info = get_feature_data(layer, lat, lon, date, conn)
    close_db_connection(conn)
    return jsonify(feat_info)

@app.route('/get_all_meteostations')
def get_all_meteostations():
    conn = get_db_connection()
    feature_collection = get_meteo_stations_geojson(conn)
    close_db_connection(conn)
    return jsonify(feature_collection)

@app.route('/get_meteostation_info/<layer>/<lat>/<lon>/<date>')
def get_meteostation_info(layer, lat, lon, date):
    conn = get_db_connection()
    meteostation_info = get_meteostation_month_data(conn, lat, lon, date)
    close_db_connection(conn)
    return jsonify(meteostation_info)

@app.route('/get_data_from_station/<lat>/<lon>/', defaults={'date': None})
@app.route('/get_data_from_station/<lat>/<lon>/<date>')
def get_data_from_station(lat, lon, date):
    conn = get_db_connection()
    station_data = get_data_from_meteostation(conn, lat, lon, date)
    close_db_connection(conn)
    return jsonify(station_data)

@app.route('/get_product_info/<layer>')
def get_product_info(layer):
    products_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'products.json')
    try:
        with open(products_path, 'r') as f:
            products = json.load(f)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    product_info = products.get(layer, {})
    return jsonify(product_info)

@app.route('/clim_chart/<layer>/<lat>/<lon>')
def clim_chart(layer, lat, lon):
    style = get_key_config(layer).get('style')
    rules = parse_sld_rules(f"./misc/sld/{style}")
    rules_json = json.dumps(rules)
    color_min = get_key_config(layer).get('chart_color_min')
    color_max = get_key_config(layer).get('chart_color_max')
    config = load_config()
    base_url = config['base'].get('base_url', '')
    conn = get_db_connection()
    time_bounds = get_data_time_bounds(lat, lon, layer, conn)
    close_db_connection(conn)
    return render_template('clim_chart.html',lat=lat,lon=lon,layer=layer,year_init=time_bounds['min_year'],year_end=time_bounds['max_year'], color_min=color_min, color_max=color_max, style=rules_json, localhost=base_url)

@app.route('/clim_station_chart/<layer>/<lat>/<lon>')
def clim_station_chart(layer, lat, lon):
    color_min = get_key_config(layer).get('chart_color_min')
    color_max = get_key_config(layer).get('chart_color_max')
    config = load_config()
    base_url = config['base'].get('base_url', '')
    conn = get_db_connection()
    time_bounds = get_station_time_bounds(lat, lon, conn)
    close_db_connection(conn)
    return render_template('clim_station_chart.html',lat=lat,lon=lon,layer=layer,year_init=time_bounds['min_year'],year_end=time_bounds['max_year'], color_min=color_min, color_max=color_max, localhost=base_url)

@app.route('/get_metadata/<layer>')
def get_metadata(layer):
    filename = f"{layer}.xml"
    xml_path = os.path.join(os.path.dirname(__file__), '..', 'metadata', filename)
    try:
        with open(xml_path, 'r') as f:
            xml_content = f.read()
        return Response(xml_content, mimetype='application/xml')
    except Exception as e:
        return Response(f"<error>{str(e)}</error>", mimetype='application/xml', status=404)

@app.route('/export_table/<table_name>', methods=['POST'])
def export_table(table_name):
    init_date = request.json.get("init_date")
    end_date = request.json.get("end_date")
    bbox = request.json.get("bbox") 
    if bbox == {}:
        bbox = None
    output_filename = request.json.get("output_filename") or f"{table_name}_{init_date}_{end_date}.nc"
    conn = get_db_connection()
    result = export_table_to_netcdf(conn, table_name, 'grid_025dd', 0.25, init_date, end_date, bbox, output_filename)
    close_db_connection(conn)
    return jsonify(result)

@app.route('/')
def main_map():
    map_config = get_key_config('map')
    layers = {}
    layer_names = map_config["layers"].split(',')
    for layer_name in layer_names:
        layer = get_key_config(layer_name)
        conn = get_db_connection()
        time_bounds = get_layer_time_bounds(layer_name, conn)
        close_db_connection(conn)
        layer['time_bounds'] = time_bounds
        layers[layer_name] = layer
    config = load_config()
    base_url = config['base'].get('base_url', '')
    map_config['layers'] = layers
    map_config['localhost'] = base_url
    print(map_config)
    return render_template('main_map.html', map_config=map_config)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="WebGIS Droughts Application")
    parser.add_argument('--development', action='store_true', help="Run in development mode")
    args = parser.parse_args()
    if args.development:
        app.run(host="0.0.0.0",debug=True)
    else:
        serve(app, host='0.0.0.0', port=5000)