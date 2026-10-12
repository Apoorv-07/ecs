import numpy as np
from preprocess.clean import hampel, resample_uniform


def test_hampel_removes_spike():
    x = np.sin(np.linspace(0, 6, 200)); x[100] = 50
    y, out = hampel(x)
    assert out[100] and abs(y[100]) < 2


def test_resample_flags_gap():
    t = np.concatenate([np.arange(0, 5, 0.1), np.arange(8, 12, 0.1)])
    X = np.random.randn(len(t), 3)
    t_u, X_u, valid = resample_uniform(t, X, fs=10, max_gap_s=1.0)
    assert not valid[(t_u > 5.5) & (t_u < 7.5)].any()
    assert valid[t_u < 4].all()
