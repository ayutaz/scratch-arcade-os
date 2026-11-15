"""確認済みの部分字形からCのROM用headerを生成する。"""
import hashlib
import json
from pathlib import Path

from .display import FONT_PATH, FONT_SHA, LABELS


def generate(output, source=FONT_PATH):
    source, output = Path(source), Path(output)
    raw = source.read_bytes()
    data = json.loads(raw)
    required = {c for c in ''.join(LABELS) if ord(c) > 127}
    if data.get('size') != 20 or data.get('source_sha256') != FONT_SHA or set(data.get('glyphs', {})) != required:
        raise ValueError('fixed UI font source/schema')
    glyphs = []
    for char, text in sorted(data['glyphs'].items()):
        bits = bytes.fromhex(text)
        if len(bits) != 60 or not any(bits):
            raise ValueError('UI glyph size/empty')
        glyphs.append((ord(char), bits))
    lines = ['/* Lab OS UI Bitmap. Noto Sans JP derivative / SIL OFL 1.1.',
             ' * Copyright 2014-2021 Adobe. See prototypes/lab-os/assets/OFL.txt. */',
             '#ifndef LAB_UI_FONT_H', '#define LAB_UI_FONT_H', '#include <stdint.h>',
             'typedef struct {uint32_t codepoint; uint8_t bits[60];} LabUiGlyph;',
             '#define LAB_UI_GLYPH_COUNT ' + str(len(glyphs)),
             'static const LabUiGlyph lab_ui_font[] = {']
    for codepoint, bits in glyphs:
        lines.append('    {0x%x, {%s}},' % (codepoint, ','.join('0x%02x' % b for b in bits)))
    lines += ['};', '#endif', '']
    output.mkdir(parents=True, exist_ok=True)
    (output / 'lab_ui_font.h').write_text('\n'.join(lines))
    return {'glyphs': len(glyphs), 'bitmap_bytes': sum(len(b) for _, b in glyphs),
            'source_sha256': FONT_SHA, 'input_sha256': hashlib.sha256(raw).hexdigest()}
