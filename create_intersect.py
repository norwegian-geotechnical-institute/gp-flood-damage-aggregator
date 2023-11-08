import numpy as np
import rasterio
from pyproj import Proj, Transformer
from rasterio.transform import rowcol, from_bounds
import argparse
import os
import logging
import csv
import fiona
import math

from config import LOG_LEVEL, LOG_FORMAT, LOG_DIR

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)

#working_directory = os.path.join(FLOOD_MAPS_DIR, "merged_floodmaps")
#flooded_elements_file = "assigned_osm.json"
#feature_raster = "features.tif"

def main():
    description_str = """
        Creates mask from input geojson file containing flooded road segments. 
        Each pixel is set to True if it contains a coordinate of a flooded segment.
        In addition it creates a CSV, listing all the coordinates of every flooded segment.
    """
    parser = argparse.ArgumentParser(description=description_str)
    parser.add_argument('osm_file', type=str,
                        help='input geojson file with segments')
    parser.add_argument('epsg', type=int,
                        help='epsg code of output coordinates')
    parser.add_argument('out_csv', type=str,
                        help='Name of output file (type csv).')
    parser.add_argument('mask_out', type=str,
                        help='Boolean raster (Gtiff). True where there are flooded elements.')
    parser.add_argument('y_res', type=float,
                        help='pixel size northing.')
    parser.add_argument('x_res', type=float,
                        help='pixel size easting.')
    args = parser.parse_args()

    # Add new file handler to logger.
    file_handler = logging.FileHandler(filename=os.path.join(LOG_DIR,"create_intersect-log.txt"))
    log_formatter = logging.Formatter(fmt=LOG_FORMAT)
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(LOG_LEVEL)
    logging.getLogger().addHandler(file_handler)

    logging.info("Running create_intersect.py")
    logging.info("osm_file: {}".format(args.osm_file))
    logging.info("out_csv: {}".format(args.out_csv))
    logging.info("mask_out: {}".format(args.mask_out))

    rastercoords_from_lonlat = Transformer.from_proj(
        Proj('epsg:4326'),  # source coordinates (lonlat)
        Proj('epsg:{}'.format(args.epsg)),  # target coordinates
        always_xy=True  # Use easting-northing, longitude-latitude order of coordinates.
    )
    header = ["id", "coo_nr", "x", "y", "row", "col"]
    with open(args.out_csv, 'w', encoding='UTF8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)

        with fiona.open(args.osm_file, 'r') as assigned_osm:
            lon_min, lat_min, lon_max, lat_max= assigned_osm.bounds
            ((x_min, x_max), (y_min, y_max)) = rastercoords_from_lonlat.transform((lon_min, lon_max), (lat_min, lat_max))

            # Generate boolean raster of
            height, width = math.ceil((y_max-y_min)/args.y_res), math.ceil((x_max-x_min)/args.x_res)
            contains_elements = np.full((height, width), False, dtype=np.uint8)
            logging.info("Raster size: {} times {}".format(height, width))

            with rasterio.open(
                args.mask_out, 'w', driver='GTiff',
                height = contains_elements.shape[0], width = contains_elements.shape[1],
                count=1, nbits=1, dtype=contains_elements.dtype,
                crs='epsg:{}'.format(args.epsg),
                transform=from_bounds(x_min, y_min, x_max, y_max, width=width, height=height)
                ) as dataset:

                for element in assigned_osm:

                    element_id = element["properties"]["id"]
                    coords = element["geometry"]["coordinates"]
                    xs, ys = rastercoords_from_lonlat.transform(*zip(*coords))

                    rows, cols = rowcol(dataset.transform, xs, ys)
                    try:
                        contains_elements[rows, cols] = np.full(len(rows), True, dtype=np.uint8)
                    except IndexError as error:
                        logging.warning("{} - OSM Segment is outside of raster bounds.")
                        contained_in_raster = [0 <= row < dataset.shape[0] and 0 <= col < dataset.shape[1] for (row, col) in zip(rows, cols)]
                        rows = [row for (contained, row) in zip(contained_in_raster, rows) if contained]
                        cols = [col for (contained, col) in zip(contained_in_raster, cols) if contained]
                        contains_elements[rows, cols] = np.full(len(rows), True, dtype=np.uint8)

                    for coo_nr, (x, y, row, col) in enumerate(zip(xs, ys, rows, cols)):
                        writer.writerow([element_id, coo_nr, x, y, row, col])

                dataset.write(contains_elements, 1)
                logging.info("Wrote: {}".format(args.mask_out))
        logging.info("Wrote: {}. Done".format(args.out_csv))

if __name__ == "__main__":
    main()

