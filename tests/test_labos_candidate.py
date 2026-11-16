import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_labos_c_store as contract
import test_labos_lfs as fs
from labos import target

ROOT = contract.ROOT
MAIN = ROOT / 'firmware/esp-idf/lab-os-core/main'


class CandidateTests(unittest.TestCase):
    def test_candidate_actions_use_separate_project_and_keep_flash_forbidden(self):
        for action, idf_action in (('build-candidate', 'build'), ('size-candidate', 'size')):
            cmd = target.command(action)
            self.assertEqual(cmd[-1], idf_action)
            self.assertEqual(cmd[cmd.index('-C') + 1], str(ROOT / 'firmware/esp-idf/lab-os-candidate'))
            self.assertEqual(cmd[cmd.index('-B') + 1], str(ROOT / 'build/lab-os-candidate'))
            self.assertIn('SDKCONFIG=' + str(ROOT / 'build/lab-os-candidate/sdkconfig'), cmd)
        for action in ('flash-candidate', 'build-candidate flash', 'monitor-candidate'):
            with self.assertRaises(ValueError): target.command(action)

    def test_candidate_prepare_binds_header_seed_and_metadata_to_proposed_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = target.prepare_candidate(Path(tmp))
            header = (Path(tmp) / 'generated/lab_candidate.h').read_text()
            self.assertIn('#define LAB_CANDIDATE_ADDRESS 0x110000u', header)
            self.assertIn('#define LAB_CANDIDATE_BYTES 0x100000u', header)
            self.assertIn('#define LAB_CANDIDATE_QUOTA 0xe0000u', header)
            self.assertEqual(result['candidate_layout']['status'], 'proposal-only-not-approved-for-flash')
            self.assertEqual(result['candidate_layout']['lab_apps'], {'address': 0x110000, 'bytes': 0x100000, 'quota': 0xe0000})
            self.assertEqual(result['seed_image']['bytes'], 0x100000)
            self.assertIsNone(result['seed_image']['flash_address'])
            self.assertFalse(result['device_tested'])
            self.assertEqual(result, json.loads((Path(tmp) / 'prepared.json').read_text()))

    def test_layout_rejects_overlap_foreign_shape_encryption_and_wrong_seed_size(self):
        original = (ROOT / 'firmware/esp-idf/lab-os-candidate/partitions.csv').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'partitions.csv'
            for bad in (original.replace('0x110000', '0x100000'),
                        original.replace('0x110000', '0x810000'),
                        original.replace('lab_apps,data,littlefs', 'lab_apps,data,spiffs'),
                        original.replace('lab_apps,data,littlefs,0x110000,0x100000,', 'lab_apps,data,littlefs,0x110000,0x100000,encrypted'),
                        original.replace('lab_apps,data,littlefs,0x110000,0x100000,', 'lab_apps,data,littlefs,0x110000,0x200000,'),
                        original + '\nforeign,data,0x40,0x220000,0x1000,\n'):
                path.write_text(bad)
                with self.subTest(bad=bad), self.assertRaises(ValueError): target.candidate_layout(path)

    def test_main_prepares_candidate_before_invoking_fixed_idf_build(self):
        with mock.patch.object(target.subprocess, 'run', side_effect=[
                mock.Mock(stdout=target.IDF_COMMIT + '\n'), mock.Mock(returncode=0)]) as run, \
             mock.patch.object(target, 'verify_littlefs') as verify, \
             mock.patch.object(target, 'prepare_candidate') as prepare:
            self.assertEqual(target.main(['build-candidate']), 0)
        prepare.assert_called_once_with();verify.assert_called_once_with()
        self.assertEqual(run.call_args.args[0][-1], 'build')

    def test_entry_uses_boot_config_poll_yield_and_cleanup_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'lab_candidate.h').write_text('#define LAB_CANDIDATE_ADDRESS 0x110000u\n#define LAB_CANDIDATE_BYTES 0x100000u\n#define LAB_CANDIDATE_QUOTA 0xe0000u\n')
            (folder / 'pthread.h').write_text('''
              typedef unsigned long pthread_t;
              int pthread_create(pthread_t *,const void *,void *(*)(void *),void *);
              int pthread_join(pthread_t,void **);
            ''')
            (folder / 'esp_pthread.h').write_text('''
              #include <stddef.h>
              #include <stdbool.h>
              #define ESP_OK 0
              typedef struct {size_t stack_size,prio;bool inherit_cfg;const char *thread_name;int pin_to_core;unsigned stack_alloc_caps;} esp_pthread_cfg_t;
              esp_pthread_cfg_t esp_pthread_get_default_config(void);
              int esp_pthread_set_cfg(const esp_pthread_cfg_t *);
            ''')
            (folder / 'fixture.c').write_text('''
              #include "board_boot.h"
              #include "state_mount.h"
              #include "resource_monitor.h"
              #include "voice_service.h"
              #include <stdio.h>
              #include <string.h>
              #include "pthread.h"
              #include "esp_pthread.h"
              #include <stdlib.h>
              static unsigned mode,steps,closes,delays,bad,binds,states,voices;static uint32_t now=100;
              static char trace[160];static unsigned used,on_thread,created,joined;static void *(*entry)(void *);
              esp_pthread_cfg_t esp_pthread_get_default_config(void){return (esp_pthread_cfg_t){.stack_size=3072,.prio=5,.pin_to_core=-1};}
              int esp_pthread_set_cfg(const esp_pthread_cfg_t *c){
                if(c->stack_size!=16384 || c->prio!=1 || c->pin_to_core!=0 || c->inherit_cfg || !c->thread_name || strcmp(c->thread_name,"lab-os"))bad=1;
                return mode==4 ? -1 : 0;
              }
              int pthread_create(pthread_t *t,const void *attr,void *(*f)(void *),void *arg){
                if(attr || arg || !f || steps || closes || used)bad=1;
                if(mode==5)return -1;*t=17;entry=f;created++;return 0;
              }
              int pthread_join(pthread_t t,void **out){
                if(t!=17 || out || !entry || created!=1)bad=1;
                joined++;on_thread=1;void *result=entry(NULL);on_thread=0;if(result)bad=1;return 0;
              }
              extern LabResourceMonitor lab_candidate_resources;
              int lab_resource_readout(void *p,uint32_t kind,uint32_t sequence,uint8_t out[80],uint32_t *length){
                (void)p;(void)kind;(void)sequence;(void)out;(void)length;return 0;
              }
              bool lab_transfer_set_telemetry(LabTransfer *t,LabTransferTelemetry read,void *context){
                binds++;if(!t || read!=lab_resource_readout || context!=&lab_candidate_resources)bad=1;
                return mode!=2;
              }
              bool lab_resource_poll(LabResourceMonitor *m,uint32_t t,uint32_t stage,uint32_t flags){
                if(!m || t<100)bad=1;used+=(unsigned)snprintf(trace+used,sizeof(trace)-used,"%u:%u,",stage,flags);return true;
              }
              int64_t esp_timer_get_time(void){return (int64_t)now*1000;}
              void vTaskDelay(uint32_t ticks){if(ticks!=1)bad=1;delays++;now+=10;}
              bool lab_board_boot_open(LabBoardBoot *b,const LabBootConfig *c,uint32_t t){
                if(!on_thread)bad=1;
                if(!b || c->profile!=1 || c->layout.address!=0x110000 || c->layout.bytes!=0x100000 || c->quota!=0xe0000 || t!=100)bad=1;
                b->runtime_owned=true;b->ready=mode!=1;b->session.usb.active=mode==0 || mode==2 || mode==6;return mode!=1;
              }
              int lab_voice_call(void *c,LabAudio *a,uint32_t owner,uint32_t op,uint32_t value,uint32_t time){
                (void)c;(void)a;(void)owner;(void)op;(void)value;(void)time;return -1;
              }
              bool lab_board_sound_set_voice(LabBoardSound *s,void *context,int (*call)(void *,LabAudio *,uint32_t,uint32_t,uint32_t,uint32_t)){
                if(!on_thread || !s || !context || call!=lab_voice_call || steps || closes || binds || states)bad=1;
                voices++;return mode!=7;
              }
              bool lab_state_mount_attach(LabStateMount *s,LabHome *h,lfs_t *fs,bool create){
                if(!on_thread || !s || !h || !fs || !create || steps || closes)bad=1;
                states++;return mode!=6;
              }
              int lab_board_boot_step(LabBoardBoot *b,uint32_t t){
                if(!b || t<100 || (steps && t==100))bad=1;
                steps++;b->session.home.mode=steps==1 ? LAB_RUNNING : LAB_HOME;
                b->gc.active=steps>=2;b->session.usb.transfer.session=steps>=2 ? 7 : 0;
                if(steps==3)b->ready=false;return steps==3 ? LAB_LOOP_STOPPED : LAB_LOOP_INPUT_ERROR;
              }
              bool lab_board_boot_close(LabBoardBoot *b){if(!b)bad=1;
                b->ready=false;b->gc.active=false;b->session.usb.transfer.session=0;
                if(++closes<2)return false;b->runtime_owned=false;return true;}
              void app_main(void);
              int main(int argc,char **argv){mode=argc>1 ? atoi(argv[1]) : 0;app_main();
                if(mode!=4 && mode!=5 && (created!=1 || joined!=1))bad=1;
                if((mode==4 || mode==5) && (steps || closes || created || joined))bad=1;
                printf("steps=%u closes=%u delays=%u bad=%u binds=%u states=%u voices=%u trace=%s\\n",steps,closes,delays,bad,binds,states,voices,trace);return bad;}
            ''')
            flags = ['-I' + str(ROOT / 'tests/native' / name) for name in
                     ('wifi_fixture','boot_fixture', 'session_fixture', 'display_fixture', 'input_fixture', 'usb_fixture', 'flash_fixture','audio_fixture')]
            flags += ['-I' + str(p) for p in (folder, MAIN, ROOT / 'prototypes/lab-os/native', fs.LFS,
                      contract.SOURCE / 'core/iwasm/include')]
            exe = folder / 'entry'
            p = subprocess.run(['/usr/bin/clang', '-std=c11', '-Wall', '-Wextra', '-Werror', *flags,
                                str(MAIN / 'candidate_main.c'), str(folder / 'fixture.c'), '-o', str(exe)],
                               capture_output=True, text=True, timeout=30)
            self.assertEqual(p.returncode, 0, p.stderr)
            for mode, expected in ((0, 'steps=3 closes=2 delays=3 bad=0 binds=1 trace=1:0,2:3,2:7,2:27,4:25,5:25,5:1,6:0,'),
                                   (1, 'steps=0 closes=2 delays=1 bad=0 binds=0 trace=1:0,3:1,5:1,5:1,6:0,'),
                                   (2, 'steps=0 closes=2 delays=1 bad=0 binds=1 trace=1:0,3:3,5:3,5:1,6:0,'),
                                   (3, 'steps=3 closes=2 delays=3 bad=0 binds=0 trace=1:0,2:3,2:7,2:27,4:25,5:25,5:1,6:0,'),
                                   (4, 'steps=0 closes=0 delays=0 bad=0 binds=0 trace=3:0,'),
                                   (5, 'steps=0 closes=0 delays=0 bad=0 binds=0 trace=3:0,'),
                                   (6, 'steps=0 closes=2 delays=1 bad=0 binds=1 trace=1:0,3:3,5:3,5:1,6:0,'),
                                   (7, 'steps=0 closes=2 delays=1 bad=0 binds=0 trace=1:0,3:3,5:3,5:1,6:0,')):
                p = subprocess.run([str(exe), str(mode)], capture_output=True, text=True, timeout=5)
                self.assertEqual(p.returncode, 0, p.stderr)
                expected=expected.replace(' trace=',f' states={1 if mode in (0,3,6) else 0} voices={0 if mode in (1,4,5) else 1} trace=')
                self.assertEqual(p.stdout.strip(), expected)


if __name__ == '__main__': unittest.main()
