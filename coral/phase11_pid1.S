/* CORAL Phase 11 / RAM HFS+ PID 1: fork, execve, wait4.
 * A tiny, text-only, position-independent ARM64 Mach-O via pinned mkinit.py.
 * This is NOT Apple's launchd and never touches persistent storage.
 * Darwin ARM64 fork returns child pid in x0 in BOTH processes and sets
 * x1=0 in parent / x1=1 in child (see go syscall exec_bsd.go).
 */
#define SYS_exit 1
#define SYS_fork 2
#define SYS_write 4
#define SYS_open 5
#define SYS_wait4 7
#define SYS_select 93
#define SYS_execve 59
#define O_RDWR 2

.text
.globl _start
.p2align 2
_start:
    and x9, sp, #~15
    mov sp, x9

    adr x0, path_console
    mov x1, #O_RDWR
    mov x2, #0
    mov x16, #SYS_open
    svc #0x80
    b.cs fatal_no_console
    mov x19, x0              /* forever-valid console fd */

    adr x1, parent_intro
    adr x2, parent_intro_end
    bl print_range

    mov x16, #SYS_fork
    svc #0x80
    b.cs fork_error
    cmp x1, #1
    b.eq child_process
    /* Parent: x0 is child pid. Protect across printf and wait. */
    mov x21, x0
    cbz x21, fork_error
    adr x1, parent_fork
    adr x2, parent_fork_end
    bl print_range

    /* wait4(pid, &status, 0, NULL); at 16-byte aligned SP */
    sub sp, sp, #32
    str wzr, [sp]
    mov x0, x21
    mov x1, sp
    mov x2, #0
    mov x3, #0
    mov x16, #SYS_wait4
    svc #0x80
    b.cs wait_error_stack
    cmp x0, x21
    b.ne wait_error_stack
    ldr w9, [sp]
    add sp, sp, #32
    cbnz w9, child_status_error
    adr x1, parent_success
    adr x2, parent_success_end
    bl print_range
    b heartbeat

child_process:
    /* Child: argv={"/bin/coral-child",NULL}, envp={NULL} */
    sub sp, sp, #32
    adr x0, path_child
    str x0, [sp]
    str xzr, [sp, #8]
    str xzr, [sp, #16]
    mov x1, sp
    add x2, sp, #16
    mov x16, #SYS_execve
    svc #0x80
    /* A successful execve never returns. */
    add sp, sp, #32
    adr x1, child_exec_error
    adr x2, child_exec_error_end
    bl print_range
    mov x0, #111
    mov x16, #SYS_exit
    svc #0x80
    b fatal_no_console

wait_error_stack:
    add sp, sp, #32
    adr x1, wait_error
    adr x2, wait_error_end
    bl print_range
    b fatal_no_console

fork_error:
    adr x1, fork_failed
    adr x2, fork_failed_end
    bl print_range
    b fatal_no_console

child_status_error:
    adr x1, status_failed
    adr x2, status_failed_end
    bl print_range
    b fatal_no_console

heartbeat:
    adr x1, alive
    adr x2, alive_end
    bl print_range
    mov x0, #0
    mov x1, #0
    mov x2, #0
    mov x3, #0
    adr x4, five_sec
    mov x16, #SYS_select
    svc #0x80
    b heartbeat

/* x1 start, x2 end; preserve x19, x21 */
print_range:
    sub x2, x2, x1
    mov x0, x19
    mov x16, #SYS_write
    svc #0x80
    ret

fatal_no_console:
    b fatal_no_console

.p2align 3
five_sec:
    .quad 5
    .quad 0
path_console:
    .asciz "/dev/console"
path_child:
    .asciz "/bin/coral-child"
parent_intro:
    .ascii "\nCORAL11: PID1 HFS+ root active\n"
parent_intro_end:
parent_fork:
    .ascii "CORAL11: fork succeeded, waiting for child\n"
parent_fork_end:
parent_success:
    .ascii "CORAL11: child exited status 0\nCORAL11: PID1 still alive\n"
parent_success_end:
child_exec_error:
    .ascii "CORAL11 ERROR: child execve failed\n"
child_exec_error_end:
fork_failed:
    .ascii "CORAL11 ERROR: fork failed\n"
fork_failed_end:
wait_error:
    .ascii "CORAL11 ERROR: wait4 failed\n"
wait_error_end:
status_failed:
    .ascii "CORAL11 ERROR: child nonzero exit/status\n"
status_failed_end:
alive:
    .ascii "CORAL11: PID1 still alive\n"
alive_end:
