import qrcode
from PIL import Image
import os
import time

def render_qr_terminal(url):
    """
    在终端用字符画显示二维码（简化版）
    返回字符串，可直接打印
    """
    # 生成 PIL 图像
    qr = qrcode.QRCode(box_size=1, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    # 转成黑白像素矩阵
    pixels = img.load()
    w, h = img.size
    # 字符映射（半块字符更好看，这里用简单方块）
    lines = []
    for y in range(0, h, 2):
        line = ''
        for x in range(w):
            top = pixels[x, y] == 0  # 黑为 True
            bottom = (y + 1 < h) and (pixels[x, y+1] == 0)
            if top and bottom:
                line += '█'
            elif top and not bottom:
                line += '▀'
            elif not top and bottom:
                line += '▄'
            else:
                line += ' '
        lines.append(line)
    return '\n'.join(lines)

def format_time():
    return time.strftime('%H:%M:%S')