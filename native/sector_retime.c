#include <stdint.h>
#include <string.h>
#define EXPORT __declspec(dllexport)
static uint32_t edc_tab[256];
static uint8_t fwd[256], back[256];
static int ready;
static void init(void) {
    if (ready) return;
    for (unsigned i=0;i<256;i++) {
        uint32_t v=i;
        for (unsigned j=0;j<8;j++) v=(v>>1)^((v&1)?0xD8018001u:0);
        edc_tab[i]=v;
        unsigned step=((i<<1)^((i&128)?0x11d:0))&255;
        fwd[i]=(uint8_t)step; back[i^step]=(uint8_t)i;
    }
    ready=1;
}
static void ecc(const uint8_t *s, unsigned majors, unsigned minors,
                unsigned mult, unsigned inc, uint8_t *dest) {
    unsigned size=majors*minors;
    for (unsigned major=0;major<majors;major++) {
        unsigned index=(major>>1)*mult+(major&1);
        uint8_t a=0,b=0;
        for (unsigned minor=0;minor<minors;minor++) {
            uint8_t v=s[index]; index=(index+inc)%size;
            a=fwd[a^v]; b^=v;
        }
        a=back[fwd[a]^b]; dest[major]=a; dest[major+majors]=a^b;
    }
}
static void checksum(uint8_t *s) {
    uint32_t v=0;
    for (unsigned i=0;i<2064;i++) v=(v>>8)^edc_tab[(v^s[i])&255];
    for (unsigned i=0;i<4;i++) s[2064+i]=(uint8_t)(v>>(8*i));
    memset(s+2068,0,8);
    ecc(s+12,86,24,2,86,s+2076);
    ecc(s+12,52,43,86,88,s+2248);
}
static int mode1(const uint8_t *s) {
    static const uint8_t sync[12]={0,255,255,255,255,255,255,255,255,255,255,0};
    return !memcmp(s,sync,12) && s[15]==1;
}
static uint8_t bcd(unsigned v) {return (uint8_t)(((v/10)<<4)|(v%10));}
EXPORT int retime_sectors(uint8_t *data, unsigned count, unsigned lba) {
    init();
    for (unsigned i=0;i<count;i++) {
        uint8_t *s=data+i*2352; if (!mode1(s)) return -(int)i-1;
        unsigned t=lba+i+150;
        s[12]=bcd(t/4500); s[13]=bcd((t/75)%60); s[14]=bcd(t%75);
        checksum(s);
    }
    return 0;
}
EXPORT int verify_sectors(const uint8_t *data, unsigned count, unsigned lba) {
    init(); uint8_t copy[2352];
    for (unsigned i=0;i<count;i++) {
        const uint8_t *s=data+i*2352; if (!mode1(s)) return -(int)i-1;
        unsigned t=lba+i+150;
        if (s[12]!=bcd(t/4500)||s[13]!=bcd((t/75)%60)||s[14]!=bcd(t%75)) return -(int)i-1;
        memcpy(copy,s,2352); checksum(copy);
        if (memcmp(copy,s,2352)) return -(int)i-1;
    }
    return 0;
}
