import os
import osmium
import json
import fiona
from shapely.geometry import LineString, box
from shapely.ops import transform, unary_union
import shapely.wkb as wkblib
from pyproj import Proj, CRS, Transformer
import rasterio
import logging
from rasterio.transform import from_bounds, rowcol
from rasterio.windows import Window
import argparse
from functools import singledispatch

from numpy import array, sum, zeros, float32, float64
from config import LOG_LEVEL, LOG_FORMAT, LOG_DIR

logging.getLogger().setLevel(LOG_LEVEL)
logger = logging.getLogger("assign_raster_to_osm_elements")
log_formatter = logging.Formatter(fmt=LOG_FORMAT)

# Add stream handler
stream_handler = logging.StreamHandler()
stream_handler.setLevel(LOG_LEVEL)
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

#raster_filename = "features.tif"
#features = ["depth", "velocity"]
#scenarios = ["20", "100", "1000"]
search_tags = {"highway": {"motorway", "trunk", "primary", "secondary", "tertiary", "motorway_link", "trunk_link",
                           "primary_link", "secondary_link", "tertiary_link"}}
# To run:
#python assign_raster_to_osm_elements.py "$DATADIR/floodmaps/features.vrt" "$DATADIR/osm_extracts/portugal-latest.osm.pbf" 
# "$GENERATED/assigned.json" --zero_contour "$DATADIR/floodmaps/zero_contour.shp"

# Transform to readable json.
#  cat assigned_osm.json | python -m json.tool > pretty_assigned_osm.json

# Global factory that creates WKB from osmium geometry
wkbfab = osmium.geom.WKBFactory()


def main():
    description_str = """
    Loads open street map data from pbf (protobuff file, PBF_OSM_FILE) using osmium.
    Filtering on tags and bounding boxes created from zero_contour.shp. The raster is then evaluated at
    Each OSM element coordinate. Further distance between points are computed. Before writing element to file
    a second filtering is done by checking that the segment is indeed inundated (checking that the sum of first band
    in raster_files is nonzero). Finally all inundated elements are written to geojson assigned_osm.json.
    TODO: It would increase speed to filter pbf file by bounding boxes before application.
    """
    parser = argparse.ArgumentParser(description=description_str)
    parser.add_argument('raster_file', type=str,
                        help='Raster file. Expect band description to be set.')
    parser.add_argument('pbf_osm_file', type=str,
                        help='pbf file containing extract of open street map.')
    parser.add_argument('out_file', type=str,
                        help='Name of output file (type json).')
    parser.add_argument('--zero_contour', type=str,
                        help='Contour of the raster as shapefile. Check intersection with bounding box to filter osm file.')
    args = parser.parse_args()

    if args.zero_contour:
        print("zero_contour: {}".format(args.zero_contour))
    load_from_pbf_file(args)


def load_from_pbf_file(args):

    # os.chdir(os.path.join(FLOOD_MAPS_DIR, scenario))
    if not os.path.exists(LOG_DIR):
        os.mkdir(LOG_DIR)

    # Add new file handler to logger.
    file_handler = logging.FileHandler(filename=os.path.join(LOG_DIR,"assign_raster_to_osm_elements-log.txt"))
    # log_formatter = logging.Formatter(fmt=LOG_FORMAT)
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(LOG_LEVEL)
    logger.addHandler(file_handler)

    # Starts filter
    h = WayHandler(args)
    # osm_file = os.path.join(OSM_DATA_DIR, PBF_OSM_FILE)
    logger.info("Applies WayHandler to {}".format(args.pbf_osm_file))
    logger.info("Raster is: {}".format(args.raster_file))
    h.apply_file(args.pbf_osm_file, locations=True, idx='flex_mem')

    # Note down some stats.
    logger.info(f"Total length of selected elements: {h.total_length}.")
    logger.info(f"Nr of selected elements: {h.nr_of_flooded_elements}.")
    logger.info(f"Nr of filtered elements: {h.nr_of_filtered_elements}.")

    with open(args.out_file, 'w') as outfile:
        logger.info("Writes to geojson file {}.".format(args.out_file))
        json.dump(h.flooded_elements, outfile, default=to_serializable)

# To enable json serialization of np.float32 arrays.
@singledispatch
def to_serializable(val):
    """Used by default."""
    return str(val)


@to_serializable.register(float32)
def ts_float32(val):
    """Used if *val* is an instance of numpy.float32."""
    return float64(val)


class WayHandler(osmium.SimpleHandler):
    def __init__(self, args):
        osmium.SimpleHandler.__init__(self)
        self.flooded_elements = {
            "type": "FeatureCollection",
            "features": [],
        }
        # self.scenario = scenario
        self.args = args
        if self.args.zero_contour:
            self.bboxes = self.get_bounding_boxes(self.args.zero_contour)

        # Load raster along with certain related properties.
        self.raster = self.load_raster()
        self.total_length = 0
        self.nr_of_flooded_elements = 0
        self.nr_of_filtered_elements = 0

    def load_raster(self):
        logger.info("Loads rasterfile: {}".format(self.args.raster_file))
        with rasterio.open(self.args.raster_file) as source:
            file = source.name  # filename
            bounds = {"west": source.bounds.left, "south": source.bounds.bottom, "east": source.bounds.right,
                      "north": source.bounds.top, "width": source.width, "height": source.height}
            rastercoords_from_lonlat = Transformer.from_proj(
                Proj('epsg:4326'),  # source coordinates (lonlat)
                Proj(source.crs),  # target coordinates
                always_xy=True  # Use easting-northing, longitude-latitude order of coordinates.
            )
            return {"file": file, "bounds": bounds, "rowcol_from_coords": from_bounds(**bounds),
                    "rastercoords_from_lonlat": rastercoords_from_lonlat.transform, "count": source.count,
                    "band_names": source.descriptions}

    def way(self, w):
        # Test if all tags evaluate to true. Could also apply "any"  to check if one is true.
        # https://wiki.openstreetmap.org/wiki/Tags
        if all([w.tags.get(key) in search_tags.get(key) for key in search_tags.keys()]):
            wkb = wkbfab.create_linestring(w)
            """
            dir(w) ->
            ['__class__', '__delattr__', '__dir__', '__doc__', '__eq__', '__format__', '__ge__', '__getattribute__',
             '__gt__', '__hash__', '__init__', '__init_subclass__', '__le__', '__lt__', '__module__', '__ne__',
             '__new__', '__reduce__', '__reduce_ex__', '__repr__', '__setattr__', '__sizeof__', '__str__',
             '__subclasshook__', 'changeset', 'deleted', 'ends_have_same_id', 'ends_have_same_location', 'id',
             'is_closed', 'nodes', 'positive_id', 'replace', 'tags', 'timestamp', 'uid', 'user', 'user_is_anonymous',
             'version', 'visible']
            """
            structure_shape_lonlat = wkblib.loads(wkb, hex=True)
            if not self.args.zero_contour or structure_shape_lonlat.intersects(self.bboxes):
                structure_shape = transform(self.raster["rastercoords_from_lonlat"], structure_shape_lonlat)
                structure_raster_values = self.get_raster_values(structure_shape, w.id)
                if abs(structure_raster_values).sum() > 0:
                    # some raster values are nonzero at some part of the segment!
                    structure_record = {
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": structure_shape_lonlat.coords[:]
                        },
                        "properties": {
                          "id": w.id,
                          "highway": w.tags.get("highway"),
                          "bridge": w.tags.get("bridge"),
                          "lanes": w.tags.get("lanes"),
                          "tunnel": w.tags.get("tunnel"),
                          "spatial_fields": {self.raster["band_names"][band_nr]: list(structure_raster_values[band_nr])
                                            for band_nr in range(self.raster["count"])},
                          "deltas": list(self.calculate_delta(structure_shape))
                        }
                    }
                    self.flooded_elements["features"].append(structure_record)
                    self.total_length += structure_shape.length
                    self.nr_of_flooded_elements += 1
            self.nr_of_filtered_elements += 1

    def get_raster_values(self, structure_shape, id):
        rows, cols = rowcol(self.raster["rowcol_from_coords"], *zip(*structure_shape.coords[:]))
        with rasterio.open(self.raster["file"]) as dataset:
            col_off, row_off = min(cols), min(rows)
            width, height = max(cols)-col_off+1, max(rows)-row_off+1
            win = dataset.read(window=Window(col_off,row_off,width,height))
            win[win < 0] = 0. # NB!!! Replacing negative values with zero!
            win_rows = [row - row_off for row in rows]
            win_cols = [col - col_off for col in cols]
            try:
                return win[:, win_rows, win_cols]
            except IndexError as error:
                logger.warning("{} - OSM Segment is outside of raster bounds. Unable to assign raster value to "
                                "entire segment. Filling missing values with zeros. Check segment: "
                                "https://www.openstreetmap.org/way/{}".format(error, id))
                _, height, width = win.shape
                logger.debug("win.shape: {}".format(str(win.shape)))
                logger.debug("win_rows: {}, win_cols: {}".format(win_rows, win_cols))
                # filter rows and colums contained in raster.
                contained_in_raster = [0 <= row < height and 0 <= col < width for (row, col) in zip(win_rows, win_cols)]
                logger.debug("contained_in_raster: {}".format(contained_in_raster))
                win_rows = [row for (contained, row) in zip(contained_in_raster, win_rows) if contained]
                win_cols = [col for (contained, col) in zip(contained_in_raster, win_cols) if contained]

                logger.debug("win_rows: {}, win_cols: {}".format(win_rows, win_cols))
                # append zero values outside of raster bounds.
                structure_raster_values = zeros([self.raster["count"], len(contained_in_raster)])
                for band_nr in range(self.raster["count"]):
                    structure_raster_values[band_nr][array(contained_in_raster)] = \
                        win[band_nr, win_rows, win_cols]
        return structure_raster_values

    def calculate_delta(self, line):
        # returns list of distances between points in line (shapely)
        coords = array(line.coords[:])
        return sum((coords[1:] - coords[:-1]) ** 2, axis=-1) ** 0.5

    def get_bounding_boxes(self, zero_contour_file):
        """
        Creates set of bounding boxes containing the polygons in the file zero_contour.shp
        """
        logger.info("Computes bounding boxes from flood contours file: {}".format(zero_contour_file))
        with fiona.open(zero_contour_file, 'r') as source:
            project = Transformer.from_proj(
                Proj(CRS.from_wkt(source.crs_wkt)),  # source coordinates
                Proj('epsg:4326'),  # target coordinates (lonlat)
                always_xy=True  # Use easting-northing, longitude-latitude order of coordinates.
            )
            bounding_boxes = []
            for flood_contour in source:
                flood_zero_contour = LineString(flood_contour['geometry']['coordinates'])
                bounding_boxes.append(box(*transform(project.transform, flood_zero_contour).bounds))

        return unary_union(bounding_boxes)

if __name__ == "__main__":
    main()

