import requests

def download_image(url, save_path):
    """
    直接从 URL 下载图片并保存。
    支持 Apple Maps / satellites.pro / Google Maps / 任意图片 URL。
    """
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(r.content)
            print("下载完成:", save_path)
        else:
            print("下载失败，HTTP 状态码:", r.status_code)
    except Exception as e:
        print("下载过程中发生错误:", e)


# 在这里把你的 Apple Maps URL 粘贴进来！
url = "https://sat-cdn.apple-mapkit.com/tile?style=7&size=1&scale=1&z=19&x=253085&y=170034&v=10311&accessKey=1770310977_4654790101657753386_%2F_zTQ3u5D2b55P3wb0%2Fxi47O6AgB6RKTFyoN4Op%2BB5ibI%3D"

# 保存的文件名
save_name = "tile.jpg"

# 执行下载
download_image(url, save_name)