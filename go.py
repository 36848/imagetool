import os
import math
import time
import requests
from io import BytesIO
from PIL import Image

from dotenv import load_dotenv

# 加载 .env 文件中的变量
load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    raise RuntimeError("未找到 GOOGLE_API_KEY，请在 .env 文件中设置。")


# 配置区 GOOGLE_API_KEY = 
MAPTYPE = "satellite"  # 'satellite' | 'hybrid' | 'roadmap' | 'terrain'

# 单张静态图的逻辑尺寸（scale=1 时的像素）
SIZE_X, SIZE_Y = 640, 640       # Google Static Maps 常用最大 640
SCALE = 2                       # 渲染像素放大倍数（返回图像尺寸变为 1280x1280，但地面覆盖不变）

# 下载节流/重试
REQUEST_TIMEOUT = 20
RETRIES = 3
SLEEP_BETWEEN = 0.2  # s

# 合成图最大像素保护（避免内存爆炸）——注意这里是“渲染像素”（已乘以 SCALE）
MAX_TOTAL_PIXELS = 100_000_000  # 100MP

# =========================
# Web Mercator 常量
# =========================
EARTH_RADIUS = 6378137.0
INITIAL_RES = 156543.03392804097  # m/px at zoom=0 (Web Mercator, scale=1)

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
    """Meters per logical pixel at given zoom (i.e., scale=1)."""
    return INITIAL_RES / (2 ** zoom)

def build_static_url(lat: float, lon: float, zoom: int,
                     size_x=SIZE_X, size_y=SIZE_Y, scale=SCALE, maptype=MAPTYPE):
    #  必须使用 '&'，不要使用 HTML 转义的 '&amp;'
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
                img = Image.open(BytesIO(r.content)).convert("RGB")
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
    方案（Option B）：
      * 所有几何/距离计算均在 “1x 逻辑像素空间” 完成（SIZE_X / SIZE_Y / meters_per_pixel）。
      * 仅在渲染时把像素乘以 SCALE。
    返回：
      grid_cols, grid_rows,
      step_px_world_x, step_px_world_y,        # 逻辑像素步长
      step_px_render_x, step_px_render_y,      # 渲染像素步长（= 逻辑步长 * SCALE）
      eff_px_render_w, eff_px_render_h,        # 单图渲染像素（W,H）= SIZE_* * SCALE
      mosaic_px_render_w, mosaic_px_render_h,  # 总拼图渲染像素（W,H）
      top_left_mx, top_left_my,                # 拼图左上角（米，Web Mercator）
      res_1x,                                  # 每逻辑像素的米数（scale=1 的分辨率）
      world_px_w, world_px_h                   # 单图逻辑像素（W,H）= SIZE_X/Y
    """
    # 逻辑像素分辨率（scale=1）
    res_1x = meters_per_pixel(zoom)

    # 单图逻辑像素
    world_px_w = SIZE_X
    world_px_h = SIZE_Y

    # 每张图地面覆盖（米）——注意：scale 不改变覆盖范围
    eff_w_m = world_px_w * res_1x
    eff_h_m = world_px_h * res_1x

    # 网格步进（逻辑像素）
    step_px_world_x = max(1, int(round(world_px_w * (1.0 - overlap_ratio))))
    step_px_world_y = max(1, int(round(world_px_h * (1.0 - overlap_ratio))))

    # 对应地面步长（米）
    step_w_m = step_px_world_x * res_1x
    step_h_m = step_px_world_y * res_1x

    # 计算网格列/行数 + 总拼图逻辑像素尺寸
    if width_m <= eff_w_m:
        grid_cols = 1
        mosaic_px_world_w = world_px_w
    else:
        n_steps_x = math.ceil((width_m - eff_w_m) / step_w_m)
        grid_cols = n_steps_x + 1
        mosaic_px_world_w = world_px_w + n_steps_x * step_px_world_x

    if height_m <= eff_h_m:
        grid_rows = 1
        mosaic_px_world_h = world_px_h
    else:
        n_steps_y = math.ceil((height_m - eff_h_m) / step_h_m)
        grid_rows = n_steps_y + 1
        mosaic_px_world_h = world_px_h + n_steps_y * step_px_world_y

    # 渲染像素尺寸（乘以 SCALE）
    eff_px_render_w = world_px_w * SCALE
    eff_px_render_h = world_px_h * SCALE
    step_px_render_x = step_px_world_x * SCALE
    step_px_render_y = step_px_world_y * SCALE
    mosaic_px_render_w = mosaic_px_world_w * SCALE
    mosaic_px_render_h = mosaic_px_world_h * SCALE

    # 组合像素总量保护（以渲染像素计）
    total_pixels = mosaic_px_render_w * mosaic_px_render_h
    if total_pixels > MAX_TOTAL_PIXELS:
        raise MemoryError(
            f"拼接图过大：{mosaic_px_render_w}x{mosaic_px_render_h} ≈ {total_pixels/1e6:.1f} MP，"
            f"超过上限 {MAX_TOTAL_PIXELS/1e6:.0f} MP。请降低范围或 zoom。"
        )

    # 用 Web Mercator 计算整个拼图的左上角（米）——注意用“逻辑像素 * res_1x”
    center_mx, center_my = lonlat_to_mercator(center_lon, center_lat)
    mosaic_w_m = mosaic_px_world_w * res_1x
    mosaic_h_m = mosaic_px_world_h * res_1x
    top_left_mx = center_mx - mosaic_w_m / 2.0
    top_left_my = center_my + mosaic_h_m / 2.0

    return (
        grid_cols, grid_rows,
        step_px_world_x, step_px_world_y,
        step_px_render_x, step_px_render_y,
        eff_px_render_w, eff_px_render_h,
        mosaic_px_render_w, mosaic_px_render_h,
        top_left_mx, top_left_my,
        res_1x,
        world_px_w, world_px_h
    )

def run_static_mosaic(center_lat, center_lon, width_m, height_m, zoom,
                      out_dir="output_static",
                      overlap_ratio=0.10, maptype=MAPTYPE,
                      save_name_prefix=None, make_pgw=True, make_dxf=False):
    """
    主流程：下载 + 拼接 + 世界文件 (+ 可选 DXF)
    * 所有几何/坐标用 1x 逻辑像素 + res_1x（米/逻辑像素）
    * 画布与粘贴偏移用渲染像素（乘以 SCALE）
    """
    os.makedirs(out_dir, exist_ok=True)
    if save_name_prefix is None:
        save_name_prefix = f"static_{maptype}_z{zoom}"

    (
        grid_cols, grid_rows,
        step_px_world_x, step_px_world_y,
        step_px_render_x, step_px_render_y,
        eff_px_render_w, eff_px_render_h,
        mosaic_px_render_w, mosaic_px_render_h,
        top_left_mx, top_left_my,
        res_1x,
        world_px_w, world_px_h
    ) = plan_grid_center_range(
        center_lon=center_lon, center_lat=center_lat,
        width_m=width_m, height_m=height_m, zoom=zoom,
        overlap_ratio=overlap_ratio
    )

    print(f"[PLAN] cols x rows = {grid_cols} x {grid_rows}")
    print(f"[PLAN] step_world_px = {step_px_world_x} x {step_px_world_y}, per_img_world_px = {world_px_w} x {world_px_h}")
    print(f"[PLAN] step_render_px = {step_px_render_x} x {step_px_render_y}, per_img_render_px = {eff_px_render_w} x {eff_px_render_h}")
    print(f"[PLAN] mosaic_render_px = {mosaic_px_render_w} x {mosaic_px_render_h}, res_1x={res_1x:.6f} m/px, scale={SCALE}")

    mosaic = Image.new("RGB", (mosaic_px_render_w, mosaic_px_render_h), (255, 255, 255))

    # 为每一格计算中心点（Web Mercator），再转回经纬度请求 Static
    for j in range(grid_rows):
        for i in range(grid_cols):
            # 本块中心（米）——全部基于“逻辑像素 * res_1x”
            cx_m = top_left_mx + (world_px_w / 2 + i * step_px_world_x) * res_1x
            cy_m = top_left_my - (world_px_h / 2 + j * step_px_world_y) * res_1x

            lon, lat = mercator_to_lonlat(cx_m, cy_m)

            tile_name = f"{save_name_prefix}_{j:02d}_{i:02d}.png"
            tile_path = os.path.join(out_dir, tile_name)

            ok = download_static(lat=lat, lon=lon, zoom=zoom, out_path=tile_path)
            if not ok:
                print(f"[WARN] 下载失败，留空：({i},{j})")
                continue

            try:
                im = Image.open(tile_path).convert("RGB")
            except Exception as e:
                print(f"[WARN] 打开失败 {tile_path}: {e}")
                continue

            # 粘贴位置（渲染像素）
            px = i * step_px_render_x
            py = j * step_px_render_y

            # 保险：如果返回尺寸不是期望的（例如 API 变动），可居中/调整
            # 这里简单直接粘贴
            mosaic.paste(im, (px, py))

            time.sleep(SLEEP_BETWEEN)

    mosaic_path = os.path.join(out_dir, f"{save_name_prefix}_mosaic.png")
    mosaic.save(mosaic_path)
    print(f"[OK] 拼接完成 → {mosaic_path}")

    wld_path = None
    if make_pgw:
        # PGW（世界文件）：A D B E C F
        # A = 像素宽方向地面分辨率（米/渲染像素）
        # E = 像素高方向地面分辨率（通常为 -A）
        # 注意：渲染像素的米/像素 = res_1x / SCALE
        A = res_1x / SCALE
        D = 0.0
        B = 0.0
        E = -res_1x / SCALE
        # C/F = 左上像素中心的地理坐标（米）
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
    center_lat = 53.275367
    center_lon = -9.043783

    # 目标覆盖范围（米）
    width_m = 400    # 左右方向覆盖宽
    height_m = 400   # 上下方向覆盖高

    # 清晰度（zoom越大越清）
    zoom = 18       # 可尝试 20（视地区可用性）

    out_dir = "out_static"
    overlap_ratio = 0.10  # 相邻子图重叠 10%（减少接缝）

    run_static_mosaic(center_lat, center_lon, width_m, height_m, zoom,
                      out_dir=out_dir, overlap_ratio=overlap_ratio,
                      maptype=MAPTYPE, save_name_prefix=None,
                      make_pgw=True, make_dxf=True)
