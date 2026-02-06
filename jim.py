#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apple Maps / satellites.pro 手动 accessKey 下载瓦片并拼接成大图
完全自动化版本：不需要命令行参数，运行一次即可下载 + 拼接。

注意：
- accessKey 必须从浏览器 F12 → Network 抓到（有效期 10~15 分钟）
- 抓到的 accessKey 必须保持原样粘贴到 ACCESS_KEY 变量中
"""

import os
import math
import time
import requests
from io import BytesIO
from PIL import Image

# ============================================================
# 🔧🔧🔧 手动配置区（你只需要修改这里） 🔧🔧🔧
# ============================================================

ACCESS_KEY = "1770310977_4654790101657753386_%2F_zTQ3u5D2b55P3wb0%2Fxi47O6AgB6RKTFyoN4Op%2BB5ibI%3D"

ZOOM = 20                     # 瓦片缩放级别
MIN_LON, MIN_LAT = -7.07 ,52.20  # 左下角（经纬度）
MAX_LON, MAX_LAT = -7.05 ,52.18  # 右上角（经纬度）52.185437121388404, -7.059602755044289

OUT_DIR = "tiles_z14"        # 下载的瓦片保存到此文件夹
OUTPUT_IMAGE = "ireland_satellite_z14.png"   # 拼接结果图像

# Apple Maps tile 参数（一般不需要改）
TILE_SIZE = 256
APPLE_TILE_HOST = "https://sat-cdn.apple-mapkit.com"
APPLE_TILE_STYLE = 7
APPLE_TILE_SIZE_PARAM = 1
APPLE_TILE_SCALE = 1
APPLE_TILE_VERSION = 10311

# 下载相关参数
REQUEST_TIMEOUT = 20
RETRIES = 3
SLEEP_BETWEEN = 0.25


# ============================================================
#                 以下为核心代码（无需改动）
# ============================================================

def lonlat_to_tile(lon: float, lat: float, zoom: int):
    lat = max(-85.05112878, min(85.05112878, lat))
    x = (lon + 180.0) / 360.0 * (2 ** zoom)
    y = (
        (1.0 - math.log(math.tan(math.radians(lat)) + 1.0 / math.cos(math.radians(lat))) / math.pi)
        / 2.0 * (2 ** zoom)
    )
    return int(x), int(y)


def bbox_to_tile_range(min_lon, min_lat, max_lon, max_lat, zoom):
    x1, y2 = lonlat_to_tile(min_lon, min_lat, zoom)
    x2, y1 = lonlat_to_tile(max_lon, max_lat, zoom)
    return min(x1,x2), max(x1,x2), min(y1,y2), max(y1,y2)


def build_tile_url(z, x, y, access_key):
    return (
        f"{APPLE_TILE_HOST}/tile"
        f"?style={APPLE_TILE_STYLE}"
        f"&size={APPLE_TILE_SIZE_PARAM}"
        f"&scale={APPLE_TILE_SCALE}"
        f"&z={z}&x={x}&y={y}"
        f"&v={APPLE_TILE_VERSION}"
        f"&accessKey={access_key}"
    )


def download_tile(z, x, y, access_key, out_path):
    url = build_tile_url(z, x, y, access_key)
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                img = Image.open(BytesIO(r.content)).convert("RGB")
                img.save(out_path)
                return True
            print(f"[WARN] HTTP {r.status_code} while downloading x={x} y={y}")
        except Exception as e:
            print(f"[ERROR] attempt {attempt}: {e}")
        time.sleep(attempt * 0.7)
    return False


def download_area():
    if not ACCESS_KEY:
        raise RuntimeError("请先设置 ACCESS_KEY！")

    os.makedirs(OUT_DIR, exist_ok=True)

    x_min, x_max, y_min, y_max = bbox_to_tile_range(MIN_LON, MIN_LAT, MAX_LON, MAX_LAT, ZOOM)

    print(f"[INFO] Zoom={ZOOM}")
    print(f"[INFO] X: {x_min} → {x_max}")
    print(f"[INFO] Y: {y_min} → {y_max}")

    total = (x_max - x_min + 1) * (y_max - y_min + 1)
    done = 0

    for x in range(x_min, x_max + 1):
        for y in range(y_min, y_max + 1):
            out_path = f"{OUT_DIR}/{x}_{y}.jpg"
            if os.path.exists(out_path):
                done += 1
                continue

            print(f"[Downloading] {done+1}/{total} tile ({x},{y})")
            download_tile(ZOOM, x, y, ACCESS_KEY, out_path)
            done += 1
            time.sleep(SLEEP_BETWEEN)

    print("[INFO] 下载完成！")


def stitch_tiles():
    files = [f for f in os.listdir(OUT_DIR) if "_" in f]
    coords = [(int(f.split("_")[0]), int(f.split("_")[1].split(".")[0])) for f in files]

    xs = sorted(set([c[0] for c in coords]))
    ys = sorted(set([c[1] for c in coords]))

    width = len(xs) * TILE_SIZE
    height = len(ys) * TILE_SIZE

    print(f"[INFO] 拼接图像大小: {width} x {height}")

    canvas = Image.new("RGB", (width, height), (0,0,0))

    for xi, x in enumerate(xs):
        for yi, y in enumerate(ys):
            path = f"{OUT_DIR}/{x}_{y}.jpg"
            if not os.path.exists(path):
                print(f"[WARN] 缺失瓦片: {path}")
                continue

            img = Image.open(path)
            x1 = xi * TILE_SIZE
            y1 = yi * TILE_SIZE
            canvas.paste(img, (x1, y1))

    canvas.save(OUTPUT_IMAGE)
    print(f"[INFO] 拼接完成: {OUTPUT_IMAGE}")


if __name__ == "__main__":
    print("=== 开始下载 Apple Maps 瓦片 ===")
    download_area()

    print("\n=== 开始拼接大图 ===")
    stitch_tiles()

    print("\n 完成！")