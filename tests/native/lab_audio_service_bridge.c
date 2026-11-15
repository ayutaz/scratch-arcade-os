#include "audio_service.h"
#include <stdlib.h>
#include <string.h>
static LabAudio s;static int16_t buffer[32000];
static int16_t output[32000];static unsigned output_frames;static int full_scale;
static unsigned calls[5];static int open_result,close_result,io_result,drain_result;
static int open(void *c,int mode){if(c!=&s || (mode!=1 && mode!=2))abort();calls[0]++;return open_result;}
static int read(void *c,int16_t *p,uint32_t n){if(c!=&s || n>256)abort();calls[1]++;for(unsigned i=0;i<n;i++)p[i]=full_scale ? (i&1 ? 32767 : -32768) : (int16_t)(i+1);return io_result;}
static int write(void *c,const int16_t *p,uint32_t n){if(c!=&s || !p || n>256)abort();calls[2]++;if(io_result>0 && (unsigned)io_result<=n && output_frames+(unsigned)io_result<=32000){memcpy(output+output_frames,p,(unsigned)io_result*2);output_frames+=(unsigned)io_result;}return io_result;}
static int drain(void *c){if(c!=&s)abort();calls[3]++;return drain_result;}
static int close(void *c){if(c!=&s)abort();calls[4]++;return close_result;}
int test_init(unsigned capacity){memset(&s,0,sizeof(s));memset(buffer,0,sizeof(buffer));memset(calls,0,sizeof(calls));open_result=close_result=1;io_result=0;drain_result=0;output_frames=0;full_scale=0;
 LabAudioIo io={&s,open,read,write,drain,close};return lab_audio_init(&s,&io,buffer,capacity);}
void test_results(int o,int c,int i,int d){open_result=o;close_result=c;io_result=i;drain_result=d;}
int test_claim(unsigned owner,unsigned flags){return lab_audio_claim(&s,owner,flags);}
int test_release(unsigned owner){return lab_audio_release(&s,owner);}
int test_tone(unsigned owner,unsigned hz,unsigned ms,unsigned now){return lab_audio_tone(&s,owner,hz,ms,now);}
int test_record(unsigned owner,unsigned ms,unsigned now){return lab_audio_record(&s,owner,ms,now);}
int test_play(unsigned owner,unsigned now){return lab_audio_play_recording(&s,owner,now);}
int test_poll(unsigned now){return lab_audio_poll(&s,now);}
unsigned test_owner(void){return s.owner;}unsigned test_recorded(void){return s.recorded;}
unsigned test_phase(void){return s.phase;}unsigned test_position(void){return s.position;}
unsigned test_calls(unsigned i){return calls[i];}int test_sample(unsigned i){return buffer[i];}

void test_full_scale(int value){full_scale=value;}
unsigned test_output_frames(void){return output_frames;}
int test_output(unsigned i){return output[i];}
int test_gain(unsigned owner,unsigned gain){return lab_audio_set_gain(&s,owner,gain);}
unsigned test_gain_value(void){return s.replay_gain;}
void test_set_sample(unsigned i,int value){buffer[i]=(int16_t)value;}
int test_record_metric(unsigned owner,unsigned field){
 LabAudioRecordingMetrics m;
 if(!lab_audio_recording_metrics(&s,owner,&m) || field>11)return -1;
 if(field>=8){uint32_t bins[4];if(!lab_audio_recording_bands(&s,owner,bins))return -1;return (int)bins[field-8];}
 int values[8]={(int)m.frames,m.minimum,m.maximum,m.mean,(int)m.rms,(int)m.ac_rms,(int)m.centered_peak,(int)m.saturated_frames};
 return values[field];
}
