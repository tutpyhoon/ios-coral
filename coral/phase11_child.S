/* CORAL 11 secondary statically signed ARM64 Mach-O from /bin/coral-child.
 * NOT Apple's code. Must run only after PID1 fork+execve.
 */
#define SYS_exit 1
#define SYS_write 4
#define SYS_open 5
#define SYS_getpid 20
#define O_RDWR 2
.text
.globl _start
.p2align 2
_start:
    and x9, sp, #~15
    mov sp, x9
    adr x0, console
    mov x1, #O_RDWR
    mov x2, #0
    mov x16, #SYS_open
    svc #0x80
    b.cs failed
    mov x19, x0

    mov x16, #SYS_getpid
    svc #0x80
    b.cs failed
    cmp x0, #1
    b.le failed                /* Child must NOT be PID 1. */

    adr x1, pass
    adr x2, pass_end
    sub x2, x2, x1
    mov x0, x19
    mov x16, #SYS_write
    svc #0x80
    b.cs failed

    mov x0, #0
    mov x16, #SYS_exit
    svc #0x80
failed:
    mov x0, #29
    mov x16, #SYS_exit
    svc #0x80
1:  b 1b

console:
    .asciz "/dev/console"
pass:
    .ascii "CORAL11: child exec succeeded\n"
pass_end:
