
from flask import Flask, json, jsonify, render_template, Response, request, redirect, url_for, session, stream_with_context
from flask_cors import CORS
from waitress import serve
import configparser
import os
import psycopg2
import requests
import threading
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps

from src.get_layer_info import (
    get_feature_data, get_layer_time_bounds, get_meteo_stations_geojson, get_meteostation_month_data,
    get_feature_data_from_lat_lon, get_data_time_bounds, get_data_from_meteostation,
    get_station_time_bounds, get_station_data_from_lat_lon, export_table_to_netcdf, parse_sld_rules,
    get_feature_data_from_lat_lon_dekad,netcdf_to_geotiff, export_table_to_geotiff
)
from src.import_meteo_csv import import_meteo_csv_stream   
from src.create_layer import read_nc_file_stream
from src.create_layer_tif import read_geotiff_file_stream, get_existing_grid_table
from src.seeding import seed_layer_tiles
import time

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
# Progress message management
###############################################################################
def save_progress_message(user_name, process_id, message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO progress_message (user_name, process_id, message) VALUES (%s, %s, %s)",
        (user_name, process_id, message)
    )
    conn.commit()
    cur.close()
    close_db_connection(conn)

def get_progress_messages(user_name, process_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT message FROM progress_message WHERE user_name = %s AND process_id = %s ORDER BY created_at ASC",
        (user_name, process_id)
    )
    messages = [row[0] for row in cur.fetchall()]
    cur.close()
    close_db_connection(conn)
    return messages

def clear_progress_messages(user_name, process_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM progress_message WHERE user_name = %s AND process_id = %s",
        (user_name, process_id)
    )
    conn.commit()
    cur.close()
    close_db_connection(conn)       

def clear_user_progress_messages(user_name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM progress_message WHERE user_name = %s",
        (user_name,)
    )
    conn.commit()
    cur.close()
    close_db_connection(conn)

###############################################################################
# Admin user management
###############################################################################

def get_admin_user(username):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, password_hash, is_superuser FROM admin_users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    close_db_connection(conn)
    return user

def create_admin_user(username, password, is_superuser=False):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO admin_users (username, password_hash, is_superuser) VALUES (%s, %s, %s)", 
                (username, generate_password_hash(password), is_superuser))
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
###############################################################################
###                                                                         ###
###                             Flask app                                   ###   
###                                                                         ###
###############################################################################
###############################################################################

app = Flask(__name__)
app.secret_key = 'droughts'  # Change this!
CORS(app)

###############################################################################
###############################################################################
# ADMINISTRATIVE ROUTES
###############################################################################
###############################################################################
@app.context_processor
def inject_user():
    return dict(user_name=session.get('admin_username'))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

####################################################
# Alerts, progress and information messages
####################################################

@app.route('/admin/send_alert', methods=['POST'])
@admin_required
def admin_send_alert():
    user_name = request.form.get('user_name')
    alert_text = request.form.get('alert_text')
    if not user_name or not alert_text or len(alert_text) > 300:
        return jsonify({'status': 'error', 'message': 'Invalid input'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO alerts (user_name, alert_text) VALUES (%s, %s)",
        (user_name, alert_text)
    )
    conn.commit()
    cur.close()
    close_db_connection(conn)
    return jsonify({'status': 'success'})

@app.route('/admin/delete_alert', methods=['POST'])
@admin_required
def admin_delete_alert():
    alert_id = request.form.get('alert_id')
    if not alert_id:
        return redirect(url_for('admin_dashboard'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM alerts WHERE id = %s", (alert_id,))
    conn.commit()
    cur.close()
    close_db_connection(conn)
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/progress_messages')
@admin_required
def progress_messages():
    process_id = request.args.get('process_id')
    user_name = session.get('admin_username')
    if process_id == "all":
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT message FROM progress_message WHERE user_name = %s ORDER BY created_at ASC",
            (user_name,)
        )
        messages = [row[0] for row in cur.fetchall()]
        cur.close()
        close_db_connection(conn)
    else:
        messages = get_progress_messages(user_name, process_id)
    return jsonify({'messages': messages})

####################################################
# Logout
####################################################

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    return redirect(url_for('main_map'))

####################################################
# Login
####################################################

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
            session['is_superuser'] = user[3]
            return redirect(url_for('admin_dashboard'))
        else:
            error = "Invalid username or password"
    return render_template('admin_login.html', error=error)

####################################################
# Administrative dashboard
####################################################

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    user_name = session.get('admin_username')
    is_superuser = session.get('is_superuser')
    clear_user_progress_messages(user_name)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, user_name, alert_time, alert_text FROM alerts ORDER BY alert_time DESC")
    alerts = [
        dict(id=row[0], user_name=row[1], alert_time=row[2], alert_text=row[3])
        for row in cur.fetchall()
    ]
    cur.close()
    close_db_connection(conn)
    return render_template('admin_dashboard_content.html', user_name=session.get('admin_username'), alerts=alerts, is_superuser=is_superuser)

####################################################
# Administrative edition of configuration
####################################################
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
            edited_config = configparser.ConfigParser()
            edited_config.read_string(config_raw)
            # Remove sections not present in edited_config
            for section in list(config.sections()):
                if section not in edited_config.sections() and section not in ['database', 'geoserver']:
                    config.remove_section(section)
            # Update/add sections and keys from edited_config
            for section in edited_config.sections():
                if section == 'database' or section == 'geoserver':
                    continue
                if not config.has_section(section):
                    config.add_section(section)
                for key, value in edited_config.items(section):
                    if section == 'base' and key == 'base_url':
                        continue
                    config.set(section, key, value)
            # Save the full config
            with open(config_path, 'w') as f:
                config.write(f)
            message = "Configuration updated successfully."

            # Reload config from disk after saving
            config = configparser.ConfigParser()
            config.read(config_path)
            filtered_config = configparser.ConfigParser()
            for section in config.sections():
                if section == 'database' or section == 'geoserver':
                    continue
                filtered_config.add_section(section)
                for key, value in config.items(section):
                    if section == 'base' and key == 'base_url':
                        continue
                    filtered_config.set(section, key, value)

    # Prepare config text for textarea
    from io import StringIO
    output = StringIO()
    filtered_config.write(output)
    config_raw = output.getvalue()

    return render_template('admin_config.html', config_raw=config_raw, message=message)

####################################################
# User management
####################################################
@app.route('/admin/users', methods=['GET', 'POST'])
@admin_required
def admin_users():
    message = None
    if request.method == 'POST':
        action = request.form['action']
        username = request.form['username']
        password = request.form.get('password')
        is_superuser = request.form.get('is_superuser')
        print(f"Action: {action}, Username: {username}, Is Superuser: {is_superuser}")
        if action == 'create':
            create_admin_user(username, password, is_superuser)
            message = f"User {username} created."
        elif action == 'delete':
            delete_admin_user(username)
            message = f"User {username} deleted."
        elif action == 'change_password':
            change_admin_password(username, password)
            message = f"Password for {username} changed."
    return render_template('admin_users.html', message=message)

####################################################
# Upload management
####################################################
@app.route('/admin/upload', methods=['GET', 'POST'])
@admin_required
def admin_upload():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    upload_folder = os.path.join(project_root, 'fileExchange', 'uploads')
    message = None

    # List uploaded files
    uploaded_files = [f for f in os.listdir(upload_folder) if os.path.isfile(os.path.join(upload_folder, f))]

    if request.method == 'POST':
        if 'delete_file' in request.form:
            file_to_delete = request.form.get('delete_file')
            filepath = os.path.join(upload_folder, file_to_delete)
            if os.path.exists(filepath):
                os.remove(filepath)
                message = f"File '{file_to_delete}' deleted successfully."
            else:
                message = f"File '{file_to_delete}' not found."
        elif 'download_file' in request.form:
            file_to_download = request.form.get('download_file')
            filepath = os.path.join(upload_folder, file_to_download)
            if os.path.exists(filepath):
                with open(filepath, 'rb') as f:
                    response = Response(f.read(), mimetype='application/octet-stream')
                    response.headers.set('Content-Disposition', 'attachment', filename=file_to_download)
                return response
            else:
                message = f"File '{file_to_download}' not found."
        elif 'file' in request.files:
            file = request.files['file']
            if file.filename == '':
                message = "No selected file"
            else:
                filepath = os.path.join(upload_folder, file.filename)
                file.save(filepath)
                message = f"File '{file.filename}' uploaded successfully."

        # Refresh file list after upload/delete
        uploaded_files = [f for f in os.listdir(upload_folder) if os.path.isfile(os.path.join(upload_folder, f))]

    return render_template('admin_upload.html', message=message, uploaded_files=uploaded_files)

####################################################
# Download management
####################################################

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

####################################################
# Meteo station data import with progress tracking
####################################################

@app.route('/admin/add_station_data', methods=['GET', 'POST'])
@admin_required
def admin_add_station_data():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    upload_folder = os.path.join(project_root, 'fileExchange', 'uploads')
    csv_files = [f for f in os.listdir(upload_folder) if f.lower().endswith('.csv')]
    json_files = [f for f in os.listdir(upload_folder) if f.lower().endswith('.json')]
    xml_files = [f for f in os.listdir(upload_folder) if f.lower().endswith('.xml')]
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

    return render_template('admin_add_station_data.html', csv_files=csv_files, json_files=json_files, xml_files=xml_files, message=message)

###
### Background meteo station data import with progress tracking
###

def import_meteo_stations_background(csv_file, config_path, sql_path, product_json, layer_xml, metadata_folder, user_name):
    process_id = f"import_meteostations:{os.path.basename(csv_file)}"
    clear_progress_messages(user_name, process_id)
    error_message = None
    success = True
    try:
        # Delete previous data
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM meteostation_month_data;")
            conn.commit()
            cur.close()
            close_db_connection(conn)
            msg = "Previous data deleted (if any)."
            print(msg)
            save_progress_message(user_name, process_id, msg)
        except Exception:
            msg = "Could not delete previous data (ignored)."
            print(msg)
            save_progress_message(user_name, process_id, msg)
        # Import CSV
        try:
            from src.import_meteo_csv import import_meteo_csv_stream
            for message in import_meteo_csv_stream(csv_file, config_path=config_path, sql_path=sql_path):
                print(message)
                save_progress_message(user_name, process_id, message)
        except Exception as e:
            error_message = f"Error importing: {e}"
            print(error_message)
            save_progress_message(user_name, process_id, error_message)
            success = False
        if success:
            if product_json:
                try:
                    target_json = os.path.join(metadata_folder, "meteo_stations.json")
                    if os.path.exists(target_json):
                        os.remove(target_json)
                    os.rename(product_json, target_json)
                    msg = f"Product info file moved to '{target_json}'."
                    print(msg)
                    save_progress_message(user_name, process_id, msg)
                except Exception as e:
                    msg = f"Could not move product info file: {e}"
                    print(msg)
                    save_progress_message(user_name, process_id, msg)
            # Move layer metadata XML
            if layer_xml:
                try:
                    target_xml = os.path.join(metadata_folder, "meteo_stations.xml")
                    if os.path.exists(target_xml):
                        os.remove(target_xml)
                    os.rename(layer_xml, target_xml)
                    msg = f"Metadata file moved to '{target_xml}'."
                    print(msg)
                    save_progress_message(user_name, process_id, msg)
                except Exception as e:
                    msg = f"Could not move metadata file: {e}"
                    print(msg)
                    save_progress_message(user_name, process_id, msg)
            # Delete CSV file if successful
            """
            try:
                os.remove(csv_file)
                msg = f"Imported '{os.path.basename(csv_file)}' successfully and deleted the file."
                print(msg)
                save_progress_message(user_name, process_id, msg)
            except Exception as e:
                msg = f"Imported but could not delete CSV file: {e}"
                print(msg)
                save_progress_message(user_name, process_id, msg)
            """
        # Send alert to user
        alert_text = error_message if error_message else f"Meteostation import finished successfully."
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO alerts (user_name, alert_text) VALUES (%s, %s)",
                (user_name, alert_text[:300])
            )
            conn.commit()
            cur.close()
            close_db_connection(conn)
        except Exception as e:
            print(f"Could not send alert: {e}")
        # Final progress message and cleanup
        save_progress_message(user_name, process_id, "process finished")
        time.sleep(3)  # Wait 3 seconds before clearing messages to ensure frontend has time to fetch final messages
        clear_progress_messages(user_name, process_id)
    except Exception as e:
        msg = f"Background process error: {e}"
        print(msg)
        save_progress_message(user_name, process_id, msg)

@app.route('/admin/import_meteo_stations_stream', methods=['POST'])
@admin_required
def import_meteo_stations_stream():
    csv_filename = request.form.get('csv_filename')
    if not csv_filename:
        return jsonify({'status': 'error', 'message': 'No CSV filename provided.'}), 400
    
    product_json_name = request.form.get('product_json')
    layer_xml_name = request.form.get('layer_xml')

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    csv_file = os.path.join(project_root, 'fileExchange', 'uploads', csv_filename)
    config_path = os.path.join(project_root, 'config', 'config.ini')
    sql_path = os.path.join(project_root, 'DB_Scripts', 'meteo_stations.sql')
    metadata_folder = os.path.join(project_root, 'metadata')
    user_name = session.get('admin_username')

    if not os.path.isfile(csv_file):
        return jsonify({'status': 'error', 'message': f"CSV file '{csv_filename}' not found."}), 400


    # Build full paths for product_json and layer_xml if provided
    product_json = os.path.join(project_root, 'fileExchange', 'uploads', product_json_name) if product_json_name else None
    layer_xml = os.path.join(project_root, 'fileExchange', 'uploads', layer_xml_name) if layer_xml_name else None

    thread = threading.Thread(
        target=import_meteo_stations_background,
        args=(csv_file, config_path, sql_path, product_json, layer_xml, metadata_folder, user_name)
    )
    thread.start()

    process_id = f"import_meteostations:{csv_filename}"
    return jsonify({'status': 'started', 'process_id': process_id, 'message': 'Import started in background. You will receive an alert when it finishes.'})

############################################################
# Layer creation
#############################################################

@app.route('/admin/layer_creation', methods=['GET', 'POST'])
@admin_required
def admin_layer_creation():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    upload_folder = os.path.join(project_root, 'fileExchange', 'uploads')
    layer_files = [f for f in os.listdir(upload_folder) if f.lower().endswith('.nc') or f.lower().endswith('.tif') or f.lower().endswith('.tiff')]
    json_files = [f for f in os.listdir(upload_folder) if f.lower().endswith('.json')]
    xml_files = [f for f in os.listdir(upload_folder) if f.lower().endswith('.xml')]
    message = None

    return render_template(
        'admin_layer_creation.html',
        layer_files=layer_files,
        json_files=json_files,
        xml_files=xml_files,
        message=message
    )

####
#### Background layer creation process
#### 

def layer_creation_background(nc_file, layer_name, value_dim, time_dim, lon_dim, lat_dim, config_path, add_to_table, product_json, layer_xml, metadata_folder, user_name):
    process_id = f"layer_creation:{layer_name}"
    clear_progress_messages(user_name, process_id)  # Clear old messages
    error_message = None
    success = True
    try:
        for message in read_nc_file_stream(
            nc_file,
            layer_name,
            value_dim,
            time_dim,
            lon_dim,
            lat_dim,
            config_path=config_path,
            add_to_table=add_to_table
        ):
            print(message)
            save_progress_message(user_name, process_id, message)
            if message.startswith("Error"):
                error_message = message
                success = False

        # Only delete files if process was successful
        action = "addition" if add_to_table else "creation"
        if success:
            msg_action = "edited" if add_to_table else "created"
            # Move product info JSON
            if product_json:
                try:
                    target_json = os.path.join(metadata_folder, f"{layer_name}.json")
                    os.rename(product_json, target_json)
                    msg = f"Product info file moved to '{target_json}'."
                    print(msg)
                    save_progress_message(user_name, process_id, msg)
                except Exception as e:
                    msg = f"Could not move product info file: {e}"
                    print(msg)
                    save_progress_message(user_name, process_id, msg)
            # Move layer metadata XML
            if layer_xml:
                try:
                    target_xml = os.path.join(metadata_folder, f"{layer_name}.xml")
                    os.rename(layer_xml, target_xml)
                    msg = f"Metadata file moved to '{target_xml}'."
                    print(msg)
                    save_progress_message(user_name, process_id, msg)
                except Exception as e:
                    msg = f"Could not move metadata file: {e}"
                    print(msg)
                    save_progress_message(user_name, process_id, msg)
        else:
            msg = f"Layer {action} failed: {error_message}"
            print(msg)
            save_progress_message(user_name, process_id, msg)
            # Do NOT delete or move files

        # --- Send alert to user ---
        alert_text = error_message if error_message else f"Layer '{layer_name}' {action} finished successfully."
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO alerts (user_name, alert_text) VALUES (%s, %s)",
                (user_name, alert_text[:300])
            )
            conn.commit()
            cur.close()
            close_db_connection(conn)
            # Delete all progress messages for this process
            time.sleep(3)  # Wait 3 seconds before clearing
            clear_progress_messages(user_name, process_id)
        except Exception as e:
            print(f"Could not send alert: {e}")
    except Exception as e:
        msg = f"Background process error: {e}"
        print(msg)
        save_progress_message(user_name, process_id, msg)
    finally:
        # Always write END at the end of the process
        try:
            save_progress_message(user_name, process_id, "**END**")
        except Exception as e:
            print(f"Could not write END message: {e}")

@app.route('/admin/create_layer_stream', methods=['POST'])
@admin_required
def create_layer_stream():
    layer_file = request.form.get('layer_file')
    layer_name = request.form.get('layer_name')
    time_dim = request.form.get('time_dim')
    lon_dim = request.form.get('lon_dim')
    lat_dim = request.form.get('lat_dim')
    value_dim = request.form.get('value_dim')
    product_json_name = request.form.get('product_json')
    layer_xml_name = request.form.get('layer_xml')
    add_to_table = request.form.get('add_to_table', 'false') == 'true'

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    upload_folder = os.path.join(project_root, 'fileExchange', 'uploads')
    metadata_folder = os.path.join(project_root, 'metadata')
    nc_file = os.path.join(upload_folder, layer_file)
    product_json = os.path.join(upload_folder, product_json_name) if product_json_name else None
    layer_xml = os.path.join(upload_folder, layer_xml_name) if layer_xml_name else None
    config_path = os.path.join(project_root, 'config', 'config.ini')
    user_name = session.get('admin_username')

    # Start the background thread
    thread = threading.Thread(
        target=layer_creation_background,
        args=(nc_file, layer_name, value_dim, time_dim, lon_dim, lat_dim, config_path, add_to_table, product_json, layer_xml, metadata_folder, user_name)
    )
    thread.start()

    # Immediately respond to the client
    return jsonify({'status': 'started', 'message': 'Layer creation started in background. You will receive an alert when it finishes.'})

####
#### Background layer creation process from GeoTIFF file
#### 

def layer_creation_tif_background(tif_file, layer_name, config_path, add_to_table, user_name, metadata_folder=None, product_json=None, layer_xml=None):
    process_id = f"layer_creation:{layer_name}"
    clear_progress_messages(user_name, process_id)
    error_message = None
    success = True
    try:
        from src.create_layer_tif import read_geotiff_file_stream
        for message in read_geotiff_file_stream(
            tif_file,
            layer_name,
            config_path=config_path,
            add_to_table=add_to_table
        ):
            print(message)
            save_progress_message(user_name, process_id, message)
            if message.startswith("Error"):
                error_message = message
                success = False
        # Move product info JSON and layer metadata XML if provided and successful
        if success and metadata_folder:
            if product_json:
                try:
                    target_json = os.path.join(metadata_folder, f"{layer_name}.json")
                    os.rename(product_json, target_json)
                    msg = f"Product info file moved to '{target_json}'."
                    print(msg)
                    save_progress_message(user_name, process_id, msg)
                except Exception as e:
                    msg = f"Could not move product info file: {e}"
                    print(msg)
                    save_progress_message(user_name, process_id, msg)
            if layer_xml:
                try:
                    target_xml = os.path.join(metadata_folder, f"{layer_name}.xml")
                    os.rename(layer_xml, target_xml)
                    msg = f"Metadata file moved to '{target_xml}'."
                    print(msg)
                    save_progress_message(user_name, process_id, msg)
                except Exception as e:
                    msg = f"Could not move metadata file: {e}"
                    print(msg)
                    save_progress_message(user_name, process_id, msg)
        msg = f"Layer creation from GeoTIFF {'finished successfully.' if success else 'failed: ' + str(error_message)}"
        save_progress_message(user_name, process_id, msg)
        alert_text = msg
    except Exception as e:
        alert_text = f"Background process error: {e}"
        save_progress_message(user_name, process_id, alert_text)
    finally:
        # Always write END at the end of the process
        try:
            save_progress_message(user_name, process_id, "**END**")
        except Exception as e:
            print(f"Could not write END message: {e}")
    # Send alert to user
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO alerts (user_name, alert_text) VALUES (%s, %s)",
            (user_name, alert_text[:300])
        )
        conn.commit()
        cur.close()
        close_db_connection(conn)
        time.sleep(3)  # Wait 3 seconds before clearing
        clear_progress_messages(user_name, process_id)
    except Exception as e:
        print(f"Could not send alert: {e}")    

@app.route('/admin/create_layer_tif_stream', methods=['POST'])
@admin_required
def create_layer_tif_stream():
    layer_file = request.form.get('layer_file')
    layer_name = request.form.get('layer_name')
    add_to_table = request.form.get('add_to_table', 'false') == 'true'
    product_json_name = request.form.get('product_json')
    layer_xml_name = request.form.get('layer_xml')
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    upload_folder = os.path.join(project_root, 'fileExchange', 'uploads')
    metadata_folder = os.path.join(project_root, 'metadata')
    tif_file = os.path.join(upload_folder, layer_file)
    product_json = os.path.join(upload_folder, product_json_name) if product_json_name else None
    layer_xml = os.path.join(upload_folder, layer_xml_name) if layer_xml_name else None
    config_path = os.path.join(project_root, 'config', 'config.ini')
    user_name = session.get('admin_username')

    thread = threading.Thread(
        target=layer_creation_tif_background,
        args=(tif_file, layer_name, config_path, add_to_table, user_name, metadata_folder, product_json, layer_xml)
    )
    thread.start()

    return jsonify({'status': 'started', 'message': 'Layer creation from GeoTIFF started in background. You will receive an alert when it finishes.'})

############################################################
# Tile seeding
############################################################
@app.route('/admin/seed_layer', methods=['GET', 'POST'])
@admin_required
def admin_seed_layer():
    message = None
    # Get published layers from GeoServer workspace
    config = load_config()
    layers = []
    try:
        geoserver_url = config['base'].get('geoserver_url', '').rstrip('/')
        workspace = config['geoserver'].get('workspace', '')
        username = config['geoserver'].get('username', '')
        password = config['geoserver'].get('password', '')
        rest_url = f"{geoserver_url}/rest/workspaces/{workspace}/layers.json"
        resp = requests.get(rest_url, auth=(username, password), timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            published_layers = [l['name'] for l in data.get('layers', {}).get('layer', [])]
            # Exclude grid layers
            grid_names = set()
            if 'grids' in config:
                grid_names = set(config['grids'].values())
            layers = [lname for lname in published_layers if lname not in grid_names]
    except Exception as e:
        print(f"Could not fetch layers from GeoServer: {e}")

    if request.method == 'POST':
        layer = request.form.get('layer')
        zoom_start = int(request.form.get('zoom_start', 3))
        zoom_stop = int(request.form.get('zoom_stop', 8))
        try:
            seed_layer_tiles(layer, zoom_start, zoom_stop)
            message = f"Seeding started for layer '{layer}' (zoom {zoom_start}-{zoom_stop})."
        except Exception as e:
            message = f"Error: {e}"
    return render_template('admin_seed_layer.html', message=message, layers=layers)

# =============================
# Admin: Layer Status Overview
# =============================
@app.route('/admin/layers')
@admin_required
def admin_layers():
    # 1. Layers from config.ini
    config = load_config()
    config_layers = set()
    if 'map' in config and 'layers' in config['map']:
        config_layers = set(l.strip() for l in config['map']['layers'].split(',') if l.strip())

    # Get grid layer names from [grids] section
    grid_names = set()
    if 'grids' in config:
        grid_names = set(config['grids'].values())

    # 2. Layers from database (views, except geography_columns and geometry_columns)
    db_views = set()
    db_tables = set()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM information_schema.views WHERE table_schema='public' AND table_name NOT IN ('geography_columns', 'geometry_columns')")
        db_views = set(row[0] for row in cur.fetchall())
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")
        db_tables = set(row[0] for row in cur.fetchall())
        cur.close()
        close_db_connection(conn)
    except Exception as e:
        print(f"DB error: {e}")

    # 3. Layers from GeoServer (published in workspace)
    gs_layers = set()
    try:
        geoserver_url = config['base'].get('geoserver_url', '').rstrip('/')
        workspace = config['geoserver'].get('workspace', '')
        username = config['geoserver'].get('username', '')
        password = config['geoserver'].get('password', '')
        rest_url = f"{geoserver_url}/rest/workspaces/{workspace}/layers.json"
        resp = requests.get(rest_url, auth=(username, password), timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            gs_layers = set(l['name'] for l in data.get('layers', {}).get('layer', []))
    except Exception as e:
        print(f"GeoServer error: {e}")

    # 4. Union of all layer names, excluding grids
    all_layers = sorted((config_layers | db_views | gs_layers) - grid_names)

    # Map layer name to topic (from config)
    layer_to_topic = {}
    for section in config.sections():
        if section in config_layers and 'topic' in config[section]:
            layer_to_topic[section] = config[section]['topic']

    layers_info = []
    for lname in all_layers:
        # Only if declared in config and topic is facilities, check both views and tables
        if lname in config_layers and layer_to_topic.get(lname) == 'facilities':
            # Special case for meteostations and facility layers which can be a table
            in_db = (lname in db_views) or (lname in db_tables) or (lname == 'meteo_stations' and 'meteostation_month_data' in db_tables)  
        else:
            in_db = lname in db_views
        layers_info.append({
            'name': lname,
            'in_config': lname in config_layers,
            'in_db': in_db,
            'in_geoserver': lname in gs_layers
        })
    return render_template('admin_layers.html', layers_info=layers_info)

############################################################
# Export data to NetCDF
############################################################
def export_table_background(user_name, table_name, init_date, end_date, bbox, output_filename, format):
    process_id = f"export_table:{table_name}"
    clear_progress_messages(user_name, process_id)
    try:
        conn = get_db_connection()
        grid_name = get_existing_grid_table(conn,table_name)
        print(f"Using grid '{grid_name}' for export.")
        if format == ".nc":
            msg = f"Exporting to NetCDF format."
            print(msg) 
            save_progress_message(user_name, process_id, msg)
            for message in export_table_to_netcdf(conn, table_name, init_date, end_date, bbox, output_filename):
                print(message)
                save_progress_message(user_name, process_id, message)
        elif format == ".tif":    
            msg = f"Exporting to GeoTIFF format "
            print(msg)
            save_progress_message(user_name, process_id, msg)
            for message in export_table_to_geotiff(conn, table_name, init_date, end_date, bbox, output_filename):
                print(message)
                save_progress_message(user_name, process_id, message)
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        close_db_connection(conn)
        msg = f"Export finished. File: {output_filename}"
        print(msg)
        save_progress_message(user_name, process_id, msg)
        alert_text = f"Export of '{table_name}' finished successfully."
    except Exception as e:
        msg = f"Error exporting table: {e}"
        print(msg)
        save_progress_message(user_name, process_id, msg)
        alert_text = msg
    # Send alert to user
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO alerts (user_name, alert_text) VALUES (%s, %s)",
            (user_name, alert_text[:300])
        )
        conn.commit()
        cur.close()
        close_db_connection(conn)
    except Exception as e:
        print(f"Could not send alert: {e}")
    # Final progress message and cleanup
    save_progress_message(user_name, process_id, "process finished")
    clear_progress_messages(user_name, process_id)

@app.route('/admin/export_table/<table_name>', methods=['POST'])
@admin_required
def export_table(table_name):
    init_date = request.json.get("init_date")
    end_date = request.json.get("end_date")
    bbox = request.json.get("bbox") 
    if bbox == {}:
        bbox = None
    format = request.json.get("format") or ".nc"

    if request.json.get("output_filename") is None:
        output_filename = f"{table_name}_{init_date}_{end_date}{format}"
    else:
        output_filename = f"{request.json.get('output_filename')}{format}"

    user_name = session.get('admin_username')

    thread = threading.Thread(
        target=export_table_background,
        args=(user_name, table_name, init_date, end_date, bbox, output_filename, format)
    )
    thread.start()

    process_id = f"export_table:{table_name}"
    return jsonify({'status': 'started', 'process_id': process_id, 'message': 'Export started in background. You will receive an alert when it finishes.'})

###############################################################################
# Public API endpoints
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
    rules_json = None  # Default
    if style == "SLD" or style == "sld":
        geoserver_url = get_key_config('base').get('geoserver_url')
        username = get_key_config('geoserver').get('username')
        password = get_key_config('geoserver').get('password')
        workspace = get_key_config('geoserver').get('workspace', 'droughts')

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
            rules_json = json.dumps(rules) if rules else None
        except Exception as e:
            print(f"Error fetching SLD from GeoServer: {e}")
            rules_json = None
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

@app.route('/')
def main_map():
    print("starting")
    map_config = get_key_config('map')
    layers = {}
    layer_names = map_config["layers"].split(',')
    print("layer_names:", layer_names)
    
    for layer_name in layer_names:
        layer = get_key_config(layer_name)
        layers[layer_name] = layer
    
    print("loaded layers")
    config = load_config()
    base_url = config['base'].get('base_url', '')
    map_config['layers'] = layers
    map_config['localhost'] = base_url
    print(map_config)
    return render_template('main_map.html', map_config=map_config, logged_in=session.get('admin_logged_in', False))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="WebGIS Droughts Application")
    parser.add_argument('--development', action='store_true', help="Run in development mode")
    args = parser.parse_args()
    if args.development:
        app.run(host="0.0.0.0",debug=True)
    else:
        serve(app, host='0.0.0.0', port=5000)