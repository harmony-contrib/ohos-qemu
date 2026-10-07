/* Compare the public EGL wrapper's claims with the QEMU Mesa backend. */
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>

typedef EGLDisplay (*get_display_t)(EGLNativeDisplayType);
typedef EGLBoolean (*initialize_t)(EGLDisplay, EGLint *, EGLint *);
typedef const char *(*query_string_t)(EGLDisplay, EGLint);
typedef EGLBoolean (*terminate_t)(EGLDisplay);
typedef EGLBoolean (*choose_config_t)(EGLDisplay, const EGLint *, EGLConfig *, EGLint, EGLint *);
typedef EGLBoolean (*bind_api_t)(EGLenum);
typedef EGLContext (*create_context_t)(EGLDisplay, EGLConfig, EGLContext, const EGLint *);
typedef EGLBoolean (*destroy_context_t)(EGLDisplay, EGLContext);
typedef EGLint (*get_error_t)(void);

static void inspect(const char *path)
{
    void *library = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!library) {
        printf("%s: dlopen failed: %s\n", path, dlerror());
        return;
    }
    get_display_t get_display = (get_display_t)dlsym(library, "eglGetDisplay");
    initialize_t initialize = (initialize_t)dlsym(library, "eglInitialize");
    query_string_t query_string = (query_string_t)dlsym(library, "eglQueryString");
    terminate_t terminate = (terminate_t)dlsym(library, "eglTerminate");
    choose_config_t choose_config = (choose_config_t)dlsym(library, "eglChooseConfig");
    bind_api_t bind_api = (bind_api_t)dlsym(library, "eglBindAPI");
    create_context_t create_context = (create_context_t)dlsym(library, "eglCreateContext");
    destroy_context_t destroy_context = (destroy_context_t)dlsym(library, "eglDestroyContext");
    get_error_t get_error = (get_error_t)dlsym(library, "eglGetError");
    if (!get_display || !initialize || !query_string || !terminate || !choose_config ||
        !bind_api || !create_context || !destroy_context || !get_error) {
        printf("%s: missing EGL entry point\n", path);
        dlclose(library);
        return;
    }
    EGLDisplay display = get_display(EGL_DEFAULT_DISPLAY);
    EGLint major = 0, minor = 0;
    if (!initialize(display, &major, &minor)) {
        printf("%s: eglInitialize failed\n", path);
        dlclose(library);
        return;
    }
    const char *extensions = query_string(display, EGL_EXTENSIONS);
    printf("%s: EGL %d.%d robust=%d extensions=%s\n", path, major, minor,
           extensions && strstr(extensions, "EGL_EXT_create_context_robustness") != NULL,
           extensions ? extensions : "(null)");
    const EGLint config_attributes[] = {
        EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
        EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
        EGL_NONE,
    };
    EGLConfig config = NULL;
    EGLint config_count = 0;
    if (bind_api(EGL_OPENGL_ES_API) &&
        choose_config(display, config_attributes, &config, 1, &config_count) && config_count > 0) {
        const EGLint plain_attributes[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
        const EGLint robust_attributes[] = {
            EGL_CONTEXT_CLIENT_VERSION, 2,
            EGL_CONTEXT_OPENGL_ROBUST_ACCESS_EXT, EGL_TRUE,
            EGL_NONE,
        };
        EGLContext plain = create_context(display, config, EGL_NO_CONTEXT, plain_attributes);
        printf("%s: gles2_plain=%d error=0x%x\n", path, plain != EGL_NO_CONTEXT, get_error());
        if (plain != EGL_NO_CONTEXT) destroy_context(display, plain);
        EGLContext robust = create_context(display, config, EGL_NO_CONTEXT, robust_attributes);
        printf("%s: gles2_robust=%d error=0x%x\n", path, robust != EGL_NO_CONTEXT, get_error());
        if (robust != EGL_NO_CONTEXT) destroy_context(display, robust);
    }
    terminate(display);
    dlclose(library);
}

int main(void)
{
#if defined(__aarch64__) || defined(__x86_64__)
    inspect("/system/lib64/platformsdk/libEGL.so");
    inspect("/system/lib64/libEGL.so.1.0.0");
#else
    inspect("/system/lib/platformsdk/libEGL.so");
    inspect("/system/lib/libEGL.so.1.0.0");
#endif
    return 0;
}
