import configparser
import os
import psycopg2
import numpy as np
import xarray as xr
import argparse
import sys
import time
import re

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
# Get grid table from existing view
####################################################################################
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
# Generator version of read_geotiff_file for streaming progress updates
####################################################################################
def read_geotiff_file_stream(geotiff_file, layer_name, config_path=None, batch_size=5000, add_to_table=False):
    """
    Reads a multiband GeoTIFF (with band names as dates) and stores data into the database, similar to read_nc_file_stream.
    """
    import psycopg2
    import numpy as np
    import rasterio
    from dateutil.parser import parse as parse_date

    message = f"starting to process GeoTIFF file: {geotiff_file} for layer: {layer_name}"
    print(message)
    yield message

    config = load_config(config_path)
    grids = get_grids(config)
    db_config = dict(config.items('database'))
    conn = psycopg2.connect(**db_config)
    try:
        cursor = conn.cursor()
        with rasterio.open(geotiff_file) as src:
            arr = src.read()  # (bands, height, width)
            transform = src.transform
            count = src.count
            height = src.height
            width = src.width
            # Get band descriptions as dates
            band_dates = []
            for i in range(count):
                desc = src.descriptions[i]
                try:
                    band_dates.append(str(parse_date(desc).date()))
                except Exception:
                    band_dates.append(f"band_{i+1}")
            # Build coordinates (center of each pixel)
            lon = np.array([ (transform * (x + 0.5, 0.5))[0] for x in range(width) ])
            lat = np.array([ (transform * (0.5, y + 0.5))[1] for y in range(height) ])
            lat_sorted_idx = np.argsort(lat)
            lon_sorted_idx = np.argsort(lon)
            lat_sorted = lat[lat_sorted_idx]
            lon_sorted = lon[lon_sorted_idx]
            lat_val_to_idx = {v: i for i, v in enumerate(lat)}
            lon_val_to_idx = {v: i for i, v in enumerate(lon)}

        if add_to_table:
            DATA_GRID = get_existing_grid_table(conn, layer_name)
            message = f"Using existing grid table: {DATA_GRID}"
            print(message)
            yield message
        else:
            RES, DATA_GRID = determine_spatial_resolution(lat_sorted, grids)
            if DATA_GRID is None:
                message = "ERROR: Could not determine grid table for spatial resolution."
                print(message)
                yield message
                return
            create_tables(conn, layer_name, DATA_GRID)
            message = f"Created tables and view for layer {layer_name} with grid {DATA_GRID}"
            print(message)
            yield message

        # Fetch grid cells intersecting the GeoTIFF bounding box
        min_lat, max_lat = float(np.min(lat_sorted)), float(np.max(lat_sorted))
        min_lon, max_lon = float(np.min(lon_sorted)), float(np.max(lon_sorted))
        grid_cells = fetch_grid_cells(conn, DATA_GRID, min_lon, min_lat, max_lon, max_lat)

        # Determine if points are inside cells or at vertices
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
            message = "ERROR: GeoTIFF points are neither inside cells nor at vertices."
            print(message)
            yield message
            return

        total_cells = len(grid_cells)
        total_times = count
        total_iterations = total_cells * total_times
        progress_count = 0
        batch = []
        last_percent = -1.0
        start_time = None

        # --- INSIDE MODE ---
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
            for t_idx, date_str in enumerate(band_dates):
                for mapping in cell_to_idx:
                    if mapping is not None:
                        xcol, yrow, la_idx, lo_idx = mapping
                        try:
                            val = arr[t_idx, la_idx, lo_idx]
                        except Exception:
                            continue
                        if not np.isnan(val):
                            batch.append((xcol, yrow, float(val), date_str))
                            if len(batch) >= batch_size:
                                batch_insert(cursor, layer_name, batch)
                                batch = []
                    progress_count += 1
                    percent = (progress_count / total_iterations) * 100
                    if percent - last_percent >= 0.1 or progress_count == total_iterations:
                        if start_time is None:
                            import time
                            start_time = time.time()
                        elapsed = time.time() - start_time
                        if percent > 0:
                            estimated_total = elapsed / (percent / 100)
                            remaining = estimated_total - elapsed
                        else:
                            remaining = 0
                        message = f"Processed {progress_count}/{total_iterations} cell-times... ({percent:.1f}%) Elapsed: {int(elapsed)}s, Remaining: {int(remaining)}s"
                        print(message)
                        yield message
                        last_percent = percent
                if batch:
                    batch_insert(cursor, layer_name, batch)
                    batch = []
        # --- VERTEX MODE ---
        elif at_vertex_mode:
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
            for t_idx, date_str in enumerate(band_dates):
                for mapping in cell_to_vertex_indices:
                    if mapping is not None:
                        xcol, yrow, indices = mapping
                        vals = []
                        for la_idx, lo_idx in indices:
                            try:
                                val = arr[t_idx, la_idx, lo_idx]
                            except Exception:
                                continue
                            if not np.isnan(val):
                                vals.append(float(val))
                        if len(vals) == 4:
                            avg_value = float(np.mean(vals))
                            batch.append((xcol, yrow, avg_value, date_str))
                            if len(batch) >= batch_size:
                                batch_insert(cursor, layer_name, batch)
                                batch = []
                    progress_count += 1
                    percent = (progress_count / total_iterations) * 100
                    if percent - last_percent >= 0.1 or progress_count == total_iterations:
                        if start_time is None:
                            import time
                            start_time = time.time()
                        elapsed = time.time() - start_time
                        if percent > 0:
                            estimated_total = elapsed / (percent / 100)
                            remaining = estimated_total - elapsed
                        else:
                            remaining = 0
                        message = f"Processed {progress_count}/{total_iterations} cell-times... ({percent:.1f}%) Elapsed: {int(elapsed)}s, Remaining: {int(remaining)}s"
                        print(message)
                        yield message
                        last_percent = percent
                if batch:
                    batch_insert(cursor, layer_name, batch)
                    batch = []
        conn.commit()
        cursor.close()
        conn.close()
        message = "Layer creation from GeoTIFF completed."
        print(message)
        yield message
    except Exception as e:
        message = f"Error: {e}"
        print(message)
        yield message

####################################################################################
# MAIN
####################################################################################
def main():
    parser = argparse.ArgumentParser(description="Process GeoTiff layer ingestion parameters.")
    parser.add_argument('--geotiff_file', required=True, help="Path to GeoTIFF file")
    parser.add_argument('--layer_name', required=True, help="Layer name")
    parser.add_argument('--config_path', default=None, help="Path to config.ini")
    parser.add_argument('--add_to_table', action='store_true', help="Add data to existing table (do not create table/view)")
    args = parser.parse_args()

    try:
        for msg in read_geotiff_file_stream(
            args.geotiff_file,
            args.layer_name,
            config_path=args.config_path,
            add_to_table=args.add_to_table
        ):
            print(msg)
    except Exception as e:
        print(f"Could not process GeoTIFF file: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()