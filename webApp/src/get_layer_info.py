import configparser
import os
import psycopg2
from datetime import datetime
import numpy as np
import xarray as xr

# RE-DEFINE THESE FUNCTIONS USING THE VIEWS INSTEAD OF THE RAW TABLES
def get_feature_data(table, lat, lon, date, conn):
    """
    Get feature info from the {TABLE_NAME}_data_view based on lat, lon, and date.
    Assumes the view contains columns: cell_id, value, date, geom (geometry).
    """
    try:
        date_obj = datetime.strptime(date, '%Y-%m-%d').date()
        view_name = f"{table}_data_view"

        # Query the view for the cell containing the point and the given date
        query = f"""
            SELECT cell_id, value, date
            FROM {view_name}
            WHERE date = %s
              AND ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
            LIMIT 1;
        """
        with conn.cursor() as cursor:
            cursor.execute(query, (date_obj, lon, lat))
            result = cursor.fetchone()
            if not result:
                return {"error": "No data found for the provided date and location."}
            cell_id, value, date_val = result

        return {
            "cell_id": cell_id,
            "value": value,
            "date": str(date_val)
        }

    except Exception as e:
        return {"error": str(e)}
        
def get_feature_data_from_lat_lon(table, lat, lon, yearFrom, monthFrom, yearTo, monthTo, conn):
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
            SELECT date, value, cell_id 
            FROM {table}_data_view 
            WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
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
            
            cell_id = results[0][2]  # Assuming all rows have the same cell_id
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
                FROM {table}
                WHERE cell_id = %s
                GROUP BY month
                ORDER BY month;
            """
            with conn.cursor() as cursor:
                cursor.execute(cell_month_query, (cell_id,))
                cell_results = cursor.fetchall()
                month_stats = {int(row[0]): {"avg": row[1] or 0.0, "std": row[2] or 0.0} for row in cell_results}
                for m in months:
                    stats = month_stats.get(m, {"avg": 0.0, "std": 0.0})
                    cell_avg.append(stats["avg"])
                    cell_std.append(stats["std"])
            return {
                "cell_id": cell_id,
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

def get_data_time_bounds(lat, lon, table, conn):
    """
    Get the minimum and maximum year and month for the given location from the view.
    Returns: {"min_year": int, "min_month": int, "max_year": int, "max_month": int}
    """
    try:
        view_name = f"{table}_data_view"
        query = f"""
            SELECT MIN(date), MAX(date)
            FROM {view_name}
            WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326));
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