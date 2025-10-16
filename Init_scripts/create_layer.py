import configparser
import os
import psycopg2
import numpy as np
import xarray as xr
import argparse
import sys
import time

####################################################################################
# Read configuration
####################################################################################
config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.ini')
config = configparser.ConfigParser()
config.read(config_path)
print("Config file read from:", config_path)
print("Sections found:", config.sections())

GRIDS = dict(config['grids'])

####################################################################################
# determine spatial resolution and corresponding grid table
####################################################################################
def determine_spatial_resolution(lat):
    global DATA_GRID
    global RES

    if len(lat) < 2:
        print("Not enough latitude points to determine spatial resolution.")
        return
    RES = np.abs(lat[1] - lat[0])
    DATA_GRID = GRIDS.get(str(RES))
    print(f"Determined spatial resolution: {RES} degrees, using grid table: {DATA_GRID}")

####################################################################################
# Creates the tables to contain the information
####################################################################################
def create_tables(conn, layer_name):
    query_table = f"""
                  CREATE TABLE IF NOT EXISTS {layer_name}_data (
                    id SERIAL PRIMARY KEY,
                    xcol double precision,
                    yrow double precision,
                    value FLOAT,
                    date DATE
                  );
                  """                                 
    query_t_idx = f"""
                  CREATE INDEX IF NOT EXISTS idx_{layer_name}_data_xcol_yrow ON {layer_name}_data(xcol, yrow);
                  """
    query_drop_view = f"""
                      DROP VIEW IF EXISTS {layer_name};
                      """
    query_view = f"""
                 CREATE VIEW {layer_name} AS
                 SELECT 
                     grid.cell,
                     data.xcol,
                     data.yrow,
                     data.date,
                     data.value
                 FROM 
                     {layer_name}_data AS data
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
    cursor.execute(query_drop_view)
    conn.commit()
    cursor.execute(query_view)
    conn.commit()
    cursor.close()

####################################################################################
# Fetch only grid cells intersecting the NetCDF bounding box
####################################################################################
def fetch_grid_cells(conn, min_lon, min_lat, max_lon, max_lat):
    cursor = conn.cursor()
    query = f"""
        SELECT xcol, yrow, ST_XMin(cell), ST_XMax(cell), ST_YMin(cell), ST_YMax(cell), ST_AsText(ST_ExteriorRing(cell)) AS vertices
        FROM {DATA_GRID}
        WHERE ST_Intersects(
            cell,
            ST_MakeEnvelope(%s, %s, %s, %s, 4326)
        );
    """
    cursor.execute(query, (min_lon, min_lat, max_lon, max_lat))
    cells = []
    for row in cursor.fetchall():
        cells.append({
            "xcol": row[0],
            "yrow": row[1],
            "xmin": row[2],
            "xmax": row[3],
            "ymin": row[4],
            "ymax": row[5],
            "vertices": row[6]
        })
    cursor.close()
    return cells

####################################################################################
# Batch insert data into the table (parameterized)
####################################################################################
def batch_insert(cursor, layer_name, rows):
    query = f"INSERT INTO {layer_name}_data (xcol, yrow, value, date) VALUES (%s, %s, %s, %s);"
    cursor.executemany(query, rows)

####################################################################################
# Helper to format seconds as hh:mm:ss
####################################################################################
def format_hms(seconds):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"

####################################################################################
# Read NetCDF file and populate the database    
####################################################################################
def read_nc_file(conn, nc_file, layer_name, value_dim, time_dim, lon_dim, lat_dim, batch_size=5000):
    try:
        cursor = conn.cursor()
        ds = xr.open_dataset(nc_file)
        print(ds.info())
        print(ds.dims)
        data = ds[value_dim]
        time_vals = ds[time_dim].values
        long = np.sort(ds[lon_dim].values)  # ascending
        lat = np.sort(ds[lat_dim].values)[::-1]  # descending

        determine_spatial_resolution(lat)
        create_tables(conn, layer_name)

        min_lat, max_lat = float(np.min(lat)), float(np.max(lat))
        min_lon, max_lon = float(np.min(long)), float(np.max(long))

        grid_cells = fetch_grid_cells(conn, min_lon, min_lat, max_lon, max_lat)

        # Decide mode: points inside cells or at vertices
        center_cell = grid_cells[len(grid_cells)//2]
        cell_lat_min, cell_lat_max = center_cell['ymin'], center_cell['ymax']
        cell_lon_min, cell_lon_max = center_cell['xmin'], center_cell['xmax']

        inside_lat_mask = (lat > cell_lat_min) & (lat < cell_lat_max)
        inside_lon_mask = (long > cell_lon_min) & (long < cell_lon_max)
        inside_mode = np.any(inside_lat_mask) and np.any(inside_lon_mask)

        at_vertex_mode = False
        if not inside_mode:
            vertex_coords = [
                (cell_lat_min, cell_lon_min),
                (cell_lat_min, cell_lon_max),
                (cell_lat_max, cell_lon_min),
                (cell_lat_max, cell_lon_max)
            ]
            matches = 0
            for vlat, vlon in vertex_coords:
                lat_idx = np.where(np.isclose(lat, vlat))[0]
                lon_idx = np.where(np.isclose(long, vlon))[0]
                if lat_idx.size > 0 and lon_idx.size > 0:
                    matches += 1
            at_vertex_mode = (matches == 4)

        if not inside_mode and not at_vertex_mode:
            print("ERROR: NetCDF points are neither inside cells nor at vertices.")
            return

        total_cells = len(grid_cells)
        total_times = len(time_vals)
        total_iterations = total_cells * total_times
        progress_count = 0
        batch = []

        last_percent = -1.0
        start_time = time_module.time()

        # --- FAST "INSIDE" MODE ---
        if inside_mode:
            # Precompute mapping from cell to NetCDF index
            cell_to_idx = []
            for cell in grid_cells:
                cell_lat_min, cell_lat_max = cell['ymin'], cell['ymax']
                cell_lon_min, cell_lon_max = cell['xmin'], cell['xmax']
                inside_lat_mask = (lat > cell_lat_min) & (lat < cell_lat_max)
                inside_lon_mask = (long > cell_lon_min) & (long < cell_lon_max)
                if np.any(inside_lat_mask) and np.any(inside_lon_mask):
                    la_idx = np.where(inside_lat_mask)[0][0]
                    lo_idx = np.where(inside_lon_mask)[0][0]
                    cell_to_idx.append((cell['xcol'], cell['yrow'], la_idx, lo_idx))
                else:
                    cell_to_idx.append(None)

            # For each time step, extract all values in one go
            for t_idx, tv in enumerate(time_vals):
                for i, mapping in enumerate(cell_to_idx):
                    if mapping is not None:
                        xcol, yrow, la_idx, lo_idx = mapping
                        val = data.values[t_idx, la_idx, lo_idx]
                        if not np.isnan(val):
                            batch.append((xcol, yrow, float(val), np.datetime_as_string(tv, unit='D')))
                            if len(batch) >= batch_size:
                                batch_insert(cursor, layer_name, batch)
                                batch = []
                    # Progress update
                    progress_count += 1
                    percent = (progress_count / total_iterations) * 100
                    if percent - last_percent >= 0.1 or progress_count == total_iterations:
                        elapsed = time_module.time() - start_time
                        if percent > 0:
                            estimated_total = elapsed / (percent / 100)
                            remaining = estimated_total - elapsed
                        else:
                            remaining = 0
                        print(f"Processed {progress_count}/{total_iterations} cell-times... ({percent:.1f}%) "
                              f"Elapsed: {format_hms(elapsed)}, Remaining: {format_hms(remaining)}")
                        last_percent = percent
                if batch:
                    batch_insert(cursor, layer_name, batch)
                    batch = []

        # --- FAST "VERTEX" MODE ---
        elif at_vertex_mode:
            # Precompute mapping from cell to 4 NetCDF indices (vertices)
            cell_to_vertex_indices = []
            for cell in grid_cells:
                cell_lat_min, cell_lat_max = cell['ymin'], cell['ymax']
                cell_lon_min, cell_lon_max = cell['xmin'], cell['xmax']
                vertex_coords = [
                    (cell_lat_min, cell_lon_min),
                    (cell_lat_min, cell_lon_max),
                    (cell_lat_max, cell_lon_min),
                    (cell_lat_max, cell_lon_max)
                ]
                indices = []
                for vlat, vlon in vertex_coords:
                    lat_idx = np.where(np.isclose(lat, vlat))[0]
                    lon_idx = np.where(np.isclose(long, vlon))[0]
                    if lat_idx.size > 0 and lon_idx.size > 0:
                        indices.append((lat_idx[0], lon_idx[0]))
                if len(indices) == 4:
                    cell_to_vertex_indices.append((cell['xcol'], cell['yrow'], indices))
                else:
                    cell_to_vertex_indices.append(None)

            # For each time step, extract all values in one go
            for t_idx, tv in enumerate(time_vals):
                for i, mapping in enumerate(cell_to_vertex_indices):
                    if mapping is not None:
                        xcol, yrow, indices = mapping
                        vals = []
                        for la_idx, lo_idx in indices:
                            val = data.values[t_idx, la_idx, lo_idx]
                            if not np.isnan(val):
                                vals.append(float(val))
                        if len(vals) == 4:
                            avg_value = float(np.mean(vals))
                            batch.append((xcol, yrow, avg_value, np.datetime_as_string(tv, unit='D')))
                            if len(batch) >= batch_size:
                                batch_insert(cursor, layer_name, batch)
                                batch = []
                    # Progress update
                    progress_count += 1
                    percent = (progress_count / total_iterations) * 100
                    if percent - last_percent >= 0.1 or progress_count == total_iterations:
                        elapsed = time_module.time() - start_time
                        if percent > 0:
                            estimated_total = elapsed / (percent / 100)
                            remaining = estimated_total - elapsed
                        else:
                            remaining = 0
                        print(f"Processed {progress_count}/{total_iterations} cell-times... ({percent:.1f}%) "
                              f"Elapsed: {format_hms(elapsed)}, Remaining: {format_hms(remaining)}")
                        last_percent = percent
                if batch:
                    batch_insert(cursor, layer_name, batch)
                    batch = []

        conn.commit()
        cursor.close()
        print("All data inserted successfully.")

    except Exception as e:
        print(f"Database or processing error: {e}", file=sys.stderr)
        conn.rollback()
        if 'cursor' in locals():
            cursor.close()

####################################################################################
# MAIN
####################################################################################
def main():
    parser = argparse.ArgumentParser(description="Process NetCDF layer ingestion parameters.")
    parser.add_argument('--nc_file', required=True, help="Path to NetCDF file")
    parser.add_argument('--layer_name', required=True, help="Layer name")
    parser.add_argument('--value_dim', required=True, help="Value dimension name")
    parser.add_argument('--time_dim', default='valid_time', help="Time dimension name (default: 'valid_time')")
    parser.add_argument('--lon_dim', default='longitude', help="Longitude dimension name (default: 'longitude')")
    parser.add_argument('--lat_dim', default='latitude', help="Latitude dimension name (default: 'latitude')")
    args = parser.parse_args()

    try:
        conn = psycopg2.connect(**dict(config.items('database')))
        read_nc_file(conn, args.nc_file, args.layer_name, args.value_dim, args.time_dim, args.lon_dim, args.lat_dim)
        conn.close()
    except Exception as e:
        print(f"Could not connect to database: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    import time as time_module  # Avoid shadowing 'time' variable from NetCDF
    main()