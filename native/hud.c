/* Native small PAL8 overlay for the approved Korean COMMON HUD pixels. */
typedef unsigned int h_u32;
typedef unsigned short h_u16;
typedef struct { h_u16 sx,sy,w,h,x,y,bank; } HudMap;
typedef struct { h_u32 id; h_u16 width,height; float u0,v0,u1,v1,cx,cy,sx,sy; } HudAnim;
#include "hud_overlay.h"
extern void original_hud(const HudAnim *,h_u32,h_u32,float,float,float);
volatile h_u32 native_hud_diagnostics[8];
static volatile h_u32 *overlay_memory;

static volatile h_u32 *find_overlay(void) {
    volatile h_u32 *p=*(volatile h_u32 **)0x8c0e001c;
    unsigned i,count=*(volatile h_u32 *)0x8c0e0020;
    if (overlay_memory && overlay_memory[0]==HUD_GLOBAL_ID) return overlay_memory;
    if((h_u32)p<0x8c000000u || (h_u32)p>=0x8d000000u || count>768) return 0;
    for(i=0;i<count;++i,p+=17)
        if(p[0]==HUD_GLOBAL_ID && p[9]==512 && p[10]==128 && p[13]<0x800000u) {
            overlay_memory=p; return p;
        }
    return 0;
}

static void palettes(void) {
    volatile h_u32 *ctrl=(volatile h_u32 *)0xa05f8108;
    volatile h_u32 *ram=(volatile h_u32 *)0xa05f9000;
    unsigned i,b;
    if(*ctrl!=2 || ram[1]!=hud_palette[0][1] || ram[257]!=hud_palette[1][1] || ram[513]!=hud_palette[2][1]) {
        *ctrl=2; /* ARGB4444 palette entries match approved 4-bit RGBA pixels. */
        for(b=0;b<3;++b) for(i=0;i<256;++i) ram[b*256+i]=hud_palette[b][i];
    }
}

void native_hud(const HudAnim *parent,h_u32 texture,h_u32 color,float x,float y,float z) {
    volatile h_u32 *cache=(volatile h_u32 *)0x8c0e0024;
    volatile h_u32 *memory;
    float u0,v0,u1,v1,left,top;
    unsigned i;
    original_hud(parent,texture,color,x,y,z);
    if(parent->id!=115) return;
    native_hud_diagnostics[0]++;
    native_hud_diagnostics[1]=texture;
    native_hud_diagnostics[2]=cache[0];
    memory=find_overlay();
    if(!memory) return;
    native_hud_diagnostics[3]=(h_u32)memory;
    native_hud_diagnostics[4]=memory[13];
    palettes();
    u0=parent->u0*parent->width; v0=parent->v0*parent->height;
    u1=parent->u1*parent->width; v1=parent->v1*parent->height;
    left=x-parent->cx*(u1-u0)*parent->sx;
    top=y-parent->cy*(v1-v0)*parent->sy;
    for(i=0;i<sizeof(hud_maps)/sizeof(hud_maps[0]);++i) {
        const HudMap *m=hud_maps+i;
        HudAnim a;
        float sx=m->sx,sy=m->sy,ex=sx+m->w,ey=sy+m->h;
        float l=sx>u0?sx:u0,t=sy>v0?sy:v0;
        float r=ex<u1?ex:u1,b=ey<v1?ey:v1;
        if(l>=r || t>=b) continue;
        a.id=HUD_GLOBAL_ID; a.width=512; a.height=128;
        a.u0=(m->x+l-sx)/512.0f; a.v0=(m->y+t-sy)/128.0f;
        a.u1=(m->x+r-sx)/512.0f; a.v1=(m->y+b-sy)/128.0f;
        a.cx=0; a.cy=0; a.sx=parent->sx; a.sy=parent->sy;
        memory[3]=(memory[3]&~0x06000000u)|((h_u32)m->bank<<25);
        /* This sprite API takes a global GBIX, independent of the model texture list. */
        cache[0]=cache[1]=0xffffffffu;
        original_hud(&a,HUD_GLOBAL_ID,color,left+(l-u0)*parent->sx,top+(t-v0)*parent->sy,z);
        native_hud_diagnostics[5]++;
    }
    cache[0]=cache[1]=0xffffffffu;
    ((int (*)(h_u32))0x8c05dc00)(texture);
}
