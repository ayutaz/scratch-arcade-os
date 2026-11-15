/* 320x240 scanline UI shared by host rendering and the non-flashing S3 core. */
#include "ui.h"
#include "lab_ui_font.h"
#include "micropython-1.25.0-font_petme128_8x8.h"
#include <stdio.h>

#define RGB(r,g,b) ((uint16_t)((((r)>>3)<<11)|(((g)>>2)<<5)|((b)>>3)))
#define BG RGB(16,28,43)
#define FG RGB(237,245,255)

static const uint8_t *glyph(uint32_t codepoint) {
    for(unsigned i=0;i<LAB_UI_GLYPH_COUNT;i++)
        if(lab_ui_font[i].codepoint==codepoint)return lab_ui_font[i].bits;
    return NULL;
}
static uint32_t next_char(const char *text,size_t limit,size_t *at) {
    unsigned char c=(unsigned char)text[(*at)++];
    if(c<128)return c;
    unsigned rest=c>=0xc2 && c<=0xdf ? 1 : c>=0xe0 && c<=0xef ? 2 : c>=0xf0 && c<=0xf4 ? 3 : 0;
    if(!rest || *at+rest>limit)return 0xfffd;
    uint32_t value=c & (rest==1 ? 31 : rest==2 ? 15 : 7);
    for(unsigned i=0;i<rest;i++) {
        unsigned char b=(unsigned char)text[*at+i];
        if((b & 0xc0)!=0x80)return 0xfffd;
        value=(value<<6)|(b & 63);
    }
    *at+=rest;
    if((rest==1 && value<128) || (rest==2 && value<2048) || (rest==3 && value<65536) ||
       value>0x10ffff || (value>=0xd800 && value<=0xdfff))return 0xfffd;
    return value;
}
static void text_row(uint16_t *pixels,uint32_t y,int x,int top,const char *text,size_t limit,uint16_t color) {
    if((int)y<top || (int)y>=top+20)return;
    unsigned line=y-(unsigned)top;
    size_t at=0;
    while(at<limit && text[at]) {
        uint32_t c=next_char(text,limit,&at);
        unsigned width=c<128 ? 8 : 20;
        if(x+(int)width>308)break;
        const uint8_t *bits=c>=128 ? glyph(c) : NULL;
        for(unsigned col=0;col<width;col++) {
            bool on=false;
            if(c>=32 && c<=127 && line>=2 && line<18)
                on=(font_petme128_8x8[(c-32)*8+col] & (1u<<((line-2)/2)))!=0;
            else if(c>=128 && bits)on=(bits[line*3+col/8] & (128u>>(col%8)))!=0;
            else if(c>=128)on=(line>=2 && line<=17 && (col==2 || col==17)) ||
                                ((line==2 || line==17) && col>=2 && col<=17);
            if(on && x+(int)col>=0)pixels[x+col]=color;
        }
        x+=(int)width;
    }
}
#define TEXT(x,top,value,color) text_row(pixels,y,x,top,value,sizeof(value)-1,color)

static void rectangle(uint16_t *pixels,uint32_t y,int x,int top,int width,int height,uint16_t color) {
    if((int)y<top || (int)y>=top+height)return;
    for(int i=x;i<x+width;i++)pixels[i]=color;
}
static bool valid(const LabHome *home,uint32_t y) {
    if(!home || y>=240 || home->count>LAB_MAX_APPS ||
       (home->count && home->selected>=home->count) ||
       (!home->count && home->selected) || (unsigned)home->notice>LAB_NOTICE_NETWORK)return false;
    if(home->mode==LAB_RUNNING) {
        if(home->vm.draw_count>128)return false;
        for(uint32_t i=0;i<home->vm.draw_count;i++) {
            const int32_t *r=home->vm.draws[i];
            if(r[0]<0 || r[0]>=320 || r[1]<0 || r[1]>=240 || r[2]<1 || r[2]>320-r[0] ||
               r[3]<1 || r[3]>240-r[1] || r[4]<0 || r[4]>65535)return false;
        }
    }
    return home->mode==LAB_HOME || home->mode==LAB_RUNNING || home->mode==LAB_RELEASE || home->mode==LAB_CLEANUP;
}
bool lab_ui_row(const LabHome *home,uint32_t y,uint16_t pixels[320]) {
    if(!pixels || !valid(home,y))return false;
    for(unsigned i=0;i<320;i++)pixels[i]=home->mode==LAB_RUNNING ? 0 : BG;
    if(home->mode==LAB_RUNNING) {
        for(uint32_t i=0;i<home->vm.draw_count;i++) {
            const int32_t *r=home->vm.draws[i];
            rectangle(pixels,y,r[0],r[1],r[2],r[3],(uint16_t)r[4]);
        }
        return true;
    }
    if(home->mode==LAB_CLEANUP) {
        TEXT(70,82,"ホームに戻ります",FG);TEXT(130,117,"WAIT...",FG);return true;
    }
    if(home->mode==LAB_RELEASE) {
        if(home->notice==LAB_NOTICE_FAULT) {TEXT(50,82,"アプリを停止しました",FG);}
        else {TEXT(70,82,"ホームに戻ります",FG);}
        TEXT(50,117,"キーを離してください",FG);
        return true;
    }
    rectangle(pixels,y,0,0,320,44,RGB(29,48,72));
    TEXT(12,10,"Lab App OS",FG);TEXT(244,10,"ホーム",FG);
    uint32_t start=home->selected ? home->selected-1 : 0;
    for(uint32_t i=start;i<home->count && i<start+2;i++) {
        int top=56+(int)(i-start)*58;
        bool selected=i==home->selected;
        uint16_t border=selected ? RGB(118,212,255) : RGB(52,70,91);
        uint16_t fill=selected ? RGB(40,91,131) : RGB(27,43,63);
        rectangle(pixels,y,12,top,296,52,border);
        rectangle(pixels,y,13,top+1,294,50,fill);
        text_row(pixels,y,24,top+4,home->apps[i].title,80,FG);
        char label[64];
        snprintf(label,sizeof(label),"%.*s  v%.*s",32,home->apps[i].id,24,home->apps[i].version);
        text_row(pixels,y,24,top+28,label,sizeof(label),RGB(173,197,220));
    }
    if(!home->count) {TEXT(60,85,"アプリがありません",FG);}
    switch(home->notice) {
        case LAB_NOTICE_FAULT:TEXT(12,178,"アプリを停止しました",RGB(255,170,162));break;
        case LAB_NOTICE_AUDIO:TEXT(12,178,"AUDIO UNAVAILABLE",RGB(255,170,162));break;
        case LAB_NOTICE_NETWORK:TEXT(12,178,"NETWORK UNAVAILABLE",RGB(255,170,162));break;
        case LAB_NOTICE_STORAGE:TEXT(12,178,"STORAGE ERROR",RGB(255,170,162));break;
        case LAB_NOTICE_HOST_INPUT:TEXT(12,178,"INPUT ERROR",RGB(255,170,162));break;
        default:break;
    }
    TEXT(12,210,"A: 起動  UP/DOWN: 選択",RGB(173,197,220));
    return true;
}

bool lab_ui_render(const LabHome *home,LabUiSink sink,void *context) {
    if(!sink)return false;
    uint16_t pixels[320];
    for(uint32_t y=0;y<240;y++)
        if(!lab_ui_row(home,y,pixels) || !sink(context,y,pixels))return false;
    return true;
}
