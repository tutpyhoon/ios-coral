/* CORAL Phase 12 experimental *READ-ONLY* UFS media probe.
 * Called only with EL1/MMU-off and live-Google-DT checks from flame/probe.c.
 * This DOES write UFS host-controller QUEUE REGISTERS and ring its doorbell:
 * it does NOT issue SCSI WRITE or modify storage media. Unlike reg-only 06,
 * DMA is required and MAY hang on unknown SMMU mappings. NEVER auto-flash.
 */
#ifndef CORAL_UFS_MEDIA12_H
#define CORAL_UFS_MEDIA12_H

#define CORAL_UFS 0x01d84000UL
#define UFS_REG_CAP 0x00
#define UFS_REG_HCS 0x30
#define UFS_REG_HCE 0x34
#define UFS_REG_UTRLBA 0x50
#define UFS_REG_UTRLBAU 0x54
#define UFS_REG_UTRLDBR 0x58
#define UFS_REG_UTRLRSR 0x60
#define UFS_HCS_DP 1u
#define UFS_HCS_UTRLRDY 2u
#define UFS_BLOCK 4096u

struct coral_utrd {
    uint32_t dw0, dw1, dw2, dw3;
    uint32_t ucdba, ucdbau, resp, prdt;
};
struct coral_ucd {
    uint8_t cmd[512];
    uint8_t resp[512];
    struct {
        uint32_t addr_lo, addr_hi, reserved, dbc;
    } prdt[1];
};
_Static_assert(sizeof(struct coral_utrd) == 32, "unexpected UTRD");
_Static_assert(sizeof(struct coral_ucd) == 1040, "unexpected UCD");

static volatile struct coral_utrd c_utrl[32] __attribute__((aligned(1024)));
static volatile struct coral_ucd c_ucd __attribute__((aligned(128)));
static volatile uint8_t c_data[UFS_BLOCK] __attribute__((aligned(4096)));
static unsigned c_tag = 0;
static int c_took_over = 0;

static uint32_t c_read(uint32_t offset)
{
    __asm__ volatile("dsb sy" ::: "memory");
    uint32_t val = *(volatile uint32_t *)(CORAL_UFS + offset);
    __asm__ volatile("dsb sy" ::: "memory");
    return val;
}
static void c_write(uint32_t offset, uint32_t value)
{
    __asm__ volatile("dsb sy" ::: "memory");
    *(volatile uint32_t *)(CORAL_UFS + offset) = value;
    __asm__ volatile("dsb sy" ::: "memory");
}
static void c_zero(volatile void *ptr, unsigned size)
{
    volatile uint8_t *p = (volatile uint8_t *)ptr;
    for (unsigned i=0; i<size; i++) p[i] = 0;
}
static uint32_t c_be32(volatile const uint8_t *p)
{
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 |
           (uint32_t)p[2] << 8 | p[3];
}
static uint64_t c_ticks(void)
{
    uint64_t t;
    __asm__ volatile("isb; mrs %0, cntvct_el0":"=r"(t));
    return t;
}

/* Whitelist: TEST UNIT READY, READ CAPACITY (10), READ(10) at GPT LBA1.
 * no arbitrary CDB, no write CDB, no filesystem modification.
 */
static uint32_t c_command(uint8_t opcode, uint32_t lba, uint32_t bytes)
{
    if (!c_took_over) return 90;
    if (opcode != 0x00 && opcode != 0x25 && opcode != 0x28) return 91;
    if ((opcode == 0x00 && bytes != 0) ||
        (opcode == 0x25 && bytes != 8) ||
        (opcode == 0x28 && (lba != 1 || bytes != UFS_BLOCK))) return 92;
    if (c_read(UFS_REG_UTRLDBR)) return 93;

    c_zero(c_utrl, sizeof(c_utrl));
    c_zero(&c_ucd, sizeof(c_ucd));
    c_zero(c_data, sizeof(c_data));
    c_ucd.cmd[0] = 0x01;                   /* UFS COMMAND */
    c_ucd.cmd[1] = bytes ? 0x40 : 0x00;   /* read direction */
    c_ucd.cmd[2] = 0;                     /* LUN 0 */
    c_ucd.cmd[3] = (uint8_t)++c_tag;
    c_ucd.cmd[12] = (uint8_t)(bytes >> 24);
    c_ucd.cmd[13] = (uint8_t)(bytes >> 16);
    c_ucd.cmd[14] = (uint8_t)(bytes >> 8);
    c_ucd.cmd[15] = (uint8_t)bytes;
    c_ucd.cmd[16] = opcode;
    if (opcode == 0x28) {
        c_ucd.cmd[18] = (uint8_t)(lba >> 24);
        c_ucd.cmd[19] = (uint8_t)(lba >> 16);
        c_ucd.cmd[20] = (uint8_t)(lba >> 8);
        c_ucd.cmd[21] = (uint8_t)lba;
        c_ucd.cmd[24] = 0;
        c_ucd.cmd[25] = 1;
    }

    uintptr_t cmd_phys = (uintptr_t)&c_ucd;
    c_utrl[0].dw0 = (1u << 28) | ((bytes ? 2u : 0u) << 25) | (1u << 24);
    c_utrl[0].dw2 = 0x0f; /* invalid before controller updates */
    c_utrl[0].ucdba = (uint32_t)cmd_phys;
    c_utrl[0].ucdbau = (uint32_t)(cmd_phys >> 32);
    c_utrl[0].resp = (512u / 4u) << 16 | (512u / 4u);
    if (bytes) {
        uintptr_t data_phys = (uintptr_t)&c_data;
        c_ucd.prdt[0].addr_lo = (uint32_t)data_phys;
        c_ucd.prdt[0].addr_hi = (uint32_t)(data_phys >> 32);
        c_ucd.prdt[0].dbc = bytes - 1;
        c_utrl[0].prdt = (1024u / 4u) << 16 | 1u;
    }
    __asm__ volatile("dsb sy" ::: "memory");
    c_write(UFS_REG_UTRLDBR, 1);
    uint64_t start = c_ticks();
    const uint64_t limit = 19200000u;  /* ~1 second at verified 19.2 MHz */
    while (c_read(UFS_REG_UTRLDBR) & 1u) {
        if (c_ticks() - start >= limit)
            return 1;       /* halt; no recovery writes, restart phone */
    }
    __asm__ volatile("dsb sy" ::: "memory");
    if ((c_utrl[0].dw2 & 0xffu) != 0u) return 2;
    if (c_ucd.resp[0] != 0x21u) return 3;
    if (c_ucd.resp[7] != 0u) return 4;
    return 0;
}

static void coral_ufs_media_test(void)
{
    line("CORAL12: BOUNDED UFS MEDIA READ");
    line("NO SCSI WRITE / NO PARTITION CHANGES");
    uint32_t cap = c_read(UFS_REG_CAP);
    uint32_t hce = c_read(UFS_REG_HCE);
    uint32_t hcs = c_read(UFS_REG_HCS);
    if ((cap & (1u << 24)) == 0 || (cap & 31u) < 1u ||
        !(hce & 1u) || (hcs & (UFS_HCS_DP | UFS_HCS_UTRLRDY)) !=
           (UFS_HCS_DP | UFS_HCS_UTRLRDY) ||
        c_read(UFS_REG_UTRLDBR) != 0 || c_read(UFS_REG_UTRLRSR) != 1u) {
        line("CORAL12: UNSAFE QUEUE STATE - STOP");
        return;
    }

    /* Only state mutation is transfer-list takeover and read-command bell.
     * All referenced buffers belong to the running temporary boot image.
     * The firmware SMMU may still reject the physical DMA addresses.
     */
    uintptr_t ring = (uintptr_t)&c_utrl;
    if ((ring & 1023u) || ((uintptr_t)&c_ucd & 127u)) {
        line("CORAL12: BAD DMA ALIGNMENT - STOP");
        return;
    }
    c_write(UFS_REG_UTRLRSR, 0);
    c_write(UFS_REG_UTRLBA, (uint32_t)ring);
    c_write(UFS_REG_UTRLBAU, (uint32_t)(ring >> 32));
    c_write(UFS_REG_UTRLRSR, 1);
    if (c_read(UFS_REG_UTRLBA) != (uint32_t)ring ||
        c_read(UFS_REG_UTRLBAU) != (uint32_t)(ring >> 32) ||
        c_read(UFS_REG_UTRLRSR) != 1u) {
        line("CORAL12: UFS QUEUE TAKEOVER FAILED");
        return;
    }
    c_took_over = 1;
    line("CORAL12: UFS QUEUE TAKEOVER OK");
    uint32_t rc = c_command(0x00,0,0);
    hex("CORAL12 TUR rc",rc);
    if (rc) { line("CORAL12: STOP AFTER TUR"); return; }
    rc = c_command(0x25,0,8);
    hex("CORAL12 CAP rc",rc);
    if (rc) { line("CORAL12: STOP AFTER CAP"); return; }
    uint32_t last = c_be32(c_data);
    uint32_t block = c_be32(c_data+4);
    hex("CORAL12 LASTLBA",last);
    hex("CORAL12 BLOCK",block);
    if (block != 4096u || last < 2u) {
        line("CORAL12: UNKNOWN DEVICE GEOMETRY - STOP");
        return;
    }
    rc = c_command(0x28,1,UFS_BLOCK);
    hex("CORAL12 READ GPT rc",rc);
    if (rc) { line("CORAL12: STOP AFTER GPT READ"); return; }
    if (c_data[0]=='E' && c_data[1]=='F' && c_data[2]=='I' &&
        c_data[3]==' ' && c_data[4]=='P' && c_data[5]=='A' &&
        c_data[6]=='R' && c_data[7]=='T')
        line("CORAL12: GPT HEADER READ VERIFIED");
    else
        line("CORAL12: GPT SIGNATURE NOT FOUND");
    line("CORAL12: NO DISK WRITES EXECUTED");
}
#endif
