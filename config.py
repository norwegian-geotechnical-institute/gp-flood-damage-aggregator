import logging
import os

# Config for Preprocessing Portugal
DATADIR = os.environ["DATADIR"]

LOG_DIR = os.path.join(os.environ["DATADIR"],'logs')
LOG_LEVEL = logging.INFO
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

COST_ROAD = {
    'motorway': [0.00142, 0.0079, 0.01019],  # M€/m
    'primary': [0.00142, 0.0079, 0.01019],
    'secondary': [0.000060, 0.00043, 0.00135],
    'tertiary': [0.000060, 0.00043, 0.00135],
    'trunk': [0.00012, 0.00061, 0.00163]
}

COST_RAIL = {
    'Railway': [0.00155, 0.0031, 0.004805]     # M€/m
}


# Used for estimating damage function.
# Dynamic for velocities > 1m/s
DAMAGE_ROAD_DYNAMIC = {
    'Cat1': [0., 0.05, 0.1],          #  <0,5 m depth
    'Cat2': [0.05, 0.1, 0.45],        #  0,5 < x <2
    'Cat3': [0.1, 0.45, 0.8]          #  >2 m depth
}

# Static for velocities < 1m/s
DAMAGE_ROAD_STATIC = {
    'Cat1': [0, .0001, .05],
    'Cat2': [.001, .01, .05],
    'Cat3': [.05, .1, .2]
}

DAMAGE_ROAD_MERGE = {
    'Cat1': [0, .001, .05],
    'Cat2': [.001, .01, .05],
    'Cat3': [.01, .1, .35]
}
