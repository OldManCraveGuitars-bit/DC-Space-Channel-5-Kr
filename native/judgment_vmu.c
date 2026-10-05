/* SC5 JP's original asynchronous VMU driver. No emulator/file-system calls. */
typedef unsigned char v_u8;
typedef unsigned short v_u16;
typedef unsigned int v_u32;
extern volatile v_u32 native_judgment_level;
extern int original_vmu_result(v_u32,v_u32,v_u32,v_u32);
extern int original_vmu_completion(v_u32,v_u32,v_u32);

static const char setting_name[] = "SC5KR_JUDGE";
static const char setting_id[] = "SC5KR-JUDGE-V1";
static v_u8 setting_package[1024] __attribute__((aligned(32)));
static v_u8 setting_time[8];
static v_u32 loaded,dirty,delay,operation,written_level;
/* state: 0 waiting, 1 absent, 2 loaded, 3 saving, 4 saved, 5 error.
   The final driver callback is retained for diagnostics, not treated as a
   successful write until the original driver has released its job. */
volatile v_u32 native_judgment_vmu_diagnostics[12];

static void copy(v_u8 *to,const v_u8 *from,unsigned length) {
    while (length--) *to++=*from++;
}
static unsigned crc(const v_u8 *p,unsigned length) {
    unsigned value=0,i,j;
    for(i=0;i<length;++i) {
        value^=(unsigned)p[i]<<8;
        for(j=0;j<8;++j) value=(value<<1)^((value&0x8000)?0x1021:0);
        value&=0xffff;
    }
    return value;
}
static unsigned valid(void) {
    unsigned i,saved,computed;
    for(i=0;i<sizeof(setting_id)-1;++i)
        if(setting_package[48+i]!=(v_u8)setting_id[i]) return 0;
    if(*(v_u16 *)(setting_package+64)!=1 || *(v_u16 *)(setting_package+68)!=0 ||
       *(v_u32 *)(setting_package+72)!=16 ||
       *(v_u32 *)(setting_package+640)!=0x314a354b ||
       setting_package[644]<1 || setting_package[644]>6 ||
       setting_package[645]!=(v_u8)(setting_package[644]^0xff)) return 0;
    saved=*(v_u16 *)(setting_package+70);
    *(v_u16 *)(setting_package+70)=0;
    computed=crc(setting_package,656);
    *(v_u16 *)(setting_package+70)=saved;
    return saved==computed;
}
static void prepare(void) {
    unsigned i;
    for(i=0;i<1024;++i) setting_package[i]=0;
    copy(setting_package,(const v_u8 *)"SC5 KR JUDGMENT",15);
    copy(setting_package+16,(const v_u8 *)"Space Channel 5 KR settings",27);
    copy(setting_package+48,(const v_u8 *)setting_id,sizeof(setting_id)-1);
    *(v_u16 *)(setting_package+64)=1;
    *(v_u16 *)(setting_package+66)=4;
    *(v_u32 *)(setting_package+72)=16;
    /* The original save's palette and first icon, without new artwork. */
    copy(setting_package+96,(const v_u8 *)0x8c03add8,32);
    copy(setting_package+128,(const v_u8 *)0x8c03adf8,512);
    *(v_u32 *)(setting_package+640)=0x314a354b; /* K5J1 */
    setting_package[644]=(v_u8)native_judgment_level;
    setting_package[645]=(v_u8)(native_judgment_level^0xff);
    *(v_u16 *)(setting_package+70)=(v_u16)crc(setting_package,656);
}
void native_judgment_vmu_changed(void) {
    dirty=1;
    delay=90; /* Debounce navigation: one write for a settled selection. */
}
int native_vmu_result(v_u32 unit,v_u32 command,v_u32 step,v_u32 result) {
    if(operation && unit==0) {
        native_judgment_vmu_diagnostics[4]=unit;
        native_judgment_vmu_diagnostics[5]=command;
        native_judgment_vmu_diagnostics[6]=step;
        native_judgment_vmu_diagnostics[11]=result;
        native_judgment_vmu_diagnostics[8]++;
        return 0;
    }
    return original_vmu_result(unit,command,step,result);
}
int native_vmu_completion(v_u32 unit,v_u32 command,v_u32 result) {
    if(operation && unit==0 && (command==11 || command==12)) {
        native_judgment_vmu_diagnostics[7]=result;
        native_judgment_vmu_diagnostics[9]=1;
        return 0;
    }
    /* Original driver callbacks 1/2 report insertion/removal. */
    if(unit==0 && (command==1 || command==2)) loaded=0;
    return original_vmu_completion(unit,command,result);
}
void native_judgment_vmu_tick(void) {
    volatile v_u32 *manager=*(volatile v_u32 **)0x8c103a50;
    volatile v_u16 *ready=(volatile v_u16 *)(0x8c103a60+60);
    int (*busy)(unsigned)=(void *)0x8c04a240;
    int (*info)(unsigned,const char *,void *)=(void *)0x8c04a20e;
    int (*read)(unsigned,const char *,void *,unsigned)=(void *)0x8c04a364;
    int (*write)(unsigned,const char *,void *,unsigned,void *,v_u32)=(void *)0x8c04a3bc;
    v_u32 entry[5];
    int found;
    if(delay) --delay;
    if(operation) {
        if(busy(0)) return;
        if(operation==1) {
            if(native_judgment_vmu_diagnostics[9] && native_judgment_vmu_diagnostics[7]==0 && valid()) {
                if(!dirty) native_judgment_level=setting_package[644];
                native_judgment_vmu_diagnostics[0]=2;
            } else native_judgment_vmu_diagnostics[0]=5;
        } else if(native_judgment_vmu_diagnostics[9] && native_judgment_vmu_diagnostics[7]==0) {
            if(native_judgment_level==written_level) dirty=0;
            native_judgment_vmu_diagnostics[0]=4;
            native_judgment_vmu_diagnostics[2]=written_level;
            native_judgment_vmu_diagnostics[3]++;
        } else {native_judgment_vmu_diagnostics[0]=5;delay=300;}
        operation=0;
    }
    native_judgment_vmu_diagnostics[1]=dirty;
    if(!manager || manager[0]!=5 || ready[0]!=1 || ready[1]!=1 || busy(0)) return;
    if(!loaded) {
        if(delay) return;
        found=info(0,setting_name,entry);
        loaded=1;
        if(found==0) {
            /* Reject a same-name file of a different size before raw read. */
            if(*(v_u16 *)((v_u8 *)entry+4)!=2) {
                native_judgment_vmu_diagnostics[0]=5;return;
            }
            operation=1;
            native_judgment_vmu_diagnostics[9]=0;
            native_judgment_vmu_diagnostics[7]=0xffffffff;
            if(read(0,setting_name,setting_package,0)!=0) {
                operation=0;loaded=0;delay=300;
            }
            return;
        }
        native_judgment_vmu_diagnostics[0]=1;
    }
    if(!dirty || delay) return;
    /* Refuse to overwrite a foreign file using our filename. */
    found=info(0,setting_name,entry);
    if(found==0 && (!valid() || *(v_u16 *)((v_u8 *)entry+4)!=2)) {
        native_judgment_vmu_diagnostics[0]=5;delay=300;return;
    }
    prepare();
    ((void (*)(void *))0x8c0109a0)(setting_time);
    written_level=native_judgment_level;
    native_judgment_vmu_diagnostics[7]=0xffffffff;
    native_judgment_vmu_diagnostics[9]=0;
    operation=2;
    if(write(0,setting_name,setting_package,2,setting_time,0x80000000u)!=0) {
        operation=0;delay=300;native_judgment_vmu_diagnostics[0]=5;
    } else native_judgment_vmu_diagnostics[0]=3;
}
