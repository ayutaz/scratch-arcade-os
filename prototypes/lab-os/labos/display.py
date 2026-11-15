"""320x240のホスト描画。実機LCDの初期化や性能を再現しない。"""
import hashlib
import importlib.util
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[1]
FONT_PATH = BASE / 'assets/glyphs.json'
FONT_SHA = 'c2f3b4d463500a2ddcd3849cded1fceeb9fd6d1c32e6cbecd568453ba50fc68f'
LABELS = ('ホーム', 'ゲーム', 'カウンター', '起動', '選択', '開始', '終了', '戻る',
          'ホームに戻ります', 'キーを離してください', 'アプリがありません',
          'アプリを停止しました', '更新しました', '削除しました', '資源の解放に失敗しました')


def build_font(source, target):
    """確認済みOFL原本だけを使い、固定20pxの部分字形を生成する。"""
    source, target = Path(source), Path(target)
    if hashlib.sha256(source.read_bytes()).hexdigest() != FONT_SHA:
        raise ValueError('font source hash')
    spec = importlib.util.spec_from_file_location('lab_font_builder', ROOT / 'scripts/build_japanese_font.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    characters = {c for c in ''.join(LABELS) if ord(c) > 127}
    glyphs = module.rasterize(source, characters)
    data = {'size': 20, 'source_sha256': FONT_SHA,
            'glyphs': {c: b.hex() for c, b in sorted(glyphs.items())}}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    return data


def load_font():
    return json.loads(FONT_PATH.read_text())


def key_mask(names):
    mapping = {'right': 1, 'left': 2, 'down': 4, 'up': 8,
               'z': 16, 'r': 32, 'x': 64, 'f': 128}
    return sum(bit for name, bit in mapping.items() if name in names)


def rgb565(value):
    r, g, b = (value >> 11) & 31, (value >> 5) & 63, value & 31
    return (r * 255 // 31, g * 255 // 63, b * 255 // 31)


class Text:
    def __init__(self, image):
        self.image = image
        self.draw = ImageDraw.Draw(image)
        self.font = load_font()['glyphs']
        self.latin = ImageFont.load_default(size=13)

    def write(self, xy, value, fill='#edf5ff', max_x=308):
        x, y = xy
        for char in value:
            width = 8 if ord(char) < 128 else 20
            if x + width > max_x:
                break
            if ord(char) < 128:
                self.draw.text((x, y + 3), char, font=self.latin, fill=fill)
            elif char in self.font:
                raw = bytes.fromhex(self.font[char])
                for row in range(20):
                    for col in range(20):
                        if raw[row * 3 + col // 8] & (128 >> (col % 8)):
                            self.draw.point((x + col, y + row), fill=fill)
            else:
                # 未収録の任意文字は欠字マークで示し、全文対応を装わない。
                self.draw.rectangle((x + 2, y + 2, x + 17, y + 17), outline=fill)
            x += width


def render(home):
    image = Image.new('RGB', (320, 240), '#000000' if home.mode == 'running' else '#101c2b')
    draw = ImageDraw.Draw(image)
    text = Text(image)
    if home.mode == 'running':
        for x, y, w, h, color in home.commands:
            draw.rectangle((x, y, x + w - 1, y + h - 1), fill=rgb565(color))
        return image
    if home.mode == 'release':
        text.write((70, 82), 'ホームに戻ります')
        text.write((50, 117), 'キーを離してください')
        return image
    draw.rectangle((0, 0, 319, 43), fill='#1d3048')
    text.write((12, 10), 'Lab App OS')
    text.write((244, 10), 'ホーム')
    for i, app in enumerate(home.apps):
        # 選択位置を含む最大2件の窓。アプリ件数は2件に制限しない。
        start = max(0, home.selected - 1)
        if not start <= i < start + 2:
            continue
        y = 56 + (i - start) * 58
        selected = i == home.selected
        draw.rounded_rectangle((12, y, 307, y + 51), radius=6,
                               fill='#285b83' if selected else '#1b2b3f',
                               outline='#76d4ff' if selected else '#34465b')
        text.write((24, y + 4), app['title'])
        text.write((24, y + 28), app['id'] + '  v' + app['version'], fill='#adc5dc')
    if not home.apps:
        text.write((60, 85), 'アプリがありません')
    text.write((12, 178), home.notice, fill='#f0cb8b')
    if home.failures:
        text.write((12, 202), 'ERROR: ' + ', '.join(sorted(home.failures)), fill='#ffaaa2')
    else:
        text.write((12, 210), 'Z(A): 起動  UP/DOWN: 選択', fill='#adc5dc')
    return image
