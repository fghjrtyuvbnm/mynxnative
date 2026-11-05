// Exercise the real GL uniform APIs; the optional GPU path also checks array
// texture slots beside a scalar sampler with a one-pixel offscreen draw.
#define main gl_imports_test_main
#include "t_gl_imports.m"
#undef main

static void uniform_arrays(void) {
    GLuint pr = h_glCreateProgram();
    prog_t *p = prog_of(pr);
    p->linked = 1; p->nu = 1; p->u = zalloc(sizeof *p->u);
    strlcpy(p->u[0].name, "tex", sizeof p->u[0].name);
    p->u[0].type = T_SAMP2D; p->u[0].count = 4;
    h_glUseProgram(pr);
    GLint loc = h_glGetUniformLocation(pr, "tex");
    assert(loc == h_glGetUniformLocation(pr, "tex[0]"));
    assert(h_glGetUniformLocation(pr, "tex[4]") == -1);
    GLint units[] = {5,9,2,6};
    h_glUniform1iv(loc, 4, units);
    for (int i = 0; i < 4; i++) { GLint got = -1; h_glGetUniformiv(pr, loc+i, &got); assert(got == units[i]); }
    GLint update[] = {7,3}; h_glUniform1iv(loc+1, 2, update);
    GLint expected[] = {5,7,3,6};
    for (int i = 0; i < 4; i++) { GLint got = -1; h_glGetUniformiv(pr, loc+i, &got); assert(got == expected[i]); }
    h_glUniform1i(loc+3, 11);
    GLfloat value = -1; h_glGetUniformfv(pr, loc+3, &value); assert(value == 11);
    char name[32]; GLint count; GLenum type;
    h_glGetActiveUniform(pr, 0, sizeof name, NULL, &count, &type, name);
    assert(!strcmp(name,"tex[0]") && count == 4 && type == GL_SAMPLER_2D);
    h_glDeleteProgram(pr);
    puts("PASS: sampler array bulk update, element update, reflection and readback");
}

static GLuint compile_file(const char *dir, const char *name, GLenum stage) {
    char path[4096]; snprintf(path,sizeof path,"%s/%s",dir,name);
    FILE *f=fopen(path,"rb"); assert(f); fseek(f,0,SEEK_END); long n=ftell(f); rewind(f);
    char *text=calloc((size_t)n+1,1); assert(fread(text,1,(size_t)n,f)==(size_t)n); fclose(f);
    GLuint shader=h_glCreateShader(stage); const char *source=text;
    h_glShaderSource(shader,1,&source,NULL); h_glCompileShader(shader); free(text);
    assert(shader_of(shader)->fn); return shader;
}

static void render_arrays(const char *cache, const char *sources) {
    setenv("DM_MSL_DIR",cache,1); setenv("DM_TEST_NO_METAL4","1",1);
    dev_init();
    GLuint pr=h_glCreateProgram();
    h_glAttachShader(pr,compile_file(sources,"array.vert",GL_VERTEX_SHADER));
    h_glAttachShader(pr,compile_file(sources,"array.frag",GL_FRAGMENT_SHADER));
    h_glLinkProgram(pr); assert(prog_of(pr)->linked); h_glUseProgram(pr);
    const int units[3]={1,3,7}; const uint8_t colors[3][4]={{204,0,0,255},{0,153,0,255},{0,0,102,255}};
    GLuint textures[4]; h_glGenTextures(4,textures);
    for (int i=0;i<4;i++) {
        h_glActiveTexture(GL_TEXTURE0+(i<3?units[i]:0)); h_glBindTexture(GL_TEXTURE_2D,textures[i]);
        h_glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
        h_glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
        h_glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,1,1,0,GL_RGBA,GL_UNSIGNED_BYTE,i<3?colors[i]:NULL);
    }
    GLuint fb; h_glGenFramebuffers(1,&fb); h_glBindFramebuffer(GL_FRAMEBUFFER,fb);
    h_glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,textures[3],0);
    assert(h_glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
    h_glViewport(0,0,1,1); h_glDisable(GL_BLEND);
    GLint tex=h_glGetUniformLocation(pr,"tex"); assert(tex>=0);
    h_glUniform1iv(tex,2,units);
    h_glUniform1i(h_glGetUniformLocation(pr,"extra"),7);
    h_glUniform1f(h_glGetUniformLocation(pr,"weight"),1);
    h_glDrawArrays(GL_TRIANGLES,0,3);
    uint8_t pixel[4]={0}; h_glReadPixels(0,0,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel);
    fprintf(stderr,"Sampler pixel: %u %u %u %u\n",pixel[0],pixel[1],pixel[2],pixel[3]);
    assert(abs((int)pixel[0]-204)<=1 && abs((int)pixel[1]-153)<=1 && abs((int)pixel[2]-102)<=1 && pixel[3]==255);
    puts("PASS: sampler array and adjacent scalar bind three distinct texture units on GPU");
}

int main(int argc,char **argv) {
    uniform_arrays();
    if (argc==4 && !strcmp(argv[1],"--gpu")) render_arrays(argv[2],argv[3]);
    return 0;
}
