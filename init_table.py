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
def grid_from_csv(filename):
    table=filename.replace(".csv","")
    conn = psycopg2.connect(
            database="droughts",
            host="127.0.0.1",
            user="postgres",
            password="postgres",
            port="5432"
        )
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
    conn.close()

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
def insert_from_nc(table,filename,value_dim,time_dim,lon_dim,lat_dim):
    conn = psycopg2.connect(
            database="droughts",
            host="127.0.0.1",
            user="postgres",
            password="postgres",
            port="5432"
        )
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
    conn.close()