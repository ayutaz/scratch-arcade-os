#include "input.h"
#include <stdlib.h>
void *test_filter_new(void) {return calloc(1,sizeof(LabInputFilter));}
void test_filter_free(void *p) {free(p);}
int test_sample(LabInputFilter *f,uint32_t keys,int x,int y,uint32_t now,LabInputSample *out) {
    return lab_input_sample(f,keys,x,y,now,out);
}

int test_neutral(const LabInputSample *s) {return lab_input_is_neutral(s);}
