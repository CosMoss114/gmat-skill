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


def detect_maneuver(oem_path, sample_step=500, sma_threshold=10.0):
    """
    Detect candidate maneuvers by sampling and comparing Keplerian elements.

    Args:
        oem_path:       Path to OEM file
        sample_step:    Spacing between coarse samples (in data points)
        sma_threshold:  dSMA threshold in km to flag a candidate maneuver

    Returns:
        dict with keys:
            detected:       bool
            candidates:     list of (idx_lo, idx_hi, dSMA)
            maneuver_epoch: str or None (epoch of best candidate)
            dV_estimate:    float or None (raw velocity difference, NOT propulsive dV)
    """
    data = parse_oem(oem_path)
    n = len(data["times"])

    # Coarse sampling
    indices = list(range(0, n, sample_step))
    sample_states = {
        "X": data["X"][indices], "Y": data["Y"][indices], "Z": data["Z"][indices],
        "VX": data["VX"][indices], "VY": data["VY"][indices], "VZ": data["VZ"][indices],
    }
    sma, _, _, _, _ = keplerian_batch(sample_states)

    # Find jumps
    candidates = []
    for i in range(1, len(sma)):
        dSMA = abs(sma[i] - sma[i - 1])
        if dSMA > sma_threshold:
            candidates.append((indices[i - 1], indices[i], dSMA))

    if not candidates:
        return {"detected": False, "candidates": [], "maneuver_epoch": None, "dV_estimate": None}

    # Pick the largest jump
    best = max(candidates, key=lambda c: c[2])
    lo, hi, _ = best

    # Binary search to narrow down
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
        "idx_range": (lo, hi),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Detect maneuvers from OEM file (demo)")
    parser.add_argument("oem", help="Path to OEM file")
    parser.add_argument("--step", "-s", type=int, default=500,
                        help="Coarse sampling step (default 500)")
    parser.add_argument("--threshold", "-t", type=float, default=10.0,
                        help="dSMA threshold in km (default 10)")
    args = parser.parse_args()

    result = detect_maneuver(args.oem, args.step, args.threshold)

    if result["detected"]:
        print(f"Maneuver candidate at {result['maneuver_epoch']}")
        print(f"  dV (raw, NOT propulsive): {result['dV_estimate']:.2f} m/s")
        print(f"  SMA change near maneuver point: see binary search range {result['idx_range']}")
    else:
        print("No maneuver detected at current threshold.")
        print("Try lowering --threshold if you suspect small maneuvers.")
