/**
 * bus_decode.h  --  Table-driven C64 expansion port decode for MonitorTask
 *
 * The C64 qualifies every CPU access to the I/O pages with /IO1 ($DE00-$DEFF)
 * and /IO2 ($DF00-$DFFF), so the page never has to be decoded: the line that
 * goes LOW gives it, and A0-A7 give the offset.  Everything that depends on
 * the offset and on the card state is precomputed here into 256-entry tables.
 *
 * Snapshots used by the bus loop:
 *   dedicated GPIO input  bit 0 = PHI2, bit 1 = R/W, bit 2 = /IO1, bit 3 = /IO2
 *   GPIO.in               bits 12-19 = A0-A7, bits 4-11 = D0-D7
 *
 * IO2 table entry (uint8_t), indexed by [VERA selected][A0-A7]:
 *   bit 0      dedicated GPIO output level of DEV_SEL_N
 *   CT_IO2     always set: the cycle belongs to the card
 *   CT_WR_REG  write cycle: latch / GeoRAM register at this offset
 *
 * /IO1 needs no table: the GeoRAM window is always active and the byte is
 * win[A0-A7], win being the 256-byte page selected by $DFFE/$DFFF.
 *
 * No ESP-IDF dependencies: also compiled by the host test (test/).
 * Style: Allman
 */

#ifndef BUS_DECODE_H
#define BUS_DECODE_H

#include <stdint.h>
#include <stdbool.h>

/* The hot loop runs from IRAM: helpers must never become calls into flash. */
#define BUS_INLINE static inline __attribute__((always_inline))

#define DEDIC_OUT_DEVSELN    (1u << 0)
#define DEDIC_OUT_CTRL_MASK  0x01u
#define DEDIC_OUT_CTRL_IDLE  0x01u   /* HIGH = deasserted (active LOW) */

/* Dedicated GPIO input channels */
#define DEDIC_IN_PHI2        (1u << 0)
#define DEDIC_IN_RW          (1u << 1)
#define DEDIC_IN_IO1N        (1u << 2)
#define DEDIC_IN_IO2N        (1u << 3)
#define DEDIC_IN_IO_MASK     (DEDIC_IN_IO1N | DEDIC_IN_IO2N)

#define CT_IO2     (1u << 5)
#define CT_IO1     (1u << 6)
#define CT_WR_REG  (1u << 7)

/* IO2 map.  The GeoRAM registers sit at the top of IO2 ($DFFE/$DFFF), so the
 * VERA uses the bottom of IO2 and the select latch sits just below them. */
#define VERA_REG_BASE       0xDF00u  /* VERA registers $DF00-$DF1F */
#define VERA_REG_COUNT      0x20u
#ifndef CARD_SEL_LATCH
#define CARD_SEL_LATCH      0xFDu    /* $DFFD: VERA select, write != 0 selects, 0 deselects */
#endif
#define GEORAM_PAGE_REG     0xFEu    /* $DFFE: 256-byte page in block (0-63) */
#define GEORAM_BLOCK_REG    0xFFu    /* $DFFF: 16 KB block (0-15 for 256 KB) */

#define GEORAM_PAGE_MASK    0x3Fu
#define GEORAM_BLOCK_MASK   0x0Fu

/*
 * IO2 entry for one offset: DEV_SEL_N for the VERA registers $DF00-$DF1F
 * only while the VERA is selected; the latch and the GeoRAM registers are
 * always written (the GeoRAM is always active, like the original cartridge).
 */
BUS_INLINE uint32_t bus_io2_ctrl(uint32_t off8, bool selected)
{
    uint32_t c = DEDIC_OUT_CTRL_IDLE | CT_IO2;
    if (selected && off8 < VERA_REG_COUNT)
        c &= ~DEDIC_OUT_DEVSELN;
    if (off8 == CARD_SEL_LATCH || off8 == GEORAM_PAGE_REG || off8 == GEORAM_BLOCK_REG)
        c |= CT_WR_REG;
    return c;
}

/* Fill the IO2 tables: [0] VERA deselected, [1] VERA selected. */
static inline void bus_build_io2_tables(uint8_t io2[2][256])
{
    for (uint32_t sel = 0; sel < 2u; sel++)
        for (uint32_t off8 = 0; off8 < 256u; off8++)
            io2[sel][off8] = (uint8_t)bus_io2_ctrl(off8, sel != 0);
}

/* Offset of the GeoRAM page visible at $DE00. */
BUS_INLINE uint32_t bus_georam_offset(uint32_t block, uint32_t page)
{
    return ((block & GEORAM_BLOCK_MASK) << 14) | ((page & GEORAM_PAGE_MASK) << 8);
}

#endif /* BUS_DECODE_H */
