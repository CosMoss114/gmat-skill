#!/usr/bin/env python3
"""
Launch Window Calculator — 空间站过顶发射窗口预测

给定空间站 OEM 轨道数据和地面站（酒泉/文昌），计算发射窗口。
通过解析 Kepler 传播器前向/后向推进，在发射时刻前后搜索过顶事件。

Algorithm:
    1. 从 OEM 数据获得 Kepler 根数初值
    2. 解析 Kepler 传播 (二体) 覆盖搜索窗口
    3. 每步计算 EME2000 → ECEF → 天顶投影 → 仰角
    4. 检测连续过顶段: AOS (仰角≥10°) → 峰值 → LOS (仰角<10°)
    5. 峰值仰角 ≥80° 的过顶段标记为发射窗口

Usage:
    python launch_window.py <oem_file> [--site Jiuquan|Wenchang|JQ|WC]
                                       [--t0 "2026-05-24T23:08:36+08:00"]
                                       [--min-elevation 80]
                                       [--window-hours 4]
"""

import sys
import os
import json
import argparse
from datetime import datetime, timedelta, timezone
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oem_reader import parse_oem, keplerian_batch

# =============================================================================
# Constants
# =============================================================================
MU_EARTH = 398600.4415       # km^3/s^2
RE_EARTH = 6378.1363         # km (equatorial radius)
FLAT_EARTH = 1.0 / 298.257   # flattening
J2_EARTH = 1.0826267e-3
OMEGA_EARTH = 7.2921150e-5   # rad/s
DEG = np.pi / 180.0

# Ground station definitions
SITES = {
    "Jiuquan":  {"lat": 40.959054, "lon": 100.292301, "alt_km": 1.0,  "alias": ["JQ", "酒泉"]},
    "Wenchang": {"lat": 19.316717, "lon": 109.800042, "alt_km": 0.1,  "alias": ["WC", "文昌"]},
}

# Beijing timezone
BJT = timezone(timedelta(hours=8))


# =============================================================================
# Time & coordinate utilities
# =============================================================================

def jd_from_datetime(dt: datetime) -> float:
    """Convert UTC datetime to Julian Date."""
    import calendar as cal
    a = (14 - dt.month) // 12
    y = dt.year + 4800 - a
    m = dt.month + 12 * a - 3
    jdn = dt.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    jd = jdn + (dt.hour - 12) / 24.0 + dt.minute / 1440.0 + dt.second / 86400.0
    jd += dt.microsecond / 86400000000.0
    return jd


def gmst_degrees(jd: float) -> float:
    """Greenwich Mean Sidereal Time in degrees at given JD."""
    T = (jd - 2451545.0) / 36525.0
    gmst = 280.46061837 + 360.98564736629 * (jd - 2451545.0)
    gmst += 0.000387933 * T * T - T * T * T / 38710000.0
    return gmst % 360.0


def eme2000_to_ecef(x, y, z, jd):
    """Rotate EME2000 (J2000) vector to ECEF via GMST."""
    theta = -np.radians(gmst_degrees(jd))
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    return x * cos_t - y * sin_t, x * sin_t + y * cos_t, z


def ecef_to_latlon(x, y, z):
    """ECEF Cartesian (km) to geodetic lat/lon (deg) and altitude (km)."""
    r_xy = np.sqrt(x * x + y * y)
    lon = np.degrees(np.arctan2(y, x))
    # Iterative solution for lat
    lat = np.arctan2(z, r_xy * (1.0 - FLAT_EARTH))
    for _ in range(5):
        N = RE_EARTH / np.sqrt(1.0 - FLAT_EARTH * (2.0 - FLAT_EARTH) * np.sin(lat)**2)
        alt = r_xy / np.cos(lat) - N
        lat = np.arctan2(z, r_xy * (1.0 - FLAT_EARTH * N / (N + alt)))
    N = RE_EARTH / np.sqrt(1.0 - FLAT_EARTH * (2.0 - FLAT_EARTH) * np.sin(lat)**2)
    alt = r_xy / np.cos(lat) - N
    return np.degrees(lat), lon, alt


def station_ecef(lat_deg, lon_deg, alt_km):
    """Geodetic → ECEF Cartesian (km)."""
    lat_r = np.radians(lat_deg)
    lon_r = np.radians(lon_deg)
    sin_lat = np.sin(lat_r)
    N = RE_EARTH / np.sqrt(1.0 - FLAT_EARTH * (2.0 - FLAT_EARTH) * sin_lat * sin_lat)
    x = (N + alt_km) * np.cos(lat_r) * np.cos(lon_r)
    y = (N + alt_km) * np.cos(lat_r) * np.sin(lon_r)
    z = (N * (1.0 - FLAT_EARTH)**2 + alt_km) * sin_lat
    return x, y, z


def elevation_deg(sat_ecef, sta_ecef):
    """
    Compute elevation angle (deg) of satellite from ground station.
    Positive = above horizon.
    """
    dx = sat_ecef[0] - sta_ecef[0]
    dy = sat_ecef[1] - sta_ecef[1]
    dz = sat_ecef[2] - sta_ecef[2]
    r_sta = np.sqrt(sta_ecef[0]**2 + sta_ecef[1]**2 + sta_ecef[2]**2)
    # Unit vector: up (zenith) at station
    ux = sta_ecef[0] / r_sta
    uy = sta_ecef[1] / r_sta
    uz = sta_ecef[2] / r_sta
    # Range magnitude
    rng = np.sqrt(dx*dx + dy*dy + dz*dz)
    if rng < 1e-9:
        return 90.0
    # dot product of line-of-sight with zenith → cos(zenith_angle)
    los_dot_zen = (dx * ux + dy * uy + dz * uz) / rng
    zen_angle = np.arccos(np.clip(los_dot_zen, -1.0, 1.0))
    return 90.0 - np.degrees(zen_angle)


# =============================================================================
# Kepler solver
# =============================================================================

def cartesian_to_kepler(x, y, z, vx, vy, vz, mu=MU_EARTH):
    """Cartesian → Keplerian elements (a, e, i, RAAN, AOP, TA) in radians."""
    r = np.array([x, y, z])
    v = np.array([vx, vy, vz])
    r_mag = np.linalg.norm(r)
    v_sq = np.dot(v, v)
    h = np.cross(r, v)
    h_mag = np.linalg.norm(h)
    # SMA from vis-viva
    a = 1.0 / (2.0 / r_mag - v_sq / mu)
    # ECC vector
    e_vec = np.cross(v, h) / mu - r / r_mag
    e = np.linalg.norm(e_vec)
    # Inclination
    i = np.arccos(np.clip(h[2] / h_mag, -1.0, 1.0))
    # RAAN
    n_vec = np.array([-h[1], h[0], 0.0])
    n_mag = np.linalg.norm(n_vec)
    if n_mag < 1e-12:
        raan = 0.0
    else:
        raan = np.arccos(np.clip(n_vec[0] / n_mag, -1.0, 1.0))
        if n_vec[1] < 0:
            raan = 2 * np.pi - raan
    # AOP
    if e < 1e-12 or n_mag < 1e-12:
        aop = 0.0
    else:
        aop = np.arccos(np.clip(np.dot(n_vec, e_vec) / (n_mag * e), -1.0, 1.0))
        if e_vec[2] < 0:
            aop = 2 * np.pi - aop
    # True anomaly
    if e < 1e-12 or r_mag < 1e-12:
        ta = 0.0
    else:
        ta = np.arccos(np.clip(np.dot(e_vec, r) / (e * r_mag), -1.0, 1.0))
        if np.dot(r, v) < 0:
            ta = 2 * np.pi - ta
    return a, e, i, raan, aop, ta


def kepler_to_cartesian(a, e, i, raan, aop, ta, mu=MU_EARTH):
    """Keplerian (rad) → Cartesian (km, km/s) in inertial frame."""
    # Position in perifocal frame
    p = a * (1.0 - e * e)
    r_mag = p / (1.0 + e * np.cos(ta))
    r_pf = np.array([r_mag * np.cos(ta), r_mag * np.sin(ta), 0.0])
    # Velocity in perifocal frame
    v_pf = np.array([-np.sqrt(mu / p) * np.sin(ta),
                      np.sqrt(mu / p) * (e + np.cos(ta)), 0.0])
    # Rotation matrix: perifocal → inertial (3-1-3 sequence)
    cos_O, sin_O = np.cos(raan), np.sin(raan)
    cos_i, sin_i = np.cos(i), np.sin(i)
    cos_w, sin_w = np.cos(aop), np.sin(aop)
    R = np.array([
        [cos_O * cos_w - sin_O * sin_w * cos_i, -cos_O * sin_w - sin_O * cos_w * cos_i, sin_O * sin_i],
        [sin_O * cos_w + cos_O * sin_w * cos_i, -sin_O * sin_w + cos_O * cos_w * cos_i, -cos_O * sin_i],
        [sin_w * sin_i, cos_w * sin_i, cos_i]
    ])
    r = R @ r_pf
    v = R @ v_pf
    return r[0], r[1], r[2], v[0], v[1], v[2]


def propagate_kepler(a, e, i, raan, aop, ta0, dt, mu=MU_EARTH):
    """
    Propagate Keplerian state by dt seconds.
    Returns new true anomaly (rad).
    Accounts for J2 secular drift of RAAN and AOP.
    """
    # Mean motion
    n = np.sqrt(mu / (a * a * a))
    # Mean anomaly at t0
    if e < 1e-12:
        M0 = ta0  # circular case
    else:
        sin_E0 = np.sin(ta0) * np.sqrt(1.0 - e*e) / (1.0 + e * np.cos(ta0))
        cos_E0 = (e + np.cos(ta0)) / (1.0 + e * np.cos(ta0))
        E0 = np.arctan2(sin_E0, cos_E0)
        M0 = E0 - e * np.sin(E0)
    M = (M0 + n * dt) % (2 * np.pi)
    # Solve Kepler: M = E - e sin(E)
    E = M
    for _ in range(20):
        dE = (M - E + e * np.sin(E)) / (1.0 - e * np.cos(E))
        E += dE
        if abs(dE) < 1e-12:
            break
    # True anomaly
    if e < 1e-12:
        ta = M
    else:
        sin_ta = np.sin(E) * np.sqrt(1.0 - e*e) / (1.0 - e * np.cos(E))
        cos_ta = (np.cos(E) - e) / (1.0 - e * np.cos(E))
        ta = np.arctan2(sin_ta, cos_ta) % (2 * np.pi)

    # J2 secular rates (rad/s)
    J2 = J2_EARTH
    n = np.sqrt(mu / (a * a * a))
    factor = 1.5 * J2 * (RE_EARTH / (a * (1.0 - e*e)))**2 * n
    dRAAN = -factor * np.cos(i)
    dAOP = factor * (2.0 - 2.5 * np.sin(i)**2)

    raan_new = (raan + dRAAN * dt) % (2 * np.pi)
    aop_new = (aop + dAOP * dt) % (2 * np.pi)
    return ta, raan_new, aop_new


def propagate_and_elevation(dt, a, e, i, raan0, aop0, ta0, sta_ecef, jd0):
    """
    Propagate by dt seconds from JD0 and return (jd, elevation_deg, sub_lat, sub_lon).
    """
    ta, raan, aop = propagate_kepler(a, e, i, raan0, aop0, ta0, dt)
    x, y, z, _, _, _ = kepler_to_cartesian(a, e, i, raan, aop, ta)
    jd = jd0 + dt / 86400.0
    x_ecef, y_ecef, z_ecef = eme2000_to_ecef(x, y, z, jd)
    el = elevation_deg((x_ecef, y_ecef, z_ecef), sta_ecef)
    # Sub-satellite point (for ground-track direction filter)
    sub_lat, sub_lon, _ = ecef_to_latlon(x_ecef, y_ecef, z_ecef)
    return jd, el, sub_lat, sub_lon


# =============================================================================
# Pass detection
# =============================================================================

def detect_passes(jd_list, el_list, lat_list=None, min_el=10.0,
                  peak_threshold=60.0, time_step_s=30.0):
    """
    Detect satellite passes from elevation time series.

    If lat_list is provided, filters passes by ground-track direction:
    only NW→SE (descending, latitude decreasing) passes are kept.
    (Chinese launch vehicles require southeast-bound trajectories for
    range safety — ascending passes go southeast into open ocean.)

    Returns list of dicts: {t_aos, t_los, t_peak, el_peak, is_window, direction}
    """
    passes = []
    in_pass = False
    pass_start = None
    pass_vals = []   # (jd, el, lat)
    best = (0, -90, 0)

    for idx, (jd, el) in enumerate(zip(jd_list, el_list)):
        lat_val = lat_list[idx] if lat_list else None
        if el >= min_el:
            if not in_pass:
                in_pass = True
                pass_start = jd
                pass_vals = []
                best = (jd, el, lat_val or 0)
            pass_vals.append((jd, el, lat_val or 0))
            if el > best[1]:
                best = (jd, el, lat_val or 0)
        else:
            if in_pass and pass_vals:
                _close_pass(passes, pass_start, jd, best, pass_vals, peak_threshold, lat_list is not None)
            pass_vals = []
            in_pass = False

    if in_pass and pass_vals:
        _close_pass(passes, pass_start, jd_list[-1], best, pass_vals, peak_threshold, lat_list is not None)

    # Merge adjacent passes (noise at edge)
    merged = []
    for p in passes:
        if merged and abs(p["t_aos"] - merged[-1]["t_los"]) < time_step_s / 86400.0:
            prev = merged[-1]
            prev["t_los"] = p["t_los"]
            if p["el_peak"] > prev["el_peak"]:
                prev["el_peak"] = p["el_peak"]
                prev["t_peak"] = p["t_peak"]
                prev["direction"] = p["direction"]
            prev["is_window"] = prev["el_peak"] >= peak_threshold and prev.get("direction", "") != "ascending"
        else:
            merged.append(p)
    return merged


def _close_pass(passes, t_aos, t_los, best, pass_vals, peak_threshold, has_lat):
    """Determine pass direction and append to passes list."""
    direction = ""
    if has_lat and len(pass_vals) >= 3:
        # Latitudes at AOS, peak, LOS: N→S = descending = valid
        lat_aos = pass_vals[0][2]
        lat_los = pass_vals[-1][2]
        if lat_los < lat_aos:
            direction = "descending"   # NW→SE, valid launch window
        else:
            direction = "ascending"    # SW→NE, excluded

    is_window = best[1] >= peak_threshold
    if has_lat:
        is_window = is_window and direction == "descending"

    passes.append({
        "t_aos": t_aos,
        "t_los": t_los,
        "t_peak": best[0],
        "el_peak": best[1],
        "is_window": is_window,
        "direction": direction,
    })


# =============================================================================
# Main computation
# =============================================================================

def compute_launch_windows(oem_path, site_name, t0_str=None,
                           min_elevation=60.0, window_hours=4.0, step_s=30.0):
    """
    Compute launch windows for a given site and OEM file.

    Args:
        oem_path:      Path to CSS OEM file
        site_name:     Ground station key ("Jiuquan", "JQ", etc.)
        t0_str:        Target launch time ISO string with timezone
                       (default: latest OEM point)
        min_elevation: Minimum peak elevation for a valid window (deg)
        window_hours:  Hours before/after t0 to search
        step_s:        Time step in seconds for elevation sampling

    Returns:
        dict with keys: site, t0, passes, windows, oem_info
    """
    # Resolve site
    site_key = None
    for key, info in SITES.items():
        aliases = [key] + info.get("alias", [])
        if site_name in aliases:
            site_key = key
            break
    if site_key is None:
        return {"error": f"Unknown site: {site_name}. Available: {list(SITES.keys())}"}
    site = SITES[site_key]

    # Parse OEM
    data = parse_oem(oem_path)
    n = len(data["times"])
    oem_t0 = data["times"][0]
    oem_tn = data["times"][-1]

    # Determine reference Keplerian state (use first OEM point)
    a0, e0, i0, raan0, aop0, ta0 = cartesian_to_kepler(
        data["X"][0], data["Y"][0], data["Z"][0],
        data["VX"][0], data["VY"][0], data["VZ"][0],
    )

    # Parse t0
    if t0_str is None:
        t0_utc = oem_tn  # default to end of OEM
    else:
        t0_utc = _parse_iso(t0_str)

    jd0 = jd_from_datetime(oem_t0)
    jd_t0 = jd_from_datetime(t0_utc)
    dt_from_oem_to_t0 = (jd_t0 - jd0) * 86400.0  # seconds, negative if t0 before OEM

    # Ground station ECEF position (constant for this search)
    sta_ecef = station_ecef(site["lat"], site["lon"], site["alt_km"])

    # Search grid
    dt_start = -window_hours * 3600.0
    dt_end = window_hours * 3600.0
    n_steps = int((dt_end - dt_start) / step_s) + 1

    jd_list = []
    el_list = []
    lat_list = []

    for i in range(n_steps):
        dt = dt_start + i * step_s
        # dt is relative to t0; from OEM reference, the offset is dt_from_oem_to_t0 + dt
        dt_from_oem = dt_from_oem_to_t0 + dt
        _, el, sub_lat, _ = propagate_and_elevation(
            dt_from_oem, a0, e0, i0, raan0, aop0, ta0, sta_ecef, jd0)
        # jd at this step
        jd_at_step = jd_t0 + dt / 86400.0
        jd_list.append(jd_at_step)
        el_list.append(el)
        lat_list.append(sub_lat)

    # Detect passes with ground-track direction filter (NW->SE only)
    passes = detect_passes(jd_list, el_list, lat_list,
                           min_el=10.0, peak_threshold=min_elevation, time_step_s=step_s)
    windows = [p for p in passes if p["is_window"]]

    # Format for output
    result = {
        "site": site_key,
        "site_lat": site["lat"],
        "site_lon": site["lon"],
        "t0_utc": t0_utc.isoformat(),
        "t0_bjt": (t0_utc.replace(tzinfo=timezone.utc).astimezone(BJT))
                   .strftime("%Y-%m-%dT%H:%M:%S+08:00") if t0_utc else None,
        "oem_start": oem_t0.isoformat(),
        "oem_end": oem_tn.isoformat(),
        "oem_points": n,
        "min_elevation_threshold": min_elevation,
        "search_window_hours": window_hours,
        "total_passes": len(passes),
        "valid_windows": len(windows),
        "passes": [_format_pass(p) for p in passes],
        "windows": [_format_pass(p) for p in windows],
    }
    return result


def _parse_iso(s):
    """Parse ISO datetime string, possibly with timezone offset.
    Returns naive datetime in UTC."""
    s = s.strip()
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt.replace(tzinfo=None)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {s}")


def _jd_to_utc(jd):
    """Convert JD back to UTC datetime (approximate)."""
    jd_int = int(jd + 0.5)
    frac = jd + 0.5 - jd_int
    # Gregorian calendar from JD
    a = jd_int + 32044
    b = (4 * a + 3) // 146097
    c = a - (146097 * b) // 4
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d - 4800 + m // 10
    secs = frac * 86400.0
    h = int(secs // 3600)
    secs -= h * 3600
    mi = int(secs // 60)
    secs -= mi * 60
    s = int(secs)
    us = int((secs - s) * 1e6)
    return datetime(year, month, day, h, mi, s, us)


def _format_pass(p):
    """Format a pass dict for JSON output."""
    return {
        "aos_utc": _jd_to_utc(p["t_aos"]).isoformat(),
        "aos_bjt": (_jd_to_utc(p["t_aos"]).replace(tzinfo=timezone.utc)
                    .astimezone(BJT).strftime("%Y-%m-%dT%H:%M:%S+08:00")),
        "los_utc": _jd_to_utc(p["t_los"]).isoformat(),
        "peak_utc": _jd_to_utc(p["t_peak"]).isoformat(),
        "peak_el_deg": round(p["el_peak"], 2),
        "duration_s": round((p["t_los"] - p["t_aos"]) * 86400.0, 1),
        "is_launch_window": p["is_window"],
        "direction": p.get("direction", ""),
    }


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CSS launch window calculator")
    parser.add_argument("oem", help="Path to CSS OEM file")
    parser.add_argument("--site", "-s", default="Jiuquan",
                        help="Ground station: Jiuquan(JQ) or Wenchang(WC)")
    parser.add_argument("--t0", default=None,
                        help="Target launch time (ISO, e.g. 2026-05-24T23:08:36+08:00). "
                             "If omitted, uses OEM end time for future prediction.")
    parser.add_argument("--min-elevation", "-e", type=float, default=75.0,
                        help="Minimum peak elevation for valid window (deg, default 75)")
    parser.add_argument("--window-hours", "-w", type=float, default=4.0,
                        help="Hours before/after t0 to search (default 4)")
    parser.add_argument("--step", type=float, default=30.0,
                        help="Time step in seconds (default 30)")
    parser.add_argument("--json", action="store_true",
                        help="Output full JSON (otherwise human-readable)")
    args = parser.parse_args()

    result = compute_launch_windows(
        args.oem, args.site, args.t0,
        min_elevation=args.min_elevation,
        window_hours=args.window_hours,
        step_s=args.step,
    )

    if "error" in result:
        print(f"ERROR: {result['error']}")
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        # Human-readable output
        print(f"Site: {result['site']} ({result['site_lat']:.4f}N, {result['site_lon']:.4f}E)")
        print(f"T0:   {result['t0_bjt']} (BJT)")
        print(f"OEM:  {result['oem_start']} → {result['oem_end']} ({result['oem_points']} pts)")
        print(f"Min elevation threshold: {result['min_elevation_threshold']}°")
        print(f"Search: ±{result['search_window_hours']}h around T0")
        print(f"Passes detected: {result['total_passes']}")
        print(f"Launch windows:  {result['valid_windows']}")
        print()

        for i, p in enumerate(result["passes"]):
            direction = p.get("direction", "")
            dir_label = f" [{direction}]" if direction else ""
            marker = "★ LAUNCH WINDOW" if p["is_launch_window"] else "  Pass"
            print(f"[{i+1}] {marker}: peak={p['peak_el_deg']:.1f}° at {p['peak_utc']} UTC{dir_label}")
            print(f"    AOS/LOS: {p['aos_utc']} -> {p['los_utc']} UTC")
            print(f"    Duration: {p['duration_s']:.0f}s ({p['duration_s']/60:.1f} min)")
            if p["is_launch_window"]:
                print(f"    Beijing: {p['aos_bjt']} -> BJT")
            print()