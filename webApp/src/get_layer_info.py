import configparser
import os
import psycopg2
from datetime import datetime
import numpy as np
import xarray as xr

def get_feature_data(table,lat,lon,date,conn):
    """Get feature info from the database based on layer, lat, lon, and date."""
    try:
        # Convert date string to a date object
        date_obj = datetime.strptime(date, '%Y-%m-%d').date()
        
        # SQL query to find the cell_id for the given lat/lon
        cell_id_query = f"""
            SELECT cell_id 
            FROM grid_{table} 
            WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326));
        """
        
        with conn.cursor() as cursor:
            cursor.execute(cell_id_query, (lon, lat))
            result = cursor.fetchone()
            if not result:
                return {"error": "No grid cell found for the provided coordinates."}
            cell_id = result[0]
        
        # SQL query to get the value for the given cell_id and date
        value_query = f"""
            SELECT value 
            FROM {table} 
            WHERE cell_id = %s AND date = %s;
        """
        
        with conn.cursor() as cursor:
            cursor.execute(value_query, (cell_id, date_obj))
            result = cursor.fetchone()
            if not result:
                return {"error": "No data found for the provided date and location."}
            value = result[0]
        
        return {
            "cell_id": cell_id,
            "value": value,
            "date": date,
            "latitude": lat,
            "longitude": lon
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
        
        # Find cell_id for the given lat/lon
        cell_id_query = f"""
            SELECT cell_id 
            FROM grid_{table} 
            WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326));
        """
        with conn.cursor() as cursor:
            cursor.execute(cell_id_query, (lon, lat))
            result = cursor.fetchone()
            if not result:
                return {"error": "No grid cell found for the provided coordinates."}
            cell_id = result[0]
        
        # Get values for the selected cell and date range
        value_query = f"""
            SELECT date, value 
            FROM {table} 
            WHERE cell_id = %s AND date BETWEEN %s AND %s
            ORDER BY date;
        """
        with conn.cursor() as cursor:
            cursor.execute(value_query, (cell_id, date_from, date_to))
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
                        ]
            }
    
    except Exception as e:
        return {"error": str(e)}