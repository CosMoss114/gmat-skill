#!/usr/bin/env python3
"""
Altitude Plotter — Generate perigee/apogee altitude time series from OEM data.

Uses oem_reader.py to parse OEM files and compute Keplerian elements,
then plots altitude history with matplotlib.

Usage:
    python plot_altitude.py <oem_file> [--output <path>] [--step <N>]
"""

import sys
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

# Import sibling module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oem_reader import parse_oem, keplerian_batch


def plot_altitude(oem_path, output_path=None, subsample=1):
    """
    Generate altitude time series plot from OEM file.

    Args:
        oem_path:    Path to OEM file
        output_path: Path for output PNG (default: derived from OEM name)
        subsample:   Plot every Nth point (1 = all points)
    """
    print(f"Parsing: {oem_path}")
    data = parse_oem(oem_path)
    n = len(data["times"])
    print(f"  {n} state vectors")

    # Subsample
    idx = slice(None, None, subsample)
    times = data["times"][idx]
    X = data["X"][idx]; Y = data["Y"][idx]; Z = data["Z"][idx]
    VX = data["VX"][idx]; VY = data["VY"][idx]; VZ = data["VZ"][idx]

    print("Computing Keplerian elements (analytic)...")
    sma, ecc, inc, hp, ha = keplerian_batch(
        {"X": X, "Y": Y, "Z": Z, "VX": VX, "VY": VY, "VZ": VZ}
    )

    # Trend
    z = np.polyfit(range(len(sma)), sma, 1)
    trend_total = z[0] * len(sma)

    print(f"  Perigee: {hp.min():.1f} ~ {hp.max():.1f} km")
    print(f"  Apogee:  {ha.min():.1f} ~ {ha.max():.1f} km")
    print(f"  SMA trend: {trend_total:+.2f} km over {len(times)} points")

    # ==========================================================================
    # Plot
    # ==========================================================================
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    obj_name = data["metadata"].get("object_name", "Spacecraft")
    t0, t1 = data["times"][0], data["times"][-1]
    fig.suptitle(f"{obj_name} Orbit Evolution  ({t0.strftime('%Y-%m-%d')} ~ {t1.strftime('%Y-%m-%d')})",
                 fontsize=14, fontweight="bold")

    # Panel 1: Perigee & Apogee
    ax1 = axes[0]
    ax1.plot(times, hp, linewidth=0.5, color="#2196F3", label="Perigee")
    ax1.plot(times, ha, linewidth=0.5, color="#F44336", label="Apogee")
    ax1.fill_between(times, hp, ha, alpha=0.08, color="gray")
    ax1.set_ylabel("Altitude (km)")
    ax1.legend(loc="upper right", fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(hp.min() - 2, ha.max() + 2)

    # Panel 2: SMA with trend
    ax2 = axes[1]
    ax2.plot(times, sma, linewidth=0.6, color="#4CAF50")
    trend_line = np.poly1d(z)
    ax2.plot(times, trend_line(range(len(sma))), "--", linewidth=1.2, color="darkgreen",
             label=f"Trend: {trend_total:+.2f} km")
    ax2.set_ylabel("SMA (km)")
    ax2.legend(loc="upper right", fontsize=9)
    ax2.grid(True, alpha=0.3)

    # Panel 3: Eccentricity
    ax3 = axes[2]
    ax3.plot(times, ecc * 1000, linewidth=0.6, color="#FF9800")
    ax3.set_ylabel("ECC (x10^-3)")
    ax3.set_xlabel("Date (UTC)")
    ax3.grid(True, alpha=0.3)

    # Format x-axis
    for ax in axes:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        ax.xaxis.set_major_locator(mdates.DayLocator())

    plt.tight_layout()

    if output_path is None:
        base = os.path.splitext(os.path.basename(oem_path))[0]
        output_path = os.path.join(os.path.dirname(oem_path) or ".", f"{base}_altitude.png")

    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"\nSaved: {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Plot altitude from OEM file")
    parser.add_argument("oem", help="Path to OEM file")
    parser.add_argument("--output", "-o", default=None, help="Output PNG path")
    parser.add_argument("--step", "-s", type=int, default=1,
                        help="Subsample step (default 1 = all points)")
    args = parser.parse_args()
    plot_altitude(args.oem, args.output, args.step)
