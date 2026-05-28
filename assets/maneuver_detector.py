#!/usr/bin/env python3
"""
Maneuver Detector — Detect orbital maneuvers from OEM data.

DEMO / WORK-IN-PROGRESS.
The current logic samples Keplerian elements at coarse intervals and flags
changes exceeding thresholds as candidate maneuvers. A binary search then
narrows down the maneuver epoch.

Limitations (to be addressed in future versions):
    1. Natural LEO SMA oscillations (J2) can trigger false positives at low thresholds.
       Need to incorporate expected perturbation models.
    2. dV estimation uses raw velocity differences between OEM points, which includes
       orbital velocity — NOT the propulsive delta-V. Requires state transition matrix
       or GMAT-based back-propagation.
    3. Thresholds (dSMA > 10 km, etc.) are heuristic and body-dependent.

Usage:
    python maneuver_detector.py <oem_file> [--step <N>]
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oem_reader import parse_oem, keplerian_batch


def detect_maneuver(oem_path, sample_step=500, sma_threshold=5.0, orbit_window=24):
    """
    Detect candidate maneuvers by comparing per-orbit-smoothed SMA.

    J2 (Earth oblateness) causes ~7 km SMA oscillation per orbit at LEO.
    Without orbit-period smoothing, natural oscillations are misidentified
    as maneuvers. This function smooths SMA over one orbital period before
    differencing, then flags persistent jumps above sma_threshold.

    Args:
        oem_path:       Path to OEM file
        sample_step:    Spacing between coarse samples (in data points)
        sma_threshold:  dSMA threshold in km AFTER orbit-period smoothing
        orbit_window:   Points per orbit for SMA smoothing (default 24 ≈ 90min/4min)

    Returns:
        dict with keys:
            detected:       bool
            candidates:     list of (idx_lo, idx_hi, dSMA_smoothed)
            maneuver_epoch: str or None
            dV_estimate:    float or None
    """
    data = parse_oem(oem_path)
    n = len(data["times"])

    if n < 2 * orbit_window:
        return {"detected": False, "candidates": [], "maneuver_epoch": None,
                "dV_estimate": None, "note": f"Not enough data points ({n})"}

    # Compute full-resolution SMA for per-orbit smoothing
    sma_full, _, _, _, _ = keplerian_batch(data)

    # Per-orbit smoothing: boxcar filter (one orbit window)
    # Use mode="valid" to avoid edge artifacts, then trim identical amount from both ends
    kernel = np.ones(orbit_window) / orbit_window
    sma_smoothed = np.convolve(sma_full, kernel, mode="valid")  # len = n - orbit_window + 1
    trim = orbit_window // 2
    # sma_smoothed already has valid-only convolution; further trim for safety
    sma_trimmed = sma_smoothed[trim:len(sma_smoothed) - trim]

    if len(sma_trimmed) < 2 * sample_step:
        return {"detected": False, "candidates": [], "maneuver_epoch": None,
                "dV_estimate": None, "note": f"Too few points after smoothing ({len(sma_trimmed)})"}

    # Map trimmed array indices back to original data indices:
    # sma_trimmed[i] corresponds to original index: i + trim + orbit_window//2
    offset = trim + orbit_window

    # Coarse sample the TRIMMED, SMOOTHED SMA
    n_trimmed = len(sma_trimmed)
    indices_trimmed = list(range(0, n_trimmed, sample_step))
    if len(indices_trimmed) < 2:
        return {"detected": False, "candidates": [], "maneuver_epoch": None,
                "dV_estimate": None, "note": "Coarse sampling too sparse"}

    sma_sampled = sma_trimmed[indices_trimmed]

    # Find jumps in smoothed SMA
    candidates = []
    for i in range(1, len(sma_sampled)):
        dSMA = abs(sma_sampled[i] - sma_sampled[i - 1])
        if dSMA > sma_threshold:
            # Map back to original indices: sma_trimmed[j] ⇔ original[j + offset]
            orig_lo = indices_trimmed[i - 1] + offset
            orig_hi = indices_trimmed[i] + offset
            candidates.append((orig_lo, orig_hi, dSMA))

    if not candidates:
        return {"detected": False, "candidates": [], "maneuver_epoch": None,
                "dV_estimate": None}

    # Pick the largest jump
    best = max(candidates, key=lambda c: c[2])
    lo, hi, dSMA_best = best

    # Binary search on raw SMA to pinpoint (now we know it's a real persistent shift)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        mid_states = {
            "X": np.array([data["X"][lo], data["X"][mid]]),
            "Y": np.array([data["Y"][lo], data["Y"][mid]]),
            "Z": np.array([data["Z"][lo], data["Z"][mid]]),
            "VX": np.array([data["VX"][lo], data["VX"][mid]]),
            "VY": np.array([data["VY"][lo], data["VY"][mid]]),
            "VZ": np.array([data["VZ"][lo], data["VZ"][mid]]),
        }
        sma_pair, _, _, _, _ = keplerian_batch(mid_states)
        dSMA_mid = abs(sma_pair[1] - sma_pair[0])
        if dSMA_mid > sma_threshold / 2:
            hi = mid
        else:
            lo = mid

    # Raw velocity difference (WARNING: includes orbital velocity, not propulsive dV)
    v_before = np.array([data["VX"][lo], data["VY"][lo], data["VZ"][lo]])
    v_after = np.array([data["VX"][hi], data["VY"][hi], data["VZ"][hi]])
    dv_raw = np.linalg.norm(v_after - v_before) * 1000  # m/s

    return {
        "detected": True,
        "candidates": candidates,
        "maneuver_epoch": data["times"][lo].strftime("%Y-%m-%dT%H:%M:%S"),
        "dV_estimate": dv_raw,
        "dSMA_smoothed": dSMA_best,
        "idx_range": (lo, hi),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Detect maneuvers from OEM file (demo)")
    parser.add_argument("oem", help="Path to OEM file")
    parser.add_argument("--step", "-s", type=int, default=500,
                        help="Coarse sampling step (default 500)")
    parser.add_argument("--threshold", "-t", type=float, default=5.0,
                        help="dSMA threshold in km (default 5.0, applied after orbit-period smoothing)")
    parser.add_argument("--window", "-w", type=int, default=24,
                        help="Points per orbit for SMA smoothing (default 24)")
    args = parser.parse_args()

    result = detect_maneuver(args.oem, args.step, args.threshold, args.window)

    if result["detected"]:
        print(f"Maneuver candidate at {result['maneuver_epoch']}")
        print(f"  dSMA (smoothed): {result.get('dSMA_smoothed', '?'):.2f} km")
        print(f"  dV (raw, NOT propulsive): {result['dV_estimate']:.2f} m/s")
        print(f"  Index range: {result['idx_range']}")
    else:
        note = result.get("note", "")
        print(f"No maneuver detected at current threshold ({args.threshold} km).")
        if note:
            print(f"  {note}")
        else:
            print("  Try lowering --threshold if you suspect small maneuvers.")
