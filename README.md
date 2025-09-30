# WebGIS_Droughts
WebGIS portable tool 

Folder structure:
- DB_Scripts --> Model SQL scripts for the GDB of the project
- Init_Scripts --> Scripts to be run to initialize data
- webApp --> Web application to be run with Flask

# ###################################################
# Init_scripts
# ###################################################

# ----------------------------------------------
# meteostat_to_csv.py
# ----------------------------------------------
This script fetches monthly weather data from the Meteostat API for weather stations within a specified bounding box (using top-left and bottom-right coordinates), date range, and number of stations. It saves the results to a CSV file with columns for latitude, longitude, elevation, station name, year, month, and climate variables (tavg, tmax, tmin, prcp).

Parameters:

--top_left: Top-left corner of bounding box as "lat,lon" (default: 24.0,-18.0)
--bottom_right: Bottom-right corner as "lat,lon" (default: 4.0,16.0)
--start_date, --end_date: Date range in YYYY-MM-DD format
--n_stations: Number of stations to retrieve
--csv_path: Output CSV file path

Parameters by default:

python meteostat_to_csv.py 
  --top_left "24.0,-18.0" 
  --bottom_right "4.0,16.0" 
  --start_date 1994-01-01 
  --end_date 2025-08-01 
  --n_stations 50 
  --csv_path ecowas_stations.csv

# ----------------------------------------------
# import_meteo_csv.py
# ----------------------------------------------
This script imports weather station data from a CSV file into the `meteostation_month_data` table in the database. If the table does not exist, it is automatically created using the SQL definition in `meteo_stations.sql`.

**Command-line parameters:**

--db_os_users: If set, uses OS user configuration for the database connection (default: not set, uses configuration from `config.ini`).

**Example usage:**

python import_meteo_csv.py --db_os_users
python import_meteo_csv.py

**Functionality:**
The script reads the CSV file (default: `ecowas_stations.csv`), maps its columns to the database schema, and inserts each record. It supports climate variables such as tavg, tmax, tmin, and prcp, and automatically creates the geometry column from latitude and longitude.

# ----------------------------------------------
# init_layer_data.py
# ----------------------------------------------
This script initializes and populates database tables and views for climate and drought layers using existing raw tables and NetCDF files. It can create grid tables, import data from NetCDF, and set up SQL views for efficient spatial and temporal queries.

**Command-line parameters:**

- `--db_os_users`: If set, uses OS user configuration for the database connection (default: not set, uses configuration from `config.ini`).

**Example usage:**

python init_layer_data.py --db_os_users
python init_layer_data.py

**Functionality:**
- Reads database configuration from `config.ini` or uses OS user connection.
- Creates necessary tables and views for the specified layer.
- Optionally creates a grid table from NetCDF data if not already present.
- Imports climate data from NetCDF files into the database.
- Supports flexible initialization for different layers and grid configurations.

**Note:**  
This is an initial version. It will be adjusted to work with the correct grids of JRC

# ----------------------------------------------
# seeding.py
# ----------------------------------------------
The script seeds (pre-generates) map tiles for a specified layer in GeoServer using a list of dates.  
It connects to the database only to retrieve available dates (if enabled), then sends seed requests to GeoServer for each date, zoom level, and format.

**Command-line parameters:**

- `--os_users`: If set, uses OS user configuration for the database connection (default: not set, uses explicit connection parameters).

**Example usage:**

python seeding.py --os_users
python seeding.py

**Functionality:**
- Connects to the database to fetch available dates (or uses a hardcoded list for testing).
- For each date, sends a seed request to GeoServer to generate map tiles for the specified layer and time.

**Note:**  
- This script is for GeoServer tile seeding, not for database data seeding.

# ----------------------------------------------
# layer_publish.py
# ----------------------------------------------
**Note:**  
This script is still not working fine, has problems enabling the features of tile caching, so for the moment the publication must be done manually from the Geoserver interface


This script automates the publication of a spatial layer to GeoServer using hardcoded configuration values. It connects to the GeoServer REST API and uploads or updates layer settings, including workspace, datastore, style, time dimension, and tile caching.

**Parameters:**

- All configuration (GeoServer URL, credentials, layer name, workspace, datastore, style, etc.) is set directly in the script.

**Usage:**

python layer_publish.py

**Functionality:**
- Publishes the specified feature type (vector layer) to GeoServer.
- Sets the default style for the layer.
- Enables the time dimension for the layer.
- Enables tile caching and sets the gridset for fast map rendering.

# ###################################################
# WebApp
# ###################################################

# ----------------------------------------------
# app.py
# ----------------------------------------------
This script runs the main Flask web application for the WebGIS Droughts project. It provides the backend for interactive drought and climate mapping, serving both the web frontend and a set of REST API endpoints.

**Usage:**

python app.py [--db_os_users]


**Command-line parameters:**

- `--db_os_users`: If set, uses OS user configuration for the database connection (default: not set, uses configuration from `config.ini`).

**Functionality:**
- Serves the interactive map and timeline for drought and climate data visualization.
- Handles requests for spatial data, time series, and statistics.
- Connects to the database to retrieve and process geospatial and climate information.
- Supports configuration via `config.ini` or OS user connection.

**Main API Endpoints:**

- `/`  
  Serves the main web interface for interactive mapping.

- `/get_time_bounds/<lat>/<lon>/<table>`  
  Returns the available time range (min/max year and month) for a given layer and location.

- `/get_data_from_lat_lon/<lat>/<lon>/<yearFrom>/<monthFrom>/<yearTo>/<monthTo>/<table>`  
  Returns climate or drought data for a given location and date range.

- `/get_feature_info/<layer>/<lat>/<lon>/<date>`  
  Returns feature information for a given layer, location, and date.

- `/get_meteostation_info/<layer>/<lat>/<lon>/<date>`  
  Returns monthly data for meteorological stations near a given location.

- `/get_product_info/<layer>`  
  Returns product information for a given layer from the products configuration.

- `/clim_chart/<layer>/<lat>/<lon>`  
  Renders a climate chart for the selected layer and location.

- `/get_metadata/<layer>`  
  Returns XML metadata for a given layer.
