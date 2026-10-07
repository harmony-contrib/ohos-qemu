#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <stdio.h>

static int probe(int version, EGLint renderable)
{
    EGLDisplay display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    EGLint major = 0;
    EGLint minor = 0;
    EGLint count = 0;
    EGLBoolean initialized = eglInitialize(display, &major, &minor);
    printf("gles%d.egl_get_display=%d initialize=%d error=0x%x version=%d.%d\n",
        version, display != EGL_NO_DISPLAY, initialized, eglGetError(), major, minor);
    if (!initialized) {
        return 1;
    }
    EGLint attributes[] = {
        EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
        EGL_RENDERABLE_TYPE, renderable,
        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8,
        EGL_NONE,
    };
    EGLConfig config = 0;
    EGLBoolean chose = eglChooseConfig(display, attributes, &config, 1, &count);
    printf("gles%d.choose=%d count=%d error=0x%x\n", version, chose, count, eglGetError());
    if (!chose || count == 0) {
        eglTerminate(display);
        return 1;
    }
    EGLint pbufferAttributes[] = {EGL_WIDTH, 16, EGL_HEIGHT, 16, EGL_NONE};
    EGLSurface surface = eglCreatePbufferSurface(display, config, pbufferAttributes);
    EGLint contextAttributes[] = {EGL_CONTEXT_CLIENT_VERSION, version, EGL_NONE};
    EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT, contextAttributes);
    EGLBoolean current = EGL_FALSE;
    if (surface != EGL_NO_SURFACE && context != EGL_NO_CONTEXT) {
        current = eglMakeCurrent(display, surface, surface, context);
    }
    printf("gles%d.surface=%d context=%d current=%d error=0x%x vendor=%s renderer=%s gl_version=%s\n",
        version, surface != EGL_NO_SURFACE, context != EGL_NO_CONTEXT, current, eglGetError(),
        current ? (const char *)glGetString(GL_VENDOR) : "",
        current ? (const char *)glGetString(GL_RENDERER) : "",
        current ? (const char *)glGetString(GL_VERSION) : "");
    int failed = !current;
    if (current) {
        unsigned char pixel[4] = {0};
        glViewport(0, 0, 16, 16);
        glClearColor(0.2f, 0.4f, 0.6f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT);
        glReadPixels(0, 0, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, pixel);
        GLenum error = glGetError();
        failed = error != GL_NO_ERROR || pixel[0] < 50 || pixel[0] > 52 ||
            pixel[1] < 101 || pixel[1] > 103 || pixel[2] < 152 || pixel[2] > 154 || pixel[3] != 255;
        printf("gles%d.readback=%u,%u,%u,%u gl_error=0x%x pass=%d\n", version,
            pixel[0], pixel[1], pixel[2], pixel[3], error, !failed);
        eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    }
    if (context != EGL_NO_CONTEXT) {
        eglDestroyContext(display, context);
    }
    if (surface != EGL_NO_SURFACE) {
        eglDestroySurface(display, surface);
    }
    eglTerminate(display);
    return failed;
}

int main(void)
{
    int gles2 = probe(2, EGL_OPENGL_ES2_BIT);
    int gles3 = probe(3, 0x0040); /* EGL_OPENGL_ES3_BIT_KHR */
    return gles2 || gles3;
}
