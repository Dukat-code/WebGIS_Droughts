# This script fetches monthly weather data from the Meteostat API for a specified region
# this is not necessary for the application, so we  will not include meteostat in requirements.txt for the time being
# it is only shown here to have an initial approach to fetch and store the data integrating libraries of meteo stations

import pandas as pd
from meteostat import Stations, Monthly
from datetime import datetime
import argparse
import sys

def save_monthly_meteostat_csv(top_left, bottom_right, start_date, end_date, n_stations, csv_path):
    """
    Fetch monthly data from Meteostat for a region and save to CSV.
    Parameters:
        start_date (str): Start date in 'YYYY-MM-DD' format
        end_date (str): End date in 'YYYY-MM-DD' format
        n_stations (int): Number of stations to retrieve
        csv_path (str): Output CSV file path
    """
    # ECOWAS region bounding box
    stations = Stations().bounds(top_left, bottom_right)
    stations = stations.fetch(limit=n_stations)

    all_data = []
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    for idx, row in stations.iterrows():
        print(row)
        station_id = row['wmo']
        latitude = row['latitude']
        longitude = row['longitude']
        elevation = row['elevation']
        station_name = row['name']

        data = Monthly(station_id, start, end).fetch()
        data = data.reset_index()
        for _, d in data.iterrows():
            all_data.append({
                'latitude': latitude,
                'longitude': longitude,
                'elevation': elevation,
                'station_name': station_name,
                'year': d['time'].year,
                'month': d['time'].month,
                'tavg': d.get('tavg', None),
                'tmax': d.get('tmax', None),
                'tmin': d.get('tmin', None),
                'prcp': d.get('prcp', None)
            })

    df = pd.DataFrame(all_data)
    df.to_csv(csv_path, index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch monthly Meteostat data and save to CSV.")
    parser.add_argument('--top_left', type=str, default=(24.0, -18.0), help="top left corner of bounding box as (lat, lon)")
    parser.add_argument('--bottom_right', type=str, default=(4.0, 16.0), help="bottom right corner of bounding box as (lat, lon)")
    parser.add_argument('--start_date', type=str, default='1994-01-01', help="Start date in YYYY-MM-DD format")
    parser.add_argument('--end_date', type=str, default='2025-08-01', help="End date in YYYY-MM-DD format")
    parser.add_argument('--n_stations', type=int, default=50, help="Number of stations to retrieve")
    parser.add_argument('--csv_path', type=str, default='ecowas_stations.csv', help="Output CSV file path")

    args = parser.parse_args()

    try:
        save_monthly_meteostat_csv(
            args.top_left,
            args.bottom_right,
            args.start_date,
            args.end_date,
            args.n_stations,
            args.csv_path
        )
        print(f"CSV file saved to {args.csv_path}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)