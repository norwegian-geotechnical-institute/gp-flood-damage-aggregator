from numpy.random import default_rng
from numpy import median
import matplotlib.pyplot as plt
rng = default_rng()


def pert(a, b, c, size):
    rng = default_rng()
    alpha = 1 + 4*(b-a)/(c-a)
    beta = 1 + 4*(c-b)/(c-a)
    return (c-a)*rng.beta(alpha, beta, size) + a


def plot_damage(DAMAGE, samples=100000, bins=50, file_name=None):
    if len(DAMAGE.keys()) > 1:
        fig, axs = plt.subplots(1, len(DAMAGE.keys()), sharex=False)
    else:
        fig, ax = plt.subplots(1, len(DAMAGE.keys()), sharex=False)
        axs = [ax]

    for nr, (key, (a, b, c)) in enumerate(DAMAGE.items()):
        values = pert(a, b, c, samples)
        axs[nr].hist(values, bins=bins, density=True, log=False, alpha=1.)
        axs[nr].set_title(key)

    if file_name is not None:
        plt.savefig(file_name)
    plt.show()


def check_stats(DAMAGE, samples=10000):
    stats = {}
    for key, (a, b, c) in DAMAGE.items():
        stats[key] = {}
        values = pert(a, b, c, samples)
        stats[key]['samples'] = samples
        stats[key]['pop_mean'] = (a + 4*b + c)/6
        stats[key]['sample_mean'] = values.mean()
        stats[key]['pop_median'] = (a + 6*b + c)/8
        stats[key]['sample_median'] = median(values)
    return stats
