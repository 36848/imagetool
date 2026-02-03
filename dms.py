import re

def dms_to_decimal(dms_str: str) -> float:
    """
    将 DMS 字符串（例如：53°07'04.7"N 或 9°08'30.9"W）转换为十进制度（float）。
    支持可选的空格与大小写，方向 N/S/E/W 用于确定正负。
    """
    s = dms_str.strip().upper()

    # 提取方向（可选）
    sign = 1
    if s.endswith('S') or s.endswith('W'):
        sign = -1
        s = s[:-1].strip()
    elif s.endswith('N') or s.endswith('E'):
        sign = 1
        s = s[:-1].strip()

    # 允许的分隔：度符°、分符'、秒符" 或者 空格/冒号
    # 尽量同时兼容 53°07'04.7" / 53 07 04.7 / 53:07:04.7 三类写法
    # 先把常见分隔统一替换为空格
    s = s.replace('°', ' ').replace("'", ' ').replace('"', ' ')
    s = s.replace(':', ' ')
    # 再按空格切分
    parts = [p for p in re.split(r'\s+', s) if p]

    if len(parts) == 3:
        deg, minu, sec = parts
    elif len(parts) == 2:
        # 若只有度和分（无秒）
        deg, minu = parts
        sec = '0'
    elif len(parts) == 1:
        # 若只有度（无分秒）
        deg = parts[0]
        minu = '0'
        sec = '0'
    else:
        raise ValueError(f"DMS 格式无法解析：{dms_str}")

    deg = float(deg)
    minu = float(minu)
    sec = float(sec)

    decimal = sign * (deg + minu/60.0 + sec/3600.0)
    return decimal