"""Explainable educational baselines. No function uses future measurements.

These functions return proxy/measurement states, never an operational safety verdict.
Times are seconds; temperatures Celsius; displacement mm; angular rates rad/s.
"""
from __future__ import annotations

import math
import numpy as np


def validate_time(time):
    t = np.asarray(time, dtype=float)
    if t.ndim != 1 or not len(t) or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError('Time must be finite, nonempty and strictly increasing')
    return t


def trailing_slope(time, values, window, max_gap):
    """OLS on a past-only complete window. Missing data stays unknown."""
    t = validate_time(time)
    y = np.asarray(values, dtype=float)
    if y.shape != t.shape:
        raise ValueError('Time/value lengths differ')
    out = np.full(len(t), np.nan)
    for i in range(len(t)):
        # Include the last observation at/before the window boundary. This also
        # covers slightly irregular clocks without pretending a short warmup is full.
        start = max(0, np.searchsorted(t, t[i] - window, side='right') - 1)
        tx, yy = t[start:i + 1], y[start:i + 1]
        if len(tx) < 3 or tx[-1] - tx[0] < window - 1e-8:
            continue
        if not np.isfinite(yy).all() or np.max(np.diff(tx)) > max_gap:
            continue
        x = tx - tx.mean()
        out[i] = float(np.dot(x, yy - yy.mean()) / np.dot(x, x))
    return out


def flashover_proxy(time, temperature, window=60., horizon=60., threshold=600.):
    """Forecast upper-layer temperature criterion, NOT observed flashover labels."""
    t = validate_time(time)
    y = np.asarray(temperature, dtype=float)
    slope = trailing_slope(t, y, window, max_gap=30.)
    predicted = y + np.maximum(slope, 0) * horizon
    states = []
    for value, forecast in zip(y, predicted):
        if not np.isfinite(value):
            states.append('unknown')
        elif value >= threshold:
            states.append('criterion')
        elif not np.isfinite(forecast):
            states.append('unknown')
        elif forecast >= threshold:
            states.append('watch')
        else:
            states.append('below')
    return dict(slope_c_s=slope, predicted_c=predicted, state=states)


def structural_limits(time, displacement):
    """Fit once on Test 7's initial 60 s, not a certified healthy population."""
    t = validate_time(time)
    d = np.asarray(displacement, float)
    mask = t - t[0] <= 60
    if t[-1] - t[0] < 60 or not np.isfinite(d[mask]).all():
        raise ValueError('A complete initial reference interval is required')
    rates = np.abs(trailing_slope(t[mask], d[mask], 20, 3) * 60)
    rates = rates[np.isfinite(rates)]
    def robust(v, floor):
        median = np.median(v)
        return float(max(floor, median + 6 * 1.4826 * np.median(np.abs(v - median))))
    return dict(displacement_mm=robust(np.abs(d[mask] - d[0]), 3.),
                rate_mm_min=robust(rates, .5), reference_s=60, persistence_s=5,
                source='Test7 initial 0–60 s; median + 6 × 1.4826 × MAD; design floors 3 mm, 0.5 mm/min')


def structural_anomaly(time, displacement, limits):
    t = validate_time(time)
    d = np.asarray(displacement, float)
    if d.shape != t.shape:
        raise ValueError('Time/value lengths differ')
    rate = trailing_slope(t, d, 20, 3) * 60
    delta = d - d[0]
    states, since, latched = [], None, False
    for i in range(len(t)):
        if not np.isfinite(delta[i]) or not np.isfinite(rate[i]) or t[i] - t[0] < 60:
            states.append('unknown'); since = None; continue
        large = abs(delta[i]) >= limits['displacement_mm']
        fast = abs(rate[i]) >= limits['rate_mm_min']
        if large and fast:
            since = t[i] if since is None else since
            latched = latched or t[i] - since >= limits['persistence_s']
        else:
            since = None
        states.append('anomaly' if latched else 'watch' if large or fast else 'below')
    return dict(displacement_mm=delta, rate_mm_min=rate, state=states)


def pdr(time, acceleration, gyro_z, step_length=.7, static_s=40.):
    """Level handheld baseline: causal norm peaks + bias-corrected yaw integration.

    Coordinates are initially arbitrary N/E. A separate, explicit initial heading
    calibration may rotate these coordinates; reference paths never enter this function.
    """
    t = validate_time(time)
    a, g = np.asarray(acceleration, float), np.asarray(gyro_z, float)
    if a.shape != (len(t), 3) or g.shape != t.shape or not np.isfinite(a).all() or not np.isfinite(g).all():
        raise ValueError('Complete synchronized IMU measurements required')
    if not 0 < step_length <= 2 or t[-1] - t[0] <= static_s:
        raise ValueError('Invalid stride configuration or missing initial static period')
    reference = t - t[0] < 30
    bias = float(np.mean(g[reference]))
    gravity = float(np.mean(np.linalg.norm(a[reference], axis=1)))
    heading, filtered, last_step = 0., 0., -float('inf')
    xy = np.zeros((len(t), 2)); yaw = np.zeros(len(t)); steps = []
    history = []
    for i in range(1, len(t)):
        dt = t[i] - t[i - 1]
        if dt > .1:
            raise ValueError('IMU gap > 100 ms; reacquire reference before PDR')
        xy[i] = xy[i - 1]
        if t[i] - t[0] < static_s:
            continue  # Initial static phase is calibration, not an online estimate.
        heading -= (g[i] - bias) * dt
        yaw[i] = heading
        filtered += dt / (.08 + dt) * (float(np.linalg.norm(a[i])) - gravity - filtered)
        history.append(filtered)
        if len(history) >= 3 and history[-2] > 1.0 and history[-3] < history[-2] >= history[-1] and t[i] - last_step >= .28:
            xy[i] += step_length * np.array([math.cos(heading), math.sin(heading)])
            last_step = t[i]; steps.append(i)
    return dict(xy=xy, yaw=yaw, steps=np.asarray(steps, int), gyro_bias=bias)


def trilaterate(anchors, ranges):
    """2D range least squares for a future UWB prototype; not measured field data."""
    a, r = np.asarray(anchors, float), np.asarray(ranges, float)
    if a.ndim != 2 or a.shape[1] != 2 or len(a) < 3 or r.shape != (len(a),):
        raise ValueError('At least three 2D anchors and matching ranges required')
    if not np.isfinite(a).all() or not np.isfinite(r).all() or np.any(r <= 0):
        raise ValueError('Invalid anchors/ranges')
    matrix = 2 * (a[1:] - a[0])
    if np.linalg.matrix_rank(matrix) < 2 or np.linalg.cond(matrix) > 100:
        raise ValueError('Anchor geometry is degenerate')
    rhs = r[0] ** 2 - r[1:] ** 2 + np.sum(a[1:] ** 2, axis=1) - np.sum(a[0] ** 2)
    xy = np.linalg.lstsq(matrix, rhs, rcond=None)[0]
    residual = float(np.sqrt(np.mean((np.linalg.norm(a - xy, axis=1) - r) ** 2)))
    return dict(x=float(xy[0]), y=float(xy[1]), residual_m=residual)
