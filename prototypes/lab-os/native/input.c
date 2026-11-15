#include "input.h"
static int axis(int raw) {
    int delta=raw-2048;
    if(delta>=-120 && delta<=120)return 0;
    int sign=delta<0 ? -1 : 1;
    int magnitude=delta<0 ? -delta-120 : delta-120;
    return sign*((magnitude*100+964)/1928);
}
bool lab_input_sample(LabInputFilter *f,uint32_t keys,int x_raw,int y_raw,uint32_t now,LabInputSample *out) {
    if(!f || !out || keys>31 || x_raw<0 || x_raw>4095 || y_raw<0 || y_raw>4095)return false;
    if(!f->primed) {
        f->stable=f->candidate=keys;f->primed=true;
        for(unsigned i=0;i<5;i++)f->changed[i]=now;
    } else for(unsigned i=0;i<5;i++) {
        uint32_t bit=1u<<i;
        if((keys^f->candidate)&bit) {f->candidate^=bit;f->changed[i]=now;}
        else if(now-f->changed[i]>=20)f->stable=(f->stable&~bit)|(keys&bit);
    }
    /* Conservative release gate: a raw press must never look neutral while
     * its debounced held edge is still pending. Stable releases also wait. */
    LabInputSample sample={.keys=keys|f->stable,.x=axis(x_raw),.y=axis(y_raw)};
    if(sample.x>LAB_INPUT_DIRECTION_THRESHOLD)sample.held|=2;
    if(sample.x<-LAB_INPUT_DIRECTION_THRESHOLD)sample.held|=1;
    if(sample.y>LAB_INPUT_DIRECTION_THRESHOLD)sample.held|=8;
    if(sample.y<-LAB_INPUT_DIRECTION_THRESHOLD)sample.held|=4;
    if(f->stable&LAB_KEY_FN)sample.held|=128;
    if(f->stable&LAB_KEY_A)sample.held|=16;
    if(f->stable&LAB_KEY_B)sample.held|=64;
    if(f->stable&LAB_KEY_X)sample.held|=32;
    *out=sample;return true;
}
