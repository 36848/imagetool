import os
import math
import time
import requests
from io import BytesIO
from PIL import Image

# =========================
# 配置区（请按需修改）
# =========================
GOOGLE_API_KEY = "YOUR_GOOGLE_STATIC_MAPS_KEY"   # ← 填你的 Key
MAPTYPE = "satellite"                            # 可选: 'satellite' | 'hybrid' | 'roadmap' | 'terrain'

# 单张静态图尺寸：策略A（尽量大块）+ 策略B（scale=2 提升像素密度）
SIZE_X, SIZE_Y = 640, 640     # Google Static size 上限常用 640
SCALE = 2                     # 等效分辨率翻倍：640x640@2x → 1280x1280

# 下载节流/重试
REQUEST_TIMEOUT = 20
RETRIES = 3
SLEEP_BETWEEN = 0.2  # s

# 合成图最大像素保护（避免内存爆炸）
MAX_TOTAL_PIXELS = 220_000_000  # ~220MP，按你的机器内存可调

# =========================
# Web Mercator 常量
# =========================
EARTH_RADIUS = 6378137.0
INITIAL_RES = 156543.03392804097  # m/px at zoom=0 (Web Mercator)

def lonlat_to_mercator(lon: float, lat: float):
    x = math.radians(lon) * EARTH_RADIUS
    # clamp lat for mercator
    lat = max(-85.05112878, min(85.05112878, lat))
    y = EARTH_RADIUS * math.log(math.tan(math.pi/4 + math.radians(lat)/2))
    return x, y

def mercator_to_lonlat(x: float, y: float):
    lon = math.degrees(x / EARTH_RADIUS)
    lat = math.degrees(2 * math.atan(math.exp(y / EARTH_RADIUS)) - math.pi/2)
    return lon, lat

def meters_per_pixel(zoom: int) -> float:
    return INITIAL_RES / (2 ** zoom)

def build_static_url(lat: float, lon: float, zoom: int, size_x=SIZE_X, size_y=SIZE_Y, scale=SCALE, maptype=MAPTYPE):
    return (
        "https://maps.googleapis.com/maps/api/staticmap"
        f"?center={lat:.8f},{lon:.8f}&zoom={zoom}"
        f"&size={size_x}x{size_y}&scale={scale}"
        f"&maptype={maptype}&key={GOOGLE_API_KEY}"
    )

def download_static(lat, lon, zoom, out_path):
    """下载一张静态图（带重试与节流）"""
    url = build_static_url(lat, lon, zoom)
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                img = Image.open(BytesIO(r.content))
                img.save(out_path)
                return True
            else:
                print(f"[WARN] HTTP {r.status_code} url={url}")
        except Exception as e:
            print(f"[ERROR] attempt {attempt}: {e}")
        if attempt < RETRIES:
            time.sleep(0.6 * attempt)
    return False

def plan_grid_center_range(center_lon, center_lat, width_m, height_m, zoom, overlap_ratio=0.10):
    """
    根据中心+范围，计算网格数量与步长（既考虑策略A的大块size，也叠加策略B的scale=2）
    返回：
      grid_cols, grid_rows, step_px_x, step_px_y, eff_px_w, eff_px_h, mosaic_px_w, mosaic_px_h,
      top_left_mx, top_left_my (用于世界文件/定位)
    """
    res = meters_per_pixel(zoom)
    eff_px_w = SIZE_X * SCALE       # 等效像素宽（策略B）
    eff_px_h = SIZE_Y * SCALE

    # 每张图地面覆盖（米）
    eff_w_m = eff_px_w * res
    eff_h_m = eff_px_h * res

    # 网格步进（像素）（有重叠，策略A：尽量少块）
    step_px_x = max(1, int(round(eff_px_w * (1.0 - overlap_ratio))))
    step_px_y = max(1, int(round(eff_px_h * (1.0 - overlap_ratio))))
    step_w_m = step_px_x * res
    step_h_m = step_px_y * res

    # 按最少块覆盖 width_m/height_m
    if width_m <= eff_w_m:
        grid_cols = 1
        mosaic_px_w = eff_px_w
    else:
        # 计算需要多少“步进”
        n_steps = math.ceil((width_m - eff_w_m) / step_w_m)
        grid_cols = n_steps + 1
        mosaic_px_w = eff_px_w + n_steps * step_px_x

    if height_m <= eff_h_m:
        grid_rows = 1
        mosaic_px_h = eff_px_h
    else:
        n_steps = math.ceil((height_m - eff_h_m) / step_h_m)
        grid_rows = n_steps + 1
        mosaic_px_h = eff_px_h + n_steps * step_px_y

    # 组合像素总量保护
    total_pixels = mosaic_px_w * mosaic_px_h
    if total_pixels > MAX_TOTAL_PIXELS:
        raise MemoryError(
            f"拼接图过大：{mosaic_px_w}x{mosaic_px_h} ≈ {total_pixels/1e6:.1f} MP，"
            f"超过上限 {MAX_TOTAL_PIXELS/1e6:.0f} MP。请降低范围或zoom。"
        )

    # 用 Web Mercator 计算整个拼图的左上角（米）
    center_mx, center_my = lonlat_to_mercator(center_lon, center_lat)
    mosaic_w_m = mosaic_px_w * res
    mosaic_h_m = mosaic_px_h * res
    top_left_mx = center_mx - mosaic_w_m / 2.0
    top_left_my = center_my + mosaic_h_m / 2.0

    return (grid_cols, grid_rows, step_px_x, step_px_y,
            eff_px_w, eff_px_h, mosaic_px_w, mosaic_px_h,
            top_left_mx, top_left_my, res)

def run_static_mosaic(center_lat, center_lon, width_m, height_m, zoom,
                      out_dir="output_static",
                      overlap_ratio=0.10, maptype=MAPTYPE,
                      save_name_prefix=None, make_pgw=True, make_dxf=False):
    """
    主流程：下载 + 拼接 + 世界文件 (+ 可选 DXF)
    """
    os.makedirs(out_dir, exist_ok=True)
    if save_name_prefix is None:
        save_name_prefix = f"static_{maptype}_z{zoom}"

    (grid_cols, grid_rows, step_px_x, step_px_y,
     eff_px_w, eff_px_h, mosaic_px_w, mosaic_px_h,
     top_left_mx, top_left_my, res) = plan_grid_center_range(
        center_lon=center_lon, center_lat=center_lat,
        width_m=width_m, height_m=height_m, zoom=zoom,
        overlap_ratio=overlap_ratio
    )

    print(f"[PLAN] cols x rows = {grid_cols} x {grid_rows}")
    print(f"[PLAN] step_px = {step_px_x} x {step_px_y}, per_img_px = {eff_px_w} x {eff_px_h}")
    print(f"[PLAN] mosaic_px = {mosaic_px_w} x {mosaic_px_h}, res={res:.6f} m/px")

    mosaic = Image.new("RGB", (mosaic_px_w, mosaic_px_h), (255, 255, 255))

    # 为每一格计算中心点（Web Mercator），再转回经纬度请求 Static
    for j in range(grid_rows):
        for i in range(grid_cols):
            # 本块中心（米）
            cx_m = top_left_mx + (eff_px_w/2 + i*step_px_x) * res
            cy_m = top_left_my - (eff_px_h/2 + j*step_px_y) * res

            lon, lat = mercator_to_lonlat(cx_m, cy_m)

            tile_name = f"{save_name_prefix}_{j:02d}_{i:02d}.png"
            tile_path = os.path.join(out_dir, tile_name)

            ok = download_static(lat=lat, lon=lon, zoom=zoom, out_path=tile_path)
            if not ok:
                print(f"[WARN] 下载失败，留空：({i},{j})")
                continue

            try:
                im = Image.open(tile_path)
            except Exception as e:
                print(f"[WARN] 打开失败 {tile_path}: {e}")
                continue

            # 粘贴位置（像素）
            px = i * step_px_x
            py = j * step_px_y
            mosaic.paste(im, (px, py))

            time.sleep(SLEEP_BETWEEN)

    mosaic_path = os.path.join(out_dir, f"{save_name_prefix}_mosaic.png")
    mosaic.save(mosaic_path)
    print(f"[OK] 拼接完成 → {mosaic_path}")

    wld_path = None
    if make_pgw:
        # PGW（世界文件）：A D B E C F
        # A = res, D=0, B=0, E=-res
        # C = 左上像素中心X = top_left_mx + A/2
        # F = 左上像素中心Y = top_left_my + E/2
        A = res
        D = 0.0
        B = 0.0
        E = -res
        C = top_left_mx + A * 0.5
        F = top_left_my + E * 0.5

        wld_path = mosaic_path[:-4] + ".pgw"
        with open(wld_path, "w", encoding="utf-8") as f:
            f.write(f"{A:.12f}\n{D:.12f}\n{B:.12f}\n{E:.12f}\n{C:.12f}\n{F:.12f}\n")
        print(f"[OK] 世界文件生成 → {wld_path}")

    if make_dxf:
        try:
            export_dxf_with_image(mosaic_path, wld_path, os.path.join(out_dir, f"{save_name_prefix}.dxf"))
        except Exception as e:
            print(f"[WARN] 生成 DXF 失败：{e}")

    return mosaic_path, wld_path

# （可选）DXF 输出：按世界文件定位图像
def export_dxf_with_image(image_path, worldfile_path, out_dxf_path):
    import ezdxf
    from PIL import Image as PILImage
    import os

    with open(worldfile_path, "r") as f:
        lines = [float(x) for x in f.read().strip().splitlines()]
    A, D, B, E, C, F = lines
    w_px, h_px = PILImage.open(image_path).size
    width_m = w_px * A
    height_m = h_px * (-E)
    insert_x = C
    insert_y = F - height_m

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # meters
    msp = doc.modelspace()

    # 兼容旧版 ezdxf 的参数名 size_in_pixel
    image_def = doc.add_image_def(os.path.abspath(image_path), size_in_pixel=(w_px, h_px))
    msp.add_image(image_def, insert=(insert_x, insert_y), size_in_units=(width_m, height_m), rotation=0)
    doc.saveas(out_dxf_path)
    print(f"[OK] DXF 输出 → {out_dxf_path}")

if __name__ == "__main__":
    # ======== 示例参数（请按需修改）========
    # 地图中心（都柏林市中心示例）
    center_lat = 53.3478
    center_lon = -6.2597

    # 目标覆盖范围（米）
    width_m = 600     # 左右方向覆盖宽
    height_m = 600    # 上下方向覆盖高

    # 清晰度（zoom越大越清）
    zoom = 19         # 可尝试 20（是否可用取决于该地区数据）

    out_dir = "out_static_mosaic"
    overlap_ratio = 0.10  # 相邻子图重叠 10%（避免接缝）

    run_static_mosaic(center_lat, center_lon, width_m, height_m, zoom,
                      out_dir=out_dir, overlap_ratio=overlap_ratio,
                      maptype=MAPTYPE, save_name_prefix=None,
                      make_pgw=True, make_dxf=True)