/* Reuse the strict I2S shim with separate diagnostic symbols. */
#define test_reset test_audio_reset
#define test_fault test_audio_fault
#define test_io test_audio_io
#define test_calls test_audio_calls
#define test_bad test_audio_bad
#define test_pin test_audio_pin
#define test_new test_audio_new
#define test_free test_audio_free
#define test_open test_audio_open
#define test_close test_audio_close
#define test_write test_audio_write
#define test_read test_audio_read
#define test_ready test_audio_ready
#define test_sent test_audio_sent
#define test_drained test_audio_drained
#define test_auto_io test_audio_auto_io
#define test_output_budget test_audio_output_budget
#include "lab_board_audio_bridge.c"
#include "audio_memory.h"
static int16_t *pcm_live;static uint32_t pcm_frames;
static unsigned pcm_allocs,pcm_frees,pcm_bad,pcm_zero,pcm_largest;
static int pcm_alloc_fail,pcm_free_fail;
void test_audio_memory_reset(void){pcm_allocs=pcm_frees=pcm_bad=pcm_zero=pcm_largest=0;pcm_alloc_fail=pcm_free_fail=0;}
void test_audio_memory_fault(int alloc,int release){pcm_alloc_fail=alloc;pcm_free_fail=release;}
unsigned test_audio_memory(unsigned i){return i==0 ? pcm_allocs : i==1 ? pcm_frees : i==2 ? pcm_frames*2 : i==3 ? pcm_bad : i==4 ? pcm_zero : pcm_largest;}
int16_t *lab_audio_pcm_alloc(uint32_t frames){pcm_allocs++;if(frames*2>pcm_largest)pcm_largest=frames*2;
 if(pcm_live || (frames!=16000 && frames!=32000)){pcm_bad++;return NULL;}
 if(pcm_alloc_fail)return NULL;pcm_live=malloc(frames*2);if(pcm_live){pcm_frames=frames;memset(pcm_live,0x55,frames*2);}return pcm_live;
}
bool lab_audio_pcm_free(int16_t *p,uint32_t frames){
 if(!p || p!=pcm_live || frames!=pcm_frames){pcm_bad++;return false;}
 pcm_zero=1;for(uint32_t i=0;i<frames;i++)if(p[i])pcm_zero=0;
 if(pcm_free_fail)return false;memset(p,0,frames*2);free(p);pcm_live=NULL;pcm_frames=0;pcm_frees++;return true;
}

bool lab_audio_pcm_banks_alloc(LabAudioPcm *p,uint32_t frames) {
 pcm_allocs++;
 if(!p || p->frames || pcm_live || (frames!=16000 && frames!=32000)){pcm_bad++;return false;}
 if(pcm_alloc_fail)return false;
 for(unsigned i=0;i<(frames+4095)/4096;i++) {
  unsigned n=frames-i*4096;if(n>4096)n=4096;
  if(n*2>pcm_largest)pcm_largest=n*2;
  p->banks[i]=malloc(n*2);
  if(!p->banks[i])abort();
  memset(p->banks[i],0x55,n*2);
 }
 p->frames=pcm_frames=frames;pcm_live=p->banks[0];return true;
}
bool lab_audio_pcm_banks_free(LabAudioPcm *p) {
 if(!p || !p->frames || p->banks[0]!=pcm_live || p->frames!=pcm_frames){pcm_bad++;return false;}
 pcm_zero=1;
 for(unsigned i=0;i<p->frames;i++)if(p->banks[i/4096][i%4096])pcm_zero=0;
 if(pcm_free_fail)return false;
 for(unsigned i=0;i<(p->frames+4095)/4096;i++) {
  unsigned n=p->frames-i*4096;if(n>4096)n=4096;
  memset(p->banks[i],0,n*2);free(p->banks[i]);p->banks[i]=NULL;
 }
 p->frames=pcm_frames=0;pcm_live=NULL;pcm_frees++;return true;
}
