CREATE SEQUENCE IF NOT EXISTS meteo_data_id_seq
START WITH 1
INCREMENT BY 1
NO MINVALUE
NO MAXVALUE
CACHE 1;

CREATE TABLE IF NOT EXISTS meteostation_month_data 
(
    id integer NOT NULL DEFAULT nextval('meteo_data_id_seq'::regclass),
    geom geometry(Point,4326),
	latitude numeric(6,2),
	longitude numeric(6,3),
	elevation numeric(6,2),
    station_name character varying(255) COLLATE pg_catalog."default",
    year integer,
    month integer,
    date date,
    tavg numeric(6,2),
    tmax numeric(6,2),
    tmin numeric(6,2),
    prcp numeric(6,2),
    CONSTRAINT meteostation_month_data_pkey PRIMARY KEY (id)
)