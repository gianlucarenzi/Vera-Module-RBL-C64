/**
 * test_bus_decode.c  --  host-side equivalence test for include/bus_decode.h
 *
 * Builds the IO2 tables used by MonitorTask and compares each entry, and the
 * GeoRAM window offset, with reference range-compare logic for every offset
 * x VERA selected state, and every page x block register value.
 *
 *   cc -O2 -Wall -I../../include test_bus_decode.c -o test_bus_decode && ./test_bus_decode
 *
 * The VERA registers ($DF00-$DF1F) answer only when the VERA is selected
 * through $DFFD; the latch and the GeoRAM registers ($DFFD-$DFFF) are always
 * written, the GeoRAM being always active.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include "bus_decode.h"

static unsigned long checks, errors;

static void expect(bool ok, const char *what, unsigned v)
{
    checks++;
    if (!ok && ++errors <= 20)
        printf("FAIL %s (%u)\n", what, v);
}

int main(void)
{
    static uint8_t io2[2][256];
    bus_build_io2_tables(io2);

    for (int sel = 0; sel <= 1; sel++)
    {
        for (uint32_t a = 0xDF00u; a <= 0xDFFFu; a++)
        {
            uint8_t off8 = a & 0xFFu;
            uint32_t c = io2[sel][off8];

            bool e_devsel = sel && a >= 0xDF00u && a <= 0xDF1Fu;
            bool e_reg    = a == 0xDFFDu || a == 0xDFFEu || a == 0xDFFFu;

            expect(((c & DEDIC_OUT_DEVSELN) == 0) == e_devsel, "DEV_SEL_N", a);
            expect(((c & CT_WR_REG) != 0) == e_reg, "register write", a);
            expect((c & CT_IO2) != 0 && (c & CT_IO1) == 0, "IO2 flag", a);
            expect((c & ~(DEDIC_OUT_CTRL_MASK | CT_IO2 | CT_WR_REG)) == 0, "spare bits", a);
        }
    }

    /* GeoRAM window: offset = block * 16384 + page * 256, registers masked */
    for (uint32_t block = 0; block < 256u; block++)
        for (uint32_t page = 0; page < 256u; page++)
            expect(bus_georam_offset(block, page) ==
                   (block % 16u) * 16384u + (page % 64u) * 256u, "georam offset",
                   (block << 8) | page);

    /* Dedicated input bits used by the bus loop assembly */
    expect(DEDIC_IN_IO_MASK == 0x0Cu && DEDIC_IN_RW == 2u, "dedicated input bits", 0);

    printf("=== %lu checks, %lu errors\n", checks, errors);
    return errors != 0;
}
