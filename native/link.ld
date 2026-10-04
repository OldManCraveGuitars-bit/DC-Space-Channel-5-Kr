OUTPUT_ARCH(sh)
ENTRY(_native_frame)
SECTIONS {
    . = 0x8c250000;
    .text : { *(.text*) }
    .rodata : { *(.rodata*) }
    .data : { *(.data*) }
    . = ALIGN(32);
    .bss : { *(.bss*) *(COMMON) }
    payload_end = .;
    ASSERT(payload_end <= 0x8c270000, "Native payload exceeds executable padding")
    /DISCARD/ : { *(.comment) *(.eh_frame*) *(.note*) }
}
