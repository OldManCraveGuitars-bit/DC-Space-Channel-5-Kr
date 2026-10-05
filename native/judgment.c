/* Native ROM option and player input judgment. All addresses belong to SC5 JP. */
typedef unsigned char j_u8;
typedef unsigned short j_u16;
typedef unsigned int j_u32;
typedef struct { j_u32 extent; j_u16 color,padding; } MenuPixel;
typedef struct { j_u16 first,count; } MenuRange;
#include "judgment_pixels.h"

extern void original_options(j_u32 *menu);
extern void original_judgment(void *,void *,float);
extern void original_judgment_alt(void *,void *,float);

/* This is session state in the executable; 1 is the cold-boot default. */
volatile j_u32 native_judgment_level = 1;
volatile j_u32 native_judgment_diagnostics[8];
volatile j_u32 native_judgment_menu_ready;
static j_u32 judgment_menu_focus;
extern void native_menu_color(j_u32);
extern void native_menu_rect(unsigned,unsigned,unsigned,unsigned);

void native_draw_judgment(void) {
    unsigned g,i;
    for (g=0;g<7;++g) {
        const MenuRange *range=judgment_ranges+g;
        j_u32 previous=0;
        for (i=0;i<range->count;++i) {
            const MenuPixel *p=judgment_pixels+range->first+i;
            j_u32 c=p->color,alpha=((c>>12)&15)*17;
            j_u32 rgb=(((c>>8)&15)*17<<16)|(((c>>4)&15)*17<<8)|(c&15)*17;
            if (judgment_menu_focus) rgb &= 0xffff00u;
            if (g && g!=native_judgment_level) alpha=(alpha*128+127)/255;
            c=rgb|(alpha<<24);
            if (c!=previous) {native_menu_color(c);previous=c;}
            c=p->extent;
            native_menu_rect((g ? JUDGMENT_DIGIT_X+(g-1)*24 : 56)+(c&511),JUDGMENT_ROW_Y+((c>>9)&31),
                             (c>>14)&511,(c>>23)&31);
        }
    }
}

static void menu_sound(void) {
    ((void (*)(j_u32,j_u32,j_u32))0x8c052d90)(0,12,7);
}

void native_options(j_u32 *menu) {
    volatile j_u32 *input = (volatile j_u32 *)0x8c16a2fc;
    j_u32 pressed = input[1], repeat = input[3], mask_pressed=0, mask_repeat=0;
    if (!menu[0]) {
        if ((repeat & 16) && menu[1]==0) {
            menu[1]=4; mask_repeat=16; menu_sound();
        } else if ((repeat & 32) && menu[1]==3) {
            menu[1]=4; mask_repeat=32; menu_sound();
        } else if (menu[1]==4) {
            if (repeat & 16) {
                menu[1]=3; mask_repeat=16; menu_sound();
            } else if (repeat & 32) {
                menu[1]=0; mask_repeat=32; menu_sound();
            } else if (pressed & (4|8|128)) {
                native_judgment_level = native_judgment_level==6 ? 1 : native_judgment_level+1;
                mask_pressed=4|8|128; menu_sound();
            } else if (pressed & 64) {
                native_judgment_level = native_judgment_level==1 ? 6 : native_judgment_level-1;
                mask_pressed=64; menu_sound();
            }
        }
        /* Row 4 is a value, so its A/START must never index the four-entry
           original submenu constructor table. */
        if (menu[1]==4) mask_pressed |= 4|8;
        input[1] = pressed & ~mask_pressed;
        input[3] = repeat & ~mask_repeat;
    }
    original_options(menu);
    input[1]=pressed;
    input[3]=repeat;
    if (!menu[0]) {
        judgment_menu_focus=menu[1]==4;
        native_judgment_menu_ready=1;
    }
    native_judgment_diagnostics[0]=native_judgment_level;
}

typedef struct {
    j_u8 status,actor,button,reserved;
    float outer_early,success_early,center,success_late,outer_late;
} Note;

/* Current beat is (song-frame - segment-frame)*numerator/denominator.
   The game's +0xb0 conversion rounds this ratio to an integer; read the
   original tempo command to retain the exact seconds requested by the user. */
static float extra_beats(void) {
    const j_u8 *clock = *(const j_u8 **)0x8c104c38;
    const j_u16 *tempo;
    j_u32 index,ptr;
    float result;
    if (!clock || native_judgment_level<2 || native_judgment_level>6) return 0.0f;
    index=*(const j_u32 *)(clock+84);
    if (index>=8) return 0.0f;
    ptr=*(const j_u32 *)(clock+0xbc+index*8+4);
    if (ptr<0x8c000000u || ptr>0x8cfffff8u) return 0.0f;
    tempo=(const j_u16 *)ptr;
    if (!tempo[2] || !tempo[3]) return 0.0f;
    result=(float)(native_judgment_level-1)*1.2f*(float)tempo[2]/(float)tempo[3];
    return result;
}

static void judge(void *system,void *bank,float beat,unsigned alternate) {
    j_u8 *b=bank;
    Note *notes=(Note *)(b+16);
    float saved[32][4],extra=extra_beats();
    unsigned i,count=b[3];
    if (extra>0.0f && count<=32) {
        for (i=0;i<count;++i) {
            Note *n=notes+i;
            saved[i][0]=n->outer_early; saved[i][1]=n->success_early;
            saved[i][2]=n->success_late; saved[i][3]=n->outer_late;
            n->outer_early-=extra; n->success_early-=extra;
            n->success_late+=extra; n->outer_late+=extra;
        }
        /* A resolved dance note must not swallow an early press for the next
           note when expanded windows overlap. Preserve hold/release state and
           let the original routine advance and score at most one press. */
        i=b[2];
        if (i+1<count && notes[i].status && !(notes[i].button&8) && !b[0] &&
            beat>=notes[i].center && beat>=notes[i+1].success_early)
            notes[i].outer_late=beat;
        native_judgment_diagnostics[1]++;
        native_judgment_diagnostics[2]=*(j_u32 *)&extra;
        native_judgment_diagnostics[3]=count;
        native_judgment_diagnostics[4]=(j_u32)bank;
    }
    if (alternate) original_judgment_alt(system,bank,beat);
    else original_judgment(system,bank,beat);
    if (extra>0.0f && count<=32) {
        for (i=0;i<count;++i) {
            Note *n=notes+i;
            n->outer_early=saved[i][0]; n->success_early=saved[i][1];
            n->success_late=saved[i][2]; n->outer_late=saved[i][3];
        }
    }
}
void native_judgment(void *system,void *bank,float beat) { judge(system,bank,beat,0); }
void native_judgment_alt(void *system,void *bank,float beat) { judge(system,bank,beat,1); }
