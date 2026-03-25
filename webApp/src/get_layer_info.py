import time
from datetime import datetime
import decimal
import os
import re
import numpy as np
import pandas as pd
import geopandas as gpd
import xarray as xr
import json
import gc
import xml.etree.ElementTree as ET
import configparser
import rasterio
from rasterio.transform import from_origin

################################################################
# CONFIGURATION
################################################################
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'config.ini')
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

################################################################
################################################################
# Functions to get layer info from the database
################################################################
################################################################

############################################################
# Get feature data from the database
############################################################
def get_feature_data(layer, lat, lon, date, conn):
    """
    Get feature info from the {layer} based on lat, lon, and date.
    Assumes the view contains columns: xcol, yrow, value, date, cell (geometry).
    """
    try:
        date_obj = datetime.strptime(date, '%Y-%m-%d').date()
        query = f"""
            SELECT xcol, yrow, value, date
            FROM {layer}
            WHERE date = %s
              AND ST_Contains(cell, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
            LIMIT 1;
        """
        with conn.cursor() as cursor:
            cursor.execute(query, (date_obj, lon, lat))
            result = cursor.fetchone()
            if not result:
                return {"error": "No data found for the provided date and location."}
            xcol, yrow, value, date_val = result

        return {
            "xcol": xcol,
            "yrow": yrow,
            "value": value,
            "date": str(date_val)
        }

    except Exception as e:
        return {"error": str(e)}


        

#############################################################
# Get feature data from lat/lon over a date range
#############################################################
def get_feature_data_from_lat_lon(layer, lat, lon, yearFrom, monthFrom, yearTo, monthTo, conn):
    """
    Get feature info from the database based on layer, lat, lon, and date,
    returned as a numpy array [year][month], plus avg and st_dev per month
    for the selected cell over all dates in the table.
    """
    try:
        date_from = datetime(yearFrom, monthFrom, 1).date()
        date_to = datetime(yearTo, monthTo, 1).date()
        value_query = f"""
            SELECT date, value, xcol, yrow
            FROM {layer}
            WHERE ST_Contains(cell, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
            AND date BETWEEN %s AND %s
            ORDER BY date;
        """
        with conn.cursor() as cursor:
            cursor.execute(value_query, (lon, lat, date_from, date_to))
            results = cursor.fetchall()
            if not results:
                return {"error": "No data found for the provided date range and location."}
            years = list(range(yearFrom, yearTo + 1))
            months = list(range(1, 13))
            arr = np.full((len(years), len(months)), np.nan)
            xcol = results[0][2]
            yrow = results[0][3]
            for row in results:
                date_obj = row[0]
                value = row[1]
                year_idx = date_obj.year - yearFrom
                month_idx = date_obj.month - 1
                if 0 <= year_idx < len(years) and 0 <= month_idx < len(months):
                    arr[year_idx, month_idx] = value
            arr = np.nan_to_num(arr, nan=0.0)
            cell_avg = []
            cell_std = []
            cell_month_query = f"""
                SELECT EXTRACT(MONTH FROM date) AS month, AVG(value) AS avg, STDDEV(value) AS std
                FROM {layer}
                WHERE xcol = %s AND yrow = %s
                GROUP BY month
                ORDER BY month;
            """
            with conn.cursor() as cursor:
                cursor.execute(cell_month_query, (xcol, yrow))
                cell_results = cursor.fetchall()
                month_stats = {int(row[0]): {"avg": row[1] or 0.0, "std": row[2] or 0.0} for row in cell_results}
                for m in months:
                    stats = month_stats.get(m, {"avg": 0.0, "std": 0.0})
                    cell_avg.append(stats["avg"])
                    cell_std.append(stats["std"])
            return {
                "x": xcol,
                "y": yrow,
                "sample": arr.tolist(),
                "years": years,
                "months": months,
                "date_from": str(date_from),
                "date_to": str(date_to),
                "latitude": lat,
                "longitude": lon,
                "avg": cell_avg,
                "std": cell_std,
                "labels": [
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"
                ],
            }
    except Exception as e:
        return {"error": str(e)}

#############################################################
# Get feature data from lat/lon over a date range (dekads)
#############################################################    
def get_feature_data_from_lat_lon_dekad(layer, lat, lon, dateFrom, dateTo, conn):
    """
    Get feature info from the database based on layer, lat, lon, and date,
    returned as a numpy array [year][month][dekad], plus avg and st_dev per dekad
    for the selected cell over all dates in the table.
    Dekads: 1 = days 1-10, 2 = days 11-20, 3 = days 21-end of month.
    """
    try:
        date_from = datetime.strptime(dateFrom, "%Y-%m-%d").date()
        date_to = datetime.strptime(dateTo, "%Y-%m-%d").date()
        value_query = f"""
            SELECT date, value, xcol, yrow
            FROM {layer}
            WHERE ST_Contains(cell, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
            AND date BETWEEN %s AND %s
            ORDER BY date;
        """
        with conn.cursor() as cursor:
            cursor.execute(value_query, (lon, lat, date_from, date_to))
            results = cursor.fetchall()
            if not results:
                return {"error": "No data found for the provided date range and location."}
            # Get all years and months in the range
            years = sorted(list(set([row[0].year for row in results])))
            months = list(range(1, 13))
            dekads = [1, 2, 3]
            arr = np.full((len(years), len(months), len(dekads)), np.nan)
            xcol = results[0][2]
            yrow = results[0][3]
            year_idx_map = {y: i for i, y in enumerate(years)}
            for row in results:
                date_obj = row[0]
                value = row[1]
                year_idx = year_idx_map[date_obj.year]
                month_idx = date_obj.month - 1
                day = date_obj.day
                if 1 <= day <= 10:
                    dekad_idx = 0
                elif 11 <= day <= 20:
                    dekad_idx = 1
                else:
                    dekad_idx = 2
                arr[year_idx, month_idx, dekad_idx] = value
            arr = np.nan_to_num(arr, nan=0.0)
            # Compute avg and std per dekad (over all years/months)
            dekad_avgs = []
            dekad_stds = []
            for d in range(3):
                dekad_values = arr[:, :, d].flatten()
                valid = dekad_values[dekad_values != 0.0]
                if valid.size > 0:
                    dekad_avgs.append(float(np.mean(valid)))
                    dekad_stds.append(float(np.std(valid)))
                else:
                    dekad_avgs.append(0.0)
                    dekad_stds.append(0.0)
            return {
                "x": xcol,
                "y": yrow,
                "sample": arr.tolist(),
                "years": years,
                "months": months,
                "dekads": [1, 2, 3],
                "date_from": str(date_from),
                "date_to": str(date_to),
                "latitude": lat,
                "longitude": lon,
                "avg_per_dekad": dekad_avgs,
                "std_per_dekad": dekad_stds,
                "labels": [
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"
                ],
                "dekad_labels": ["Days 1-10", "Days 11-20", "Days 21-end"]
            }
    except Exception as e:
        return {"error": str(e)}

#############################################################
# Get time bounds for data at a given lat/lon
#############################################################
def get_data_time_bounds(lat, lon, layer, conn):
    """
    Get the minimum and maximum date for the given location from the view.
    Returns: {"min_date": "YYYY-MM-DD", "max_date": "YYYY-MM-DD"}
    """
    try:
        query = f"""
            SELECT MIN(date), MAX(date)
            FROM {layer}
            WHERE ST_Contains(cell, ST_SetSRID(ST_MakePoint(%s, %s), 4326));
        """
        with conn.cursor() as cursor:
            cursor.execute(query, (lon, lat))
            min_date, max_date = cursor.fetchone()
            if not min_date or not max_date:
                return None
            # Convert to string if necessary
            if isinstance(min_date, str):
                min_date_str = min_date
            else:
                min_date_str = min_date.strftime("%Y-%m-%d")
            if isinstance(max_date, str):
                max_date_str = max_date
            else:
                max_date_str = max_date.strftime("%Y-%m-%d")
            return {
                "min_date": min_date_str,
                "max_date": max_date_str
            }
    except Exception as e:
        return None

#############################################################
# Get time bounds for a given layer
#############################################################
def get_layer_time_bounds(layer, conn):
    """
    Get the minimum and maximum date for the given layer,
    and all available dates as a sorted list of strings.
    Returns: {"min_date": "YYYY-MM-DD", "max_date": "YYYY-MM-DD", "all_dates": [date_str, ...]}
    """
    try:
        # Get min and max date
        query = f"""
            SELECT MIN(date), MAX(date)
            FROM {layer}
        """
        with conn.cursor() as cursor:
            cursor.execute(query)
            min_date, max_date = cursor.fetchone()
            if not min_date or not max_date:
                return None
            if isinstance(min_date, str):
                min_date_str = min_date
            else:
                min_date_str = min_date.strftime("%Y-%m-%d")
            if isinstance(max_date, str):
                max_date_str = max_date
            else:
                max_date_str = max_date.strftime("%Y-%m-%d")
        # Get all available dates
        query_dates = f"SELECT DISTINCT date FROM {layer} ORDER BY date ASC"
        with conn.cursor() as cursor:
            cursor.execute(query_dates)
            all_dates = [row[0].strftime("%Y-%m-%d") if not isinstance(row[0], str) else row[0] for row in cursor.fetchall()]
        return {
            "min_date": min_date_str,
            "max_date": max_date_str,
            "all_dates": all_dates
        }
    except Exception as e:
        return None
#############################################################
#############################################################
# Functions to get meteostation data from the database
#############################################################   
#############################################################   

#############################################################
# Get meteostation data for one station 
# within 0.1 degree of lat/lon and date
#############################################################
def get_meteostation_month_data(conn, lat, lon, date):
    """
    Retrieve data from meteostation_month_data for one station within 0.1 degree of the given lat/lon and date.
    Returns a dict with latitude, longitude, elevation, station_name, year, month, tavg, tmax, tmin, prcp.
    """
    try:
        query = """
            SELECT latitude, longitude, elevation, station_name, year, month, tavg, tmax, tmin, prcp
            FROM meteostation_month_data
            WHERE ABS(latitude - %s) <= 0.1
              AND ABS(longitude - %s) <= 0.1
              AND date = %s
            LIMIT 1;
        """
        with conn.cursor() as cursor:
            cursor.execute(query, (lat, lon, date))
            result = cursor.fetchone()
            if not result:
                return None
            keys = ['latitude', 'longitude', 'elevation', 'station_name', 'year', 'month', 'tavg', 'tmax', 'tmin', 'prcp']
            return dict(zip(keys, result))
    except Exception as e:
        return {"error": str(e)}

#############################################################
# Get all meteostations as GeoJSON
#############################################################
def get_meteo_stations_geojson(conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT distinct station_name, latitude, longitude, ST_AsGeoJSON(geom) AS geojson
        FROM meteostation_month_data
    """)
    features = []
    for row in cursor.fetchall():
        lat = float(row[1]) if isinstance(row[1], decimal.Decimal) else row[1]
        lon = float(row[2]) if isinstance(row[2], decimal.Decimal) else row[2]
        feature = {
            "type": "Feature",
            "geometry": json.loads(row[3]),
            "properties": {
                "name": row[0],
                "latitude": lat,
                "longitude": lon
            }
        }
        features.append(feature)
    cursor.close()
    return {
        "type": "FeatureCollection",
        "features": features
    }

#############################################################  
# Get meteostation data for one station at lat/lon and date
#############################################################
def get_data_from_meteostation(conn, lat, lon, date):
    try:
        query = """
            SELECT date, tavg, tmax, tmin, prcp
            FROM meteostation_month_data
            WHERE latitude = %s
              AND longitude = %s
        """
        if date:
            query += " AND date = %s"
            params = (lat, lon, date)
        else:
            params = (lat, lon)
            query += """
                ORDER BY date DESC
                LIMIT 1;
            """
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            result = cursor.fetchone()
            if not result:
                return {}
            keys = ['date', 'tavg', 'tmax', 'tmin', 'prcp']
            return dict(zip(keys, result))
    except Exception as e:
        return {"error": str(e)}

#############################################################
# Get time bounds for a given meteostation at lat/lon
#############################################################
def get_station_time_bounds(lat, lon, conn):
    """
    Get the minimum and maximum year and month for the given meteostation location.
    Returns: {"min_year": int, "min_month": int, "max_year": int, "max_month": int}
    """
    try:
        query = """
            SELECT MIN(date), MAX(date)
            FROM meteostation_month_data
            WHERE latitude = %s AND longitude = %s;
        """
        with conn.cursor() as cursor:
            cursor.execute(query, (lat, lon))
            min_date, max_date = cursor.fetchone()
            if not min_date or not max_date:
                return None
            if isinstance(min_date, str):
                min_date = datetime.strptime(min_date, "%Y-%m-%d").date()
            if isinstance(max_date, str):
                max_date = datetime.strptime(max_date, "%Y-%m-%d").date()
            return {
                "min_year": min_date.year,
                "min_month": min_date.month,
                "max_year": max_date.year,
                "max_month": max_date.month
            }
    except Exception as e:
        return None

#############################################################
# Get feature info from the database based on layer, lat, lon, and date,
# returned as a numpy array [year][month], plus avg and st_dev per month
# for the selected cell over all dates in the table.
#############################################################
def get_station_data_from_lat_lon(layer, variable, lat, lon, yearFrom, monthFrom, yearTo, monthTo, conn):
    """
    Get feature info from the database based on layer, lat, lon, and date,
    returned as a numpy array [year][month], plus avg and st_dev per month
    for the selected cell over all dates in the table.
    """
    try:
        date_from = datetime(yearFrom, monthFrom, 1).date()
        date_to = datetime(yearTo, monthTo, 1).date()
        value_query = f"""
            SELECT date, {variable}
            FROM {layer}
            WHERE latitude = %s AND longitude = %s
            AND date BETWEEN %s AND %s
            ORDER BY date;
        """
        with conn.cursor() as cursor:
            cursor.execute(value_query, (lat, lon, date_from, date_to))
            results = cursor.fetchall()
            if not results:
                return {"error": "No data found for the provided date range and location."}
            years = list(range(yearFrom, yearTo + 1))
            months = list(range(1, 13))
            arr = np.full((len(years), len(months)), np.nan)
            for row in results:
                date_obj = row[0]
                value = row[1]
                year_idx = date_obj.year - yearFrom
                month_idx = date_obj.month - 1
                if 0 <= year_idx < len(years) and 0 <= month_idx < len(months):
                    arr[year_idx, month_idx] = value
            arr = np.nan_to_num(arr, nan=0.0)
            cell_avg = []
            cell_std = []
            cell_month_query = f"""
                SELECT EXTRACT(MONTH FROM date) AS month, AVG({variable}) AS avg, STDDEV({variable}) AS std
                FROM {layer}
                WHERE latitude = %s AND longitude = %s
                GROUP BY EXTRACT(MONTH FROM date)
                ORDER BY month;
            """
            with conn.cursor() as cursor:
                cursor.execute(cell_month_query, (lat, lon))
                cell_results = cursor.fetchall()
                month_stats = {int(row[0]): {"avg": row[1] or 0.0, "std": row[2] or 0.0} for row in cell_results}
                for m in months:
                    stats = month_stats.get(m, {"avg": 0.0, "std": 0.0})
                    cell_avg.append(stats["avg"])
                    cell_std.append(stats["std"])
            return {
                "sample": arr.tolist(),
                "years": years,
                "months": months,
                "date_from": str(date_from),
                "date_to": str(date_to),
                "latitude": lat,
                "longitude": lon,
                "avg": cell_avg,
                "std": cell_std,
                "labels": [
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"
                ],
            }
    except Exception as e:
        return {"error": str(e)}

#############################################################
#############################################################
# Functions to export data to NetCDF or GeoTIFF
#############################################################
#############################################################
#############################################################
# Get grid table from existing view
#############################################################
def get_existing_grid_table(conn, layer_name):
    cursor = conn.cursor()
    try:
        query = f"""
            SELECT definition
            FROM pg_views
            WHERE viewname = %s
        """
        cursor.execute(query, (layer_name,))
        result = cursor.fetchone()
        if not result:
            raise Exception(f"Could not find view definition for {layer_name}")
        definition = result[0]
        print("DEBUG: View definition for", layer_name)
        print(definition)
        # Updated regex to match both "JOIN <table> grid" and "JOIN <table> AS grid"
        match = re.search(r'JOIN\s+([a-zA-Z0-9_\.]+)\s+(?:AS\s+)?grid', definition)
        if not match:
            raise Exception("Could not parse grid table from view definition.")
        grid_table = match.group(1)
        print(f"Existing grid table for layer {layer_name}: {grid_table}")
        return grid_table
    finally:
        cursor.close()

#############################################################
# Get grid resolution from config.ini
#############################################################
def get_grid_resolution(grid_name, config_path=None):
    """
    Given a grid name and config.ini, return the resolution for that grid as a float.
    """
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'config.ini')
    config = configparser.ConfigParser()
    config.read(config_path)
    if 'grids' not in config:
        raise KeyError("Missing [grids] section in config.ini")
    for res_str, grid in config['grids'].items():
        if grid == grid_name:
            try:
                return float(res_str)
            except Exception:
                raise ValueError(f"Resolution key '{res_str}' is not a valid float.")
    raise ValueError(f"Grid name '{grid_name}' not found in [grids] section of config.ini.")        

#############################################################
# Calculate centroid lat/lon from xcol/yrow
#############################################################
def get_centroid_lat_lon(min_xcol, min_yrow, max_lat, min_lon, resolution, xcol_final, yrow_final):
    delta_x = xcol_final - min_xcol
    delta_y = yrow_final - min_yrow
    centroid_lat = max_lat - delta_y * resolution
    centroid_lon = min_lon + delta_x * resolution
    return centroid_lat, centroid_lon

#############################################################
# Format seconds to HH:MM:SS
#############################################################
def format_hms(seconds):
        seconds = int(seconds)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02}:{m:02}:{s:02}"

#############################################################
# Export table data to NetCDF
#############################################################
def export_table_to_netcdf(conn, table_name, init_date, end_date, bbox, output_filename, chunksize=100000):
    
    yield "Starting export..."

    grid_name = get_existing_grid_table(conn, table_name)
    resolution = get_grid_resolution(grid_name)

    # Get bounds
    if bbox:
        query = f"""
            SELECT MIN(xcol), MAX(xcol), MIN(yrow), MAX(yrow)
            FROM {table_name}
            WHERE ST_Intersects(cell, ST_MakeEnvelope(%s, %s, %s, %s, 4326));
        """
        params = [bbox["min_lon"], bbox["min_lat"], bbox["max_lon"], bbox["max_lat"]]
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            result = cursor.fetchone()
            if not result:
                yield "No data found in the table."
                return
            min_xcol, max_xcol, min_yrow, max_yrow = result
    else:
        query = f"SELECT MIN(xcol), MAX(xcol), MIN(yrow), MAX(yrow) FROM {table_name};"
        with conn.cursor() as cursor:
            cursor.execute(query)
            min_xcol, max_xcol, min_yrow, max_yrow = cursor.fetchone()

    # Get reference point for centroid calculation
    query = f"""
        SELECT xcol, yrow, ST_AsText(ST_Centroid(cell)) AS centroid
        FROM {table_name}
        WHERE xcol = %s AND yrow = %s
        LIMIT 1;
    """
    with conn.cursor() as cursor:
        cursor.execute(query, (min_xcol, min_yrow))
        result = cursor.fetchone()
        if not result:
            yield "No data found in the table."
            return
        _, _, centroid_wkt = result
        coords = centroid_wkt.replace('POINT(', '').replace(')', '').split()
        min_lon, max_lat = float(coords[0]), float(coords[1])

    # Prepare main query
    query = f"""
        SELECT t.xcol, t.yrow, t.date, t.value
        FROM {table_name} t
        JOIN {grid_name} g ON t.xcol = g.xcol AND t.yrow = g.yrow
        WHERE t.date BETWEEN %s AND %s
    """
    params = [init_date, end_date]
    if bbox:
        query += """
            AND t.xcol BETWEEN %s AND %s
            AND t.yrow BETWEEN %s AND %s
        """
        params.extend([min_xcol, max_xcol, min_yrow, max_yrow])

    # Count total rows
    count_query = f"SELECT COUNT(*) FROM ({query}) AS subq"
    with conn.cursor() as cursor:
        cursor.execute(count_query, params)
        total_rows = cursor.fetchone()[0]
    if total_rows == 0:
        yield "No data found for the given parameters."
        return

    all_dfs = []
    processed_rows = 0
    last_percent = -1.0
    start_time = time.time()

    try:
        for i, df in enumerate(pd.read_sql(query, conn, params=params, chunksize=chunksize)):
            if df.empty:
                continue
            df['latitude'], df['longitude'] = zip(*[
                get_centroid_lat_lon(min_xcol, min_yrow, max_lat, min_lon, resolution, row['xcol'], row['yrow'])
                for _, row in df.iterrows()
            ])
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index(['latitude', 'longitude', 'date'])
            all_dfs.append(df)
            processed_rows += len(df)
            percent = (processed_rows / total_rows) * 100
            elapsed = time.time() - start_time
            if percent > 0:
                estimated_total = elapsed / (percent / 100)
                remaining = estimated_total - elapsed
            else:
                remaining = 0
            if percent - last_percent >= 0.1 or processed_rows == total_rows:
                yield (f"Processed {processed_rows}/{total_rows} rows... ({percent:.1f}%) "
                       f"Elapsed: {format_hms(elapsed)}, Remaining: {format_hms(remaining)}")
                last_percent = percent
            del df
            gc.collect()
        if not all_dfs:
            yield "No data found for the given parameters."
            return
        big_df = pd.concat(all_dfs)
        del all_dfs
        gc.collect()
        big_df = big_df.groupby(['latitude', 'longitude', 'date']).mean().reset_index()
        # Only keep the 'value' column for export
        big_df = big_df[['latitude', 'longitude', 'date', 'value']]
        big_df = big_df.set_index(['latitude', 'longitude', 'date'])
        ds = xr.Dataset.from_dataframe(big_df)
        ds.to_netcdf(output_filename)
        del ds, big_df
        gc.collect()
        yield f"Export completed successfully. File: {output_filename}"
    except Exception as e:
        yield f"Error exporting data to NetCDF: {e.__class__.__name__}: {e}"

#############################################################
# Export table data to a multiband GeoTIFF
#############################################################
def export_table_to_geotiff(conn, table_name, init_date, end_date, bbox, output_filename, chunksize=100000):
    """
    Export table data to a multiband GeoTIFF.
    Each band corresponds to a date, and the band description is set to the date string.
    """
    
    grid_name = get_existing_grid_table(conn, table_name)
    resolution = get_grid_resolution(grid_name)

    yield "Starting export..."

    # Get bounds
    yield "Calculating bounds for export..."
    if bbox:
        query = f"""
            SELECT MIN(xcol), MAX(xcol), MIN(yrow), MAX(yrow)
            FROM {table_name}
            WHERE ST_Intersects(cell, ST_MakeEnvelope(%s, %s, %s, %s, 4326));
        """
        params = [bbox["min_lon"], bbox["min_lat"], bbox["max_lon"], bbox["max_lat"]]
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            result = cursor.fetchone()
            if not result:
                yield "No data found in the table."
                return
            min_xcol, max_xcol, min_yrow, max_yrow = result
    else:
        query = f"SELECT MIN(xcol), MAX(xcol), MIN(yrow), MAX(yrow) FROM {table_name};"
        with conn.cursor() as cursor:
            cursor.execute(query)
            min_xcol, max_xcol, min_yrow, max_yrow = cursor.fetchone()
    yield f"Bounds determined: xcol=({min_xcol}, {max_xcol}), yrow=({min_yrow}, {max_yrow})"

    # Get reference point for transform
    yield "Getting reference point for GeoTIFF transform..."
    query = f"""
        SELECT xcol, yrow, ST_AsText(ST_Centroid(cell)) AS centroid
        FROM {table_name}
        WHERE xcol = %s AND yrow = %s
        LIMIT 1;
    """
    with conn.cursor() as cursor:
        cursor.execute(query, (min_xcol, min_yrow))
        result = cursor.fetchone()
        if not result:
            yield "No data found in the table."
            return
        _, _, centroid_wkt = result
        coords = centroid_wkt.replace('POINT(', '').replace(')', '').split()
        min_lon, max_lat = float(coords[0]), float(coords[1])
    yield f"Reference point: lon={min_lon}, lat={max_lat}"

    # Prepare main query
    yield "Querying table data for export..."
    query = f"""
        SELECT t.xcol, t.yrow, t.date, t.value
        FROM {table_name} t
        JOIN {grid_name} g ON t.xcol = g.xcol AND t.yrow = g.yrow
        WHERE t.date BETWEEN %s AND %s
    """
    params = [init_date, end_date]
    if bbox:
        query += """
            AND t.xcol BETWEEN %s AND %s
            AND t.yrow BETWEEN %s AND %s
        """
        params.extend([min_xcol, max_xcol, min_yrow, max_yrow])

    # Read all data into a DataFrame
    df = pd.read_sql(query, conn, params=params)
    if df.empty:
        yield "No data found for the given parameters."
        return
    yield f"Data loaded: {len(df)} records, {df['date'].nunique()} dates."

    # Prepare grid
    yield "Preparing grid and array for GeoTIFF..."
    xcols = np.arange(min_xcol, max_xcol + 1)
    yrows = np.arange(min_yrow, max_yrow + 1)
    dates = sorted(df['date'].unique())
    arr = np.full((len(dates), len(yrows), len(xcols)), np.nan, dtype=np.float32)
    date_to_band = {date: i for i, date in enumerate(dates)}

    # Fill array
    yield "Filling array with table values..."
    for idx, row in enumerate(df.itertuples(index=False), 1):
        x_idx = int(row.xcol - min_xcol)
        y_idx = int(row.yrow - min_yrow)
        band_idx = date_to_band[row.date]
        arr[band_idx, y_idx, x_idx] = row.value
        if idx % 100000 == 0:
            yield f"Filled {idx} records into array..."

    # GeoTIFF transform (align to cell centroids)
    pixel_width = resolution
    pixel_height = resolution
    # Offset by half a pixel to align pixel centers with cell centroids
    transform = from_origin(min_lon - 0.5 * pixel_width, max_lat + 0.5 * pixel_height, pixel_width, pixel_height)
    yield "Array filled. Starting GeoTIFF writing... (centroid-aligned)"

    # Write GeoTIFF
    with rasterio.open(
        output_filename,
        'w',
        driver='GTiff',
        height=arr.shape[1],
        width=arr.shape[2],
        count=arr.shape[0],
        dtype=arr.dtype,
        crs='EPSG:4326',
        transform=transform,
    ) as dst:
        for i, date in enumerate(dates):
            dst.write(arr[i, :, :], i + 1)
            dst.set_band_description(i + 1, str(date))
            percent = (i + 1) / len(dates) * 100
            yield f"Written band {i+1}/{len(dates)} ({percent:.1f}%) - {date}"

    yield f"Multiband GeoTIFF written to {output_filename}"

#############################################################
# Export NetCDF variable/time slice to GeoTIFF
#############################################################
def netcdf_to_geotiff(nc_path, geotiff_path=None):
    import xarray as xr
    import os
    import rasterio
    from rasterio.transform import from_origin

    ds = xr.open_dataset(nc_path)
    var_name = list(ds.data_vars)[0]
    arr = ds[var_name].values  # shape: (latitude, longitude, date)
    print("Data array shape:", arr.shape)
    lat = ds['latitude'].values
    print("Latitude array shape:", lat.shape)
    lon = ds['longitude'].values
    print("Longitude array shape:", lon.shape)
    dates = ds['date'].values
    print("Dates array shape:", dates.shape)

    # Transpose array to (date, latitude, longitude) for rasterio
    arr = np.transpose(arr, (2, 0, 1))  # Now shape: (date, latitude, longitude)

    pixel_width = abs(lon[1] - lon[0])
    pixel_height = abs(lat[1] - lat[0])
    transform = from_origin(lon.min(), lat.max(), pixel_width, pixel_height)

    if geotiff_path is None:
        geotiff_path = os.path.splitext(nc_path)[0] + "_multiband.tif"

    with rasterio.open(
        geotiff_path,
        'w',
        driver='GTiff',
        height=arr.shape[1],
        width=arr.shape[2],
        count=arr.shape[0],  # number of dates as bands
        dtype=arr.dtype,
        crs='EPSG:4326',
        transform=transform,
    ) as dst:
        total = arr.shape[0]
        for t in range(total):
            dst.write(arr[t, :, :], t + 1)
            # Set band description to the date string
            date_str = str(dates[t])
            dst.set_band_description(t + 1, date_str)
            percent = (t + 1) / total * 100
            yield f"Written band {t+1}/{total} ({percent:.1f}%) - {date_str}"

    yield f"Multiband GeoTIFF written to {geotiff_path}"

#############################################################
# Convert multiband GeoTIFF to NetCDF
#############################################################
def geotiff_to_netcdf(geotiff_path, netcdf_path=None, dates=None):
    """
    Convert a multiband GeoTIFF file to a NetCDF file.
    Each band is assumed to represent a time slice (e.g., a date).
    Optionally, provide a list of date strings (len = band count).
    If not provided, will use band descriptions if available, else generic indices.
    """


    with rasterio.open(geotiff_path) as src:
        arr = src.read()  # (bands, height, width)
        transform = src.transform
        crs = src.crs
        count = src.count
        height = src.height
        width = src.width
        # Get band descriptions if available
        band_desc = [src.descriptions[i] if src.descriptions[i] else f"band_{i+1}" for i in range(count)]
        # Get coordinates (center of each pixel)
        lon = np.array([ (transform * (x + 0.5, 0.5))[0] for x in range(width) ])
        lat = np.array([ (transform * (0.5, y + 0.5))[1] for y in range(height) ])
        # rasterio uses (band, y, x), netcdf_to_geotiff expects (lat, lon, date), so transpose
        arr = np.transpose(arr, (1, 2, 0)).astype(np.float32)  # (height, width, bands) -> (lat, lon, date)

    # Handle dates
    if dates is not None:
        if len(dates) != count:
            raise ValueError("Length of dates must match number of bands in GeoTIFF.")
        time = np.array(dates)
    else:
        # Try to use band descriptions if they look like dates
        try:
            import dateutil.parser
            time = np.array([str(dateutil.parser.parse(d)) for d in band_desc])
        except Exception:
            time = np.array([f"band_{i+1}" for i in range(count)])

    # Use the same variable name as export_table_to_netcdf (value)
    var_name = "value"

    # Build DataArray and Dataset with correct dims and coords
    da = xr.DataArray(
        arr,
        dims=["latitude", "longitude", "date"],
        coords={
            "latitude": lat,
            "longitude": lon,
            "date": time
        },
        name=var_name
    )
    ds = xr.Dataset({var_name: da})
    ds.attrs["crs"] = str(crs)

    if netcdf_path is None:
        netcdf_path = os.path.splitext(geotiff_path)[0] + ".nc"

    ds.to_netcdf(netcdf_path)
    return netcdf_path

#############################################################
#############################################################
# Miscellaneous functions
#############################################################
#############################################################

#############################################################
# Parse SLD rules from SLD XML source
#############################################################

def parse_sld_rules(sld_source):
    try:
        root = ET.fromstring(sld_source)
        ns = {
            'sld': 'http://www.opengis.net/sld',
            'ogc': 'http://www.opengis.net/ogc'
        }
        rules = []
        for rule in root.findall('.//sld:Rule', ns):
            lower = None
            upper = None
            color = None
            between = rule.find('.//ogc:PropertyIsBetween', ns)
            if between is not None:
                lower_elem = between.find('.//ogc:LowerBoundary/ogc:Literal', ns)
                upper_elem = between.find('.//ogc:UpperBoundary/ogc:Literal', ns)
                if lower_elem is not None:
                    lower = float(lower_elem.text)
                if upper_elem is not None:
                    upper = float(upper_elem.text)
            le = rule.find('.//ogc:PropertyIsLessThanOrEqualTo', ns)
            if le is not None:
                upper_elem = le.find('.//ogc:Literal', ns)
                if upper_elem is not None:
                    upper = float(upper_elem.text)
            ge = rule.find('.//ogc:PropertyIsGreaterThanOrEqualTo', ns)
            if ge is not None:
                lower_elem = ge.find('.//ogc:Literal', ns)
                if lower_elem is not None:
                    lower = float(lower_elem.text)
            color_elem = rule.find('.//sld:CssParameter[@name="fill"]/ogc:Literal', ns)
            if color_elem is not None:
                color = color_elem.text
            rules.append({
                'lower_boundary': lower,
                'upper_boundary': upper,
                'color': color
            })
        return rules
    except Exception:
        return None

