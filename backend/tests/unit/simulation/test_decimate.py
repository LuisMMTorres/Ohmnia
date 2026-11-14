import numpy as np

from circuitos.simulation.post.decimate import minmax_decimate


def test_decimation_keeps_peaks_and_ends():
    x = np.linspace(0, 1, 100_001)
    y = np.sin(2 * np.pi * 50 * x)
    y[12345] = 10.0  # isolated spike must survive
    xd, (yd,) = minmax_decimate(x, [y], 1000)
    assert xd.size <= 1002
    assert yd.max() == 10.0
    assert xd[0] == 0 and xd[-1] == 1


def test_no_decimation_when_small():
    x = np.arange(10.0)
    xd, _ys = minmax_decimate(x, [x], 100)
    assert xd is x
