####################################################################################################################
# create_layer.py
# Script to create a new layer in the PostgreSQL/PostGIS database from a NetCDF file
# The script reads configuration from config.ini and uses xarray to process the NetCDF file
# It creates necessary tables and populates them with data from the NetCDF file
# example usage: 
# python create_layer.py --nc_file path/to/file.nc --layer_name layer_name --value_dim var_name [--time_dim time_var] [--lon_dim lon_var] [--lat_dim lat_var] [--db_os_users]
####################################################################################################################
import configparser
import os
import psycopg2
from datetime import datetime
import numpy as np
import xarray as xr
import argparse

####################################################################################
# Read configuration
####################################################################################
# Get the path to config.ini
config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.ini')

# Read the config file
config = configparser.ConfigParser()
config.read(config_path)
print("Config file read from:", config_path)
print("Sections found:", config.sections())

# DBConnection parameters PostgreSQL
DB_HOST = config.get('database', 'host')
DB_PORT = config.get('database', 'port')
DB_NAME = config.get('database', 'name')
DB_USER = config.get('database', 'user')
DB_PASSWORD = config.get('database', 'password')    
GRIDS = dict(config['grids'])

# DB config for OS user option
DB_CONN_STR = f"dbname={DB_NAME}"


####################################################################################
# determine spatial resolution and corresponding grid table
####################################################################################
def determine_spatial_resolution(lat):
    global DATA_GRID

    if len(lat) < 2:
        print("Not enough latitude points to determine spatial resolution.")
        return
    lat_diff = np.abs(lat[1] - lat[0])

    DATA_GRID = GRIDS.get(str(lat_diff))
    print(f"Determined spatial resolution: {lat_diff} degrees, using grid table: {DATA_GRID}")

####################################################################################
# Creates the tables to contain the information
####################################################################################
def create_tables(conn):
    query_table = f"""
                  CREATE TABLE {LAYER_NAME}_data (
                    id SERIAL PRIMARY KEY,
                    xcol double precision,
                    yrow double precision,
                    value FLOAT,
                    date DATE
                  );
                  """                                 
    query_t_idx = f"""
                  CREATE INDEX idx_{LAYER_NAME}_data_xcol_yrow ON {LAYER_NAME}_data(xcol, yrow);
                  """
    query_view = f"""
                 CREATE VIEW {LAYER_NAME} AS
                 SELECT 
                     grid.cell,
                     data.xcol,
                     data.yrow,
                     data.date,
                     data.value
                 FROM 
                     {LAYER_NAME}_data AS data
                 JOIN 
                     {DATA_GRID} AS grid
                 ON 
                     data.xcol = grid.xcol AND data.yrow = grid.yrow;
                 """  
    cursor=conn.cursor()
    cursor.execute(query_table)
    conn.commit()
    cursor.execute(query_t_idx)
    conn.commit()
    cursor.execute(query_view)
    conn.commit()
    cursor.close()

####################################################################################
# Get initial grid cell for given lat/lon
####################################################################################
def get_initial_grid_cell(lat,lon,conn):
    cursor = conn.cursor()
    query = f"""
    SELECT xcol, yrow
    FROM {DATA_GRID} AS grid
    WHERE ST_Contains(grid.cell, ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326));
    """
    print(query)
    cursor.execute(query)
    result = cursor.fetchone()
    if result:
        # If there is a candidate cell, we take it as initial
        cursor.close()
        return {"xcol": result[0], "yrow": result[1]}
    else:
        # If no cell contains the point, we find the nearest cell,
        # if more than one candidate, we take the minimum x,y as initial
        query = f"""
        SELECT min(xcol), min(yrow)
        FROM {DATA_GRID} AS grid
        WHERE ST_Intersects(grid.cell, ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326));
        """
        cursor.execute(query)
        result = cursor.fetchone()
        cursor.close()
        return {"xcol": result[0], "yrow": result[1]} if result else None

####################################################################################
# Insert data into the table
####################################################################################
def insert_into_table(xcol,yrow,date,value):
    query = f"INSERT INTO {LAYER_NAME}_data (xcol, yrow, value, date) "
    query += f"VALUES ({xcol}, {yrow}, {value if not np.isnan(value) else 'NULL'}, '{np.datetime_as_string(date, unit='D')}');"
    print(query)
    return query

####################################################################################
# Read NetCDF file and populate the database    
####################################################################################
def read_nc_file(conn):
    cursor=conn.cursor()

    ds = xr.open_dataset(NC_FILE)
    data = ds[VALUE_DIM].values  
    time = ds[TIME_DIM].values
    long = ds[LON_DIM].values 
    lat =  ds[LAT_DIM].values

    print(lat[0], lat[1], lat[2], lat[3], lat[4])
    print(long[0], long[1], long[2], long[3], long[4])
    determine_spatial_resolution(lat)
    create_tables(conn)
    initial_cell = get_initial_grid_cell(lat[0], long[0], conn)
    if not initial_cell:
        print("Initial cell not found in the grid.")
        return
    print("Initial cell found:", initial_cell)
    
    xcol = initial_cell['xcol']
    yrow = initial_cell['yrow']

    for ltc, ltv in enumerate(lat):        
        for lnc, lnv in enumerate(long):
            for tc, tv in enumerate(time):        
                query = insert_into_table(xcol, yrow, tv, data[tc, ltc, lnc])
                cursor.execute(query)
            xcol += 1 # Move to the next column
        yrow += 1 # Move to the next row
        xcol = initial_cell['xcol'] # Reset to initial column for new row

    conn.commit()
    cursor.close()

####################################################################################
# MAIN
####################################################################################
def main():
    global NC_FILE
    global LAYER_NAME 
    global VALUE_DIM
    global TIME_DIM
    global LON_DIM 
    global LAT_DIM 

    parser = argparse.ArgumentParser(description="Process NetCDF layer ingestion parameters.")
    # Mandatory parameters
    parser.add_argument('--nc_file', required=True, help="Path to NetCDF file")
    parser.add_argument('--layer_name', required=True, help="Layer name")
    parser.add_argument('--value_dim', required=True, help="Value dimension name")
    # Optional parameters with defaults
    parser.add_argument('--time_dim', default='valid_time', help="Time dimension name (default: 'valid_time')")
    parser.add_argument('--lon_dim', default='longitude', help="Longitude dimension name (default: 'longitude')")
    parser.add_argument('--lat_dim', default='latitude', help="Latitude dimension name (default: 'latitude')")
    parser.add_argument('--db_os_users', action='store_true', help="Use OS user configuration for DB connection")

    args = parser.parse_args()

    NC_FILE = args.nc_file
    LAYER_NAME = args.layer_name
    VALUE_DIM = args.value_dim
    TIME_DIM = args.time_dim
    LON_DIM = args.lon_dim
    LAT_DIM = args.lat_dim

    print(f"NC_FILE: {NC_FILE}")
    print(f"LAYER_NAME: {LAYER_NAME}")
    print(f"VALUE_DIM: {VALUE_DIM}")
    print(f"TIME_DIM: {TIME_DIM}")
    print(f"LON_DIM: {LON_DIM}")
    print(f"LAT_DIM: {LAT_DIM}")

    if args.db_os_users:
        conn = psycopg2.connect(DB_CONN_STR)
    else:
        conn = psycopg2.connect(
                database=DB_NAME,
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                port=DB_PORT
            )
    read_nc_file(conn)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()