import json
import os
import numpy as np
import logging
import rasterio
import argparse
from rasterio.transform import rowcol
from rasterio.windows import Window
from pyproj import Proj, Transformer

from config import LOG_LEVEL, LOG_FORMAT, LOG_DIR

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)

logfile = "assign_field_from_raster-log.txt"

def main():

    description_str = """
    Assigns spatial field to properties, spatial_fields from raster to geojson. If spatial field allready exists, then append values.
    """
    parser = argparse.ArgumentParser(prog="assign_field_from_raster.py",
                                     description=description_str)
    parser.add_argument('input_geojson', type=str,
                        help='geojson containing features to assign values to.')
    parser.add_argument('raster', type=str,
                        help='raster file')
    parser.add_argument('assigned_geojson', type=str,
                        help='out file')
    parser.add_argument('field_name', type=str,
                        help='Name of the assigned field.')
    parser.add_argument('-c','--categorical', action='store_true',
                        help="Raster contains cathegorical value to be assigned to each feature")
    args = parser.parse_args()

    # Add new file handler to logger.
    file_handler = logging.FileHandler(filename=os.path.join(LOG_DIR, logfile))
    log_formatter = logging.Formatter(fmt=LOG_FORMAT)
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(LOG_LEVEL)
    logging.getLogger().addHandler(file_handler)

    with open(args.input_geojson, 'r') as file:
        logging.info("Reads elements from file: {}".format(args.input_geojson))
        elements = json.load(file)

    assigned = {
        "type": "FeatureCollection",
        "features": [],
    }

    with rasterio.open(args.raster) as dataset:
        logging.info("Reads data from raster: {}".format(dataset.name))
        rastercoords_from_lonlat = Transformer.from_proj(
            Proj('epsg:4326'),  # source coordinates (lonlat)
            Proj(dataset.crs),  # target coordinates
            always_xy=True  # Use easting-northing, longitude-latitude order of coordinates.
        )
        # transforms lat-lon to raster row-col of raster
        # array = dataset.read(masked=True, out_dtype=np.float32)

        # rowcol(region_dataset.transform, -9.73363, 36.94755)
        nr_of_assigned_features = 0
        for feature in elements['features']:
            if nr_of_assigned_features%100 == 0:
                logging.info("Assigned features: {}".format(nr_of_assigned_features))

            coords = feature["geometry"]["coordinates"]
            xs, ys = rastercoords_from_lonlat.transform(*zip(*coords))
            rows, cols = rowcol(dataset.transform, xs, ys)
            # rows, cols = rowcol(dataset.transform, *zip(*coords))
            window, window_rows, window_cols = get_window(rows, cols)
            array = dataset.read(out_dtype=np.float64, window=window)

            try:
                spatial_field_list = np.round(array[:, window_rows, window_cols], 3).tolist()

            except IndexError as error:
                logging.warning("{} - OSM Segment is outside of raster bounds.")
                contained_in_raster = [0 <= row < dataset.shape[0] and 0 <= col < dataset.shape[1] for (row, col) in
                                       zip(rows, cols)]
                rows = [row for (contained, row) in zip(contained_in_raster, rows) if contained]
                cols = [col for (contained, col) in zip(contained_in_raster, cols) if contained]
                window, window_rows, window_cols = get_window(rows, cols)
                array = dataset.read(out_dtype=np.float64, window=window)

                # append zero values outside of raster bounds.
                padded_array = np.zeros([dataset.count, len(contained_in_raster)])
                padded_array[:, contained_in_raster] = array[:, window_rows, window_cols]
                spatial_field_list = np.round(padded_array, 3).tolist()

            if not args.categorical:
                if args.field_name in feature["properties"]["spatial_fields"]:
                    # Append to existing values
                    feature["properties"]["spatial_fields"][args.field_name].extend(spatial_field_list)
                else:
                    # create new property
                    feature["properties"]["spatial_fields"][args.field_name] = spatial_field_list
            else:
                # categorical value. Assign most frequent value as property.
                feature["properties"][args.field_name] = int(np.bincount(spatial_field_list[0]).argmax())
            assigned["features"].append(feature)
            nr_of_assigned_features += 1
        logging.info("Done processing features. Updated {} features".format(nr_of_assigned_features))
    with open(args.assigned_geojson, 'w') as outfile:
        json.dump(assigned, outfile)
    logging.info("Wrote to file: {}".format(args.assigned_geojson))

def get_window(rows, cols):
    # find window
    col_off = min(cols)
    row_off = min(rows)
    width = max(cols) - min(cols) + 1
    height = max(rows) - min(rows) + 1

    window_rows = [row - row_off for row in rows]
    window_cols = [col - col_off for col in cols]

    return Window(col_off, row_off, width, height), window_rows, window_cols


if __name__ == "__main__":
    main()
