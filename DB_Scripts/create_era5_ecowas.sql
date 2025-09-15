
CREATE TABLE grid_era5_ecowas (
    id INTEGER PRIMARY KEY,
    cell_id BIGINT UNIQUE,
    geom GEOMETRY(POLYGON, 4326)
);
CREATE INDEX idx_grid_era5_ecowas_cell_id ON grid_era5_ecowas1(cell_id);

CREATE TABLE era5_ecowas (
    id SERIAL PRIMARY KEY,
    cell_id BIGINT NOT NULL,
    value FLOAT,
    date DATE
);
CREATE INDEX idx_era5_ecowas_cell_id ON era5_ecowas(cell_id);


CREATE VIEW era5_ecowas_data_view AS
SELECT 
    grid.geom,
    era5.cell_id,
    era5.date,
    era5.value
FROM 
    era5_ecowas AS era5
JOIN 
    grid_era5_ecowas AS grid
ON 
    era5.cell_id = grid.cell_id;
