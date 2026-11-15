/* Platform-independent foreground app supervisor. No GPIO or filesystem code. */
#include "app_home.h"
#include <stddef.h>
#include <string.h>

static size_t length(const char *text, size_t max) {
    size_t n=0; while(n<max && text[n]) ++n; return n;
}
static bool valid_id(const char id[33]) {
    size_t n=length(id,33);
    if(!n || n>32 || id[0]<'a' || id[0]>'z')return false;
    for(size_t i=1;i<n;i++)
        if(!((id[i]>='a' && id[i]<='z') || (id[i]>='0' && id[i]<='9') || id[i]=='-'))return false;
    return true;
}
static bool valid_title(const char text[81]) {
    size_t n=length(text,81), count=0;
    if(!n || n>80)return false;
    for(size_t i=0;i<n;count++) {
        unsigned char c=(unsigned char)text[i++];
        if(c<0x80) {if(c<32 || c==127)return false;continue;}
        unsigned rest=c>=0xc2 && c<=0xdf ? 1 : c>=0xe0 && c<=0xef ? 2 : c>=0xf0 && c<=0xf4 ? 3 : 0;
        if(!rest || i+rest>n)return false;
        unsigned char next=(unsigned char)text[i];
        if((c==0xe0 && next<0xa0) || (c==0xed && next>=0xa0) ||
           (c==0xf0 && next<0x90) || (c==0xf4 && next>=0x90))return false;
        for(unsigned j=0;j<rest;j++) if(((unsigned char)text[i++] & 0xc0)!=0x80)return false;
    }
    return count<=20;
}
static bool valid_version(const char version[25]) {
    size_t n=length(version,25), at=0;
    if(!n || n>=25)return false;
    for(int part=0;part<3;part++) {
        size_t first=at;
        while(at<n && version[at]>='0' && version[at]<='9')++at;
        if(at==first || at-first>4)return false;
        if(part<2) {if(at>=n || version[at++]!='.')return false;}
    }
    return at==n;
}
static bool disabled(LabHome *home,const char *id) {
    for(uint32_t i=0;i<home->disabled_count;i++)if(!strcmp(home->disabled[i],id))return true;
    return false;
}
static void disable(LabHome *home,const char *id) {
    if(!disabled(home,id) && home->disabled_count<LAB_MAX_APPS)
        memcpy(home->disabled[home->disabled_count++],id,33);
}
static bool refresh(LabHome *home) {
    uint32_t count=home->catalog.count(home->catalog.context), accepted=0, selected=0;
    if(count>LAB_MAX_APPS)return false;
    LabAppInfo candidate[LAB_MAX_APPS]={0};
    char present[LAB_MAX_APPS][33]={{0}};
    uint32_t present_count=0;
    char old_id[33]={0};
    if(home->count)memcpy(old_id,home->apps[home->selected].id,33);
    for(uint32_t i=0;i<count;i++) {
        LabAppInfo info={0};
        if(!home->catalog.info(home->catalog.context,i,&info) ||
           !valid_id(info.id) || !valid_title(info.title) || !valid_version(info.version))continue;
        for(uint32_t j=0;j<present_count;j++)if(!strcmp(present[j],info.id))return false;
        memcpy(present[present_count++],info.id,33);
        if(!info.enabled || disabled(home,info.id))continue;
        if(!strcmp(old_id,info.id))selected=accepted;
        candidate[accepted++]=info;
    }
    if(home->count!=accepted || memcmp(home->apps,candidate,sizeof(candidate)))home->catalog_revision++;
    memcpy(home->apps,candidate,sizeof(candidate));
    home->count=accepted;home->selected=selected;
    uint32_t kept=0;
    for(uint32_t i=0;i<home->disabled_count;i++) {
        for(uint32_t j=0;j<present_count;j++)if(!strcmp(home->disabled[i],present[j])) {
            if(kept!=i)memcpy(home->disabled[kept],home->disabled[i],33);
            ++kept;break;
        }
    }
    home->disabled_count=kept;
    return true;
}
bool lab_home_init(LabHome *home,const LabCatalog *catalog) {
    if(!home || !catalog || !catalog->count || !catalog->info || !catalog->open || !catalog->release)return false;
    memset(home,0,sizeof(*home));home->catalog=*catalog;home->mode=LAB_HOME;
    return refresh(home);
}
bool lab_home_refresh(LabHome *home) {
    return home && home->mode==LAB_HOME && refresh(home);
}
bool lab_home_set_audio(LabHome *home,const LabHomeAudio *audio) {
    if(!home || !home->catalog.count || home->mode!=LAB_HOME || home->audio_owned || home->network_owned || home->state_owned ||
       home->image.bytes || home->image.lease || home->vm.instance ||
       (audio && (!audio->open || !audio->poll || !audio->close)))return false;
    home->audio=audio ? *audio : (LabHomeAudio){0};return true;
}
bool lab_home_set_network(LabHome *home,const LabHomeNetwork *network) {
    if(!home || !home->catalog.count || home->mode!=LAB_HOME || home->network_owned || home->audio_owned || home->state_owned ||
       home->image.bytes || home->image.lease || home->vm.instance ||
       (network && (!network->open || !network->poll || !network->close)))return false;
    home->network=network ? *network : (LabHomeNetwork){0};return true;
}
bool lab_home_set_state(LabHome *home,const LabHomeState *state) {
    if(!home || !home->catalog.count || home->mode!=LAB_HOME || home->state_owned ||
       home->audio_owned || home->network_owned || home->image.bytes || home->image.lease || home->vm.instance ||
       (state && (!state->open || !state->poll || !state->close)))return false;
    home->state=state ? *state : (LabHomeState){0};return true;
}
static void finish_failed(LabHome *home) {
    char id[33];memcpy(id,home->failed_id,33);
    bool quarantine=home->pending_quarantine;
    home->pending_failure=home->pending_quarantine=false;memset(home->failed_id,0,33);
    if(!quarantine || !home->catalog.quarantine || !home->catalog.quarantine(home->catalog.context,id))disable(home,id);
    if(!refresh(home)) {
        disable(home,id);
        uint32_t n=0;
        for(uint32_t i=0;i<home->count;i++)
            if(!disabled(home,home->apps[i].id))home->apps[n++]=home->apps[i];
        home->count=n;home->selected=0;
    }
}
static bool release(LabHome *home,uint32_t reason) {
    lab_vm_close(&home->vm,reason);
    home->release_reason=reason;home->mode=LAB_CLEANUP;
    bool closed=true;
    if(home->network_owned) {
        if(home->network.close(home->network.context))home->network_owned=false;
        else closed=false;
    }
    if(home->audio_owned) {
        if(home->audio.close(home->audio.context))home->audio_owned=false;
        else closed=false;
    }
    if(home->state_owned) {
        if(home->state.close(home->state.context))home->state_owned=false;
        else closed=false;
    }
    if(!closed)return false;
    if(home->image.bytes || home->image.lease)home->catalog.release(home->catalog.context,&home->image);
    memset(&home->image,0,sizeof(home->image));
    memset(home->active_id,0,sizeof(home->active_id));home->mode=LAB_RELEASE;
    if(home->pending_failure)finish_failed(home);
    return true;
}
static void failed(LabHome *home,LabHomeNotice notice,bool quarantine) {
    memcpy(home->failed_id,home->active_id,33);
    home->pending_failure=true;home->pending_quarantine=quarantine;home->notice=notice;
    release(home,2);
}
static void launch(LabHome *home,uint32_t held) {
    if(!home->count)return;
    memcpy(home->active_id,home->apps[home->selected].id,33);
    if(!home->catalog.open(home->catalog.context,home->active_id,&home->image)) {
        failed(home,LAB_NOTICE_STORAGE,false);return;
    }
    LabVmAudio audio={0};
    if((home->image.capabilities&6) && home->audio.open) {
        home->audio_owned=true;
        if(!home->audio.open(home->audio.context,home->image.capabilities,&audio)) {
            home->notice=LAB_NOTICE_AUDIO;release(home,1);return;
        }
    }
    LabVmNetwork network={0};
    if((home->image.capabilities&LAB_VM_CAP_NETWORK) && home->network.open) {
        home->network_owned=true;
        if(!home->network.open(home->network.context,home->image.capabilities,&network)) {
            home->notice=LAB_NOTICE_NETWORK;release(home,1);return;
        }
    }
    LabVmState state={0};
    if((home->image.capabilities&LAB_VM_CAP_STORAGE) && home->state.open) {
        home->state_owned=true;
        if(!home->state.open(home->state.context,home->active_id,home->image.capabilities,&state)) {
            home->notice=LAB_NOTICE_STORAGE;release(home,1);return;
        }
    }
    if(!home->image.bytes || !lab_vm_open_with_all_services(&home->vm,home->image.bytes,home->image.size,
                                        home->image.pages,home->image.budget,home->image.capabilities,
                                        home->audio_owned ? &audio : NULL,home->network_owned ? &network : NULL,home->state_owned ? &state : NULL)) {
        failed(home,LAB_NOTICE_FAULT,true);return;
    }
    home->vm.held=held; /* shield the launch key from guest pressed edges */
    home->mode=LAB_RUNNING;home->notice=LAB_NOTICE_NONE;
}
bool lab_home_frame(LabHome *home,uint32_t held,uint32_t dt) {
    if(!home)return false;
    if(held>255 || dt>60000) {
        release(home,1);home->notice=LAB_NOTICE_HOST_INPUT;return false;
    }
    home->os_time+=dt;
    uint32_t pressed=held & ~home->previous_held;home->previous_held=held;
    if(home->mode==LAB_CLEANUP) {release(home,home->release_reason);return true;}
    if(home->audio.poll)home->audio.poll(home->audio.context,home->os_time);
    if(home->network.poll)home->network.poll(home->network.context,home->os_time);
    if(home->state.poll)home->state.poll(home->state.context,home->os_time);
    if(home->mode==LAB_RELEASE) {if(!held)home->mode=LAB_HOME;return true;}
    if(home->mode==LAB_HOME) {
        if(home->count) {
            if(pressed & 4)home->selected=(home->selected+1)%home->count;
            else if(pressed & 8)home->selected=(home->selected+home->count-1)%home->count;
            if(pressed & 16)launch(home,held);
        }
        return true;
    }
    if((held & 192)==192) {release(home,1);home->notice=LAB_NOTICE_RETURN;return true;}
    int result=lab_vm_frame(&home->vm,held,dt);
    if(result<0)failed(home,LAB_NOTICE_FAULT,true);
    else if(result>0) {release(home,0);home->notice=LAB_NOTICE_RETURN;}
    return true;
}
bool lab_home_close(LabHome *home) {
    if(!home)return false;
    if(!release(home,1))return false;
    home->mode=LAB_HOME;home->previous_held=0;return true;
}
