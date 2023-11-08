import numpy as np
# import matplotlib.pyplot as plt
import rasterio
from scipy import sparse
# from scipy.linalg import cholesky
from sksparse.cholmod import cholesky

import os
import logging
import argparse
from datetime import datetime

from config import LOG_LEVEL, LOG_FORMAT, LOG_DIR

# 1 where data should be sampled, 0 else.
logfile = "gaussian_random_field-log.txt"
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)

# TODO: Use sparse sample matrix to create random field..
# Samples standard normal Gaussian fields according to the below covariance kernel.

def main():
    # It is to memory consuming to generate gaussian random numbers for entire map. Values are only needed
    # where elements are flooded. See create_intersect.py
    parser = argparse.ArgumentParser()
    description_str = """
        Sampling gaussian random field values according to the input mask. Output is raster with same size as mask
        with missing values according to the mask.
    """
    parser = argparse.ArgumentParser(description=description_str)
    parser.add_argument('mask', type=str,
                        help='Boolean raster (Gtiff). True where there are flooded elements.')
    parser.add_argument('out_file', type=str,
                        help='Name of the output file. Will be prefixed by number according to the sample.')
    parser.add_argument('samples', type=int,
                        help='Number of samples generated')
    parser.add_argument('l', type=float,
                        help="Decorrelation length.")
    parser.add_argument('--add_mask', action='store_true',
                        help='Add mask to random fields')
    args = parser.parse_args()

    # Add new file handler to logger.
    file_handler = logging.FileHandler(filename=os.path.join(LOG_DIR, logfile))
    log_formatter = logging.Formatter(fmt=LOG_FORMAT)
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(LOG_LEVEL)
    logging.getLogger().addHandler(file_handler)

    logging.info("Running gaussian-random-field.py")

    with rasterio.open(args.mask) as dataset:
        profile = dataset.profile.copy()
        profile["dtype"] = "float32"
        profile["sparse_ok"] = "TRUE"
        logging.info("Profile: {}".format(profile))
        mask = np.array(dataset.read(1), dtype=bool)

        x = np.linspace(dataset.bounds.left, dataset.bounds.right, dataset.shape[1], endpoint=False, dtype=np.float32)
        y = np.linspace(dataset.bounds.bottom, dataset.bounds.top, dataset.shape[0], endpoint=False, dtype=np.float32)

        sampler = GaussianSampler(x, y, ~mask, args.l)

        # write samples to raster.
        for sample_nr in range(args.samples):
            path, random_field_fname = os.path.split(args.out_file)
            with rasterio.open(os.path.join(path, random_field_fname.replace(".tif","-{}.tif".format(sample_nr+1))), 'w', **profile) as out_dataset:
                logging.info("Writing sample: {}".format(sample_nr))
                if args.add_mask:
                    out_dataset.write_mask(mask)
                sample = np.zeros(mask.shape, dtype=np.float32)
                sample[mask] = sampler.get_sample(1)
                out_dataset.write(sample,1)

    logging.info("Done.")


def test_gaussian_sampler():
    dataset_shape = (20, 20)
    size = 10

    x = np.linspace(-5, 5, dataset_shape[1], endpoint=False, dtype=np.float32)
    y = np.linspace(-5, 5, dataset_shape[0], endpoint=False, dtype=np.float32)

    mask = np.random.uniform(low=.0, high=1., size=dataset_shape) < 0.3

    gaussian_sampler = GaussianSampler(x, y, mask, 2.)
    sample = np.zeros((*dataset_shape, size))
    sample[~mask] = gaussian_sampler.get_sample(size)
    masked_sample = np.ma.array(data=sample[:, :, 0], mask=mask)
    plt.imshow(masked_sample)
    plt.colorbar()


class GaussianSampler:
    def __init__(self, x, y, mask, decorrelation_length):
        logging.debug("Create GaussianSampler")
        self.decorrelation_length = decorrelation_length
        # X, Y = np.meshgrid(x, y)
        # XX, YY = np.meshgrid(X[mask], Y[mask])
        # ZZ = self.covariance_kernel(XX - XX.T, YY - YY.T)
        # self.L = cholesky(ZZ)

        X, Y = np.meshgrid(x, y)
        XX, YY = np.meshgrid(X[~mask], Y[~mask], sparse=True)

        h_x = XX - XX.T
        h_y = YY - YY.T
        ZZ = np.exp(-np.sqrt(h_x ** 2 + h_y ** 2) / decorrelation_length)

        # Create sparse
        ZZ_csc = sparse.csc_matrix(ZZ)
        # Factorization
        factor = cholesky(ZZ_csc, ordering_method="natural")
        self.L = factor.L()

    def get_sample(self, size=1):
        theta = np.random.normal(0, 1, self.L.shape[0])
        return self.L @ theta

    def covariance_kernel(self, h_x, h_y):
        return np.exp(-np.sqrt(h_x**2 + h_y**2)/self.decorrelation_length)


if __name__ == "__main__":
    main()
