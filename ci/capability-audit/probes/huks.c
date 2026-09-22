#include <huks/native_huks_api.h>
#include <stdio.h>

int main(void)
{
    unsigned char data[256] = {0};
    struct OH_Huks_Blob version = {.size = sizeof(data), .data = data};
    struct OH_Huks_Result result = OH_Huks_GetSdkVersion(&version);
    printf("get_sdk_version.code=%d size=%u msg=%s value=%.*s\n",
        result.errorCode, version.size, result.errorMsg == NULL ? "" : result.errorMsg,
        (int)version.size, (char *)version.data);
    return result.errorCode == 0 ? 0 : 1;
}
