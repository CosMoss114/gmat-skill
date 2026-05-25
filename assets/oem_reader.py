#!/usr/bin/env python3
"""
OEM Reader — Parse CCSDS OEM v2.0 files and compute Keplerian elements.

CCSDS OEM (Orbit Ephemeris Message) is a standard text format for orbit data.
This module parses OEM files and converts Cartesian state vectors to Keplerian
elements analytically — no GMAT API required.

Usage:
    from oem_reader import parse_oem, keplerian_batch

    states = parse_oem("path/to/file.oem")
    sma, ecc, inc, hp, ha = keplerian_batch(states)
"""

import numpy as np
from datetime import datetime

# Earth constants
MU_EARTH = 398600.4415   # km^3/s^2
RE_EARTH = 6378.1363     # km


def parse_oem(path):
    """
    Parse a CCSDS OEM v2.0 file.

    Args:
        path: Path to .oem or .dat file

    Returns:
        dict with keys:
            times:    list[datetime]        — epochs (UTC)
            X, Y, Z:  np.ndarray (km)      — position in REF_FRAME
            VX,VY,VZ: np.ndarray (km/s)    — velocity in REF_FRAME
            metadata: dict                 — header info (object_name, ref_frame, etc.)
    """
    times = []
    X, Y, Z = [], [], []
    VX, VY, VZ = [], [], []
    metadata = {}

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Parse metadata
            if "=" in line and not line.startswith("20"):
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                if key in ("OBJECT_NAME", "OBJECT_ID", "CENTER_NAME",
                           "REF_FRAME", "TIME_SYSTEM", "START_TIME", "STOP_TIME"):
                    metadata[key.lower()] = val
                continue

            # Parse state vectors (lines starting with epoch timestamp)
            if line.startswith("20"):
                parts = line.split()
                try:
                    dt = datetime.strptime(parts[0], "%Y-%m-%dT%H:%M:%S.%f")
                except ValueError:
                    dt = datetime.strptime(parts[0], "%Y-%m-%dT%H:%M:%S")
                times.append(dt)
                X.append(float(parts[1]))
                Y.append(float(parts[2]))
                Z.append(float(parts[3]))
                VX.append(float(parts[4]))
                VY.append(float(parts[5]))
                VZ.append(float(parts[6]))

    return {
        "times": times,
        "X": np.array(X), "Y": np.array(Y), "Z": np.array(Z),
        "VX": np.array(VX), "VY": np.array(VY), "VZ": np.array(VZ),
        "metadata": metadata,
    }


def keplerian_batch(states, mu=MU_EARTH, re=RE_EARTH):
    """
    Compute Keplerian elements from Cartesian state (vectorized).

    Args:
        states: dict from parse_oem(), or any dict with keys X,Y,Z,VX,VY,VZ
        mu:     gravitational parameter (default: Earth)
        re:     equatorial radius (default: Earth)

    Returns:
        tuple of np.ndarray:
            sma:  semi-major axis (km)
            ecc:  eccentricity
            inc:  inclination (degrees)
            hp:   perigee altitude (km)
            ha:   apogee altitude (km)
    """
    X, Y, Z = states["X"], states["Y"], states["Z"]
    VX, VY, VZ = states["VX"], states["VY"], states["VZ"]

    r_mag = np.sqrt(X**2 + Y**2 + Z**2)
    v_sq = VX**2 + VY**2 + VZ**2

    # Specific angular momentum: h = r x v
    h_x = Y * VZ - Z * VY
    h_y = Z * VX - X * VZ
    h_z = X * VY - Y * VX
    h_mag = np.sqrt(h_x**2 + h_y**2 + h_z**2)

    # SMA via vis-viva: a = -mu / (2 * (v^2/2 - mu/r))
    energy = v_sq / 2.0 - mu / r_mag
    sma = -mu / (2.0 * energy)

    # Eccentricity vector: e = (v x h)/mu - r/|r|
    e_x = (VY * h_z - VZ * h_y) / mu - X / r_mag
    e_y = (VZ * h_x - VX * h_z) / mu - Y / r_mag
    e_z = (VX * h_y - VY * h_x) / mu - Z / r_mag
    ecc = np.sqrt(e_x**2 + e_y**2 + e_z**2)

    # Inclination: cos(i) = h_z / |h|
    inc = np.degrees(np.arccos(np.clip(h_z / h_mag, -1.0, 1.0)))

    # Perigee & Apogee altitude
    rp = sma * (1.0 - ecc)
    ra = sma * (1.0 + ecc)
    hp = rp - re
    ha = ra - re

    return sma, ecc, inc, hp, ha


# ==============================================================================
# CLI
# ==============================================================================
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python oem_reader.py <oem_file>")
        sys.exit(1)

    path = sys.argv[1]
    data = parse_oem(path)
    sma, ecc, inc, hp, ha = keplerian_batch(data)

    print(f"Parsed: {len(data['times'])} state vectors")
    print(f"Metadata: {data['metadata']}")
    print(f"SMA:  {sma[0]:.2f} -> {sma[-1]:.2f} km  (trend: {sma[-1]-sma[0]:+.4f} km)")
    print(f"ECC:  {ecc[0]:.6f} -> {ecc[-1]:.6f}")
    print(f"INC:  {inc[0]:.4f}  -> {inc[-1]:.4f}  deg")
    print(f"Perigee: {hp[0]:.2f} -> {hp[-1]:.2f} km")
    print(f"Apogee:  {ha[0]:.2f} -> {ha[-1]:.2f} km")
