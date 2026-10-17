#pragma once
#include "host_prelude.h"
namespace OHOS { inline bool PathToRealPath(const std::string &path,std::string &out) {
 char *value=realpath(path.c_str(),nullptr); if(!value)return false;out=value;free(value);return true;
} }
