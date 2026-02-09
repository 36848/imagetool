import os
import math
import time
import requests
from PIL import Image

# ========================
# 配置：可以自己修改
# ========================
USER_AGENT = "MapTool/1.0 (yu.xia@tmdesign.ie)"
OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

DOWNLOAD_DELAY = 0.15
TIMEOUT = 10


# ========================
# 经纬度 → OSM XYZ 瓦片
# ========================
def latlon_to_tile(lat, lon, zoom):
    lat_rad = math.radians(lat)
    n = 2 ** zoom

    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)

    return xtile, ytile


# ========================
#  使用两个点计算瓦片范围（关键）
# ========================
def calculate_tile_range_from_area(min_lat, min_lon, max_lat, max_lon, zoom):
    # 左下角
    x1, y2 = latlon_to_tile(min_lat, min_lon, zoom)

    # 右上角
    x2, y1 = latlon_to_tile(max_lat, max_lon, zoom)

    # 排序，确保 min/max 正确
    min_x, max_x = sorted([x1, x2])
    min_y, max_y = sorted([y1, y2])

    return {
        "zoom": zoom,
        "min_x": min_x,
        "max_x": max_x,
        "min_y": min_y,
        "max_y": max_y
    }


# ========================
# 下载单张瓦片
# ========================
def download_tile(x, y, z, save_path):
    url = OSM_TILE_URL.format(z=z, x=x, y=y)
    headers = {"User-Agent": USER_AGENT}

    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
    except Exception as e:
        print(f"[ERROR] {url} -> {e}")
        return False

    if r.status_code == 200:
        with open(save_path, "wb") as f:
            f.write(r.content)
        return True
    else:
        print(f"[WARN] HTTP {r.status_code}: {url}")
        return False


# ========================
# 批量下载瓦片
# ========================
def download_tiles(tile_range, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    z = tile_range["zoom"]
    print(f"[INFO] 开始下载瓦片, zoom={z}")

    for x in range(tile_range["min_x"], tile_range["max_x"] + 1):
        for y in range(tile_range["min_y"], tile_range["max_y"] + 1):
            save_name = f"{z}_{x}_{y}.png"
            save_path = os.path.join(output_dir, save_name)

            print(f"Downloading z={z} x={x} y={y}")
            ok = download_tile(x, y, z, save_path)

            if not ok:
                print(f"[WARN] 缺失瓦片: {z}/{x}/{y}")

            time.sleep(DOWNLOAD_DELAY)

    print("[OK] 所有瓦片下载完成！")


# ========================
# 拼接瓦片为大图
# ========================
def stitch_tiles(tile_folder, output_image):
    tiles = [f for f in os.listdir(tile_folder) if f.endswith(".png")]
    if not tiles:
        raise ValueError("瓦片目录为空!!")

    xs, ys = [], []
    imgs = {}

    for fn in tiles:
        z, x, y = fn.replace(".png", "").split("_")
        x, y = int(x), int(y)

        img = Image.open(os.path.join(tile_folder, fn))
        imgs[(x, y)] = img
        xs.append(x)
        ys.append(y)

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    w, h = next(iter(imgs.values())).size
    total_w = (max_x - min_x + 1) * w
    total_h = (max_y - min_y + 1) * h

    print(f"[INFO] 拼接图像大小: {total_w} x {total_h}")

    canvas = Image.new("RGB", (total_w, total_h))

    for x in range(min_x, max_x + 1):
        for y in range(min_y, max_y + 1):
            if (x, y) in imgs:
                px = (x - min_x) * w
                py = (y - min_y) * h
                canvas.paste(imgs[(x, y)], (px, py))

    os.makedirs(os.path.dirname(output_image), exist_ok=True)
    canvas.save(output_image)
    print(f"[OK] 拼接完成 → {output_image}")

    return output_image


# ========================
# 主程序
# ========================
if __name__ == "__main__":

    
    # 左下角 (bottom-left)
    MIN_LAT,MIN_LON = 52.86806351794111, -8.781503625657379
    # 右上角 (top-right)
    MAX_LAT,MAX_LON = 52.961073389581294, -8.76785417577199

    zoom = 14 #地图缩放等级 13.14.15 =15

    tile_dir = f"./tiles/z{zoom}"
    output_image = f"./output/z{zoom}.png"

    # 计算瓦片范围（基于区域）
    tile_range = calculate_tile_range_from_area(
        MIN_LAT, MIN_LON,
        MAX_LAT, MAX_LON,
        zoom
    )

    # 下载瓦片
    download_tiles(tile_range, tile_dir)

    # 拼接大图
    stitch_tiles(tile_dir, output_image)