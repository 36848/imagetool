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

DOWNLOAD_DELAY = 0.15    # 每张瓦片之间的延迟，避免对 OSM 造成压力
TIMEOUT = 10             # 网络超时时间

# ========================
# 工具函数
# ========================
def latlon_to_tile(lat, lon, zoom):
    """经纬度 → OSM XYZ 瓦片编号"""
    lat_rad = math.radians(lat)
    n = 2 ** zoom

    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)

    return xtile, ytile


def calculate_tile_range(lat, lon, zoom, half_range):
    """计算下载瓦片范围"""
    cx, cy = latlon_to_tile(lat, lon, zoom)

    return {
        "zoom": zoom,
        "min_x": cx - half_range,
        "max_x": cx + half_range,
        "min_y": cy - half_range,
        "max_y": cy + half_range
    }


def download_tile(x, y, z, save_path):
    """下载单张瓦片"""

    url = OSM_TILE_URL.format(z=z, x=x, y=y)
    headers = {"User-Agent": USER_AGENT}

    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
    except Exception as e:
        print(f"[ERROR] 下载失败：{url} -> {e}")
        return False

    if r.status_code == 200:
        with open(save_path, "wb") as f:
            f.write(r.content)
        return True
    else:
        print(f"[WARN] HTTP {r.status_code} : {url}")
        return False


def download_tiles(tile_range, output_dir):
    """批量下载瓦片"""
    os.makedirs(output_dir, exist_ok=True)

    z = tile_range["zoom"]
    print(f"[INFO] 开始下载瓦片，zoom={z}")

    for x in range(tile_range["min_x"], tile_range["max_x"] + 1):
        for y in range(tile_range["min_y"], tile_range["max_y"] + 1):

            save_name = f"{z}_{x}_{y}.png"
            save_path = os.path.join(output_dir, save_name)

            print(f"Downloading z={z} x={x} y={y}")

            ok = download_tile(x, y, z, save_path)

            if not ok:
                print(f"[WARN] 跳过缺失瓦片：z={z} x={x} y={y}")

            time.sleep(DOWNLOAD_DELAY)

    print("[OK] 完成所有瓦片下载！")


def stitch_tiles(tile_folder, output_image):
    """拼接瓦片为大图"""
    # 读取目录内的瓦片
    tiles = [f for f in os.listdir(tile_folder) if f.endswith(".png")]
    if not tiles:
        raise ValueError("瓦片目录为空或没有 PNG 文件。")

    # 解析瓦片名
    xs, ys = [], []
    imgs = {}

    for fn in tiles:
        try:
            z, x, y = fn.replace(".png", "").split("_")
            x = int(x)
            y = int(y)
        except:
            continue

        img = Image.open(os.path.join(tile_folder, fn))
        imgs[(x, y)] = img
        xs.append(x)
        ys.append(y)

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    w, h = next(iter(imgs.values())).size
    total_w = (max_x - min_x + 1) * w
    total_h = (max_y - min_y + 1) * h

    print(f"[INFO] 拼接大图尺寸：{total_w} x {total_h}")

    big = Image.new("RGB", (total_w, total_h))

    for x in range(min_x, max_x + 1):
        for y in range(min_y, max_y + 1):
            if (x, y) not in imgs:
                continue
            px = (x - min_x) * w
            py = (y - min_y) * h
            big.paste(imgs[(x, y)], (px, py))

    os.makedirs(os.path.dirname(output_image), exist_ok=True)
    big.save(output_image)
    print(f"[OK] 拼接完成 → {output_image}")

    return output_image


def dms_to_decimal(dms_str: str) -> float:
    """将 DMS (度° 分' 秒") 格式转换为十进制度 float"""
    import re

    s = dms_str.strip().upper()

    # 判断方向 N/E positive, S/W negative
    sign = 1
    if s.endswith("S") or s.endswith("W"):
        sign = -1
        s = s[:-1].strip()
    elif s.endswith("N") or s.endswith("E"):
        sign = 1
        s = s[:-1].strip()

    # 替换符号
    s = s.replace("°", " ").replace("'", " ").replace('"', " ")
    s = s.replace(":", " ")

    parts = [p for p in re.split(r"\s+", s) if p]

    deg = float(parts[0])
    minu = float(parts[1]) if len(parts) > 1 else 0
    sec = float(parts[2]) if len(parts) > 2 else 0

    decimal = sign * (deg + minu/60 + sec/3600)
    return decimal

# ========================
# 主流程
# ========================
if __name__ == "__main__":
    # 你可以更改这些参数：
   
    lat_dms = '53°52\'26.7"N' #Latitude经度
    lon_dms = '7°10\'22.3"W' #Longitude纬度

    #  转换为十进制度
    lat = dms_to_decimal(lat_dms)
    lon = dms_to_decimal(lon_dms)

    #print("转换后的坐标：", lat, lon)

    zoom = 15    #地图缩放等级 13.14.15 =15
    half_range = 5  #  范围area Map Zoom Level 1 2  3 5 10

    tile_dir = f"./tiles/a{zoom}" # need change name
    output_image = f"./output/merged_a{zoom}.png"

    # 步骤 1：计算瓦片范围
    tile_range = calculate_tile_range(lat, lon, zoom, half_range)

    # 步骤 2：下载瓦片
    download_tiles(tile_range, tile_dir)

    # 步骤 3：拼接成大图
    stitch_tiles(tile_dir, output_image)