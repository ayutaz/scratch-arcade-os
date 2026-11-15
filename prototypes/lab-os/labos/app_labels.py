"""確認済みOFLフォントから、app内専用の固定12pxラベルを生成する。"""
import hashlib
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from .display import FONT_SHA

ROOT=Path(__file__).resolve().parents[3]
FONT=ROOT/'downloads/fonts/NotoSansJP-pinned.ttf'
LABELS={'START':'A:開始','PAUSE':'A:停止','RESUME':'A:再開','END':'B:終了',
        'MOVE':'左右','RECORD':'A:録音','PLAY':'X:再生','STOP':'下:停止','DONE':'完了'}


def rasterize_font(text):
    raw=FONT.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=FONT_SHA:raise ValueError('fixed font required')
    font=ImageFont.truetype(str(FONT),12);font.set_variation_by_axes([500])
    width=round(font.getlength(text))+2;img=Image.new('L',(width,16))
    ImageDraw.Draw(img).text((0,1),text,font=font,fill=255,anchor='lt')
    return [[int(img.getpixel((x,y))>=128) for x in range(width)] for y in range(16)]


DATA=ROOT/'prototypes/lab-os/assets/app-labels.json'
DATA_SHA='027ce06670f68f310918063187c31b1b599c3ed04375197fd2084df01119829f'

def bitmap(text):
    raw=DATA.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('fixed derived labels required')
    data=json.loads(raw)
    if data['source_sha256']!=FONT_SHA:raise ValueError('font provenance')
    item=next((v for v in data['labels'].values() if v['text']==text),None)
    if item is None:raise ValueError('fixed label required')
    w=item['width'];stride=(w+7)//8;bits=bytes.fromhex(item['bits'])
    return [[int(bool(bits[y*stride+x//8] & (128>>(x%8)))) for x in range(w)] for y in range(16)]


def _horizontal(pixels):
    active={};output=[]
    for y,row in enumerate(pixels):
        runs=[];x=0
        while x<len(row):
            if not row[x]:x+=1;continue
            start=x
            while x<len(row) and row[x]:x+=1
            runs.append((start,x-start))
        next_active={}
        for x,w in runs:
            r=active.pop((x,w),[x,y,w,0]);r[3]+=1;next_active[x,w]=r
        output.extend(active.values());active=next_active
    output.extend(active.values());return output


def rectangles(pixels):
    horizontal=_horizontal(pixels)
    vertical=[[y,x,h,w] for x,y,w,h in _horizontal(list(map(list,zip(*pixels))))]
    return horizontal if len(horizontal)<=len(vertical) else vertical


def generate(path):
    lines=['/* Noto Sans JP derivative / SIL OFL 1.1. Copyright 2014-2021 Adobe.',
           ' * Source SHA-256: '+FONT_SHA,
           ' * License: assets/fonts/japanese/OFL.txt */',
           '#ifndef LAB_APP_LABELS_H','#define LAB_APP_LABELS_H','#include "lab_os.h"']
    for key,text in LABELS.items():
        runs=rectangles(bitmap(text))
        lines.append('static const uint8_t lab_label_'+key+'[][4]={'+','.join('{'+','.join(map(str,r))+'}' for r in runs)+'};')
    lines+=['enum {'+','.join('LAB_LABEL_'+key for key in LABELS)+'};',
            'static inline void lab_label(unsigned id,int32_t x,int32_t y,int32_t color){',
            ' const uint8_t (*p)[4]=0;unsigned count=0;switch(id){']
    for key in LABELS:
        lines.append(' case LAB_LABEL_'+key+':p=lab_label_'+key+';count=sizeof(lab_label_'+key+')/4;break;')
    lines+=[' default:return;}',' for(unsigned i=0;i<count;i++)rect(x+p[i][0],y+p[i][1],p[i][2],p[i][3],color);','}','#endif','']
    Path(path).write_text('\n'.join(lines))
