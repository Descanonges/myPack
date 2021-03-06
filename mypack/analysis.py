"""Various convenience analysis functions."""

import math
from bisect import bisect_left

import numpy as np
import scipy.stats as stats
import scipy.ndimage as ndimage
import scipy.optimize

import regulargrid.cartesiangrid
from ._rasterize_polygon import shp_mask as rasterize

from .downscale_f import downscale


__all__ = ['rasterize']


def get_gaussian(avg=0, std=1, A=None):
    """Return Gauss function.

    Return a gaussian function:

    x -> mode * exp( -1/2 * ((x - avg)/std)**2 )
    If mode is None, the gaussian is normalized:
    mode = 1 / (std * sqrt(2*pi))

    Parameters
    ----------
    avg: float, optional
        Mean value.
    std: float, optional
        Standard deviation
    A: float, optional
        Maximum value, if None, the
        function is normalized.
    """
    if A is None:
        A = 1./(std*np.sqrt(2*np.pi))
    return lambda x: A * np.exp(-.5*((x-avg)/std)**2)


def fit_gaussian(x, y, avg=0, std=1, A=1, **kwargs):
    """Fit data against a gaussian curve."""
    def gauss(x, avg, std, A):
        g = get_gaussian(avg, std, A)
        return g(x)

    p0 = [avg, std, A]

    coef, _ = scipy.optimize.curve_fit(gauss, x, y, p0, **kwargs)

    return coef


def downsample_average(array, x_in, y_in, x_out, y_out, axes=None):
    """Down sample 2d array by average.

    Parameters
    ----------
    array: 2D Array
        Dimensions corresponding to `x_in` and `x_out`.
        If more than 2 dimensions, other axes are stacked.
    x_in, y_in: Sequence[Float]
        Coordinates of input array (higher res.).
    x_out, x_out: Sequence[Float]
        Coordinates of output array (lower res.).
    axis: List[int]
        See `do_stack`
    """
    ndim = 2
    if axes is None:
        axes = list(range(-ndim, 0))
    lastaxes = list(range(-ndim, 0))

    # Swap axes to the end
    for i in range(ndim):
        array = np.swapaxes(array, axes[i], lastaxes[i])

    # Save shape
    stackshape = array.shape[:-ndim]
    array = np.reshape(array, (-1, *array.shape[-ndim:]))

    output = downscale.downscale_average_stack(x_in, y_in, x_out, y_out, array)
    output[~np.isfinite(output)] = 0

    array = np.reshape(array, (*stackshape, *array.shape[-ndim:]))
    output = np.reshape(output, (*stackshape, *output.shape[-ndim:]))

    # Reswap axes
    for i in range(ndim):
        array = np.swapaxes(array, axes[i], lastaxes[i])
        output = np.swapaxes(output, axes[i], lastaxes[i])

    return output


def latlon2str(lat=0, lon=0, fmt='(%lat, %lon)', fmtF='.2f'):
    """Format latitude and longitude to string.

    Restrict latitude and longitude. Append N, S, E, or W as needed.
    This is does not convert to sexagesimal format.

    fmt: Format for the output. %lat and %lon are replaced by the arguments
    fmtF: Format for conversion to string. Can be string or list of string.
    """

    if not isinstance(fmtF, list):
        fmtF = [fmtF, fmtF]

    mess = "fmtF should be string or list of two strings"
    assert isinstance(fmtF, list) and len(fmtF) == 2, mess

    lat = math.fmod(lat, 90)
    lon = math.fmod(lon, 180)

    s_lat = ['S', 'N'][lat >= 0]
    s_lon = ['W', 'E'][lon >= 0]

    fmtF = ['{{:{:s}}}'.format(z) for z in fmtF]

    latlon = [abs(lat), abs(lon)]
    s_latlon = [s_lat, s_lon]

    S = [(fmtF[i]+'{:s}').format(latlon[i], s_latlon[i])
         for i in range(2)]

    fmt = fmt.replace('%lat', S[0])
    fmt = fmt.replace('%lon', S[1])

    return fmt


def check_mask(mask):
    """Check that mask[:] are all the same. Return true if that's the case."""
    for i in range(1, mask.shape[0]):
        diff = np.any(np.bitwise_xor(mask[0], mask[i]))

        if diff:
            break

    return ~diff


def get_closest(L, elt, loc='closest'):
    """Return index closest to elt in L.

    L is a ascending sorted list
    loc: 'closest' -> take closest elt
          'left' -> take closest to the left
          'right' -> take closest to the right
    If two numbers are equally close, return the smallest number.
    """

    loc_opt = ['left', 'right', 'closest']
    if loc not in loc_opt:
        raise ValueError(
            "Invalid loc type. Expected one of: %s" % loc_opt)

    pos = bisect_left(L, elt)
    if pos == 0:
        return pos
    if pos == len(L):
        return len(L)-1

    if loc == 'closest':
        if elt - L[pos-1] <= L[pos] - elt:
            return pos-1
        return pos

    if loc == 'left':
        if elt == L[pos]:
            return pos
        return pos-1

    if loc == 'right':
        return pos


def get_intersection_line(p1, a, bl, ur):
    """Catch all intercepts between a line and a box.

    line: y=a*x + b
    box: bottom left and upper right coordinates
    """

    points = set()

    # Catch left
    y = p1[1] + (bl[0]-p1[0])*a
    if bl[1] <= y <= ur[1]:
        points.add((bl[0], y))

    # Catch right
    y = p1[1] + (ur[0]-p1[0])*a
    if bl[1] <= y <= ur[1]:
        points.add((ur[0], y))

    if a != 0:
        # Catch bottom
        x = p1[0] + (bl[1]-p1[1])/a
        if bl[0] <= x <= ur[0]:
            points.add((x, bl[1]))

        # Catch top
        x = p1[0] + (ur[1]-p1[1])/a
        if bl[0] <= x <= ur[1]:
            points.add((x, ur[1]))

    if len(points) > 0:
        return points


def get_intersection_segment(p1, p2, bl, ur):
    """Find if a segment intercept with a box. Return intercept points."""

    a = (p2[1]-p1[1])/(p2[0]-p1[0])
    points = get_intersection_line(p1, a, bl, ur)
    points_ = set()
    for p in points:
        if p[0] >= p1[0] and p[0] <= p2[0] and p[1] >= p1[1] and p[1] <= p2[1]:
            points_.add(p)

    return points_


def get_zero_dichoto(sig, target=0, t1=0, t2=None):
    """Return index at which sig crosses target.

    lower end of interval,
    interval is the smallest possible with discretisation
    """
    n = len(sig)
    sigZero = [0.]*len(sig)
    for i in range(n):
        sigZero[i] = sig[i] - target

    if t2 is None:
        t2 = n-1
    ncount = 0
    while (t2 - t1 > 1) and (ncount < 10000):
        ncount += 1
        t3 = int((t2+t1)/2)
        if sigZero[t2]*sigZero[t3] >= 0:
            t2 = t3
        else:
            t1 = t3

    return t1


def nonlinspace(N, xmin=0, xmax=1, slope=2.):
    """Return unvenly space values (more values in middle)."""
    x = np.linspace(-1, 1, N)
    y = np.sinh(slope*x)
    ymin = np.sinh(slope*x[0])
    ymax = np.sinh(slope*x[-1])
    return (y-ymin)*float(xmax-xmin)/(ymax-ymin) + min


def corr(x, y):
    """Compute Pearson correlation factor between x and y.

    x and y array like
    """
    avgX = np.average(x)
    avgY = np.average(y)

    sumxy = 0
    sumx2 = 0
    sumy2 = 0

    for i in range(len(x)):
        devX = x[i] - avgX
        devY = y[i] - avgY
        sumxy += devX*devY
        sumx2 += devX**2
        sumy2 += devY**2

    return sumxy / np.sqrt(sumx2*sumy2)


def linearFit(x, y, fixedInt=False):
    """Make a least square linear regression.

    Intercept can be fixed to zero.
    """
    n = len(x)
    if n != len(y):
        raise ValueError("x and y not of same length")

    sumx = 0
    sumy = 0
    sumxy = 0
    sumx2 = 0
    sumy2 = 0

    for i in range(n):
        xi, yi = x[i], y[i]
        sumx += xi
        sumy += yi
        sumxy += xi*yi
        sumx2 += xi**2
        sumy2 += yi**2

    fix = int(not fixedInt)

    m = (n*sumxy - fix*sumx*sumy) / (n*sumx2 - fix*sumx**2)
    b = fix*(sumy*sumx2 - sumx*sumxy) / (n*sumx2 - sumx**2)

    r = (sumy2 + m**2*sumx2 + n*b**2 + 2*m*b*sumx - 2*m*sumxy - 2*b*sumy)
    r /= sumy2

    return [m, b], r


def coef_student(n, alpha):
    """Return student coefficient.

    For n samples, for an interval
    with alpha confidence (0.95 for instance)
    """
    return stats.t.ppf(alpha, n)


def do_stack(func, ndim, array, *args, axes=None, output=None, **kwargs):
    """Apply func over certain axes of array. Loop over remaining axes.

    func: function which takes args and kwargs
    ndim: the number of dimensions func works on. The remaining dimension
        in input array will be treated as stacked and looped over
    array:
    axes: axes that func should work over, default is the last ndim axes
    output: result passed to output. default to np.zeros
    args and kwargs passed to func
    """

    if axes is None:
        axes = list(range(-ndim, 0))
    lastaxes = list(range(-ndim, 0))

    # Swap axes to the end
    for i in range(ndim):
        array = np.swapaxes(array, axes[i], lastaxes[i])

    # Save shape
    stackshape = array.shape[:-ndim]

    if output is None:
        output = np.zeros(array.shape)

    # Place all stack into one dimension
    array = np.reshape(array, (-1, *array.shape[-ndim:]))
    output = np.reshape(output, (-1, *output.shape[-ndim:]))

    for i in range(array.shape[0]):
        output[i] = func(array[i], *args, **kwargs)

    array = np.reshape(array, (*stackshape, *array.shape[-ndim:]))
    output = np.reshape(output, (*stackshape, *output.shape[-ndim:]))

    # Reswap axes
    for i in range(ndim):
        array = np.swapaxes(array, axes[i], lastaxes[i])
        output = np.swapaxes(output, axes[i], lastaxes[i])

    return output


def get_cursor(x, y, pointer, t1=None, t2=None, Xaxis=False):
    """Return coordinates for a cursor pointing at a y value on a curve.

    If Xaxis, points on a x value. t1 and t2 provides guesses, in x unit !
    (wrong guess sorta work but to avoid)
    """
    if Xaxis:
        x, y = y, x

    if t1 is None:
        t1 = 0
    else:
        t1 = get_zero_dichoto(x, target=t1)

    if t2 is not None:
        t2 = get_zero_dichoto(x, target=t2)

    # Find the corresponding between which points $pointer is
    t = get_zero_dichoto(y, target=pointer, t1=t1, t2=t2)

    slope = (y[t+1]-y[t]) / (x[t+1]-x[t])

    pointerX = (pointer-y[t]) / slope + x[t]

    return pointerX


def get_circle_kernel(n):
    """Return circular kernel for convolution of size nxn."""
    kernel = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            kernel[i, j] = (i-(n-1)/2)**2 + (j-(n-1)/2)**2 <= (n/2)**2

    return kernel


def enlarge_mask(mask, n_neighbors, axes=None):
    """Enlarge a stack of boolean mask by n_neighbors."""
    N = 2*n_neighbors + 1
    kernel = get_circle_kernel(N)

    mask = do_stack(ndimage.convolve, 2, 1.*mask, kernel, axes) > 0

    return mask


def regrid(data, limits, *grid, axes=None, **kwargs):
    """Regrid data.

    For cartesian grids (equal spacing between points).
    Relies on package RegularGrid by Johannes Buchner [1].

    Parameters
    ----------
    data: Array
        N-dimensional array to regrid.
    limits: List[List[float]]
        Extent of data for each considered coordinate.
        [[xmin, xmax], [ymin, ymax], ...]
    grid: Array
        Coordinates to regrid the data to.
        Their order is specified in `axes`.
    axes: List[int]
        Axes to regrid.
        Other axes will be stacked, and looped over.
        If None, the last axes in the array will be
        selected.
    kwargs: Any
        Passed to scipy.ndimage.map_coordinates
        Defaults 'order' to 1, and 'cval' to np.nan.

    Raises
    ------
    IndexError:
        If the number of axis is wrong.

    Examples
    --------
    Lets imagine data consisting of 2D maps, one for each month.
    Lets change the spatial resolution, using nearest interpolation.
    >>> import numpy as np
    ... data = np.rand.random(12, 128, 256)
    ... limits = [[0, 1], [0, 1]]
    ...
    ... new_x = np.linspace(*extent[:2], 256)
    ... new_y = np.linspace(*extent[2:], 512)
    ... new_data = regrid(data, extent, new_x, new_y, order=0)
    >>> print(new_data.shape)
    (12, 256, 512)

    See also
    --------
    scipy.ndimage.map_coordinates
    .. [1] Python package *regulargrid* by Johannes Buchner, see
            https://pypi.python.org/pypi/regulargrid/
    """

    class CartesianGrid(regulargrid.cartesiangrid.CartesianGrid):
        """Class with call overwritten to allow kwargs."""
        def __call__(self, *coords, **kwargs):
            # transform coords into pixel values
            coords = np.asarray(coords)
            coords = [(c - lo) * (n - 1) / (hi - lo)
                      for (lo, hi), c, n in zip(self.limits,
                                                coords,
                                                self.values.shape)]

            kw = {'order': 1, 'cval': np.nan}
            kw.update(**kwargs)
            return ndimage.map_coordinates(self.values, coords, **kw)

    def func(A, limits, coords, **kwargs):
        grid = CartesianGrid(limits, A)
        return grid(*coords, **kwargs).T

    ndim = len(grid)
    if axes is None:
        axes = list(range(-ndim, 0))

    if len(limits) != ndim:
        raise ValueError("Extent not of the right shape"
                         "(%d, expected %s)" % (len(limits), ndim))

    # New shape
    shape = list(data.shape)
    for i, ax in enumerate(axes):
        shape[ax] = len(grid[i])

    regrid = np.zeros(shape)
    coords = np.meshgrid(*grid)

    regrid = do_stack(func, ndim, data, limits, coords,
                      output=regrid, axes=axes, **kwargs)

    return regrid
