# Flood risk assessment of linear structures: A Gaussian Process framework.

This repository contains a complete set of scripts and notebooks applied to estimate the *Expected Annual Damage* (EAD) to roads asociated with river floods (in Portugal). The framework may be adapted to other regions and other types of hazards, if represented by some hazard intensity parameters associated with a damage function. To estimate the uncertainty associated with the EAD, the damage is modeled as a spatial random field. The spatial correlation of this random field is decisive to the uncertainty of the EAD. To this end, Gaussian Processes are used to embed the uncertainty associated with the flood damage function with a spatial correlation.

The methodology is described in the article [*Uncertainty in flood risk assessment of linear structures: Why correlation matters*](https://doi.org/10.1016/j.jhydrol.2023.130442).

## Data
All the data used for the analysis is freely available. Where to find it, and how to download it is described below.

## Damage Assessment
The following instructions may be used to rerun the analysis from *Uncertainty in flood risk assessment of linear structures: Why correlation matters*. The assessment is implemented in a series of steps.

Make sure you have a working python environment. See the below notes. Select a folder for storing all the data associated with the analysis. 
```bash
export DATADIR=/PATH/TO/FOLDER
```

### 1. Load the floodmaps.
To download and rasterize the floodmaps for Portugal use the script `load_floodmaps.py`. I.e.,
```bash
python load_floodmaps.py
```
The script is written with the purpose of loading a set of floodmaps for portugal from [sniamb](https://sniamb.apambiente.pt/).
Output folder is specified as a subfolder, named `floodmaps` of the `DATADIR`.
Before running the script ensure that you have GDAL available from the commandline.
The script calls `gdal_rasterize` to rasterize and `gdal_merge` to merge the floodmaps into a single multiband raster `feature.tif`.

### 2. Filter elements from OSM and assign floodmap features to road segments.
The script `assign_raster_to_osm_elements.py` applies [osmium](https://osmcode.org/pyosmium/) to load elements from Open Street Map. For each element raster values are assigned as features, named according to band description in the raster file. The raster is not loaded into memory. This makes the proceedure a bit slower, but enables the application of large rasters. First download the OSM extracts for the selected region from [geofabrik](https://download.geofabrik.de/)
```bash
[DATADIR]$ wget https://download.geofabrik.de/europe/portugal-latest.osm.pbf
```
Next, 
```bash
$ python assign_raster_to_osm_elements.py $DATADIR/floodmaps/merged_floodmaps/features.tif $DATADIR/portugal-latest.osm.pbf assigned.json
```
The selection of elements is hardcoded, but may easily changed. (As an improvement one may specify a filter in a json-file using similar code as the one found in the script `filtering.py`)

### 3. Generate random fields for damage sampling.
It is computationally expensive to generate random fields. To make sure that 
we don't need to sample values on entire map, but only where values are needed,
the first script generates a mask.
```bash
$ python create_intersect.py $DATADIR/assigned.json [epsg_NR] $DATADIR/coords.csv $DATADIR/intersects.tif [xres] [yres]
```
 - `assigned.json` is the geojson generated in step 2
 - `epsg_NR` is the EPSG code of the reference system assigned to `intersect.tif`. For Portugal we apply 27429.
 - `coords.csv` Filename/path to generated CSV listing all the points associated with each segment in `assigned.json`. For each point it records open street map id (id), position of the point in the segment  (coo_nr), position (x, y) and position in raster (row, col).
 - `intersect.tif` Filename/path of the generated mask.
 - `xres yres` is the spatial resolution of the generated mask.

The second script generates random fields with values at the points specified 
by mask. The spatial field is a Gaussian Process with mean zero and the 
covariance kernel
$$
k(x,y) = \exp\left(\frac{|x-y|}{\ell}\right)
$$
where $\ell$ is known as the decorrelation length and measured in meter. To generate the random fields: 

```bash
$ python gaussian-random-field.py $DATADIR/intersects.tif $DATADIR/random-fields/l-[l]/random_field.tif --add_mask N l
```
 - `intersect.tif` is the raster mask generated in previous step. Specifies which the part pf the raster for which to generate the field. Tested with Type=Byte.
 - `random_field.tif` is the generated random field. A number is appended before `.tif` so as to obtain `random_field-1.tif`.
 - `--add_mask` writes mask to each random field. This is particularily useful to display the fields in qgis.
 - `N` is the number of fields to be written. Each sample is a simple matrix multiplication, its the constuction of the matrix that takes time.
 - `l` is the decorrolation length applied in the kernel.

To merge all the random fields into a `.vrt` file, apply
```bash
[DATADIR/random-fields/l-[l]]$ gdalbuildvrt -separate -o random_fields.vrt random_field-*.tif
```

### 4. Assigning region codes.
If you want to aggregate values on a regional level, you will need to assign a region id to the features. 
First download [region codes](https://ec.europa.eu/eurostat/web/gisco/geodata/reference-data/administrative-units-statistical-units/nuts), and store them under `[DATADIR]/nuts`. These are shapefiles. Generating the raster from a shapefile may be done using `gdal_rasterize`, and filtering the the shapefile to include the regions of interest may be performed applying `filtering.py`. That is,
```bash
# filter region and add counter id.
python filter.py -c id -f nuts_filter.json $DATADIR/nuts/NUTS_RG_03M_2021_4326.shp $DATADIR/nuts/portugal_nuts.shp
# convert coordinates.
ogr2ogr -t_srs EPSG:27429 $DATADIR/nuts/portugal_nuts27429.shp $DATADIR/nuts/portugal_nuts.shp
# write regions to raster. First get extent of intersect
gdalinfo $DATADIR/intersects.tif -json | jq .cornerCoordinates
gdal_rasterize -a id -tr 100 100 -te 464852 4096019 630794 4632077 $DATADIR/nuts/portugal_nuts27429.shp $DATADIR/nuts/portugal_nuts.tif
```
Finally, having the region codes in raster format, apply the script `assign_field_from_raster.py` e.g., 
```bash
python assign_field_from_raster.py -c $DATADIR/assigned.json $DATADIR/nuts/portugal_nuts.tif $DATADIR/region-assigned.json region
```
Note: As an alternative approach to assigning region to each element in the `assigned.json` one may filter the geopandas dataframe in the notebook `estimate-damage.ipynb` instead. This is not implemented, but probably a simpler and more flexible approach.


### 5. Assign damage to elements.
The rest of the analysis is carried out in jupyter notebooks. The reason is that there are many choices along the way, and the notebooks serves as documentation on the analysis. Further, the investigation of results are easily augmented in this setting. The first part is concerned with the fitting of a damage function. This is done in `damage-function.ipynb`. Then, the final analysis is done in the notebook `estimate-damage.ipynb`.

## Notes on working environment.
The python version is set in .python-version as used by pyenv. Use the 
requirements.txt to create a local environment. Path to the environment can be 
set in venv.sh (used to activate the environment python shell). 

### Dependencies.

Make sure you have GDAL installed. To install [python bindings for gdal](https://mothergeo-py.readthedocs.io/en/latest/development/how-to/gdal-ubuntu-pkg.html#install-gdal-for-python): 
```bash
sudo apt-get install libgdal-dev
```
Next, 
```bash
export CPLUS_INCLUDE_PATH=/usr/include/gdal
export C_INCLUDE_PATH=/usr/include/gdal
```
and then 
```bash
pip install GDAL==version
```
where version can be found by `gdal-config --version`. Here is a (possibly incomplete) collection of libraries I had to install:

```bash
libsuitesparse-dev build-essential cmake libboost-dev libexpat1-dev zlib1g-dev libbz2-dev
```

## Funding
The development of the framework has received funding from the European Community’s H2020 Program MG-7-1-2017, Resilience to extreme (natural and human-made) events, under Grant Agreement number: 769255—"GIS-based infrastructure management system for optimized response to extreme events of terrestrial transport networks (SAFEWAY)".
The support is gratefully acknowledged.

## Further development.
The current framework does not estimate uncertainty with respect to the flood intensity parameters. The framework should be adapted to also consider uncertainty associated with flood maps.

Some straight OSM road segments have large distances between their spatial coordinates. A refinment step to obtain an upper bound on distance beetween segment coordinates may be implemented as part of the `assign_raster_to_osm_elements.py` script.
