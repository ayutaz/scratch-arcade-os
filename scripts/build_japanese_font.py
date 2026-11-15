"""OFLフォントから固定UI用20px字形を生成する。元TTFはGit管理しない。"""

import argparse
import hashlib
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

LABELS = ('開始', '停止', '戻る', '残り', 'タイマー', '時間', '設定', '再開',
          '完了', 'リセット', 'ゲーム', '結果', '得点', '最高', '再挑戦', '一時停止', '保存失敗')


def pack(rows, width, height):
    stride = (width + 7) // 8
    output = bytearray(stride * height)
    for y in range(height):
        for x in range(width):
            if rows[y][x]:
                output[y * stride + x // 8] |= 128 >> (x % 8)
    return bytes(output)


def rasterize(path, characters, size=20):
    with TTFont(path) as source:
        cmap = source.getBestCmap()
        if any(ord(char) not in cmap for char in characters):
            raise ValueError('フォントにない文字です')
    font = ImageFont.truetype(str(path), size)
    font.set_variation_by_axes([500])
    result = {}
    for char in sorted(set(characters)):
        image = Image.new('L', (size, size))
        ImageDraw.Draw(image).text((0, size - 2), char, font=font, fill=255, anchor='ls')
        result[char] = pack([[image.getpixel((x, y)) >= 128 for x in range(size)]
                            for y in range(size)], size, size)
    return result
