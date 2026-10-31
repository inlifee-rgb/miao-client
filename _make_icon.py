# -*- coding: utf-8 -*-
"""生成 MIAO 图标「主体放大」版本 + 任务栏尺寸对比图"""
from PIL import Image, ImageDraw, ImageFont

SRC = r'E:\dorimi\ai\wb_oauth\console\app-icon.png'
OUT_NEW = r'E:\dorimi\ai\wb_oauth\console\app-icon-big.png'
OUT_CMP = r'E:\dorimi\ai\wb_oauth\console\_icon_compare.png'

BG = (242, 247, 255, 255)
CROP = (176, 166, 848, 786)      # 猫头实际 bbox
TARGET_RATIO = 0.88              # 新版主体占画布比例
SIZE = 1024
RADIUS = 210


def rounded_bg(size, radius):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=BG)
    return img


def make_big():
    src = Image.open(SRC).convert('RGBA')
    cat = src.crop(CROP)
    cw, ch = cat.size
    tw = int(SIZE * TARGET_RATIO)
    th = int(tw * ch / cw)
    if th > SIZE * TARGET_RATIO:
        th = int(SIZE * TARGET_RATIO)
        tw = int(th * cw / ch)
    cat = cat.resize((tw, th), Image.LANCZOS)
    canvas = rounded_bg(SIZE, RADIUS)
    canvas.alpha_composite(cat, ((SIZE - tw) // 2, (SIZE - th) // 2))
    canvas.save(OUT_NEW)
    return canvas


def small(img, px):
    return img.resize((px, px), Image.LANCZOS)


old = Image.open(SRC).convert('RGBA')
new = make_big()

SIZES = [16, 24, 32, 48]
CELL = 150
PAD_TOP = 46
W = CELL * len(SIZES) + 40
H = PAD_TOP + CELL * 2 + 60
cmp_img = Image.new('RGB', (W, H), (243, 243, 243))
d = ImageDraw.Draw(cmp_img)
try:
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 15)
    font_s = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 13)
except Exception:
    font = font_s = ImageFont.load_default()

for row, (label, img) in enumerate([('现版（猫头 60%）', old), ('新版（猫头 88%）', new)]):
    y0 = PAD_TOP + row * CELL
    d.text((12, y0 - 26), label, font=font, fill=(40, 40, 40))
    for i, px in enumerate(SIZES):
        x0 = 20 + i * CELL
        ic = small(img, px)
        scale = 100 // px
        big = ic.resize((px * scale, px * scale), Image.NEAREST)
        bx = x0 + (CELL - 100) // 2
        by = y0 + (CELL - 100) // 2
        cmp_img.paste(big, (bx, by), big if big.mode == 'RGBA' else None)
        d.text((x0 + CELL // 2 - 18, y0 + CELL - 16), '%dpx' % px, font=font_s, fill=(110, 110, 110))

cmp_img.save(OUT_CMP)
print('新图标:', OUT_NEW)
print('对比图:', OUT_CMP)
