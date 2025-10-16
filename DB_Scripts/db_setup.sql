/*
    This script must be run after the initial setup of the database and PostGIS extension, and
    after the grid tables (grid_1dd, grid_05dd, grid_025dd) have been created.
    It creates indexes on the grid tables to optimize query performance.
*/
-- Indexes for grid_1dd table to optimize queries
CREATE INDEX idx_grid_1dd_xcol ON grid_1dd(xcol);
CREATE INDEX idx_grid_1dd_yrow ON grid_1dd(yrow);
CREATE INDEX idx_grid_1dd_xcol_yrow ON grid_1dd(xcol, yrow);
CREATE INDEX idx_grid_1dd_cell_geom ON grid_1dd USING GIST(cell);

-- Indexes for grid_05dd table to optimize queries
CREATE INDEX idx_grid_05dd_xcol ON grid_05dd(xcol);
CREATE INDEX idx_grid_05dd_yrow ON grid_05dd(yrow);
CREATE INDEX idx_grid_05dd_xcol_yrow ON grid_05dd(xcol, yrow);
CREATE INDEX idx_grid_05dd_cell_geom ON grid_05dd USING GIST(cell);

-- Indexes for grid_025dd table to optimize queries
CREATE INDEX idx_grid_025dd_xcol ON grid_025dd(xcol);
CREATE INDEX idx_grid_025dd_yrow ON grid_025dd(yrow);
CREATE INDEX idx_grid_025dd_xcol_yrow ON grid_025dd(xcol, yrow);
CREATE INDEX idx_grid_025dd_cell_geom ON grid_025dd USING GIST(cell);