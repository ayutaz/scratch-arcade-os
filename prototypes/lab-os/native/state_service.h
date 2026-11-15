#ifndef LAB_STATE_SERVICE_H
#define LAB_STATE_SERVICE_H
#include <stdbool.h>
#include <stdint.h>
enum {LAB_STATE_SLOTS=8,LAB_STATE_RECORD_BYTES=52};
typedef struct {
 void *context;
 /* Trusted OS identity, copy 0/1; complete fixed record only. 0 absent,
  * 1 found, -1 I/O error. put must finish sync/close before true. */
 int (*read)(void *,const char *,uint32_t,uint8_t *,uint32_t,uint32_t *);
 bool (*put)(void *,const char *,uint32_t,const uint8_t *,uint32_t);
} LabStateIo;
typedef struct {
 LabStateIo io;
 int32_t values[8];
 char app_id[33];
 uint32_t mask,sequence,now,last_commit;
 int bank;
 bool ready,leased,healthy,committed;
} LabState;
/* Single trusted OS actor, one manager and current foreground lease. No heap,
 * arbitrary paths, mount/format, device I/O or guest memory access here.
 * Bind identity before VM init, close VM before close/reopen. Read is cached.
 * Changed durable commits are at most once/1000ms within a lease. Unchanged
 * values do no I/O. Failed puts retain last confirmed cache and poison writes
 * until close/reopen. An uncertain completed write may be found after reopen.
 * Alternating CRC records detect corruption, not malicious modification.
 * Successful sync is not a guarantee for untested physical power failure. */
bool lab_state_init(LabState *,const LabStateIo *);
bool lab_state_open(LabState *,const char *id,uint32_t now);
bool lab_state_close(LabState *);
void lab_state_time(LabState *,uint32_t now);
int lab_state_read(LabState *,uint32_t slot,int32_t *value);
int lab_state_write(LabState *,uint32_t slot,int32_t value);
#endif
