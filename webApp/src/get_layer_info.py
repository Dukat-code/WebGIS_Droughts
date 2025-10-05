from datetime import datetime
import decimal
import numpy as np
import json

def get_feature_data(layer, lat, lon, date, conn):
    """
    Get feature info from the {layer} based on lat, lon, and date.
    Assumes the view contains columns: xcol, yrow, value, date, cell (geometry).
    """
    try:
        date_obj = datetime.strptime(date, '%Y-%m-%d').date()

        # Query the view for the cell containing the point and the given date
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
        
        # Alternative approach: get data from data view
        # Get values for the selected coords and date range
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
            
            xcol = results[0][2]    # Assuming all rows have the same xcol
            yrow = results[0][3]    # Assuming all rows have the same yrow
            for row in results:
                date_obj = row[0]
                value = row[1]
                year_idx = date_obj.year - yearFrom
                month_idx = date_obj.month - 1
                if 0 <= year_idx < len(years) and 0 <= month_idx < len(months):
                    arr[year_idx, month_idx] = value
            
            # Replace nan values with zero for the sample
            arr = np.nan_to_num(arr, nan=0.0)

            # Calculate avg and st_dev per month for the selected cell over all dates in the table
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
        #view_name = f"{table}_data_view"
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
            # Ensure min_date and max_date are datetime.date objects
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
            # Ensure min_date and max_date are datetime.date objects
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
        
        # Alternative approach: get data from data view
        # Get values for the selected coords and date range
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
            
            # Replace nan values with zero for the sample
            arr = np.nan_to_num(arr, nan=0.0)

            # Calculate avg and st_dev per month for the selected cell over all dates in the table
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