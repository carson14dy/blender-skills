"""Small synthetic building solids with hand-computed answers (metres, z up)."""
import math


def gable(L=10.0, W=8.0, eave=3.0, pitch12=6.0, split=False):
    """Ridge along x. Returns faces (roof + walls)."""
    r = eave + (W / 2) * pitch12 / 12
    roofs = [[(0, 0, eave), (L, 0, eave), (L, W / 2, r), (0, W / 2, r)],
             [(L, W, eave), (0, W, eave), (0, W / 2, r), (L, W / 2, r)]]
    if split:  # cut the first plane into two coplanar pieces with a T-junction on the ridge
        roofs[0:1] = [[(0, 0, eave), (L * 0.4, 0, eave), (L * 0.4, W / 2, r), (0, W / 2, r)],
                      [(L * 0.4, 0, eave), (L, 0, eave), (L, W / 2, r), (L * 0.4, W / 2, r)]]
    walls = [[(0, 0, 0), (L, 0, 0), (L, 0, eave), (0, 0, eave)],
             [(L, W, 0), (0, W, 0), (0, W, eave), (L, W, eave)],
             [(0, W, 0), (0, 0, 0), (0, 0, eave), (0, W / 2, r), (0, W, eave)],
             [(L, 0, 0), (L, W, 0), (L, W, eave), (L, W / 2, r), (L, 0, eave)]]
    k = math.sqrt(1 + (pitch12 / 12) ** 2)
    expect = {"plan": L * W, "sloped": L * W * k, "ridge": L, "eave": 2 * L, "rake": 4 * (W / 2) * k, "hip": 0, "valley": 0}
    return roofs + walls, expect


def hip(L=12.0, W=8.0, eave=3.0, pitch12=6.0):
    p = pitch12 / 12
    r = eave + (W / 2) * p
    a, b = W / 2, L - W / 2
    roofs = [[(0, 0, eave), (L, 0, eave), (b, W / 2, r), (a, W / 2, r)],
             [(L, W, eave), (0, W, eave), (a, W / 2, r), (b, W / 2, r)],
             [(L, 0, eave), (L, W, eave), (b, W / 2, r)],
             [(0, W, eave), (0, 0, eave), (a, W / 2, r)]]
    walls = [[(0, 0, 0), (L, 0, 0), (L, 0, eave), (0, 0, eave)], [(L, 0, 0), (L, W, 0), (L, W, eave), (L, 0, eave)],
             [(L, W, 0), (0, W, 0), (0, W, eave), (L, W, eave)], [(0, W, 0), (0, 0, 0), (0, 0, eave), (0, W, eave)]]
    k = math.sqrt(1 + p * p)
    hip_len = math.sqrt(2 * (W / 2) ** 2 + ((W / 2) * p) ** 2)
    expect = {"plan": L * W, "sloped": L * W * k, "ridge": L - W, "eave": 2 * (L + W), "rake": 0, "hip": 4 * hip_len, "valley": 0}
    return roofs + walls, expect


def lean_to():
    """6 x 6 flat-roofed box, 6 m tall, with a 3 m deep shed roof against its +y wall (4 m at the wall, 3 m at the eave)."""
    roofs = [[(0, 0, 6), (6, 0, 6), (6, 6, 6), (0, 6, 6)],
             [(0, 6, 4), (6, 6, 4), (6, 9, 3), (0, 9, 3)]]
    walls = [[(0, 0, 0), (6, 0, 0), (6, 0, 6), (0, 0, 6)],
             [(6, 0, 0), (6, 6, 0), (6, 6, 6), (6, 0, 6)],
             [(0, 6, 0), (0, 0, 0), (0, 0, 6), (0, 6, 6)],
             [(0, 6, 4), (6, 6, 4), (6, 6, 6), (0, 6, 6)],      # main wall above the lean-to roof
             [(6, 9, 0), (0, 9, 0), (0, 9, 3), (6, 9, 3)],
             [(6, 6, 0), (6, 9, 0), (6, 9, 3), (6, 6, 4)],
             [(0, 9, 0), (0, 6, 0), (0, 6, 4), (0, 9, 3)]]
    expect = {"headwall": 6.0, "eave": 24.0 + 6.0, "rake": 2 * math.sqrt(10), "ridge": 0, "top": 0, "step_flashing": 0}
    return roofs + walls, expect


def butterfly(L=10.0, W=8.0, low=3.0, high=5.0):
    """Two planes draining to a level valley in the middle."""
    roofs = [[(0, 0, high), (L, 0, high), (L, W / 2, low), (0, W / 2, low)],
             [(L, W, high), (0, W, high), (0, W / 2, low), (L, W / 2, low)]]
    walls = [[(0, 0, 0), (L, 0, 0), (L, 0, high), (0, 0, high)], [(L, W, 0), (0, W, 0), (0, W, high), (L, W, high)],
             [(0, W, 0), (0, 0, 0), (0, 0, high), (0, W / 2, low), (0, W, high)],
             [(L, 0, 0), (L, W, 0), (L, W, high), (L, W / 2, low), (L, 0, high)]]
    expect = {"valley": L, "top": 2 * L, "rake": 4 * math.hypot(W / 2, high - low), "ridge": 0, "eave": 0}
    return roofs + walls, expect
