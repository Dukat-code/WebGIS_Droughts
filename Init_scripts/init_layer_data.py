import configparser
import os
import psycopg2
import csv
from datetime import datetime
import numpy as np
import xarray as xr

# Get the path to config.ini
config_path = os.path.join(os.path.dirname(__file__), 'config', 'config.ini')

# Read the config file
config = configparser.ConfigParser()
config.read(config_path)

# DBConnection parameters PostgreSQL
DB_HOST = config.get('database', 'host')
DB_PORT = config.get('database', 'port')
DB_NAME = config.get('database', 'name')
DB_USER = config.get('database', 'user')
DB_PASSWORD = config.get('database', 'password')    

# Data parameters
TABLE_NAME = 'era5_ecowas'
CSV_FILE = 'grid_era5_ecowas.csv'
NC_FILE = 'era5_monthly_tp_ecowas.nc'
VALUE_DIM = 'tp'
TIME_DIM = 'valid_time'
LON_DIM = 'longitude'
LAT_DIM = 'latitude'

####################################################################################
# Creates the tables to contain the information
####################################################################################
def create_tables(conn):
    query_grid = f"""
                 CREATE TABLE grid_{TABLE_NAME} (
                    id INTEGER PRIMARY KEY,
                    cell_id BIGINT UNIQUE,
                    geom GEOMETRY(POLYGON, 4326)
                 );
                 """
    query_g_idx = f"""
                  CREATE INDEX idx_grid_{TABLE_NAME}_cell_id ON grid_{TABLE_NAME}(cell_id);
                  """
    query_table = f"""
                  CREATE TABLE {TABLE_NAME} (
                    id SERIAL PRIMARY KEY,
                    cell_id BIGINT NOT NULL,
                    value FLOAT,
                    date DATE
                  );
                  """                                 
    query_t_idx = f"""
                  CREATE INDEX idx_{TABLE_NAME}_cell_id ON {TABLE_NAME}(cell_id);
                  """
    query_view = f"""
                 CREATE VIEW {TABLE_NAME}_data_view AS
                 SELECT 
                     grid.geom,
                     era5.cell_id,
                     era5.date,
                     era5.value
                 FROM 
                     {TABLE_NAME} AS era5
                 JOIN 
                     grid_{TABLE_NAME} AS grid
                 ON 
                     era5.cell_id = grid.cell_id;
                 """  
    cursor=conn.cursor()
    cursor.execute(query_grid)
    conn.commit()
    cursor.execute(query_g_idx)
    conn.commit()
    cursor.execute(query_table)
    conn.commit()
    cursor.execute(query_t_idx)
    conn.commit()
    cursor.execute(query_view)
    conn.commit()
    cursor.close()

####################################################################################
# Creates the CSV for the grid based on the centroids
# takes each point of the file .nc as centroid, and generates the CSV to
# be used in the function grid_from_csv
# i.e.: create_grid_csv('era5_monthly_tp_ecowas.nc','grid_era5_ecowas.csv')
####################################################################################
def create_grid_csv(nc_file,csv_file):
    ds = xr.open_dataset(nc_file) ## ecowas
    long_era5 = np.sort(ds['longitude'].values)  # NumPy array
    lat_era5 = np.sort(ds['latitude'].values)  # NumPy array
    print("lat , long , ind")
    fieldnames=['latitude','longitude','index']
    rows = []
    i = 0
    for lat in lat_era5:
        for lon in long_era5:
            i+=1
            rows.append({'latitude':float(lat),'longitude':float(lon),'index':i})
    with open(csv_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

####################################################################################
# Returns the polygon geometry of a cell given lat,lon of centroid and resolution
####################################################################################
def cell_from_centroid(lat,lon,res):
    delta = res/2
    lat_min = lat - delta
    lat_max = lat + delta
    lon_min = lon - delta
    lon_max = lon + delta
    geom = "POLYGON(({} {}, {} {}, {} {}, {} {}, {} {}))".format(lon_min,lat_min,lon_min,lat_max,lon_max,lat_max,lon_max,lat_min,lon_min,lat_min)
    return geom

####################################################################################
# Returns a unique ID for each cell based on lat,lon of the centroid
####################################################################################
def cell_id_from_centroid(lat,lon):
    return str(int((lat+360)*1000)) + str(int((lon+360)*1000))

####################################################################################
# Creates the grid
# i.e.: grid_from_csv('grid_era5_ecowas.csv')
####################################################################################
def grid_from_csv(conn,filename,table):
    table='grid_'+table
    cursor=conn.cursor()

    arr = np.genfromtxt(filename, delimiter=",",names=True)
    resolution=arr[1][1] - arr[0][1]
    for row in arr:
        geom = cell_from_centroid(row[0], row[1], resolution)
        query = "INSERT INTO " + table +"(id,cell_id,geom) "
        query+= "VALUES ("
        query+= "" + str(int(row[2])) + ", "
        query+= "" + cell_id_from_centroid(row[0], row[1]) + ", "
        query+= "ST_GeomFromText('" + geom + "',4326));"
        print(query)
        cursor.execute(query)

    conn.commit()
    cursor.close()

####################################################################################
# inserts into a data table the information of a cell
####################################################################################
def insert_into_table(table,lat,lon,date,value):
    query = "INSERT INTO " + table +"(cell_id,value,date) "
    query+= "VALUES ("
    query+= cell_id_from_centroid(lat, lon) + ","
    query+= str(value) + ","
    query+= "'" + np.datetime_as_string(date, unit='D') + "');"
    print(query)
    return query

####################################################################################
# inserts into a table the information of a .nc file
# i.e.: insert_from_nc('era5_ecowas','era5_monthly_tp_ecowas.nc','tp','valid_time','longitude','latitude')
####################################################################################
def insert_from_nc(conn,table,filename,value_dim,time_dim,lon_dim,lat_dim):
    cursor=conn.cursor()

    ds = xr.open_dataset(filename)
    data = ds[value_dim].values  
    time = ds[time_dim].values
    long = ds[lon_dim].values 
    lat =  ds[lat_dim].values
    for ltc, ltv in enumerate(lat):        
        for lnc, lnv in enumerate(long):
            for tc, tv in enumerate(time):        
                query = insert_into_table(table,ltv,lnv,tv,data[tc,ltc,lnc])
                cursor.execute(query)

    conn.commit()
    cursor.close()

####################################################################################
# MAIN
####################################################################################
def main():
    conn = psycopg2.connect(
            database=DB_NAME,
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT
        )

    create_tables(conn)
    create_grid_csv(NC_FILE,CSV_FILE)
    grid_from_csv(conn,CSV_FILE,TABLE_NAME)
    insert_from_nc(conn,TABLE_NAME,NC_FILE,VALUE_DIM,TIME_DIM,LON_DIM,LAT_DIM)
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()