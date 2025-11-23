import time
from datetime import datetime
import decimal
import os
import numpy as np
import pandas as pd
import geopandas as gpd
import xarray as xr
import json
import gc
import xml.etree.ElementTree as ET
import configparser

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
# Functions to get layer info from the database
################################################################
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

def get_data_time_bounds(lat, lon, layer, conn):
    """
    Get the minimum and maximum year and month for the given location from the view.
    Returns: {"min_year": int, "min_month": int, "max_year": int, "max_month": int}
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

def get_layer_time_bounds(layer, conn):
    """
    Get the minimum and maximum year and month for the given location from the view.
    Returns: {"min_year": int, "min_month": int, "max_year": int, "max_month": int}
    """
    try:
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

def get_centroid_lat_lon(min_xcol, min_yrow, max_lat, min_lon, resolution, xcol_final, yrow_final):
    delta_x = xcol_final - min_xcol
    delta_y = yrow_final - min_yrow
    centroid_lat = max_lat - delta_y * resolution
    centroid_lon = min_lon + delta_x * resolution
    return centroid_lat, centroid_lon

def export_table_to_netcdf(conn, table_name, grid_name, resolution, init_date, end_date, bbox, output_filename, chunksize=100000):
    import gc
    print("Exporting table {} to NetCDF...".format(table_name))
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
                return {"error": "No data found in the table."}
            min_xcol, max_xcol, min_yrow, max_yrow = result
    else:
        query = f"SELECT MIN(xcol), MAX(xcol), MIN(yrow), MAX(yrow) FROM {table_name};"
        with conn.cursor() as cursor:
            cursor.execute(query)
            min_xcol, max_xcol, min_yrow, max_yrow = cursor.fetchone()
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
            return {"error": "No data found in the table."}
        _, _, centroid_wkt = result
        coords = centroid_wkt.replace('POINT(', '').replace(')', '').split()
        min_lon, max_lat = float(coords[0]), float(coords[1])
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
    count_query = f"SELECT COUNT(*) FROM ({query}) AS subq"
    with conn.cursor() as cursor:
        cursor.execute(count_query, params)
        total_rows = cursor.fetchone()[0]
    if total_rows == 0:
        return {"error": "No data found for the given parameters."}
    def format_hms(seconds):
        seconds = int(seconds)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02}:{m:02}:{s:02}"
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
                print(f"Processed {processed_rows}/{total_rows} rows... ({percent:.1f}%) "
                      f"Elapsed: {format_hms(elapsed)}, Remaining: {format_hms(remaining)}")
                last_percent = percent
            del df
            gc.collect()
        if not all_dfs:
            return {"error": "No data found for the given parameters."}
        big_df = pd.concat(all_dfs)
        del all_dfs
        gc.collect()
        big_df = big_df.groupby(['latitude', 'longitude', 'date']).mean().reset_index()
        big_df = big_df.set_index(['latitude', 'longitude', 'date'])
        ds = xr.Dataset.from_dataframe(big_df)
        ds.to_netcdf(output_filename)
        del ds, big_df
        gc.collect()
        print("Export completed successfully.")
        return {"success": True, "file": output_filename}
    except Exception as e:
        print(f"Error exporting data to NetCDF: {e.__class__.__name__}: {e}")
        return {"error": str(e)}

def parse_sld_rules(sld_path):
    try:
        print(f"Parsing SLD file: {sld_path}")
        tree = ET.parse(sld_path)
        root = tree.getroot()
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