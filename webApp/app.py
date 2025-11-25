from flask import Flask, json, jsonify, render_template, Response, request, redirect, url_for, session, stream_with_context
from flask_cors import CORS
from waitress import serve
import configparser
import os
import psycopg2
import requests
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps

from src.get_layer_info import (
    get_feature_data, get_layer_time_bounds, get_meteo_stations_geojson, get_meteostation_month_data,
    get_feature_data_from_lat_lon, get_data_time_bounds, get_data_from_meteostation,
    get_station_time_bounds, get_station_data_from_lat_lon, export_table_to_netcdf, parse_sld_rules,
    get_feature_data_from_lat_lon_dekad
)
from src.import_meteo_csv import import_meteo_csv_stream   
from src.create_layer import read_nc_file_stream
from src.seeding import seed_layer_tiles

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
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM admin_users;")
    user_count = cur.fetchone()[0]
    cur.close()
    close_db_connection(conn)

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # If no users exist, allow default admin login
        if user_count == 0 and username == "admin" and password == "admin":
            session['admin_logged_in'] = True
            session['admin_username'] = username
            return redirect(url_for('admin_dashboard'))

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

    # Load full config for preservation
    config = configparser.ConfigParser()
    config.read(config_path)

    # Prepare filtered config for display
    filtered_config = configparser.ConfigParser()
    for section in config.sections():
        if section == 'database' or section == 'geoserver':
            continue
        filtered_config.add_section(section)
        for key, value in config.items(section):
            if section == 'base' and key == 'base_url':
                continue
            filtered_config.set(section, key, value)

    # Handle POST (save filtered config only)
    if request.method == 'POST':
        config_raw = request.form.get('config_raw')
        if config_raw:
            # Parse edited config, update only allowed sections/keys
            edited_config = configparser.ConfigParser()
            edited_config.read_string(config_raw)
            for section in edited_config.sections():
                if section == 'database' or section == 'geoserver':
                    continue
                for key, value in edited_config.items(section):
                    if section == 'base' and key == 'base_url':
                        continue
                    if not config.has_section(section):
                        config.add_section(section)
                    config.set(section, key, value)
            # Save the full config (preserving base/base_url and database)
            with open(config_path, 'w') as f:
                config.write(f)
            message = "Configuration updated successfully."

    # Prepare config text for textarea
    from io import StringIO
    output = StringIO()
    filtered_config.write(output)
    config_raw = output.getvalue()

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

@app.route('/admin/import_meteo_stations_stream', methods=['POST'])
@admin_required
def import_meteo_stations_stream():
    # Access request.form here, before defining generate()
    csv_filename = request.form.get('csv_filename')
    if not csv_filename:
        def error_gen():
            yield "data: No CSV filename provided.\n\n"
        return Response(stream_with_context(error_gen()), mimetype='text/event-stream')

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    csv_file = os.path.join(project_root, 'fileExchange', 'uploads', csv_filename)
    config_path = os.path.join(project_root, 'config', 'config.ini')
    sql_path = os.path.join(project_root, 'DB_Scripts', 'meteo_stations.sql')

    if not os.path.isfile(csv_file):
        def error_gen():
            yield f"data: CSV file '{csv_filename}' not found.\n\n"
        return Response(stream_with_context(error_gen()), mimetype='text/event-stream')

    def generate():
        # ... rest of your streaming logic ...
        # (no access to request.form here!)
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            try:
                cur.execute("DELETE FROM meteostation_month_data;")
                conn.commit()
            except Exception:
                conn.rollback()
            cur.close()
            close_db_connection(conn)
            yield "data: Previous data deleted (if any).\n\n"
        except Exception:
            yield "data: Could not delete previous data (ignored).\n\n"

        try:
            for message in import_meteo_csv_stream(csv_file, config_path=config_path, sql_path=sql_path):
                yield f"data: {message}\n\n"
        except Exception as e:
            yield f"data: Error importing: {e}\n\n"

        try:
            os.remove(csv_file)
            yield f"data: Imported '{csv_filename}' successfully and deleted the file.\n\n"
        except Exception as e:
            yield f"data: Imported but could not delete CSV file: {e}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/admin/layer_creation', methods=['GET', 'POST'])
@admin_required
def admin_layer_creation():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    upload_folder = os.path.join(project_root, 'fileExchange', 'uploads')
    nc_files = [f for f in os.listdir(upload_folder) if f.lower().endswith('.nc')]
    json_files = [f for f in os.listdir(upload_folder) if f.lower().endswith('.json')]
    xml_files = [f for f in os.listdir(upload_folder) if f.lower().endswith('.xml')]
    message = None

    return render_template(
        'admin_layer_creation.html',
        nc_files=nc_files,
        json_files=json_files,
        xml_files=xml_files,
        message=message
    )

@app.route('/admin/create_layer_stream', methods=['POST'])
@admin_required
def create_layer_stream():
    nc_filename = request.form.get('nc_filename')
    layer_name = request.form.get('layer_name')
    value_dim = request.form.get('value_dim')
    time_dim = request.form.get('time_dim')
    lon_dim = request.form.get('lon_dim')
    lat_dim = request.form.get('lat_dim')
    product_json = request.form.get('product_json')
    layer_xml = request.form.get('layer_xml')

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    upload_folder = os.path.join(project_root, 'fileExchange', 'uploads')
    metadata_folder = os.path.join(project_root, 'metadata')
    nc_file = os.path.join(upload_folder, nc_filename)
    json_file = os.path.join(upload_folder, product_json) if product_json else None
    xml_file = os.path.join(upload_folder, layer_xml) if layer_xml else None
    config_path = os.path.join(project_root, 'config', 'config.ini')

    def generate():
        for message in read_nc_file_stream(
            nc_file,
            layer_name,
            value_dim,
            time_dim,
            lon_dim,
            lat_dim,
            config_path=config_path
        ):
            yield f"data: {message}\n\n"
        # After streaming is done, move the .json and .xml files
        try:
            os.remove(nc_file)
            yield f"data: Layer created and file '{nc_filename}' deleted.\n\n"
        except Exception as e:
            yield f"data: Layer created but could not delete file: {e}\n\n"
        # Move product info JSON
        if json_file:
            try:
                target_json = os.path.join(metadata_folder, f"{layer_name}.json")
                os.rename(json_file, target_json)
                yield f"data: Product info file moved to '{target_json}'.\n\n"
            except Exception as e:
                yield f"data: Could not move product info file: {e}\n\n"
        # Move layer metadata XML
        if xml_file:
            try:
                target_xml = os.path.join(metadata_folder, f"{layer_name}.xml")
                os.rename(xml_file, target_xml)
                yield f"data: Metadata file moved to '{target_xml}'.\n\n"
            except Exception as e:
                yield f"data: Could not move metadata file: {e}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/admin/seed_layer', methods=['GET', 'POST'])
@admin_required
def admin_seed_layer():
    message = None
    if request.method == 'POST':
        layer = request.form.get('layer')
        zoom_start = int(request.form.get('zoom_start', 3))
        zoom_stop = int(request.form.get('zoom_stop', 8))
        try:
            seed_layer_tiles(layer, zoom_start, zoom_stop)
            message = f"Seeding started for layer '{layer}' (zoom {zoom_start}-{zoom_stop})."
        except Exception as e:
            message = f"Error: {e}"
    return render_template('admin_seed_layer.html', message=message)

###############################################################################
# Existing routes
###############################################################################

@app.route('/get_data_from_lat_lon/<lat>/<lon>/<yearFrom>/<monthFrom>/<yearTo>/<monthTo>/<layer>')
def get_data_from_latlon(lat, lon, yearFrom, monthFrom, yearTo, monthTo, layer):
    conn = get_db_connection()
    feat_info = get_feature_data_from_lat_lon(layer, lat, lon, int(yearFrom), int(monthFrom), int(yearTo), int(monthTo), conn)
    close_db_connection(conn)
    return jsonify(feat_info)

@app.route('/get_data_from_latlon_dekad/<lat>/<lon>/<dateFrom>/<dateTo>/<layer>')
def get_data_from_latlon_dekad(lat, lon, dateFrom, dateTo, layer):
    conn = get_db_connection()
    feat_info = get_feature_data_from_lat_lon_dekad(layer, float(lat), float(lon), dateFrom, dateTo, conn)
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
    metadata_path = os.path.join(os.path.dirname(__file__), '..', 'metadata', f"{layer}.json")
    try:
        with open(metadata_path, 'r') as f:
            product_info = json.load(f)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(product_info)

@app.route('/clim_chart/<layer>/<lat>/<lon>')
def clim_chart(layer, lat, lon):
    print("en clim_chart")
    color_min = get_key_config(layer).get('chart_color_min')
    color_max = get_key_config(layer).get('chart_color_max')
    style = get_key_config(layer).get('style')
    rules_json = "[]"  # Default
    if style == "SLD" or style == "sld":
        geoserver_url = get_key_config('base').get('geoserver_url')
        username = get_key_config('geoserver').get('username')
        password = get_key_config('geoserver').get('password')
        workspace = "droughts"  # Change if your workspace is different

        # 1. Get the style name for the layer
        layer_info_url = f"{geoserver_url}/rest/layers/{workspace}:{layer}.json"
        try:
            resp = requests.get(layer_info_url, auth=(username, password))
            resp.raise_for_status()
            layer_info = resp.json()
            style_name = layer_info['layer']['defaultStyle']['name']
            if ':' in style_name:
                style_name = style_name.split(':', 1)[1]  # Remove workspace prefix
            # 2. Fetch the SLD using the style name
            sld_url = f"{geoserver_url}/rest/workspaces/{workspace}/styles/{style_name}.sld"
            sld_resp = requests.get(sld_url, auth=(username, password))
            sld_resp.raise_for_status()
            sld_content = sld_resp.text
            rules = parse_sld_rules(sld_content)
            rules_json = json.dumps(rules)
        except Exception as e:
            print(f"Error fetching SLD from GeoServer: {e}")
            rules_json = "[]"
    config = load_config()
    base_url = config['base'].get('base_url', '')
    conn = get_db_connection()
    time_bounds = get_data_time_bounds(lat, lon, layer, conn)
    close_db_connection(conn)
    date_format = get_key_config(layer).get('date_format')
    if not time_bounds or not time_bounds.get('min_date') or not time_bounds.get('max_date'):
        # Handle missing data gracefully
        return render_template(
            'clim_chart.html',
            lat=lat,
            lon=lon,
            layer=layer,
            min_date='',
            max_date='',
            color_min=color_min,
            color_max=color_max,
            style=rules_json,
            localhost=base_url,
            date_format=date_format,
            error="No data available for this location/layer."
        )
    return render_template(
        'clim_chart.html',
        lat=lat,
        lon=lon,
        layer=layer,
        min_date=time_bounds['min_date'],
        max_date=time_bounds['max_date'],
        color_min=color_min,
        color_max=color_max,
        style=rules_json,
        localhost=base_url,
        date_format=date_format
    )

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

    def generate():
        # Modify export_table_to_netcdf to yield messages
        for message in export_table_to_netcdf(conn, table_name, 'grid_025dd', 0.25, init_date, end_date, bbox, output_filename):
            yield f"data: {message}\n\n"
        close_db_connection(conn)

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

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