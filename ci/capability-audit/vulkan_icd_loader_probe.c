/* Diagnose whether a candidate ICD can be loaded by the guest dynamic linker. */
#include <dlfcn.h>
#include <stdio.h>

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "usage: %s /path/to/libvk_icd.so\n", argv[0]);
        return 2;
    }
    void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!library) {
        fprintf(stderr, "dlopen failed: %s\n", dlerror());
        return 1;
    }
    const char *symbols[] = {
        "vk_icdGetInstanceProcAddr",
        "vk_icdNegotiateLoaderICDInterfaceVersion",
    };
    for (unsigned index = 0; index < sizeof(symbols) / sizeof(symbols[0]); ++index) {
        printf("%s=%p\n", symbols[index], dlsym(library, symbols[index]));
        fflush(stdout);
    }
    puts("before_dlclose");
    fflush(stdout);
    dlclose(library);
    puts("after_dlclose");
    return 0;
}
