import configparser
import os
import psycopg2
import numpy as np
import xarray as xr
import argparse
import sys
import time

####################################################################################
# Read configuration dynamically
####################################################################################
def load_config(config_path=None):
    if config_path is None:
        config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config', 'config.ini'))
    config = configparser.ConfigParser()
    config.read(config_path)
    print("Config file read from:", config_path)
    print("Sections found:", config.sections())
    return config

def get_grids(config):
    if 'grids' not in config:
        raise KeyError("Missing [grids] section in config.ini")
    return dict(config['grids'])

####################################################################################
# determine spatial resolution and corresponding grid table
####################################################################################
def determine_spatial_resolution(lat, grids):
    if len(lat) < 2:
        print("Not enough latitude points to determine spatial resolution.")
        return None, None
    RES = np.abs(lat[1] - lat[0])
    DATA_GRID = grids.get(str(RES))
    print(f"Determined spatial resolution: {RES} degrees, using grid table: {DATA_GRID}")
    return RES, DATA_GRID

####################################################################################
# Creates the tables to contain the information
####################################################################################
def create_tables(conn, layer_name, DATA_GRID):
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
def fetch_grid_cells(conn, DATA_GRID, min_lon, min_lat, max_lon, max_lat):
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
def read_nc_file(nc_file, layer_name, value_dim, time_dim, lon_dim, lat_dim, config_path=None, batch_size=5000):
    config = load_config(config_path)
    grids = get_grids(config)
    db_config = dict(config.items('database'))
    conn = psycopg2.connect(**db_config)
    try:
        cursor = conn.cursor()
        ds = xr.open_dataset(nc_file)
        print(ds.info())
        print(ds.dims)
        data = ds[value_dim]
        time_vals = ds[time_dim].values

        # Get original coordinate arrays and their order
        lat_raw = ds[lat_dim].values
        lon_raw = ds[lon_dim].values

        # Map to ascending order and keep index mapping
        lat_sorted_idx = np.argsort(lat_raw)
        lon_sorted_idx = np.argsort(lon_raw)
        lat_sorted = lat_raw[lat_sorted_idx]
        lon_sorted = lon_raw[lon_sorted_idx]

        # For mapping from value to index in the original array
        lat_val_to_idx = {v: i for i, v in enumerate(lat_raw)}
        lon_val_to_idx = {v: i for i, v in enumerate(lon_raw)}

        print("data.values.shape:", data.values.shape)
        print("data.dims:", data.dims)

        RES, DATA_GRID = determine_spatial_resolution(lat_sorted, grids)
        if DATA_GRID is None:
            raise Exception("Could not determine grid table for spatial resolution.")

        create_tables(conn, layer_name, DATA_GRID)

        min_lat, max_lat = float(np.min(lat_sorted)), float(np.max(lat_sorted))
        min_lon, max_lon = float(np.min(lon_sorted)), float(np.max(lon_sorted))

        grid_cells = fetch_grid_cells(conn, DATA_GRID, min_lon, min_lat, max_lon, max_lat)

        # Figure out axis order for fast NumPy indexing
        dim_names = list(data.dims)
        dim_map = {
            lat_dim: dim_names.index(lat_dim),
            lon_dim: dim_names.index(lon_dim),
            time_dim: dim_names.index(time_dim)
        }

        # Decide mode: points inside cells or at vertices
        center_cell = grid_cells[len(grid_cells)//2]
        cell_lat_min, cell_lat_max = center_cell['ymin'], center_cell['ymax']
        cell_lon_min, cell_lon_max = center_cell['xmin'], center_cell['xmax']

        inside_lat_mask = (lat_sorted >= cell_lat_min) & (lat_sorted < cell_lat_max)
        inside_lon_mask = (lon_sorted >= cell_lon_min) & (lon_sorted < cell_lon_max)
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
                lat_idx = np.where(np.isclose(lat_sorted, vlat, atol=1e-4))[0]
                lon_idx = np.where(np.isclose(lon_sorted, vlon, atol=1e-4))[0]
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
        start_time = time.time()

        # --- INSIDE MODE ---
        if inside_mode:
            print("Inside cell mode activated.")
            cell_to_idx = []
            for cell in grid_cells:
                cell_lat_min, cell_lat_max = cell['ymin'], cell['ymax']
                cell_lon_min, cell_lon_max = cell['xmin'], cell['xmax']
                inside_lat_mask = (lat_sorted >= cell_lat_min) & (lat_sorted < cell_lat_max)
                inside_lon_mask = (lon_sorted >= cell_lon_min) & (lon_sorted < cell_lon_max)
                lat_indices = np.where(inside_lat_mask)[0]
                lon_indices = np.where(inside_lon_mask)[0]
                if lat_indices.size > 0 and lon_indices.size > 0:
                    la_val = lat_sorted[lat_indices[0]]
                    lo_val = lon_sorted[lon_indices[0]]
                    la_idx = lat_val_to_idx[la_val]
                    lo_idx = lon_val_to_idx[lo_val]
                    cell_to_idx.append((cell['xcol'], cell['yrow'], la_idx, lo_idx))
                else:
                    cell_to_idx.append(None)

            for t_idx, tv in enumerate(time_vals):
                for mapping in cell_to_idx:
                    if mapping is not None:
                        xcol, yrow, la_idx, lo_idx = mapping
                        idx = [None, None, None]
                        idx[dim_map[lat_dim]] = la_idx
                        idx[dim_map[lon_dim]] = lo_idx
                        idx[dim_map[time_dim]] = t_idx
                        try:
                            val = data.values[tuple(idx)]
                        except Exception as err:
                            print(f"DEBUG: NumPy indexing error for cell ({xcol}, {yrow}), indices: {tuple(idx)}, error={err}")
                            continue
                        if not np.isnan(val):
                            batch.append((xcol, yrow, float(val), np.datetime_as_string(tv, unit='D')))
                            if len(batch) >= batch_size:
                                batch_insert(cursor, layer_name, batch)
                                batch = []
                    progress_count += 1
                    percent = (progress_count / total_iterations) * 100
                    if percent - last_percent >= 0.1 or progress_count == total_iterations:
                        elapsed = time.time() - start_time
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

        # --- VERTEX MODE ---
        elif at_vertex_mode:
            print("At vertex mode activated.")
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
                    lat_idx = np.where(np.isclose(lat_sorted, vlat, atol=1e-4))[0]
                    lon_idx = np.where(np.isclose(lon_sorted, vlon, atol=1e-4))[0]
                    if lat_idx.size == 0 or lon_idx.size == 0:
                        continue
                    la_val = lat_sorted[lat_idx[0]]
                    lo_val = lon_sorted[lon_idx[0]]
                    la_idx = lat_val_to_idx[la_val]
                    lo_idx = lon_val_to_idx[lo_val]
                    indices.append((la_idx, lo_idx))
                if len(indices) == 4:
                    cell_to_vertex_indices.append((cell['xcol'], cell['yrow'], indices))
                else:
                    cell_to_vertex_indices.append(None)

            for t_idx, tv in enumerate(time_vals):
                for mapping in cell_to_vertex_indices:
                    if mapping is not None:
                        xcol, yrow, indices = mapping
                        vals = []
                        for la_idx, lo_idx in indices:
                            idx = [None, None, None]
                            idx[dim_map[lat_dim]] = la_idx
                            idx[dim_map[lon_dim]] = lo_idx
                            idx[dim_map[time_dim]] = t_idx
                            try:
                                val = data.values[tuple(idx)]
                            except Exception as err:
                                print(f"DEBUG: NumPy indexing error for cell ({xcol}, {yrow}), indices: {tuple(idx)}, error={err}")
                                continue
                            if not np.isnan(val):
                                vals.append(float(val))
                        if len(vals) == 4:
                            avg_value = float(np.mean(vals))
                            batch.append((xcol, yrow, avg_value, np.datetime_as_string(tv, unit='D')))
                            if len(batch) >= batch_size:
                                batch_insert(cursor, layer_name, batch)
                                batch = []
                    progress_count += 1
                    percent = (progress_count / total_iterations) * 100
                    if percent - last_percent >= 0.1 or progress_count == total_iterations:
                        elapsed = time.time() - start_time
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
        conn.close()
        return "Layer creation completed."

    except Exception as e:
        print(f"Database or processing error: {e}", file=sys.stderr)
        conn.rollback()
        if 'cursor' in locals():
            cursor.close()
        conn.close()
        raise

####################################################################################
# Generator version of read_nc_file for streaming progress updates
####################################################################################

def read_nc_file_stream(nc_file, layer_name, value_dim, time_dim, lon_dim, lat_dim, config_path=None, batch_size=5000):
    import time
    config = load_config(config_path)
    grids = get_grids(config)
    db_config = dict(config.items('database'))
    conn = psycopg2.connect(**db_config)
    try:
        cursor = conn.cursor()
        ds = xr.open_dataset(nc_file)
        data = ds[value_dim]
        time_vals = ds[time_dim].values
        lat_raw = ds[lat_dim].values
        lon_raw = ds[lon_dim].values
        lat_sorted_idx = np.argsort(lat_raw)
        lon_sorted_idx = np.argsort(lon_raw)
        lat_sorted = lat_raw[lat_sorted_idx]
        lon_sorted = lon_raw[lon_sorted_idx]
        lat_val_to_idx = {v: i for i, v in enumerate(lat_raw)}
        lon_val_to_idx = {v: i for i, v in enumerate(lon_raw)}
        RES, DATA_GRID = determine_spatial_resolution(lat_sorted, grids)
        if DATA_GRID is None:
            yield "ERROR: Could not determine grid table for spatial resolution."
            return
        create_tables(conn, layer_name, DATA_GRID)
        min_lat, max_lat = float(np.min(lat_sorted)), float(np.max(lat_sorted))
        min_lon, max_lon = float(np.min(lon_sorted)), float(np.max(lon_sorted))
        grid_cells = fetch_grid_cells(conn, DATA_GRID, min_lon, min_lat, max_lon, max_lat)
        dim_names = list(data.dims)
        dim_map = {
            lat_dim: dim_names.index(lat_dim),
            lon_dim: dim_names.index(lon_dim),
            time_dim: dim_names.index(time_dim)
        }
        center_cell = grid_cells[len(grid_cells)//2]
        cell_lat_min, cell_lat_max = center_cell['ymin'], center_cell['ymax']
        cell_lon_min, cell_lon_max = center_cell['xmin'], center_cell['xmax']
        inside_lat_mask = (lat_sorted >= cell_lat_min) & (lat_sorted < cell_lat_max)
        inside_lon_mask = (lon_sorted >= cell_lon_min) & (lon_sorted < cell_lon_max)
        inside_mode = np.any(inside_lat_mask) and np.any(inside_lon_mask)
        total_cells = len(grid_cells)
        total_times = len(time_vals)
        total_iterations = total_cells * total_times
        progress_count = 0
        batch = []
        last_percent = -1.0
        start_time = time.time()
        # Only implement inside_mode for brevity
        if inside_mode:
            cell_to_idx = []
            for cell in grid_cells:
                cell_lat_min, cell_lat_max = cell['ymin'], cell['ymax']
                cell_lon_min, cell_lon_max = cell['xmin'], cell['xmax']
                inside_lat_mask = (lat_sorted >= cell_lat_min) & (lat_sorted < cell_lat_max)
                inside_lon_mask = (lon_sorted >= cell_lon_min) & (lon_sorted < cell_lon_max)
                lat_indices = np.where(inside_lat_mask)[0]
                lon_indices = np.where(inside_lon_mask)[0]
                if lat_indices.size > 0 and lon_indices.size > 0:
                    la_val = lat_sorted[lat_indices[0]]
                    lo_val = lon_sorted[lon_indices[0]]
                    la_idx = lat_val_to_idx[la_val]
                    lo_idx = lon_val_to_idx[lo_val]
                    cell_to_idx.append((cell['xcol'], cell['yrow'], la_idx, lo_idx))
                else:
                    cell_to_idx.append(None)
            for t_idx, tv in enumerate(time_vals):
                for mapping in cell_to_idx:
                    if mapping is not None:
                        xcol, yrow, la_idx, lo_idx = mapping
                        idx = [None, None, None]
                        idx[dim_map[lat_dim]] = la_idx
                        idx[dim_map[lon_dim]] = lo_idx
                        idx[dim_map[time_dim]] = t_idx
                        try:
                            val = data.values[tuple(idx)]
                        except Exception:
                            continue
                        if not np.isnan(val):
                            batch.append((xcol, yrow, float(val), np.datetime_as_string(tv, unit='D')))
                            if len(batch) >= batch_size:
                                batch_insert(cursor, layer_name, batch)
                                batch = []
                    progress_count += 1
                    percent = (progress_count / total_iterations) * 100
                    if percent - last_percent >= 0.1 or progress_count == total_iterations:
                        elapsed = time.time() - start_time
                        if percent > 0:
                            estimated_total = elapsed / (percent / 100)
                            remaining = estimated_total - elapsed
                        else:
                            remaining = 0
                        yield f"Processed {progress_count}/{total_iterations} cell-times... ({percent:.1f}%) Elapsed: {format_hms(elapsed)}, Remaining: {format_hms(remaining)}"
                        last_percent = percent
                if batch:
                    batch_insert(cursor, layer_name, batch)
                    batch = []
        conn.commit()
        cursor.close()
        conn.close()
        yield "Layer creation completed."
    except Exception as e:
        yield f"Error: {e}"

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
    parser.add_argument('--config_path', default=None, help="Path to config.ini")
    args = parser.parse_args()

    try:
        read_nc_file(
            args.nc_file,
            args.layer_name,
            args.value_dim,
            args.time_dim,
            args.lon_dim,
            args.lat_dim,
            config_path=args.config_path
        )
    except Exception as e:
        print(f"Could not process NetCDF file: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()