/* Space Channel 5 JP native SH-4 subtitles. No emulator services or host files. */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef int s32;
void *memset(void *dest, int value, unsigned n) {
    unsigned i; u8 *p = dest;
    for (i = 0; i < n; ++i) p[i] = value;
    return dest;
}
typedef struct { u8 x, y, w, h; } Rect;
typedef struct { u16 first, count; u8 advance, reserved; } Glyph;
typedef struct { u32 start, end; u16 first, count; u16 bottom, reserved; } Cue;
typedef struct { u32 archive, duration; u16 member, first, count, reserved; } Binding;
#include "generated_data.h"

extern u32 original_voice_start(void *, u32, u32);
extern u32 original_voice_stop(void *);
extern u32 original_movie_start(void *, const char *);
extern u32 original_movie_stop(void *);
extern void original_frame(u32 direct_list);
typedef struct { void *handle; const Binding *binding; u32 sequence; } Playing;
static Playing playing[16];
static u32 sequence;
/* Read-only diagnostic words are part of the ROM payload, never host controls. */
volatile u32 native_diagnostics[12];

static void forget(void *handle) {
    unsigned i;
    for (i = 0; i < 16; ++i) if (playing[i].handle == handle) playing[i].handle = 0;
}
static void remember(void *handle, const Binding *binding) {
    unsigned i, oldest = 0;
    forget(handle);
    if (!binding) return;
    for (i = 0; i < 16; ++i) {
        if (!playing[i].handle) break;
        if (playing[i].sequence < playing[oldest].sequence) oldest = i;
    }
    if (i == 16) i = oldest;
    playing[i].binding = binding;
    playing[i].sequence = ++sequence;
    playing[i].handle = handle;
    native_diagnostics[2]++;
    native_diagnostics[3] = binding - bindings;
}
u32 native_voice_start(void *handle, u32 slot, u32 member) {
    u32 result = original_voice_start(handle, slot, member), archive = 0;
    unsigned i;
    if (slot < 32) {
        u32 *table = ((u32 **)0x8c1e78d8)[slot];
        if ((u32)table >= 0x8c000000 && (u32)table < 0x8d000000) archive = table[2];
    }
    for (i = 0; i < BINDING_COUNT; ++i)
        if (bindings[i].archive == archive && bindings[i].member == member) break;
    remember(handle, i < BINDING_COUNT ? bindings + i : 0);
    return result;
}
u32 native_voice_stop(void *handle) { forget(handle); return original_voice_stop(handle); }
static int equal_name(const char *a, const char *b) {
    unsigned i;
    for (i = 0; i < 40; ++i) {
        u8 x = a[i], y = b[i];
        if (x >= 'A' && x <= 'Z') x += 32;
        if (x != y) return 0;
        if (!x) return 1;
    }
    return 0;
}
u32 native_movie_start(void *handle, const char *name) {
    u32 result = original_movie_start(handle, name);
    unsigned i;
    /* Original start calls original stop internally. Register after it returns. */
    for (i = 0; i < MOVIE_COUNT; ++i) if (equal_name(name, movie_names[i])) break;
    remember(handle, i < MOVIE_COUNT ? bindings + movie_binding[i] : 0);
    return result;
}
u32 native_movie_stop(void *handle) { forget(handle); return original_movie_stop(handle); }

/* Integer-generated IEEE754 coordinates in the game's 640 x 480 viewport. */
static u32 coordinate(unsigned n) {
    unsigned shift = 0, value = n;
    if (!n) return 0;
    while (value >>= 1) ++shift;
    return ((shift + 127) << 23) | ((n << (23 - shift)) & 0x7fffff);
}
static void packet(const u32 *words) {
    volatile u32 *sq = (volatile u32 *)0xe0000000;
    unsigned i;
    for (i = 0; i < 8; ++i) sq[i] = words[i];
    __asm__ volatile("pref @%0" :: "r"(sq) : "memory");
}
static u32 lock_queues(void) {
    u32 saved, masked;
    __asm__ volatile("stc sr,%0" : "=r"(saved));
    masked = saved | 0xf0;
    __asm__ volatile("ldc %0,sr" :: "r"(masked) : "memory");
    return saved;
}
static void unlock_queues(u32 saved) {
    __asm__ volatile("ldc %0,sr" :: "r"(saved) : "memory");
}
static void header(u32 color) {
    /* Translucent, untextured sprite; always pass depth, disable Z writes. */
    u32 words[8] = {0xa2000000, 0xe4000000, 0x94900000, 0, color, 0, 0, 0};
    packet(words);
}
static void rectangle(unsigned x, unsigned y, unsigned w, unsigned h, u32 z) {
    u32 left = coordinate(x), right = coordinate(x + w);
    u32 top = coordinate(y), bottom = coordinate(y + h);
    /* PVR sprites use perimeter order A/B/C/D, rather than a triangle strip. */
    u32 a[8] = {0xf0000000, left, top, z, right, top, z, right};
    u32 b[8] = {bottom, z, left, bottom, 0, 0, 0, 0};
    packet(a); packet(b);
}
extern volatile u32 native_judgment_menu_ready;
extern void native_draw_judgment(void);
void native_menu_color(u32 color) { header(color); }
void native_menu_rect(unsigned x,unsigned y,unsigned w,unsigned h) {
    rectangle(x,y,w,h,0x49742410);
}
static void draw(const Cue *cue) {
    unsigned i, j, start = 0, width = 0, lines = 1, max_width = 0;
    unsigned widths[4] = {0,0,0,0}, ends[4] = {0,0,0,0}, line = 0;
    const u16 *text = text_ids + cue->first;
    u32 q0, q1;
    for (i = 0; i < cue->count; ++i) {
        u16 id = text[i];
        if (id == 0xffff || (width + glyphs[id].advance > 568 && width)) {
            if (lines == 4) return;
            widths[line] = width; ends[line++] = i; width = 0; ++lines;
            if (id == 0xffff) continue;
        }
        width += glyphs[id].advance;
    }
    widths[line] = width; ends[line] = cue->count;
    for (i = 0; i < lines; ++i) if (widths[i] > max_width) max_width = widths[i];
    if (!max_width) return;
    q0 = *(volatile u32 *)0xff000038; q1 = *(volatile u32 *)0xff00003c;
    *(volatile u32 *)0xff000038 = 0x10; *(volatile u32 *)0xff00003c = 0x10;
    {
        unsigned y = 480 - cue->bottom - lines * 28;
        header(NATIVE_BOX_COLOR);
        rectangle((640 - max_width) / 2 - 8, y - 5, max_width + 16, lines * 28 + 10, 0x49742400);
        header(0xffffffff);
        for (line = 0; line < lines; ++line) {
            unsigned x = (640 - widths[line]) / 2;
            for (i = start; i < ends[line]; ++i) {
                u16 id = text[i]; const Glyph *g;
                if (id == 0xffff) continue;
                g = glyphs + id;
                for (j = 0; j < g->count; ++j) {
                    const Rect *r = glyph_rects + g->first + j;
                    rectangle(x + r->x, y + r->y, r->w, r->h, 0x49742410);
                }
                x += g->advance;
            }
            start = ends[line];
            if (start < cue->count && text[start] == 0xffff) ++start;
            y += 28;
        }
    }
    *(volatile u32 *)0xff000038 = q0; *(volatile u32 *)0xff00003c = q1;
    native_diagnostics[4]++;
    native_diagnostics[5] = cue - cues;
}
static const Cue *current_cue(void) {
    unsigned i, j; const Cue *chosen = 0; u32 newest = 0;
    for (i = 0; i < 16; ++i) {
        Playing *p = playing + i; u32 count = 0, frequency = 1, elapsed;
        if (!p->handle) continue;
        if ((u32)p->handle < 0x8c000000 || (u32)p->handle >= 0x8d000000) {p->handle = 0; continue;}
        if (p->binding->archive == 0) {
            if (!((u32 *)p->handle)[14]) {p->handle = 0; continue;}
            ((void (*)(void *, u32 *, u32 *))0x8c058234)(p->handle, &count, &frequency);
        } else {
            u8 state = ((u8 *)p->handle)[1];
            if (!((u32 *)p->handle)[2] || state == 5) {p->handle = 0; continue;}
            ((void (*)(void *, u32 *, u32 *))0x8c0560fc)(p->handle, &count, &frequency);
        }
        /* The SDK reports count=0/frequency=1 while a stream is preparing.
           File-open time is not speech time: wait for a real sample clock. */
        if (frequency < 8000) continue;
        elapsed = (count / frequency) * 1000 + (count % frequency) * 1000 / frequency;
        if (elapsed > p->binding->duration + 500) {p->handle = 0; continue;}
        native_diagnostics[6] = elapsed; native_diagnostics[7] = frequency;
        for (j = 0; j < p->binding->count; ++j) {
            const Cue *c = cues + p->binding->first + j;
            if (elapsed >= c->start && elapsed < c->end && p->sequence >= newest) {
                chosen = c; newest = p->sequence;
            }
        }
    }
    return chosen;
}
void native_frame(u32 direct_list) {
    const Cue *cue;
    native_diagnostics[0] = 0x5343354b;
    native_diagnostics[1]++;
    native_diagnostics[8] = direct_list;
    native_diagnostics[9] = *(volatile u32 *)0x8c21c040;
    native_diagnostics[10] = *(volatile u32 *)0x8c21c088;
    cue = current_cue();
#ifdef NATIVE_DIAGNOSTIC_CUE
    if (!cue) cue = &diagnostic_cue;
#endif
    /* SC5 uses direct opaque submission followed by one buffered translucent
       list (mask 5). Append before that list's EOL so presorted game polygons
       cannot cover the subtitles. Transfer this list through the SH-4 store
       queues synchronously; no DMA/EOL race and no extra RAM/VRAM allocation.
       Frames without subtitles retain the original DMA path. */
    if ((cue || native_judgment_menu_ready) && direct_list == 0 && native_diagnostics[9] == 32 &&
        native_diagnostics[10] == 5) {
        unsigned frame = *(volatile u32 *)0x8c21bf7c;
        unsigned index = 8 + frame;
        const u32 *source = ((const u32 **)0x8c21bfa0)[index];
        u32 bytes = ((volatile u32 *)0x8c21bff0)[index];
        if (frame < 4 && bytes && !(bytes & 31) && bytes < 0x200000 &&
            ((u32)source & 0x1f000000) == 0x0c000000 &&
            ((u32)source & 0xffffff) + bytes + 32 <= 0x1000000 &&
            !(source[bytes / 4] & 0xe0000000)) {
            u32 saved_sr = lock_queues();
            u32 q0 = *(volatile u32 *)0xff000038;
            u32 q1 = *(volatile u32 *)0xff00003c;
            unsigned offset;
            *(volatile u32 *)0xff000038 = 0x10;
            *(volatile u32 *)0xff00003c = 0x10;
            for (offset = 0; offset < bytes / 4; offset += 8) packet(source + offset);
            if (cue) draw(cue);
            if (native_judgment_menu_ready) native_draw_judgment();
            native_judgment_menu_ready=0;
            /* The SDK stores the EOL just beyond its recorded byte count. */
            packet(source + bytes / 4);
            *(volatile u32 *)0xff000038 = q0;
            *(volatile u32 *)0xff00003c = q1;
            unlock_queues(saved_sr);
            native_diagnostics[11]++;
            return;
        }
    }
    original_frame(direct_list);
}
