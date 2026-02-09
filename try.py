import requests
import math
import os

# ===============================
# 你提供的新参数
# ===============================

ACCESS_KEY = "1770631857_9078434727454977329_%2F_G77Rzgal2quo%2Fs8xR1VxLaybEvGKs2aBdfoe8cSdkak%3D"

ZOOM = 19
MIN_LON, MIN_LAT = -6.24, 53.36
MAX_LON, MAX_LAT = -6.24, 53.35

OUT_DIR = "tiles_z14"
OUTPUT_IMAGE = "ireland_satellite_z14.png"

# Apple 瓦片参数
TILE_SIZE = 256
APPLE_TILE_HOST = "https://sat-cdn.apple-mapkit.com"
APPLE_TILE_STYLE = 7
APPLE_TILE_SIZE_PARAM = 1    # 正确值应该是 1，不是 18
APPLE_TILE_SCALE = 1
APPLE_TILE_VERSION = 10311


# ===============================
# 经纬度 → 瓦片编号
# ===============================

def lonlat_to_tile(lon, lat, zoom):
    lat = max(-85.05112878, min(85.05112878, lat))
    x = (lon + 180.0) / 360.0 * (2 ** zoom)
    y = (1.0 - math.log(math.tan(math.radians(lat)) +
         1.0 / math.cos(math.radians(lat))) / math.pi) / 2.0 * (2 ** zoom)
    return int(x), int(y)


# ===============================
# 构建真实可访问的 URL
# ===============================

def build_tile_url(z, x, y):
    return (
        f"{APPLE_TILE_HOST}/tile"
        f"?style={APPLE_TILE_STYLE}"
        f"&size={APPLE_TILE_SIZE_PARAM}"
        f"&scale={APPLE_TILE_SCALE}"
        f"&z={z}&x={x}&y={y}"
        f"&v={APPLE_TILE_VERSION}"
        f"&accessKey={ACCESS_KEY}"
    )


# ===============================
# 下载一张瓦片测试 accessKey 是否有效
# ===============================

def download_test_tile():
    os.makedirs(OUT_DIR, exist_ok=True)

    # 取左上角作为测试瓦片
    x, y = lonlat_to_tile(MIN_LON, MAX_LAT, ZOOM)

    url = build_tile_url(ZOOM, x, y)
    print("测试 URL：\n", url)

    save_path = f"{OUT_DIR}/test_{x}_{y}.jpg"

    try:
        r = requests.get(url, timeout=20)
        print("HTTP 状态码：", r.status_code)

        if r.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(r.content)

            print("成功：", save_path)
        else:
            print("失败")

    except Exception as e:
        print("错误：", e)


# ===============================
# 主程序入口
# ===============================

if __name__ == "__main__":
    download_test_tile()