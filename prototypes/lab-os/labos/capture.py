"""C rendererのRGB565 LE frameを画素変換する。UIを描き直さない。"""
import array
import sys
from PIL import Image
from .display import rgb565


def decode_frame(data):
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ValueError('one 320x240 RGB565 LE frame required')
    data = bytes(data)
    if len(data) != 320 * 240 * 2:
        raise ValueError('one 320x240 RGB565 LE frame required')
    values = array.array('H')
    values.frombytes(data)
    if sys.byteorder != 'little':
        values.byteswap()
    image = Image.new('RGB', (320, 240))
    image.putdata([rgb565(value) for value in values])
    return image
