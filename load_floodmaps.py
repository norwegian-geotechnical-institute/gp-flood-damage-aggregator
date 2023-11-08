import subprocess
import logging
import os
from config import LOG_LEVEL, LOG_FORMAT, DATADIR
from itertools import product
# from rtree.index import Rtree
# import fiona
# from shapely.geometry import Polygon
# from shapely.ops import transform
#from pyproj import Proj, Transformer, CRS
from osgeo import gdal

FLOOD_MAPS_DIR = os.path.join(DATADIR,'floodmaps')
SCENARIOS = ["D312_APA_AI_T{}".format(ret) for ret in ["020", "100", "1000"]]

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
url = "https://sniambgeoviewer.apambiente.pt/Geodocs/shpzips"

# Get info on the shapefile
# ogrinfo -so D312_APA_AI_T020_Profundidade_PC.shp D312_APA_AI_T020_Profundidade_PC

# Convert to raster xres, yres = 100, 100
#  gdal_rasterize -a maxwc -tr 100 100 -l D312_APA_AI_T020_Profundidade_PC D312_APA_AI_T020_Profundidade_PC.shp D312_APA_AI_T020_Profundidade_PC.tif

# Merge rasters.
# gdal_merge.py -separate -o features.tif depth.tif velocity.tif


# Create contours.
# gdal_contour -a max_depth -fl 0.001 0.5 1 2 D312_APA_AI_T020_Profundidade_PC.tif flood_categories.shp

# Todo: Generate zero_contour for maximum of all flodmaps. Construct maximum depth using gdal_calc and then apply gdal
#  contour. Quickfix: use only 1000 year scenario.

def main():
    if not os.path.exists(FLOOD_MAPS_DIR):
        os.mkdir(FLOOD_MAPS_DIR)

    for scenario in SCENARIOS:
        # Create folder for storage and processing
        scenario_path = os.path.join(FLOOD_MAPS_DIR, scenario)
        if not os.path.exists(scenario_path):
           os.mkdir(scenario_path)

        # Add new file handler to logger.
        file_handler = logging.FileHandler(filename=os.path.join(scenario_path, "load_flodmaps-log.txt"))
        log_formatter = logging.Formatter(fmt=LOG_FORMAT)
        file_handler.setFormatter(log_formatter)
        file_handler.setLevel(LOG_LEVEL)
        logging.getLogger().addHandler(file_handler)

        logging.info("Created directory {}".format(scenario_path))

        load_and_preprocess(scenario)
        # create_spatial_index(scenario)

        # Remove old file handler
        logging.getLogger().removeHandler(file_handler)

    merge_floodmaps(SCENARIOS)


def merge_floodmaps(scenarios):
    merged_path = os.path.join(FLOOD_MAPS_DIR, "merged_floodmaps")
    if not os.path.exists(merged_path):
        os.mkdir(merged_path)

    # Add file handler to logger.
    file_handler = logging.FileHandler(filename=os.path.join(merged_path, "log.txt"))
    log_formatter = logging.Formatter(fmt=LOG_FORMAT)
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(LOG_LEVEL)
    logging.getLogger().addHandler(file_handler)

    logging.info("Created directory {}".format(merged_path))

    features = ["depth.tif", "velocity.tif"]
    input_files = [os.path.join(FLOOD_MAPS_DIR, scenario, feature) for scenario, feature in product(scenarios, features)]
    command = ["gdal_merge.py", "-separate", "-o", "features.tif"]
    command.extend(input_files)
    run_process(cmd=command, cwd=merged_path)

    # set band names
    ds = gdal.Open(os.path.join(merged_path, "features.tif"), gdal.GA_Update)
    for band, (scenario, feature) in enumerate(product(scenarios, features)):
        rb = ds.GetRasterBand(band+1)
        description = "{}-{}".format(feature.replace(".tif", ""), scenario)
        rb.SetDescription(description)
        logging.info("Set band: {} - {}".format(band+1, description))
    del ds

    logging.getLogger().removeHandler(file_handler)


def load_and_preprocess(scenario):
    commands = {
        "load_depth": ["wget", "{}/{}_Profundidade_PC.zip".format(url, scenario)],
        "load_velocity": ["wget", "{}/{}_Velocidade_PC.zip".format(url, scenario)],
        "unzip_depth": ["unzip", "{}_Profundidade_PC.zip".format(scenario)],
        "unzip_velocity": ["unzip", "{}_Velocidade_PC.zip".format(scenario)],
        "delete_zipped_depth": ["rm", "{}_Profundidade_PC.zip".format(scenario)],
        "delete_zipped_velocity": ["rm", "{}_Velocidade_PC.zip".format(scenario)],
        "rasterize_depth": ["gdal_rasterize", "-a", "maxwc", "-tr", "30", "30",
                      "{}_Profundidade_PC.shp".format(scenario),
                      "depth.tif"],
        "rasterize_velocity": ["gdal_rasterize", "-a", "velmaxwc", "-tr", "30", "30",
                      "{}_Velocidade_PC.shp".format(scenario),
                      "velocity.tif"],
        "create_zero_contour": ["gdal_contour", "-fl", "0.0001", "depth.tif", "zero_contour.shp"]
    }

    for key, command in commands.items():
        logging.info(command)
        run_process(command, cwd=os.path.join(FLOOD_MAPS_DIR, scenario))


def run_process(cmd, cwd):
    completed_proc = subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE
    )
    completed_proc.check_returncode()  # raise CalledProcessError if return code is non-zero.
    log_process(completed_proc)


def log_process(completed_process):
    logging.info("Process args: {}".format(" ".join(completed_process.args)))
    # If Python version > 3.7 replace with shlex.join (better formatting in logfile).
    logging.info("Process stdout: {}".format(completed_process.stdout.decode("utf-8")))


# Not used. Keep just for reference if needed.
# def create_spatial_index(scenario):
#     flood_map_contours_filename = "flood_map_contours.shp"
#     logging.info("Creating spatial index for flood map contours.")
#     # Write shapefile to spatial index.
#     # Important!!
#     os.chdir(os.path.join(FLOOD_MAPS_DIR, scenario))
#
#     flood_areas_by_class_idx = Rtree('rtree')   # Can't rename it (bug?)
#     with fiona.open(flood_map_contours_filename, "r") as source:
#         # source.schema
#         # {'properties': OrderedDict([('ID', 'int:8'), ('max_depth', 'float:12.3')]),
#         #  'geometry': 'LineString'}
#         project = Transformer.from_proj(
#             Proj(CRS.from_wkt(source.crs_wkt)),  # source coordinates
#             Proj('epsg:4326'),  # target coordinates (lonlat)
#             always_xy=True  # Use easting-northing, longitude-latitude order of coordinates.
#         )
#
#         for flood_map_contour in source:
#             # Create shapely polygon to compute bounds
#             assert flood_map_contour['geometry']['type'] in {'LineString'}, \
#                 "Feature geometry not of type LineString"
#             if len(flood_map_contour['geometry']['coordinates']) > 2:
#                 flood_map_contour_polygon = Polygon(flood_map_contour['geometry']['coordinates'])
#                 flood_map_contour_polygon_lonlat = transform(project.transform, flood_map_contour_polygon)
#
#                 # left, bottom, right, top
#                 flood_areas_by_class_idx.insert(
#                     id=int(flood_map_contour['id']), coordinates=flood_map_contour_polygon_lonlat.bounds,
#                     obj=flood_map_contour
#                 )
#         flood_areas_by_class_idx.close()


if __name__ == "__main__":
    main()

