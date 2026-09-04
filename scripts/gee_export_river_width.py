"""
GEE Sentinel-1 river width export — Wang River, Ban Sadet (Lampang).
Runs headless (GitHub Actions) with a service account, appends one row per
overpass to wang_river_width.csv at the repo root.

Env vars required:
  GEE_SERVICE_ACCOUNT   - service account email
  GEE_PRIVATE_KEY       - full JSON key content (from GitHub Secrets)

TODO: replace the placeholder transect coordinates below with the real
surveyed lines for Khelang / Mid-river / Yao Weir before relying on the
output. Placeholders currently just span the AOI bbox at 3 latitudes.
"""

import csv
import json
import os
import sys
from datetime import datetime, timedelta

import ee

AOI = ee.Geometry.Rectangle([99.490, 18.265, 99.560, 18.335])

# TODO: replace with real transect line coordinates (lon, lat)
TRANSECTS = {
    "khelang": ee.Geometry.LineString([[99.490, 18.320], [99.560, 18.320]]),
    "mid": ee.Geometry.LineString([[99.490, 18.300], [99.560, 18.300]]),
    "yao": ee.Geometry.LineString([[99.490, 18.280], [99.560, 18.280]]),
}

WATER_THRESHOLD_DB = -15
SCALE_M = 10  # Sentinel-1 GRD pixel spacing
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "wang_river_width.csv")


def init_ee():
    email = os.environ["GEE_SERVICE_ACCOUNT"]
    key_json = os.environ["GEE_PRIVATE_KEY"]
    key_path = "/tmp/gee_key.json"
    with open(key_path, "w") as f:
        f.write(key_json)
    creds = ee.ServiceAccountCredentials(email, key_path)
    ee.Initialize(creds)


def latest_image():
    end = datetime.utcnow()
    start = end - timedelta(days=20)
    coll = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(AOI)
        .filterDate(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .sort("system:time_start", False)
    )
    n = coll.size().getInfo()
    if n == 0:
        return None, None
    img = coll.first()
    date = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd").getInfo()
    return img, date


def measure_width(img, line):
    water = img.select("VV").lt(WATER_THRESHOLD_DB)
    stats = water.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=line,
        scale=SCALE_M,
        maxPixels=1e9,
    )
    water_pixels = stats.get("VV").getInfo() or 0
    return round(water_pixels * SCALE_M, 1)


def discharge(width_mid):
    if not width_mid:
        return 0.0
    return round(0.012 * (width_mid ** 1.90), 1)


def append_csv(date, w_khelang, w_mid, w_yao, q):
    is_new = not os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(
                ["date", "width_khelang", "width_mid", "width_yao", "discharge_m3s"]
            )
        writer.writerow([date, w_khelang, w_mid, w_yao, q])


def main():
    init_ee()
    img, date = latest_image()
    if img is None:
        print("No new Sentinel-1 scene in the last 20 days, skipping.")
        return

    w_khelang = measure_width(img, TRANSECTS["khelang"])
    w_mid = measure_width(img, TRANSECTS["mid"])
    w_yao = measure_width(img, TRANSECTS["yao"])
    q = discharge(w_mid)

    append_csv(date, w_khelang, w_mid, w_yao, q)
    print(f"Appended {date}: khelang={w_khelang} mid={w_mid} yao={w_yao} Q={q}")


if __name__ == "__main__":
    main()
