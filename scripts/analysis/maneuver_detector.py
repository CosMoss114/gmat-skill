#!/usr/bin/env python3
"""
Maneuver Detector — Detect orbital maneuvers from OEM data.

V0.3.0: Dual-mode detection for impulsive (chemical) and continuous (Hall/EP) thrust.

Algorithm:
    1. Bin raw SMA into 10 equal bins (~17h each, ~11 J2 cycles) to remove
       J2 oscillations (±7 km, ~92 min period).
    2. Impulsive detection: overall SMA increase > 1.0 km → chemical thruster.
    3. Continuous detection: significant slope change between first-half and
       second-half bins → Hall/EP thruster (sustained low-thrust).
    4. For detected maneuvers: binary-search epoch, estimate ΔV via vis-viva.

CSS thruster types:
    - Chemical (impulsive):  ~100-500 N, burns seconds-minutes, dSMA jump
    - Hall/EP (continuous):  ~mN-N level, burns hours-days, gradual SMA trend change

Usage:
    python maneuver_detector.py <oem_file> [--json]
"""

import sys
import os
import json
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oem_reader import parse_oem, keplerian_batch

# Earth gravitational parameter (km³/s²)
MU_EARTH = 398600.4418
EARTH_RADIUS = 6378.1363  # km


def estimate_dv_from_sma(sma_before_km, sma_after_km):
    """Estimate propulsive ΔV from SMA change (circular vis-viva approximation)."""
    v_before = np.sqrt(MU_EARTH / sma_before_km)
    v_after = np.sqrt(MU_EARTH / sma_after_km)
    return abs(v_after - v_before) * 1000  # m/s


def estimate_thrust_acceleration(dSMA_km, duration_days, sma_km):
    """
    Estimate continuous thrust acceleration from SMA change.

    For low-thrust circular orbit raising:
        da/dt ≈ (2 * a² / μ) * a_T  (tangential acceleration)
        → a_T ≈ (Δa * μ) / (2 * a² * Δt)

    Returns acceleration in m/s².
    """
    duration_s = duration_days * 86400.0
    if duration_s <= 0:
        return 0
    a_T_kms2 = (dSMA_km * MU_EARTH) / (2 * sma_km ** 2 * duration_s)
    return a_T_kms2 * 1000  # convert to m/s²


def _binary_search_epoch(sma_full, lo, hi, orbit_window, direction):
    """Binary search for the maneuver transition epoch."""
    n = len(sma_full)
    lo = max(orbit_window, min(lo, n - orbit_window - 1))
    hi = max(orbit_window + 1, min(hi, n - orbit_window))

    for _ in range(25):
        if hi - lo <= 1:
            break
        mid = (lo + hi) // 2
        w = orbit_window * 2
        before = float(np.mean(sma_full[max(0, mid - w):mid]))
        after = float(np.mean(sma_full[mid:min(n, mid + w)]))

        if direction == "raise":
            if before < after:
                hi = mid
            else:
                lo = mid
        else:
            if before > after:
                hi = mid
            else:
                lo = mid
    return lo


def detect_maneuvers(oem_path, sample_step=200, orbit_window=24, auto_threshold=True):
    """
    Detect maneuvers: both impulsive (chemical) and continuous (Hall/EP) thrust.

    Returns dict:
        detected: bool
        maneuvers: list of dicts with keys:
            type:       "impulsive" | "continuous"
            direction:  "raise" | "lower"
            epoch:      str (ISO-format maneuver epoch)
            dSMA_km:    float (SMA change attributable to maneuver)
            dV_est_ms:  float (estimated propulsive ΔV)
            sma_before_km, sma_after_km: float
            alt_before_km, alt_after_km: float
            thrust_ms2: float (continuous only, estimated acceleration)
            duration_days: float (continuous only)
            confidence: "high" | "medium" | "low"
        sma_trend_km: total SMA change over data span
        sma_noise_std_km: bin-level noise
        decay_rate_km_day: estimated natural decay rate
    """
    data = parse_oem(oem_path)
    n = len(data["times"])

    result = {
        "detected": False,
        "maneuvers": [],
        "sma_trend_km": 0,
        "sma_noise_std_km": 0,
        "decay_rate_km_day": 0,
    }

    if n < 100:
        result["_note"] = f"Not enough data ({n} pts)"
        return result

    sma_full, _, _, _, _ = keplerian_batch(data)

    # ---- 10-bin averaging (each bin ~17h, ~11 J2 cycles) ----
    n_bins = 10
    bin_size = n // n_bins
    bin_sma = np.array([float(np.mean(sma_full[i * bin_size:(i + 1) * bin_size]))
                         for i in range(n_bins)])
    bin_t = np.arange(n_bins, dtype=float)

    # Overall trend
    trend_coef = np.polyfit(bin_t, bin_sma, 1)
    sma_span_change = float(trend_coef[0] * n_bins)
    residuals = bin_sma - np.polyval(trend_coef, bin_t)
    noise_std = float(np.std(residuals))

    # Natural decay rate (km/day): bins span the full data duration
    data_duration_days = (data["times"][-1] - data["times"][0]).total_seconds() / 86400.0
    decay_rate = abs(sma_span_change) / max(data_duration_days, 0.1) if sma_span_change < 0 else 0

    result["sma_trend_km"] = round(sma_span_change, 3)
    result["sma_noise_std_km"] = round(noise_std, 3)
    result["decay_rate_km_day"] = round(decay_rate, 4)

    # =====================================================================
    # MODE 1: Impulsive (Chemical Thruster) Detection
    # =====================================================================
    # Chemical burns are short (seconds-minutes) → sharp SMA jump.
    # Detection: overall SMA INCREASE > 1.0 km over data span.
    IMPULSIVE_THRESHOLD_KM = 1.0

    if sma_span_change > IMPULSIVE_THRESHOLD_KM:
        # Find approximate jump location via max bin-to-bin difference
        bin_diffs = np.diff(bin_sma)
        jump_bin = int(np.argmax(bin_diffs))  # bin index where SMA jumped most

        # Map to original data index
        approx_idx = (jump_bin + 1) * bin_size
        lo = max(0, approx_idx - bin_size)
        hi = min(n - 1, approx_idx + bin_size)
        epoch_idx = _binary_search_epoch(sma_full, lo, hi, orbit_window, "raise")

        win = orbit_window * 4
        sma_before = float(np.mean(sma_full[max(0, epoch_idx - win):epoch_idx]))
        sma_after = float(np.mean(sma_full[epoch_idx:min(n, epoch_idx + win)]))
        dSMA = sma_after - sma_before
        dv = estimate_dv_from_sma(sma_before, sma_after)

        result["maneuvers"].append({
            "type": "impulsive",
            "direction": "raise" if dSMA > 0 else "lower",
            "epoch": data["times"][epoch_idx].strftime("%Y-%m-%dT%H:%M:%S"),
            "dSMA_km": round(dSMA, 3),
            "dV_est_ms": round(dv, 1),
            "sma_before_km": round(sma_before, 2),
            "sma_after_km": round(sma_after, 2),
            "alt_before_km": round(sma_before - EARTH_RADIUS, 2),
            "alt_after_km": round(sma_after - EARTH_RADIUS, 2),
            "sma_span_change_km": round(sma_span_change, 3),
            "confidence": "high" if sma_span_change > 3.0 else "medium",
            "idx": int(epoch_idx),
        })
        result["detected"] = True
        return result

    # =====================================================================
    # MODE 2: Continuous (Hall/EP Thruster) Detection
    # =====================================================================
    # Hall thrusters fire for hours-days → gradual SMA slope change.
    # Detection: split bins into halves, check for significant slope change
    # where second half shows less decay or slight raise vs first half.

    mid_bin = n_bins // 2
    slope_first = float(np.polyfit(bin_t[:mid_bin], bin_sma[:mid_bin], 1)[0])
    slope_second = float(np.polyfit(bin_t[mid_bin:], bin_sma[mid_bin:], 1)[0])
    slope_change = slope_second - slope_first  # positive = less decay / raising

    # Thresholds for continuous detection
    # Slope change must be significant relative to bin noise
    MIN_SLOPE_CHANGE = 0.02  # km per bin (minimum detectable)
    # Second half must NOT be strongly decaying (or must be raising)
    MAX_DECAY_SECOND_HALF = -0.03  # km per bin

    is_slope_significant = slope_change > max(MIN_SLOPE_CHANGE, 3 * noise_std / mid_bin)
    is_second_half_flat_or_raising = slope_second > MAX_DECAY_SECOND_HALF

    if is_slope_significant and is_second_half_flat_or_raising:
        # Continuous thrust detected: SMA in second half behaves differently
        # Estimate thrust start at the mid-point
        thrust_start_idx = mid_bin * bin_size
        epoch_idx = _binary_search_epoch(sma_full,
                                          max(0, thrust_start_idx - bin_size),
                                          min(n - 1, thrust_start_idx + bin_size),
                                          orbit_window, "raise")

        # SMA before thrust (first half average) vs after (second half average)
        sma_before = float(np.mean(bin_sma[:mid_bin]))
        sma_after = float(np.mean(bin_sma[mid_bin:]))

        # Estimate thrust duration
        thrust_start_time = data["times"][epoch_idx]
        thrust_end_time = data["times"][-1]
        duration_days = (thrust_end_time - thrust_start_time).total_seconds() / 86400.0

        # SMA change attributable to thrust:
        # Expected decay (if no thrust) ≈ slope_first * mid_bin
        # Actual second-half change = slope_second * mid_bin
        # Thrust contribution = actual - expected
        expected_decay = slope_first * mid_bin
        actual_change = slope_second * mid_bin
        thrust_dSMA = actual_change - expected_decay  # positive = raising relative to expected

        # Total ΔV from thrust contribution
        sma_mid = (sma_before + sma_after) / 2
        dv = estimate_dv_from_sma(sma_mid, sma_mid + thrust_dSMA)
        thrust_accel = estimate_thrust_acceleration(thrust_dSMA, duration_days, sma_mid)

        # Confidence: higher if slope_change is larger relative to noise
        z = slope_change / max(noise_std / mid_bin, 1e-6)
        confidence = "high" if z > 5 else "medium" if z > 3 else "low"

        result["maneuvers"].append({
            "type": "continuous",
            "direction": "raise" if thrust_dSMA > 0 else "station-keeping",
            "epoch": data["times"][epoch_idx].strftime("%Y-%m-%dT%H:%M:%S"),
            "dSMA_km": round(thrust_dSMA, 3),
            "dV_est_ms": round(dv, 1),
            "thrust_accel_ms2": round(thrust_accel, 6),
            "duration_days": round(duration_days, 2),
            "sma_before_km": round(sma_before, 2),
            "sma_after_km": round(sma_after, 2),
            "alt_before_km": round(sma_before - EARTH_RADIUS, 2),
            "alt_after_km": round(sma_after - EARTH_RADIUS, 2),
            "slope_first_half_km_per_bin": round(slope_first, 4),
            "slope_second_half_km_per_bin": round(slope_second, 4),
            "confidence": confidence,
            "idx": int(epoch_idx),
        })
        result["detected"] = True

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Detect orbital maneuvers (impulsive + continuous) from OEM data"
    )
    parser.add_argument("oem", help="Path to OEM file")
    parser.add_argument("--step", "-s", type=int, default=200,
                        help="Scan granularity (default 200)")
    parser.add_argument("--window", "-w", type=int, default=24,
                        help="Points per orbit for windowing (default 24)")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    args = parser.parse_args()

    result = detect_maneuvers(args.oem, args.step, args.window)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        # Human-readable output
        trend = result["sma_trend_km"]
        if trend > 1.0:
            trend_label = "▲ RAISE"
        elif trend < -0.5:
            trend_label = "▼ DECAY"
        else:
            trend_label = "— steady"
        print(f"SMA span change: {trend:+.3f} km  ({trend_label})")
        print(f"SMA bin noise (1σ): {result['sma_noise_std_km']:.3f} km")
        print(f"Est. decay rate: {result['decay_rate_km_day']:.4f} km/day")
        print()

        if result["detected"]:
            print(f"=== {len(result['maneuvers'])} MANEUVER(S) DETECTED ===\n")
            for i, m in enumerate(result["maneuvers"], 1):
                mtype = m["type"]
                if mtype == "impulsive":
                    label = "⚡ IMPULSIVE (chemical thruster)"
                else:
                    label = "🔥 CONTINUOUS (Hall/EP thruster)"
                arrow = "▲ RAISE" if m["direction"] == "raise" else "▼ LOWER"
                conf = m.get("confidence", "?")
                print(f"[{i}] {label}  {arrow}  confidence: {conf}")
                print(f"    Epoch: {m['epoch']}")
                print(f"    SMA:   {m['sma_before_km']:.2f} → {m['sma_after_km']:.2f} km  "
                      f"(Δ = {m['dSMA_km']:+.3f} km)")
                print(f"    Alt:   {m['alt_before_km']:.2f} → {m['alt_after_km']:.2f} km")
                print(f"    ΔV:    ~{m['dV_est_ms']:.1f} m/s (circular vis-viva)")
                if mtype == "continuous":
                    print(f"    Thrust accel: ~{m['thrust_accel_ms2']:.6f} m/s²")
                    print(f"    Duration:     ~{m['duration_days']:.1f} days")
                print()
        else:
            note = result.get("_note", "")
            if note:
                print(f"No maneuver detected. ({note})")
            else:
                if trend > 0:
                    print(f"No maneuver detected (SMA increase {trend:+.2f} km "
                          f"below 1.0 km impulsive threshold).")
                else:
                    print(f"No maneuver detected (SMA trend {trend:+.2f} km — "
                          f"consistent with natural decay).")
