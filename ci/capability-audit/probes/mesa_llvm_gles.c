/* Real native EGL/GLES shader, bounds and destruction probe.
 * Package/boot provenance is established by run_root_probe, never by this log. */
#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#define REQUIRE(v) do { if (!(v)) { fprintf(stderr,"GLES contract failed line %d: %s\n",__LINE__,#v); exit(2); } } while (0)
static uint64_t shader_pixels;
static uint64_t pattern_hash=UINT64_C(1469598103934665603);
static GLuint shader(GLenum kind, const char *source)
{
    GLuint s=glCreateShader(kind); REQUIRE(s);
    glShaderSource(s,1,&source,NULL); glCompileShader(s);
    GLint ok=0; glGetShaderiv(s,GL_COMPILE_STATUS,&ok);
    if (!ok) { char log[4096]; glGetShaderInfoLog(s,sizeof(log),NULL,log); fprintf(stderr,"%s\n",log); }
    REQUIRE(ok); return s;
}
static void require_pixel(const unsigned char *p, int r, int g, int b, int a)
{
    const int values[4]={r,g,b,a};
    for (int c=0;c<4;++c) if (abs((int)p[c]-values[c])>2) {
        fprintf(stderr,"pixel channel %d got %u expected %d\n",c,p[c],values[c]);
        exit(3);
    }
}

static void shader_contract(void)
{
        const char *vs="attribute vec2 position; void main(){gl_Position=vec4(position,0.,1.);}";
        const char *fs="precision highp float; uniform float phase; uniform int mode; uniform vec4 solid;"
            "void main(){ if(mode==1) gl_FragColor=solid; else gl_FragColor=vec4("
            "mod(floor(gl_FragCoord.x)+phase,17.)/16.,"
            "mod(floor(gl_FragCoord.y)+phase,13.)/12.,mod(phase,2.)*.5+.25,1.);}";
        GLuint vert=shader(GL_VERTEX_SHADER,vs),frag=shader(GL_FRAGMENT_SHADER,fs);
        GLuint program=glCreateProgram(); REQUIRE(program);
        glAttachShader(program,vert); glAttachShader(program,frag);
        glBindAttribLocation(program,0,"position"); glLinkProgram(program);
        GLint linked=0; glGetProgramiv(program,GL_LINK_STATUS,&linked);
        if (!linked) { char log[4096];glGetProgramInfoLog(program,sizeof(log),NULL,log);fprintf(stderr,"%s\n",log); }
        REQUIRE(linked); glUseProgram(program);
        GLint phase=glGetUniformLocation(program,"phase"), mode=glGetUniformLocation(program,"mode");
        GLint solid=glGetUniformLocation(program,"solid"); REQUIRE(phase>=0 && mode>=0 && solid>=0);
        GLuint buffer=0,texture=0,fbo=0;
        const GLfloat vertices[]={-1,-1,3,-1,-1,3};
        glGenBuffers(1,&buffer); glBindBuffer(GL_ARRAY_BUFFER,buffer);
        glBufferData(GL_ARRAY_BUFFER,sizeof(vertices),vertices,GL_STATIC_DRAW);
        glVertexAttribPointer(0,2,GL_FLOAT,GL_FALSE,0,0); glEnableVertexAttribArray(0);
        glGenTextures(1,&texture); glBindTexture(GL_TEXTURE_2D,texture);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
        glGenFramebuffers(1,&fbo); glBindFramebuffer(GL_FRAMEBUFFER,fbo);
        const int sizes[][2]={{1,1},{65,33},{320,180},{1280,800}};
        for (unsigned si=0;si<sizeof(sizes)/sizeof(sizes[0]);++si) {
            int w=sizes[si][0],h=sizes[si][1];
            size_t bytes=(size_t)w*h*4;
            unsigned char *guard=malloc(bytes+32); REQUIRE(guard);
            memset(guard,0xa5,bytes+32); unsigned char *pixels=guard+16;
            glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
            glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture,0);
            REQUIRE(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
            glViewport(0,0,w,h); glDisable(GL_DITHER); glDisable(GL_BLEND);
            glPixelStorei(GL_PACK_ALIGNMENT,1);
            for (unsigned pass=0;pass<2;++pass) {
                const int p=pass ? 7 : 2;
                glUniform1i(mode,0); glUniform1f(phase,(float)p);
                glDrawArrays(GL_TRIANGLES,0,3); glFinish();
                glReadPixels(0,0,w,h,GL_RGBA,GL_UNSIGNED_BYTE,pixels);
                REQUIRE(glGetError()==GL_NO_ERROR);
                for (int y=0;y<h;++y) for (int x=0;x<w;++x) {
                    unsigned char *v=pixels+((size_t)y*w+x)*4;
                    require_pixel(v,(int)lround(((x+p)%17)*255./16.),(int)lround(((y+p)%13)*255./12.),
                        p%2 ? 191:64,255);
                    for (int c=0;c<4;++c) pattern_hash=(pattern_hash^v[c])*UINT64_C(1099511628211);
                    ++shader_pixels;
                }
            }
            glClearColor(0,0,0,1); glClear(GL_COLOR_BUFFER_BIT);
            glUniform1i(mode,1); glUniform4f(solid,1,.5,0,.5);
            glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
            glEnable(GL_SCISSOR_TEST); glScissor(0,0,(w+1)/2,h);
            glDrawArrays(GL_TRIANGLES,0,3); glFinish();
            glDisable(GL_SCISSOR_TEST); glDisable(GL_BLEND);
            glReadPixels(0,0,w,h,GL_RGBA,GL_UNSIGNED_BYTE,pixels);
            REQUIRE(glGetError()==GL_NO_ERROR);
            for (int y=0;y<h;++y) for (int x=0;x<w;++x) {
                require_pixel(pixels+((size_t)y*w+x)*4,x<(w+1)/2 ? 128:0,
                    x<(w+1)/2 ? 64:0,0,x<(w+1)/2 ? 191:255);
                ++shader_pixels;
            }
            for (int i=0;i<16;++i) REQUIRE(guard[i]==0xa5 && guard[bytes+16+i]==0xa5);
            free(guard);
        }
        glDeleteFramebuffers(1,&fbo); glDeleteTextures(1,&texture);
        glDeleteBuffers(1,&buffer); glDeleteProgram(program);
        glDeleteShader(vert); glDeleteShader(frag);
}
static void lifecycle(int version)
{
    EGLDisplay display=eglGetDisplay(EGL_DEFAULT_DISPLAY);
    EGLint major=0,minor=0,count=0;
    REQUIRE(display!=EGL_NO_DISPLAY && eglInitialize(display,&major,&minor));
    REQUIRE(eglBindAPI(EGL_OPENGL_ES_API));
    const EGLint attributes[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,
        version==3 ? 0x0040:EGL_OPENGL_ES2_BIT,
        EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_ALPHA_SIZE,8,EGL_NONE};
    EGLConfig config=0;
    REQUIRE(eglChooseConfig(display,attributes,&config,1,&count) && count>0);
    const EGLint pbuffer[]={EGL_WIDTH,16,EGL_HEIGHT,16,EGL_NONE};
    EGLSurface surface=eglCreatePbufferSurface(display,config,pbuffer);
    const EGLint context_attributes[]={EGL_CONTEXT_CLIENT_VERSION,version,EGL_NONE};
    EGLContext context=eglCreateContext(display,config,EGL_NO_CONTEXT,context_attributes);
    REQUIRE(surface!=EGL_NO_SURFACE && context!=EGL_NO_CONTEXT);
    REQUIRE(eglMakeCurrent(display,surface,surface,context));
    const char *renderer=(const char *)glGetString(GL_RENDERER);
    REQUIRE(renderer && strstr(renderer,"llvmpipe"));
    shader_contract();
    glBindFramebuffer(GL_FRAMEBUFFER,0);
    glViewport(0,0,16,16);
    glClearColor(.2f,.4f,.6f,1.f);glClear(GL_COLOR_BUFFER_BIT);glFinish();
    unsigned char pixel[4]={0};
    glReadPixels(0,0,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel);
    require_pixel(pixel,51,102,153,255);
    REQUIRE(glGetError()==GL_NO_ERROR && eglSwapBuffers(display,surface));
    REQUIRE(eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT));
    REQUIRE(eglDestroyContext(display,context));
    REQUIRE(eglDestroySurface(display,surface));
    REQUIRE(eglTerminate(display));
    REQUIRE(eglReleaseThread());
}
int main(int argc,char **argv)
{
    REQUIRE(argc==2 && strlen(argv[1])==32 && strspn(argv[1],"0123456789abcdef")==32);
    for (int version=2;version<=3;++version)
        for (unsigned generation=0;generation<3;++generation) lifecycle(version);
    REQUIRE(shader_pixels==UINT64_C(19507428));
    printf("{\"runId\":\"%s\",\"pid\":%ld,\"uid\":%ld,\"backend\":\"llvmpipe\","
        "\"glesVersions\":[2,3],\"contextGenerations\":6,\"shaderPrograms\":6,"
        "\"shaderPixels\":%llu,\"pbufferPixels\":6,\"swapCount\":6,\"teardownCount\":6,"
        "\"patternHash\":\"%016llx\",\"scope\":\"native_GLES_LLVM_shader_lifecycle\","
        "\"compositorTested\":false,\"pass\":true}\n",argv[1],(long)getpid(),(long)getuid(),
        (unsigned long long)shader_pixels,(unsigned long long)pattern_hash);
    return 0;
}
