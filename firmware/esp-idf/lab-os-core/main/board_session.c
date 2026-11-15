#include "board_session.h"
#include "control_wire.h"
#include <stddef.h>
#include <string.h>
/* Serialized OS task; failed cleanup retains this owner until a successful retry. */
static LabBoardSession *owner;
static void remote_cancel(LabBoardSession *s){
    if(s->remote.active)s->loop.gated=true;
    s->remote.active=false;s->remote.held=s->remote.duration=s->remote.session=s->remote.epoch=0;
}
static uint32_t remaining(LabBoardSession *s,uint32_t now){
    LabTransfer *t=&s->usb.transfer;uint32_t age=now-s->remote.started;
    return s->remote.active && s->usb.active && t->session==s->remote.session &&
           t->epoch==s->remote.epoch && age<s->remote.duration ? s->remote.duration-age : 0;
}
static void put32(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(i*8));}
static uint32_t draw_crc(const LabVm *vm){
    uint32_t crc=UINT32_MAX;
    for(uint32_t i=0;i<vm->draw_count;i++)for(unsigned k=0;k<5;k++)for(unsigned b=0;b<4;b++){
        crc^=(uint32_t)vm->draws[i][k]>>(8*b)&255;
        for(unsigned bit=0;bit<8;bit++)crc=(crc>>1)^(0xedb88320u & (0u-(crc&1u)));
    }
    return ~crc;
}
static int control(void *context,const uint8_t *p,uint32_t n,uint32_t now,uint8_t out[80]){
    LabBoardSession *s=context;
    if(!s || !s->ready || !out || !lab_control_wire_valid(p,n))return 0;
    if(lab_control_u32(p)==LAB_CONTROL_AUDIO){
        LabAudio *a=&s->sound.audio;
        int measured=lab_audio_peak(a);uint32_t peak=measured>0 ? (uint32_t)measured : 0;
        uint32_t fields[]={1,a->phase,a->owner!=0,a->driver_owned,a->capacity,a->recorded,
            a->total,a->position,a->kind,a->replaying,peak,(uint32_t)a->result};
        memset(out,0,80);for(unsigned i=0;i<12;i++)put32(out+4*i,fields[i]);return 1;
    }
    if(lab_control_u32(p)==LAB_CONTROL_AUDIO_METRICS){
        LabAudio *a=&s->sound.audio;LabAudioRecordingMetrics m;uint32_t bins[4];
        memset(out,0,80);put32(out,1);
        if(lab_audio_recording_metrics(a,a->owner,&m) && lab_audio_recording_bands(a,a->owner,bins)){
            uint32_t fields[]={1,1,m.frames,(uint32_t)m.minimum,(uint32_t)m.maximum,(uint32_t)m.mean,
                m.rms,m.ac_rms,m.centered_peak,m.saturated_frames,bins[0],bins[1],bins[2],bins[3],
                a->replay_gain,a->replay_scale_q15,s->sound.driver.discarded_input_frames};
            for(unsigned i=0;i<17;i++)put32(out+4*i,fields[i]);
        }
        return 1;
    }
    if(lab_control_u32(p)==LAB_CONTROL_PULSE){
        if(!s->physical_seen || !s->physical_neutral || !s->usb.active || !s->usb.transfer.session ||
           lab_transfer_busy(&s->usb.transfer))return 0;
        s->remote.held=lab_control_u32(p+4);s->remote.duration=lab_control_u32(p+8);
        s->remote.started=now;s->remote.session=s->usb.transfer.session;s->remote.epoch=s->usb.transfer.epoch;
        if(!++s->remote.generation)++s->remote.generation;
        s->remote.active=true;
        /* Explicit synthetic input may pass the USB HOME gate only after a
         * physical neutral sample. input() rechecks hardware before any frame. */
        if(s->home.mode==LAB_HOME)s->loop.gated=false;
    }
    if(s->home.vm.draw_count>128)return -1;
    uint32_t ms=remaining(s,now);
    uint32_t fields[]={1,s->home.mode,s->home.notice,s->home.selected,s->home.count,
        ms ? s->remote.held:0,ms,s->remote.generation,s->remote.applied,s->home.vm.draw_count,draw_crc(&s->home.vm)};
    memset(out,0,80);for(unsigned i=0;i<11;i++)put32(out+4*i,fields[i]);
    if(s->home.mode==LAB_RUNNING || s->home.mode==LAB_CLEANUP)memcpy(out+44,s->home.active_id,33);
    return 1;
}
static bool pending(const LabTransfer *t) {return t->session || t->upload || t->rx_size;}
static uint32_t services(void *context,uint32_t now) {
    LabBoardSession *s=context;
    lab_board_network_poll(&s->network,now);
    if(!s->usb.active){remote_cancel(s);return 0;}
    LabTransfer *t=&s->usb.transfer;
    bool before_pending=pending(t);
    /* false with active=true is TX backpressure, not a fatal lifecycle error. */
    lab_usb_transfer_poll(&s->usb,now);
    if(s->remote.active && (!remaining(s,now) || lab_transfer_busy(t) || t->rx_size))remote_cancel(s);
    uint32_t flags=s->usb.active && pending(t) ? LAB_SERVICE_INHIBIT_HOME : 0;
    /* End-state counters may be identical after reused OPEN/CLOSE IDs. */
    if(before_pending || !s->usb.active || s->usb.received)flags|=LAB_SERVICE_CHANGED;
    if(s->remote.active)flags=0;
    return flags;
}
static bool input(void *context,uint32_t now,LabInputSample *out) {
    LabBoardSession *s=context;
    if(!lab_board_input_read(&s->input,now,out)){
        s->physical_seen=s->physical_neutral=false;remote_cancel(s);return false;
    }
    s->physical_seen=true;s->physical_neutral=lab_input_is_neutral(out);
    /* Management may suppress HOME's neutral frame after a virtual pulse.
     * Release that cached edge on real neutral, without opening the gate or
     * executing Home/guest code during upload/collection. */
    if(s->home.mode==LAB_HOME && s->physical_neutral && !s->remote.active)s->home.previous_held=0;
    if(s->remote.active){
        if(!s->physical_neutral){remote_cancel(s);return false;}
        out->held=s->remote.held;s->remote.applied++;
    }
    return true;
}
static void audio_between_rows(void *context) {
    LabBoardSound *sound=context;
    /* Same actor, no guest execution or lifecycle changes. The frame's OS time
     * is reused; the next loop accounts for scanout time. Only bounded native
     * audio I/O progresses between rows, preserving the <=256-frame poll cap. */
    LabHomeAudio hooks=lab_board_sound_services(sound);
    if(hooks.poll)hooks.poll(hooks.context,sound->now);
}
static bool paint(void *context,const LabHome *home) {
    LabBoardSession *s=context;
    return lab_board_display_paint_serviced(&s->display,home,audio_between_rows,&s->sound);
}
bool lab_board_session_close(LabBoardSession *s) {
    if(!s)return false;
    s->ready=false;
    remote_cancel(s);memset(&s->remote,0,sizeof(s->remote));s->physical_seen=s->physical_neutral=false;
    lab_usb_transfer_close(&s->usb);
    if(s->loop_owned) {
        if(!lab_loop_close(&s->loop))return false;
        s->loop_owned=false;s->home_owned=false;
    }
    if(s->home_owned) {
        if(!lab_home_close(&s->home))return false;
        s->home_owned=false;
    }
    if(!lab_board_sound_close(&s->sound))return false;
    if(!lab_board_network_close(&s->network))return false;
    /* Attempt both devices, even when one cleanup fails. Keep failed objects. */
    if(s->input_owned && lab_board_input_close(&s->input))s->input_owned=false;
    if(s->display_owned && lab_board_display_close(&s->display))s->display_owned=false;
    if(s->input_owned || s->display_owned)return false;
    s->store=NULL;
    if(owner==s)owner=NULL;
    return true;
}
bool lab_board_session_open(LabBoardSession *s,LabStore *store,int profile,uint32_t nonce,uint32_t now) {
    if(!s || owner || s->store || s->home_owned || s->loop_owned || s->input_owned || s->display_owned ||
       s->ready || s->usb.active || s->sound.pcm.frames || s->sound.driver.channel || s->sound.manager.binding.audio ||
       s->network.configured || s->network.cleanup || s->network.driver.initialized || s->network.driver.netif ||
       s->network.socket.owned || s->network.udp.ready || s->network.manager.datagram ||
       !store || !store->mounted || store->lease || !nonce ||
       profile!=LAB_SESSION_PROFILE_STOCK_0111)return false;
    owner=s;s->store=store;
    LabCatalog catalog=lab_store_catalog(store);
    s->home_owned=true;
    if(!lab_home_init(&s->home,&catalog))goto failure;
    if(!lab_board_sound_init(&s->sound,LAB_AUDIO_PROFILE_STOCK_0111))goto failure;
    LabHomeAudio sound=lab_board_sound_services(&s->sound);
    if(!lab_home_set_audio(&s->home,&sound))goto failure;
    if(!lab_board_network_init(&s->network))goto failure;
    LabHomeNetwork network=lab_board_network_apps(&s->network);
    if(!lab_home_set_network(&s->home,&network))goto failure;
    /* Borrowed optional service; failure must not prevent battery/offline use. */
    lab_usb_transfer_attach(&s->usb,store,&s->home,nonce,now);
    if(s->usb.active && !lab_transfer_set_network(&s->usb.transfer,lab_board_network_control,&s->network))goto failure;
    if(s->usb.active && !lab_transfer_set_control(&s->usb.transfer,control,s))goto failure;
    s->display_owned=true;
    if(!lab_board_display_open(&s->display,LAB_DISPLAY_PROFILE_STOCK_0111))goto failure;
    s->input_owned=true;
    if(!lab_board_input_open(&s->input,LAB_INPUT_PROFILE_STOCK_0111))goto failure;
    LabLoopIo io={s,services,input,paint};
    if(!lab_loop_init(&s->loop,&s->home,&io,now))goto failure;
    s->loop_owned=true;s->ready=true;return true;
failure:
    lab_board_session_close(s);return false;
}
int lab_board_session_step(LabBoardSession *s,uint32_t now) {
    if(!s || !s->ready)return LAB_LOOP_STOPPED;
    int result=lab_loop_step(&s->loop,now);
    if(result==LAB_LOOP_STOPPED)lab_board_session_close(s);
    return result;
}
