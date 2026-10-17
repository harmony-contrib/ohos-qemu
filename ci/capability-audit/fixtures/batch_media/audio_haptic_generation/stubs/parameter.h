#pragma once
#include "host_prelude.h"
inline int GetParameter(const char *,const char *fallback,char *out,unsigned length) {
 if(length<=strlen(fallback))return -1;strcpy(out,fallback);return int(strlen(out));
}
