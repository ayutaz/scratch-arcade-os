#include "board_audio.h"
#include "audio_service.h"
#include <string.h>
static LabBoardAudio device;static LabAudio audio;static int16_t pcm[512];
void test_reset(void);void test_io(int,unsigned);void test_sent(unsigned);void test_fault(int);
int audio_scenario(int cleanup_failure){
 test_reset();memset(&device,0,sizeof(device));memset(&audio,0,sizeof(audio));
 LabAudioIo io=lab_board_audio_services(&device);
 if(!lab_audio_init(&audio,&io,pcm,512)||!lab_audio_claim(&audio,101,1))return 1;
 if(!lab_audio_tone(&audio,101,1000,32,0))return 2;
 test_io(0,512);if(lab_audio_poll(&audio,1)!=0||lab_audio_poll(&audio,2)!=0)return 3;
 if(lab_audio_poll(&audio,3)!=0)return 4;
 test_sent(5);if(lab_audio_poll(&audio,4)!=1 || device.ready)return 5;
 if(!lab_audio_release(&audio,101)||!lab_audio_claim(&audio,202,3))return 6;
 if(!lab_audio_record(&audio,202,16,5))return 7;
 test_io(0,512);
 /* Drain the 1600-frame trusted service priming before application data. */
 for(unsigned i=0;i<6;i++)if(lab_audio_poll(&audio,6)!=0)return 18;
 if(lab_audio_poll(&audio,6)!=0 || audio.position!=192)return 19;
 test_io(0,128);
 if(cleanup_failure){
  test_fault(7);if(lab_audio_poll(&audio,6)!=0)return 8;
  if(lab_audio_release(&audio,202)||lab_audio_claim(&audio,303,3))return 9;
  for(unsigned i=0;i<512;i++)if(pcm[i])return 10;
  test_fault(0);if(!lab_audio_release(&audio,202))return 11;
 }else{
  if(lab_audio_poll(&audio,6)!=1||audio.recorded!=256||pcm[0]!=0||pcm[192]!=10||pcm[193]!=-20)return 12;
  test_io(0,512);
  if(!lab_audio_play_recording(&audio,202,7)||lab_audio_poll(&audio,8)!=0)return 13;
  test_sent(5);if(lab_audio_poll(&audio,9)!=1||!lab_audio_release(&audio,202))return 14;
 }
 if(!lab_audio_claim(&audio,303,3)||lab_audio_play_recording(&audio,303,10))return 15;
 for(unsigned i=0;i<512;i++)if(pcm[i])return 16;
 if(!lab_audio_release(&audio,303)||!lab_board_audio_close(&device))return 17;
 return 0;
}
