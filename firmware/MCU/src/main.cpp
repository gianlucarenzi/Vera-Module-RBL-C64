/**
 * esp32-main.cpp  --  Commodore 64 Expansion Port  VeraX16 + GeoRAM Controller
 *
 * Target MCU: ESP32-S3FN8 (QFN56)
 *
 * This firmware allows an ESP32-S3 to interface with the 6510 bus of a
 * Commodore 64 through the expansion (cartridge) port.  The I/O area is
 * decoded at runtime from /IO1, /IO2 and A0-A7:
 *   - IO1 ($DE00–$DEFF): GeoRAM 256 KB data window (one 256-byte page)
 *   - IO2 ($DF00–$DF1F): VERA card registers (FPGA, DEV_SEL_N)
 *   - IO2 ($DFFD)      : VERA select latch (write != 0 selects, 0 deselects)
 *   - IO2 ($DFFE)      : GeoRAM page register  (write-only, 0-63)
 *   - IO2 ($DFFF)      : GeoRAM block register (write-only, 0-15)
 *
 * The VERA responds only while selected via $DFFD; the GeoRAM (window and
 * registers) is always active, like the original cartridge.
 *
 * Every cycle is qualified by the C64 /IO1 and /IO2 lines.  The PLA asserts
 * them only for CPU accesses (AEC high): VIC-II fetches, whose addresses also
 * appear on the expansion port, never assert them and are therefore ignored.
 *
 * Style: Allman
 * Language: English
 */

#include <Arduino.h>
#include <driver/gpio.h>
#include <soc/gpio_struct.h>
#include <soc/timer_group_struct.h>
#include <hal/wdt_hal.h>
#include <stddef.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <driver/dedic_gpio.h>
#include <hal/cpu_ll.h>
#include "bus_decode.h"

/* ===========================================================================
 * Hardware Pin Mapping (ESP32-S3FN8 QFN56)
 * =========================================================================== */

/* --- Bank 0 Signals (GPIO 0-31) --- */
#define PIN_PHI2        1    /* CPU Clock Phase 2 (Pin 6) */
#define PIN_RW          2    /* Read/Write, High = Read (Pin 7) */

/* D0-D7: GPIO 4 to 11 (Pins 9-16, contiguous in Bank 0): D0 = GPIO 4 */
#define DBUS_SHIFT      4
#define DBUS_MASK       (0xFFUL << DBUS_SHIFT)

/* A0-A9: GPIO 12 to 21 (Pins 17-27, pin 20 = VDD3P3_RTC, not GPIO) */
#define ABUS_LO_MASK    0x003FF000UL

/* --- Bank 1 Signals (GPIO 32-48) --- */
#define PIN_A12         33   /* Address Bit 12 (Pin 38) */
#define PIN_A13         34   /* Address Bit 13 (Pin 39) */
#define PIN_A10         35   /* Address Bit 10 (Pin 40) */
#define PIN_A11         36   /* Address Bit 11 (Pin 41) */
#define PIN_ARESET      37   /* C64 /RESET via U27 open-drain, net ~C64_RESET, pull-down R70 (Pin 42) */
#define PIN_CRESET      38   /* Vera Chip Reset Output (Pin 43) */
#define PIN_CDONE       39   /* Vera Programmed Status Input (Pin 44) */
#define PIN_DEV_SEL_N   40   /* Vera Chip Select Output (Pin 45, active LOW) */
#define PIN_IO1_N       41   /* C64 /IO1 via U6, $DE00-$DEFF CPU access (Pin 47, active LOW) */
#define PIN_IO2_N       42   /* C64 /IO2 via U6, $DF00-$DFFF CPU access (Pin 48, active LOW) */
#define PIN_A14         45   /* Address Bit 14 (Pin 51) */
#define PIN_A15         46   /* Address Bit 15 (Pin 52) */
#define PIN_ABUS_OE_N   47   /* ~OE of U3 (A8-A15) and U4 (A0-A7), 10 kΩ pull-ups R7/R34 (Pin 37, active LOW) */

/* Serial Debug (UART0 default pins on ESP32-S3 QFN56) */
#define PIN_UART_TX     43   /* UART0 TX (Pin 49) */
#define PIN_UART_RX     44   /* UART0 RX (Pin 50) */

/*
 * Strapping Pins — Power-On Boot Configuration (ESP32-S3FN8 QFN56)
 *
 * The ESP32-S3 latches four strapping pins at every chip reset (power-on,
 * CHIP_PU, brown-out, RTC watchdog; not esp_restart()), before any firmware
 * code executes.  The levels must be valid when CHIP_PU rises and for
 * t_H = 3 ms after it (datasheet v2.2, §3, Table 3-2).
 *
 * GPIO0  —  Pin  5  |  Boot mode selection  |  Internal weak PULL-UP 45 kΩ
 *   Net BOOT0: R33 4.7 kΩ pull-up, BOOT button SW3, C61 100 nF, and R54 -> Q4
 *   (auto-reset from the programmer).  Not wired to any C64 signal.
 *   CHIP_PU has R31 4.7 kΩ + C25 1 µF (4.7 ms) against 0.47 ms on GPIO0, so
 *   GPIO0 is already HIGH when the reset is released.
 *   Sampled value: HIGH → SPI boot from embedded flash.  LOW (SW3 or Q4)
 *   → joint download boot, which also needs GPIO46 LOW (see below).
 *
 * GPIO3  —  Pin  8  |  JTAG signal source   |  NO internal pull
 *   Not used by the firmware.  R71 10 kΩ pull-up to 3V3 fixes it HIGH, as the
 *   datasheet requires (§3.4: no internal pull, must not be left floating).
 *   Table 3-5: with the default eFuses GPIO3 is ignored and JTAG goes to the
 *   USB Serial/JTAG Controller; HIGH keeps that choice even if
 *   EFUSE_STRAP_JTAG_SEL is burned, so GPIO39-42 never become JTAG pins.
 *
 * GPIO45 —  Pin 51  |  VDD_SPI voltage      |  Internal weak PULL-DOWN 45 kΩ
 * GPIO46 —  Pin 52  |  ROM messages / download mode | Internal weak PULL-DOWN 45 kΩ
 *   A14 and A15, from the expansion port through U3 (74LVC4245).  The port
 *   address lines are always driven: by the 6510 (which keeps driving them
 *   while in reset) or, during PHI1 and VIC-II DMA, by the VIC-II and the
 *   board pull-ups.  Their level cannot decide the strapping, so
 *   PIN_ABUS_OE_N (GPIO47) drives ~OE of U3 and U4, and R7/R34 (10 kΩ to 3V3)
 *   hold it HIGH while the ESP32 is in reset (GPIO47 has no pull and no
 *   power-up glitch).  With U3 disabled its outputs are high-Z and the
 *   internal pull-downs read GPIO45 = GPIO46 = LOW at every chip reset:
 *     GPIO45 LOW → VDD_SPI = 3.3 V from VDD3P3_RTC (Table 3-4), the voltage
 *                  of the FN8 in-package flash (HIGH = 1.8 V: no boot);
 *     GPIO46 LOW → ROM messages suppressed; together with GPIO0 LOW it gives
 *                  the joint download boot (GPIO0 LOW + GPIO46 HIGH is
 *                  invalid), so flashing works with the C64 running.
 *   setup() drives PIN_ABUS_OE_N LOW long after the 3 ms hold time; until
 *   then A0-A15 read as LOW or floating: the bus loop starts only afterwards.
 *   Disabling U4 as well also avoids driving GPIO12-19 against U4 during
 *   their power-up glitches (Table 2-2).
 */

/* ===========================================================================
 * Bus Timing
 *
 * On the C64 the expansion port carries the 6510 address only while AEC is
 * high, i.e. during PHI2 high (PHI1 belongs to the VIC-II), so the card
 * cannot decode in advance during PHI1 as the Atari version does.  The PLA
 * qualifies CPU accesses to $DExx/$DFxx with /IO1 or /IO2 (PLA + 74LS139, a
 * few tens of ns after PHI2 rises), and the address is stable by then.
 *
 * The bus loop therefore waits for PHI2 to rise, then for /IO1 or /IO2 for at
 * most IO_QUALIFY_NS; if neither goes LOW the cycle is not the card's (other
 * address, VIC-II fetch) and is left alone.  Otherwise it samples A0-A7 once,
 * asserts DEV_SEL_N or drives the GeoRAM byte at once.  PHI2 high lasts about
 * 490 ns (PAL 0.985 MHz / NTSC 1.023 MHz) and the 6510 samples read data
 * t_DSU = 100 ns before PHI2 falls.
 *
 * Write data is sampled BUS_WR_SAMPLE_NS after PHI2 rises (6510 write data
 * valid at most t_MDS = 200 ns after PHI2 rises, held 10 ns after it falls).
 *
 * All values can be tuned with -D after measuring the real bus.
 * =========================================================================== */
#ifndef IO_QUALIFY_NS
#define IO_QUALIFY_NS       200u
#endif
#ifndef BUS_WR_SAMPLE_NS
#define BUS_WR_SAMPLE_NS    300u
#endif

#define CPU_MHZ             (F_CPU / 1000000UL)
#define NS_TO_CYCLES(ns)    (((ns) * CPU_MHZ + 999u) / 1000u)

/* ===========================================================================
 * Helper Macros & Inline Functions
 * =========================================================================== */

/**
 * Decode D0-D7 from Bank 0 snapshot.
 */
static inline __attribute__((always_inline)) uint8_t decode_data(uint32_t lo)
{
    return (uint8_t)((lo >> DBUS_SHIFT) & 0xFFu);
}

/*
 * Dedicated GPIO channel mapping — ESP32-S3 Xtensa LX7 TIE instructions
 * (ee.get_gpio_in / ee.wr_mask_gpio_out bypass the APB bus: ~1 cycle).
 *
 * Input channels  (bit index in cpu_ll_read_dedic_gpio_in() result):
 *   Ch 0 = PHI2 (GPIO 1), Ch 1 = R/W (GPIO 2), Ch 2 = /IO1 (GPIO 41),
 *   Ch 3 = /IO2 (GPIO 42)
 *   The GPIO matrix feeds the dedicated inputs without taking the pins away:
 *   the same signals stay visible in GPIO.in / GPIO.in1.
 *
 * Output channels (bit index in cpu_ll_write_dedic_gpio_mask() mask/val):
 *   Ch 0 = DEV_SEL_N  (GPIO 40)  active LOW — VERA registers
 *
 * The GeoRAM lives in the MCU and needs no select line: the data transceiver
 * (U19) output-enable gating uses DEV_SEL_N for VERA reads and /IO1 for
 * GeoRAM reads.
 * Input and output channel spaces are independent on ESP32-S3.
 * Channel bits (DEDIC_IN_* / DEDIC_OUT_*) are defined in bus_decode.h.
 */

/* ===========================================================================
 * Compile-time Configuration
 * =========================================================================== */

/* Per-register trace (EVT_REG) for debugging.  The read trace samples the
 * data bus until PHI2 falls, which delays the next cycle: debug builds only. */
#ifndef VERA_TRACE_REGS
#define VERA_TRACE_REGS 0
#endif

/* Delay between CDONE high and the release of the C64 reset (VERA POR). */
#ifndef VERA_POST_CDONE_DELAY_US
#define VERA_POST_CDONE_DELAY_US 1000u
#endif

/* ===========================================================================
 * Log Ring (Core 1 bus loop → Core 0 LogTask, which prints on Serial)
 *
 * Single producer / single consumer, lock-free: the producer only stores the
 * event and advances `head` (a few instructions, no FreeRTOS call: the bus
 * loop runs with interrupts masked).  The consumer adds the timestamp when it
 * drains the ring.  When the ring is full new events are dropped and counted.
 * =========================================================================== */
#define LOG_RING_SIZE 64u   /* power of two */

#define EVT_LATCH 0   /* VERA select latch state change */
#define EVT_REG   1   /* VERA register ($DFxx) access */

/* flags: bit0=write(1)/read(0)  bit1=latch state (EVT_LATCH) */
typedef struct
{
    uint8_t  type;
    uint8_t  offset;  /* register offset: 0x00-0xFF within the IO2 page */
    uint8_t  data;
    uint8_t  flags;
} LogEvt;

/* ===========================================================================
 * Shared Data
 * =========================================================================== */

/* Bus decode table (see bus_decode.h), built in setup(). */
static DRAM_ATTR uint8_t bus_io2[2][256];   /* IO2 by A0-A7, [VERA selected] */

/*
 * 256 KB GeoRAM — ordinary .bss in DRAM, zeroed at startup.
 * It must not go in IRAM: the bus loop accesses it with 8-bit loads/stores,
 * and a section outside the ESP-IDF IRAM layout is not reserved on the data
 * bus (it would overlap .data, .bss and the heap through the DRAM alias).
 */
static uint8_t georam_256k[256 * 1024];

static DRAM_ATTR LogEvt   log_ring[LOG_RING_SIZE];
static DRAM_ATTR uint32_t log_head = 0;     /* written by the bus loop only */
static DRAM_ATTR uint32_t log_tail = 0;     /* written by LogTask only */
static DRAM_ATTR uint32_t log_dropped = 0;  /* written by the bus loop only */

static volatile bool log_ready = false;     /* Serial started by LogTask */

/*
 * Card state that the critical path never reads: kept in memory so that the
 * bus loop's registers stay free for the decode.  The GeoRAM registers are
 * write-only on the real cartridge; they are cleared at power-on and survive
 * a C64 reset, like the original hardware.
 */
typedef struct
{
    uint8_t  selected;  /* $DFFD latch */
    uint8_t  page;      /* $DFFE, 0-63 */
    uint8_t  block;     /* $DFFF, 0-15 */
    uint32_t log_evt;   /* latch event waiting for PHI1, 0 = none */
} BusCard;

static DRAM_ATTR BusCard card = { 0, 0, 0, 0u };

/* Bit positions hard-coded in the MonitorTask assembly. */
static_assert(DEDIC_IN_RW == (1u << 1) && DEDIC_IN_IO1N == (1u << 2) &&
              DEDIC_IN_IO_MASK == 0x0Cu && DEDIC_OUT_CTRL_MASK == 1u,
              "dedicated GPIO channels used by the bus loop assembly");

/* ===========================================================================
 * Bus Drive/Release Logic
 * =========================================================================== */

/*
 * Data bus drive (in the MonitorTask assembly): GPIO.out covers Bank 0
 * entirely, so writing the byte shifted onto D0-D7 (bits 4-11) zeros the
 * remaining bits, which are all input-configured and ignore GPIO.out; then
 * GPIO.enable_w1ts turns the outputs on.  The stores are issued back to back,
 * without the memw that the compiler puts before every volatile access:
 * Xtensa keeps stores in program order, so the value still reaches GPIO.out
 * before the outputs are enabled, but the CPU does not wait for each APB
 * write to complete.
 */

/**
 * Release the data bus (set to High-Z).  Posted store, as above.
 */
static inline __attribute__((always_inline)) void bus_release(void)
{
    asm volatile("s32i  %0, %1, %2"
                 :
                 : "r"(DBUS_MASK), "r"(&GPIO), "n"(offsetof(gpio_dev_t, enable_w1tc))
                 : "memory");
}

/*
 * PHI2 edge waits: one ee.get_gpio_in and one bit branch per sample
 * (3 cycles), the shortest polling loop.
 */
static inline __attribute__((always_inline)) void wait_phi2_high(void)
{
    uint32_t t;
    asm volatile("1: ee.get_gpio_in %0\n\t"
                 "   bbci %0, 0, 1b"
                 : "=&r"(t));
}

static inline __attribute__((always_inline)) void wait_phi2_low(void)
{
    uint32_t t;
    asm volatile("1: ee.get_gpio_in %0\n\t"
                 "   bbsi %0, 0, 1b"
                 : "=&r"(t));
}

/* Push a log event into the ring without blocking (drops if full). */
static inline __attribute__((always_inline)) void log_send(uint8_t type, uint8_t offset,
                                                           uint8_t data, uint8_t flags)
{
    uint32_t h = log_head;
    if (h - __atomic_load_n(&log_tail, __ATOMIC_ACQUIRE) >= LOG_RING_SIZE)
    {
        log_dropped++;
        return;
    }
    LogEvt *e = &log_ring[h & (LOG_RING_SIZE - 1u)];
    e->type   = type;
    e->offset = offset;
    e->data   = data;
    e->flags  = flags;
    __atomic_store_n(&log_head, h + 1u, __ATOMIC_RELEASE);
}

/*
 * A latch change is only recorded here; the event is built and pushed into
 * log_ring in the following PHI1, so that the write's side effects stay short.
 * Layout: valid << 31 | offset << 16 | data << 8 | new latch state.
 */
static inline __attribute__((always_inline)) void log_defer_latch(uint32_t offset,
                                                                  uint32_t data, uint32_t sel)
{
    card.log_evt = (1u << 31) | (offset << 16) | (data << 8) | sel;
}

static inline __attribute__((always_inline)) void log_flush_deferred(void)
{
    const uint32_t e = card.log_evt;
    if (e)
    {
        card.log_evt = 0;
        log_send(EVT_LATCH, (uint8_t)(e >> 16), (uint8_t)(e >> 8),
                 0x01u | ((e & 1u) ? 0x02u : 0x00u));
    }
}

/*
 * The bus loop runs with interrupts masked, so Core 1 no longer runs the
 * FreeRTOS tick hook that feeds the interrupt watchdog (MWDT1, checked for
 * both CPUs).  Stop that watchdog, or it resets the chip after 300 ms.
 */
static void bus_int_wdt_disable(void)
{
    wdt_hal_context_t ctx = {};
    ctx.inst = WDT_MWDT1;
    ctx.mwdt_dev = &TIMERG1;
    wdt_hal_write_protect_disable(&ctx);
    wdt_hal_disable(&ctx);
    wdt_hal_write_protect_enable(&ctx);
}

/* ===========================================================================
 * MonitorTask -- Core 1, IRAM-resident, interrupts masked
 *
 * Core 1 runs only this task: it never yields and nothing else runs there
 * (no tick, no interrupts), so no bus cycle is missed.  Core 0 runs LogTask,
 * Serial and its UART interrupt, and prints the events pushed into log_ring.
 * =========================================================================== */
static void IRAM_ATTR MonitorTask(void *arg)
{
    /*
     * Dedicated GPIO bundles — MUST be created on the executing core.
     *
     * Input  bundle: [PHI2, R/W, /IO1, /IO2]  → input  ch 0-3
     * Output bundle: [DEV_SEL_N]              → output ch 0
     */
    static const int dedic_in_pins[]  = { PIN_PHI2, PIN_RW, PIN_IO1_N, PIN_IO2_N };
    static const int dedic_out_pins[] = { PIN_DEV_SEL_N };
    dedic_gpio_bundle_handle_t dedic_in_bundle, dedic_out_bundle;
    const dedic_gpio_bundle_config_t in_cfg =
    {
        .gpio_array = dedic_in_pins,
        .array_size = 4,
        .flags      = { .in_en = 1 }
    };
    const dedic_gpio_bundle_config_t out_cfg =
    {
        .gpio_array = dedic_out_pins,
        .array_size = 1,
        .flags      = { .out_en = 1 }
    };
    ESP_ERROR_CHECK(dedic_gpio_new_bundle(&in_cfg,  &dedic_in_bundle));
    ESP_ERROR_CHECK(dedic_gpio_new_bundle(&out_cfg, &dedic_out_bundle));
    /* Immediately set all control signals HIGH (deasserted) to prevent the brief
     * glitch that would occur if the dedicated GPIO output register starts at 0. */
    cpu_ll_write_dedic_gpio_mask(DEDIC_OUT_CTRL_MASK, DEDIC_OUT_CTRL_IDLE);

    /* The decode relies on the channel positions above. */
    uint32_t in_mask = 0, out_mask = 0;
    dedic_gpio_get_in_mask(dedic_in_bundle, &in_mask);
    dedic_gpio_get_out_mask(dedic_out_bundle, &out_mask);
    if (in_mask != 0x0Fu || out_mask != DEDIC_OUT_CTRL_MASK)
    {
        Serial.printf("[VeraX16] FATAL: dedicated GPIO channels in=%02lX out=%02lX\n",
                      (unsigned long)in_mask, (unsigned long)out_mask);
        Serial.flush();
        abort();
    }

    bus_release();

    const uint32_t qualify   = NS_TO_CYCLES(IO_QUALIFY_NS);
    const uint32_t wr_sample = NS_TO_CYCLES(BUS_WR_SAMPLE_NS);

    /* Decode state, kept in registers; the IO2 table is switched by pointer. */
    const uint8_t *io2_cur = bus_io2[card.selected];
    uint8_t       *win     = &georam_256k[bus_georam_offset(card.block, card.page)];

    /* From here on Core 1 belongs to the bus: no tick, no interrupts. */
    bus_int_wdt_disable();
    portDISABLE_INTERRUPTS();

    /* The VERA is configured (setup()): release the C64, the bus goes live. */
    GPIO.out1_w1ts.val = (1UL << (PIN_ARESET - 32));

    /* Align to the end of a PHI2-high phase. */
    wait_phi2_high();
    wait_phi2_low();

    for (;;)
    {
        /* ---- PHI2 rises: the 6510 owns the port (AEC high) ------------------ */
        wait_phi2_high();
        const uint32_t t_rise  = cpu_ll_get_cycle_count();
        const uint32_t t_limit = t_rise + qualify;

        /*
         * Critical path, in assembly so that every operand stays in a
         * register and the constants are loaded before the wait:
         *   1. wait (bounded by t_limit) for /IO1 or /IO2 LOW, one dedicated
         *      read per check; if neither comes the cycle is not ours (c = 0);
         *   2. one APB read of GPIO.in (A0-A7; no memw: the last store, the
         *      bus release, left in the previous PHI1);
         *   3. /IO2: c = io2_cur[A0-A7], DEV_SEL_N for this cycle with one
         *      ee.wr_mask_gpio_out (the VERA strobes are gated by PHI2 in
         *      hardware);
         *   4. /IO1 read: drive win[A0-A7] at once.  U19 passes it to the C64
         *      because /IO1 enables it (hardware gating).
         */
        uint32_t c, din, lo, off8, t1, t2;
        asm volatile(
            "   movi   %[c], 0x0C                \n\t"   /* /IO1, /IO2 in din */
            "   movi   %[t2], 1                  \n\t"   /* DEDIC_OUT_CTRL_MASK */
            "1: ee.get_gpio_in %[din]            \n\t"
            "   bnall  %[din], %[c], 2f          \n\t"   /* /IO1 or /IO2 LOW */
            "   rsr.ccount %[t1]                 \n\t"
            "   sub    %[t1], %[t1], %[tl]       \n\t"
            "   bltz   %[t1], 1b                 \n\t"
            "   movi   %[c], 0                   \n\t"   /* not ours */
            "   j      6f                        \n\t"
            "2: l32i   %[lo], %[gpio], %[o_in]   \n\t"   /* GPIO.in */
            "   extui  %[off], %[lo], 12, 8      \n\t"   /* A0-A7 */
            "   bbci   %[din], 2, 4f             \n\t"   /* /IO1 LOW: GeoRAM */
            "   add    %[t1], %[io2], %[off]     \n\t"
            "   l8ui   %[c], %[t1], 0            \n\t"   /* io2_cur[A0-A7] */
            "   ee.wr_mask_gpio_out %[c], %[t2]  \n\t"
            "   j      6f                        \n\t"
            "4: movi   %[c], %[ct_io1]           \n\t"
            "   bbci   %[din], 1, 6f             \n\t"   /* write cycle */
            "   add    %[t1], %[win], %[off]     \n\t"
            "   l8ui   %[t1], %[t1], 0           \n\t"   /* win[A0-A7] */
            "   movi   %[t2], %[m_dbus]          \n\t"
            "   slli   %[t1], %[t1], %[sh]       \n\t"
            "   s32i   %[t1], %[gpio], %[o_out]  \n\t"   /* GPIO.out */
            "   s32i   %[t2], %[gpio], %[o_en]   \n\t"   /* GPIO.enable_w1ts */
            "6:                                  \n\t"
            : [c] "=&r"(c), [din] "=&r"(din), [lo] "=&r"(lo), [off] "=&r"(off8),
              [t1] "=&r"(t1), [t2] "=&r"(t2)
            : [tl] "r"(t_limit), [gpio] "r"(&GPIO), [io2] "r"(io2_cur), [win] "r"(win),
              [ct_io1] "n"(CT_IO1 | DEDIC_OUT_CTRL_IDLE),
              [m_dbus] "n"(DBUS_MASK), [sh] "n"(DBUS_SHIFT),
              [o_in] "n"(offsetof(gpio_dev_t, in)),
              [o_out] "n"(offsetof(gpio_dev_t, out)),
              [o_en] "n"(offsetof(gpio_dev_t, enable_w1ts))
            : "memory");

        if (c && !(din & DEDIC_IN_RW))
        {
            /* 5. Write: sample the data at a fixed time after PHI2 rises
             *    (valid from t_MDS = 200 ns to 10 ns after PHI2 falls). */
            const uint32_t t_wr = t_rise + wr_sample;
            while ((int32_t)(cpu_ll_get_cycle_count() - t_wr) < 0);
            const uint8_t data = decode_data(GPIO.in);

            /* 6. Side effects, in the rest of PHI2: the new state applies
             *    from the next cycle. */
            if (c & CT_IO1)
            {
                win[off8] = data;
            }
            else if (c & CT_WR_REG)
            {
                if (off8 == CARD_SEL_LATCH)
                {
                    const uint8_t new_sel = (data != 0u);
                    if (new_sel != card.selected)
                    {
                        card.selected = new_sel;
                        io2_cur = bus_io2[new_sel];
                        log_defer_latch(off8, data, new_sel);
                    }
                }
                else
                {
                    if (off8 == GEORAM_PAGE_REG)
                        card.page = data & GEORAM_PAGE_MASK;
                    else
                        card.block = data & GEORAM_BLOCK_MASK;
                    win = &georam_256k[bus_georam_offset(card.block, card.page)];
                }
            }
#if VERA_TRACE_REGS
            else if (!(c & DEDIC_OUT_DEVSELN))
            {
                log_send(EVT_REG, (uint8_t)off8, data, 0x01u);
            }
#endif
        }
#if VERA_TRACE_REGS
        else if (c && !(c & DEDIC_OUT_DEVSELN))
        {
            /* VERA drives the bus: sample it just before PHI2 falls. */
            uint32_t last = lo, now;
            while ((now = GPIO.in) & (1UL << PIN_PHI2))
                last = now;
            log_send(EVT_REG, (uint8_t)off8, decode_data(last), 0x00u);
        }
#endif

        /* ---- PHI1: PHI2 has fallen, the VIC-II owns the port ---------------- */
        wait_phi2_low();
        bus_release();
        cpu_ll_write_dedic_gpio_mask(DEDIC_OUT_CTRL_MASK, DEDIC_OUT_CTRL_IDLE);
        log_flush_deferred();
    }
}

/* ---------------------------------------------------------------------------
 * VERA register name lookup — Core 0 only (LogTask), not IRAM-resident.
 * Registers $09-$0C are muxed by DCSEL (bits [2:1] of VERA_CTRL, offset $05).
 * --------------------------------------------------------------------------- */
static const char *vera_reg_name(uint8_t offset, uint8_t dcsel)
{
    static const char *base[8] = {
        "VERA_ADDR_L",  /* $00 */
        "VERA_ADDR_M",  /* $01 */
        "VERA_ADDR_H",  /* $02 */
        "VERA_DATA0",   /* $03 */
        "VERA_DATA1",   /* $04 */
        "VERA_CTRL",    /* $05 */
        "VERA_IEN",     /* $06 */
        "VERA_ISR",     /* $07 */
    };
    if (offset < 8)
        return base[offset];

    if (offset == 0x08)
        return "VERA_IRQLINE_L";

    if (offset >= 0x09 && offset <= 0x0C)
    {
        static const char *mux[7][4] = {
            /* DCSEL=0 */
            { "VERA_DC_VIDEO",    "VERA_DC_HSCALE",       "VERA_DC_VSCALE",       "VERA_DC_BORDER"      },
            /* DCSEL=1 */
            { "VERA_DC_HSTART",   "VERA_DC_HSTOP",        "VERA_DC_VSTART",       "VERA_DC_VSTOP"       },
            /* DCSEL=2 */
            { "VERA_FX_CTRL",     "VERA_FX_TILEBASE",     "VERA_FX_MAPBASE",      "VERA_FX_MULT"        },
            /* DCSEL=3 */
            { "VERA_FX_X_INCR_L", "VERA_FX_X_INCR_H",    "VERA_FX_Y_INCR_L",    "VERA_FX_Y_INCR_H"   },
            /* DCSEL=4 */
            { "VERA_FX_X_POS_L",  "VERA_FX_X_POS_H",     "VERA_FX_Y_POS_L",     "VERA_FX_Y_POS_H"    },
            /* DCSEL=5 */
            { "VERA_FX_X_POS_S",  "VERA_FX_Y_POS_S",     "VERA_FX_POLY_FILL_L", "VERA_FX_POLY_FILL_H" },
            /* DCSEL=6 */
            { "VERA_FX_CACHE_L",  "VERA_FX_CACHE_M",     "VERA_FX_CACHE_H",     "VERA_FX_CACHE_U"     },
        };
        return mux[(dcsel < 7) ? dcsel : 0][offset - 0x09];
    }

    if (offset >= 0x0D && offset <= 0x13)
    {
        static const char *l0[7] = {
            "VERA_L0_CONFIG",    /* $0D */
            "VERA_L0_MAPBASE",   /* $0E */
            "VERA_L0_TILEBASE",  /* $0F */
            "VERA_L0_HSCR_L",   /* $10 */
            "VERA_L0_HSCR_H",   /* $11 */
            "VERA_L0_VSCR_L",   /* $12 */
            "VERA_L0_VSCR_H",   /* $13 */
        };
        return l0[offset - 0x0D];
    }

    if (offset >= 0x14 && offset <= 0x1A)
    {
        static const char *l1[7] = {
            "VERA_L1_CONFIG",    /* $14 */
            "VERA_L1_MAPBASE",   /* $15 */
            "VERA_L1_TILEBASE",  /* $16 */
            "VERA_L1_HSCR_L",   /* $17 */
            "VERA_L1_HSCR_H",   /* $18 */
            "VERA_L1_VSCR_L",   /* $19 */
            "VERA_L1_VSCR_H",   /* $1A */
        };
        return l1[offset - 0x14];
    }

    return "?";
}

/* ===========================================================================
 * LogTask -- Core 0: owns Serial (its UART interrupt is allocated on the
 * core that calls Serial.begin) and drains log_ring filled by the bus loop.
 * =========================================================================== */
static void log_drain(void)
{
    /* Shadow of VERA_CTRL DCSEL bits [2:1]; updated on every write to $DF05. */
    static uint8_t  dcsel = 0;
    static uint32_t dropped_seen = 0;

    uint32_t t = log_tail;
    while (t != __atomic_load_n(&log_head, __ATOMIC_ACQUIRE))
    {
        LogEvt evt = log_ring[t & (LOG_RING_SIZE - 1u)];
        __atomic_store_n(&log_tail, ++t, __ATOMIC_RELEASE);

        uint32_t now = millis();
        uint32_t sec = now / 1000u;
        uint32_t ms  = now % 1000u;
        if (evt.type == EVT_LATCH)
        {
            bool enabled = (evt.flags & 0x02) != 0;
            Serial.printf("[%5lu.%03lu] [SEL ] VERA %s ($%02X written to $DF%02X)\n",
                          sec, ms,
                          enabled ? "ENABLED " : "DISABLED", evt.data,
                          evt.offset);
        }
        else  /* EVT_REG */
        {
            /* Track DCSEL so muxed registers ($09-$0C) resolve correctly. */
            if (evt.offset == 0x05 && (evt.flags & 0x01))
                dcsel = (evt.data >> 1) & 0x07;

            Serial.printf("[%5lu.%03lu] [DF%02X - %-20s] %c $%02X\n",
                          sec, ms,
                          evt.offset,
                          vera_reg_name(evt.offset, dcsel),
                          (evt.flags & 0x01) ? 'W' : 'R',
                          evt.data);
        }
    }

    uint32_t dropped = log_dropped;
    if (dropped != dropped_seen)
    {
        Serial.printf("[VeraX16] log: %lu events dropped (ring full)\n",
                      (unsigned long)(dropped - dropped_seen));
        dropped_seen = dropped;
    }
}

static void LogTask(void *arg)
{
    Serial.begin(115200, SERIAL_8N1, PIN_UART_RX, PIN_UART_TX);
    log_ready = true;
    for (;;)
    {
        log_drain();
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

/* ===========================================================================
 * System Setup -- runs on Core 1 (ARDUINO_RUNNING_CORE) until MonitorTask
 * takes the core over.
 * =========================================================================== */
void setup(void)
{
    /* Reclaim JTAG pins (GPIO 39-42) for regular GPIO usage */
    gpio_reset_pin((gpio_num_t)PIN_CDONE);     /* GPIO 39 */
    gpio_reset_pin((gpio_num_t)PIN_DEV_SEL_N); /* GPIO 40 */
    gpio_reset_pin((gpio_num_t)PIN_IO1_N);     /* GPIO 41 */
    gpio_reset_pin((gpio_num_t)PIN_IO2_N);     /* GPIO 42 */

    /* Hold C64 and VERA in reset immediately — the VERA is released below,
     * the C64 only by MonitorTask once the bus loop is ready. */
    pinMode(PIN_ARESET, OUTPUT);
    digitalWrite(PIN_ARESET, LOW);
    pinMode(PIN_CRESET, OUTPUT);
    digitalWrite(PIN_CRESET, LOW);

    /* Serial and the log printer live on Core 0. */
    xTaskCreatePinnedToCore(LogTask, "BusLog", 4096, NULL, 1, NULL, 0);
    while (!log_ready)
        delay(1);

    Serial.printf("[VeraX16] Mode: C64 expansion port (VERA $%04X-$%04X, latch $DF%02X)\n",
                  VERA_REG_BASE, VERA_REG_BASE + VERA_REG_COUNT - 1u, CARD_SEL_LATCH);
    Serial.println("[VeraX16] GeoRAM 256K: $DE00 window, $DFFE/$DFFF regs (always active)");

    bus_build_io2_tables(bus_io2);

    /* Configure GPIO Modes */
    gpio_config_t cfg = {};
    cfg.intr_type    = GPIO_INTR_DISABLE;
    cfg.pull_up_en   = GPIO_PULLUP_DISABLE;
    cfg.pull_down_en = GPIO_PULLDOWN_DISABLE;
    cfg.mode         = GPIO_MODE_INPUT;

    /* Bank 0 inputs: PHI2, RW, D0-D7, A0-A9 */
    cfg.pin_bit_mask = (1ULL << PIN_PHI2) | (1ULL << PIN_RW) | DBUS_MASK | ABUS_LO_MASK;
    gpio_config(&cfg);

    /* Bank 1 inputs: A10-A15 (wired, not needed for decode), /IO1, /IO2, CDONE */
    cfg.pin_bit_mask = (1ULL << PIN_A10) | (1ULL << PIN_A11) |
                       (1ULL << PIN_A12) | (1ULL << PIN_A13) |
                       (1ULL << PIN_A14) | (1ULL << PIN_A15) |
                       (1ULL << PIN_IO1_N) | (1ULL << PIN_IO2_N) | (1ULL << PIN_CDONE);
    gpio_config(&cfg);

    /* Strapping pins latched: enable the address translators U3/U4. */
    pinMode(PIN_ABUS_OE_N, OUTPUT);
    digitalWrite(PIN_ABUS_OE_N, LOW);

    /* Output Signal Initialization */
    pinMode(PIN_DEV_SEL_N, OUTPUT);
    digitalWrite(PIN_DEV_SEL_N, HIGH);

    /*
     * VERA bring-up:
     *  1. Release the VERA FPGA from reset → it loads the bitstream from SPI flash.
     *  2. Poll CDONE until HIGH (ICE40UP5K typically < 100 ms).
     *  3. Wait for the VERA power-on reset; MonitorTask then releases the C64.
     */
    digitalWrite(PIN_CRESET, HIGH);
    Serial.println("[VeraX16] VERA: released from reset, waiting CDONE...");
    uint32_t elapsed_ms = 0u;
    while (!digitalRead(PIN_CDONE) && elapsed_ms < 5000u)
    {
        delay(1);
        elapsed_ms++;
    }
    if (elapsed_ms < 5000u)
        Serial.printf("[VeraX16] VERA: CDONE OK (~%lu ms)\n", (unsigned long)elapsed_ms);
    else
        Serial.println("[VeraX16] VERA: CDONE timeout — FPGA not configured!");
    /* CDONE only says the bitstream is loaded: the VERA still runs its
     * internal power-on reset (128 clk25 cycles + reset synchroniser, a few
     * us).  Give it a comfortable margin before the 6510 can touch the bus. */
    delayMicroseconds(VERA_POST_CDONE_DELAY_US);

    Serial.printf("[VeraX16] Bus loop on Core 1 (/IO qualify %u ns, write sample %u ns); "
                  "C64 leaves reset\n", IO_QUALIFY_NS, BUS_WR_SAMPLE_NS);
    Serial.flush();

    /* MonitorTask takes Core 1 over (highest priority, never yields): this
     * call does not return. */
    xTaskCreatePinnedToCore(MonitorTask, "BusMonitor", 4096, NULL,
                            configMAX_PRIORITIES - 1, NULL, 1);
    Serial.println("[VeraX16] FATAL: cannot start the bus loop");
}

void loop(void)
{
    /* Not reached: MonitorTask owns Core 1. */
    vTaskDelay(portMAX_DELAY);
}
