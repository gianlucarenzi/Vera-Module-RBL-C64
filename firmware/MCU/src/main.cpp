/**
 * esp32-main.cpp  --  Commodore 64 Expansion Port  VeraX16 + GeoRAM Controller
 *
 * Target MCU: ESP32-S3FN8 (QFN56)
 *
 * This firmware allows an ESP32-S3 to interface with the 6510 bus of a
 * Commodore 64 through the expansion (cartridge) port.  The I/O area is
 * decoded at runtime from the full 16-bit address bus (A0–A15):
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
 * This version uses a definitive 34-GPIO mapping (plus Serial on 43/44)
 * with software-based 16-bit address decoding.
 *
 * Style: Allman
 * Language: English
 */

#include <Arduino.h>
#include <driver/gpio.h>
#include <soc/gpio_struct.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include <driver/dedic_gpio.h>
#include <hal/cpu_ll.h>
#include <esp_timer.h>

/* ===========================================================================
 * Hardware Pin Mapping (ESP32-S3FN8 QFN56)
 * =========================================================================== */

/* --- Bank 0 Signals (GPIO 0-31) --- */
#define PIN_PHI2        1    /* CPU Clock Phase 2 (Pin 6) */
#define PIN_RW          2    /* Read/Write, High = Read (Pin 7) */

/* D0-D7: GPIO 4 to 11 (Pins 9-16, contiguous in Bank 0) */
#define DBUS_MASK       0x00000FF0UL
static const uint8_t DBUS_PINS[8] = { 4, 5, 6, 7, 8, 9, 10, 11 };

/* A0-A9: GPIO 12 to 21 (Pins 17-27, pin 20 = VDD3P3_RTC, not GPIO) */
#define ABUS_LO_MASK    0x003FF000UL

/* --- Bank 1 Signals (GPIO 32-48) --- */
#define PIN_A12         33   /* Address Bit 12 (Pin 38) */
#define PIN_A13         34   /* Address Bit 13 (Pin 39) */
#define PIN_A10         35   /* Address Bit 10 (Pin 40) */
#define PIN_A11         36   /* Address Bit 11 (Pin 41) */
#define PIN_ARESET      37   /* C64 System Reset Output, net ARESET (Pin 42) */
#define PIN_CRESET      38   /* Vera Chip Reset Output (Pin 43) */
#define PIN_CDONE       39   /* Vera Programmed Status Input (Pin 44) */
#define PIN_DEV_SEL_N   40   /* Vera Chip Select Output (Pin 45, active LOW) */
#define PIN_IO1_N       41   /* C64 /IO1, $DE00-$DEFF CPU access (Pin 47, active LOW) */
#define PIN_IO2_N       42   /* C64 /IO2, $DF00-$DFFF CPU access (Pin 48, active LOW) */
#define PIN_A14         45   /* Address Bit 14 (Pin 51) */
#define PIN_A15         46   /* Address Bit 15 (Pin 52) */

/* Serial Debug (UART0 default pins on ESP32-S3 QFN56) */
#define PIN_UART_TX     43   /* UART0 TX (Pin 49) */
#define PIN_UART_RX     44   /* UART0 RX (Pin 50) */

/*
 * Strapping Pins — Power-On Boot Configuration (ESP32-S3FN8 QFN56)
 *
 * The ESP32-S3 samples four strapping pins during the power-on reset window,
 * before any firmware code executes.  The sampled levels select the boot mode
 * and several chip-level options.
 *
 * Timing note: PIN_ARESET (GPIO37) is configured as OUTPUT only inside setup().
 * At strapping-sample time it is still an input (high-Z), so the ESP32 has NOT
 * yet asserted the C64 reset line.  The C64's own power-on reset circuitry
 * (556 timer) holds the 6510 RESET# pin LOW, which tri-states the 6510
 * address bus.  The level shifters on the address bus are fixed-direction
 * (C64 → ESP32); with floating inputs on the C64 side the ESP32-side internal
 * pull resistors determine the final strapping level.
 *
 * GPIO0  —  Pin  5  |  Boot mode selection  |  Internal weak PULL-UP ~45 kΩ
 *   Net BOOT0: R33 4.7 kΩ pull-up, BOOT button SW3, C61, and R54 -> Q4 (auto-reset
 *   from the programmer).  Not wired to any C64 signal.
 *   Pull-up holds GPIO0 HIGH throughout the strapping window.
 *   Sampled value: HIGH → SPI boot from embedded flash (correct for normal
 *   operation).  LOW would enter UART/JTAG download mode and halt the system.
 *
 * GPIO3  —  Pin  8  |  JTAG signal source   |  NO internal pull (truly floating)
 *   Not used by the firmware: only the external 10 kΩ resistor (ex RAMBO_EN)
 *   remains.  Per the ESP32-S3 datasheet (§3.4 "JTAG Signal Source Control"):
 *   this pin has no internal pull resistors and "the strapping value must be
 *   controlled by the external circuit that cannot be in a high impedance
 *   state" — the resistor is mandatory even though the pin is otherwise NC.
 *   Pull-up → HIGH → USB Serial/JTAG Controller.  Irrelevant:
 *   ARDUINO_USB_CDC_ON_BOOT=0 disables USB CDC; GPIO19/20 are reassigned to A7/A8.
 *   (LOW would select the JTAG pins GPIO39-42, also irrelevant:
 *   gpio_reset_pin() reclaims them in setup() before the Dedicated GPIO bundle
 *   is created.)
 *   In practice GPIO3's level is moot either way: Table 3-5 shows the default
 *   (unburned) eFuse row — EFUSE_DIS_PAD_JTAG=0, EFUSE_DIS_USB_JTAG=0,
 *   EFUSE_STRAP_JTAG_SEL=0 — makes GPIO3 "Ignored" and always selects the USB
 *   Serial/JTAG Controller. The GPIO39-42 polarity above only applies if
 *   EFUSE_STRAP_JTAG_SEL has been deliberately burned to 1 (one-time
 *   programmable; not done by default in Arduino/ESP-IDF).
 *
 * GPIO45 —  Pin 51  |  VDD_SPI voltage      |  Internal weak PULL-DOWN ~5 kΩ
 *   Wired to address bit A14 via the address level shifter (C64 5 V → ESP32 3.3 V).
 *   At power-on the 6510 RESET# is LOW → A14 pin is high-Z on the C64 side
 *   → shifter output floats → internal pull-down drives GPIO45 LOW.
 *   Sampled value: LOW → VDD_SPI = 3.3 V from VDD3P3_RTC (datasheet v2.2,
 *   Table 3-4, default eFuses).  This is the value the FN8 needs: its in-package
 *   flash runs from VDD_SPI at 3.3 V (Table 1-1).
 *   Risk: if A14 is HIGH during the sampling window, VDD_SPI = 1.8 V from the
 *   flash regulator and the in-package flash is under-powered: the chip does
 *   not boot.  A14 must be LOW at power-on, or burn EFUSE_VDD_SPI_FORCE = 1 and
 *   EFUSE_VDD_SPI_TIEH = 1 (one-time) to fix VDD_SPI at 3.3 V and ignore GPIO45.
 *
 * GPIO46 —  Pin 52  |  ROM messages on UART |  Internal weak PULL-DOWN ~5 kΩ
 *   Wired to address bit A15 via the address level shifter.  Identical power-on
 *   scenario: 6510 reset → A15 high-Z → shifter floats → pull-down → GPIO46 LOW.
 *   Sampled value: LOW → first-stage ROM boot messages on UART0 suppressed.
 *   Correct for production: the firmware initialises UART0 independently via
 *   Serial.begin() and uses it exclusively for debug output.  Enabling ROM
 *   messages (HIGH) would prepend Espressif boot log lines before the firmware
 *   output, which is undesirable but not harmful.
 */

/* ===========================================================================
 * Helper Macros & Inline Functions
 * =========================================================================== */

/*
 * Decode A0-A7 (Bank 0 bits 12-19) from the GPIO input snapshot.
 * The page ($DE or $DF) is given by which of /IO1 or /IO2 is asserted, so
 * A8-A15 are not needed to decode the card's I/O space.
 */
static inline uint8_t IRAM_ATTR decode_addr_lo(uint32_t lo)
{
    return (uint8_t)((lo >> 12) & 0xFFu);
}

/**
 * Decode D0-D7 from Bank 0 snapshot.
 */
static inline uint8_t IRAM_ATTR decode_data(uint32_t lo)
{
    return (uint8_t)((lo >> 4) & 0xFFu);
}

/*
 * Dedicated GPIO channel mapping — ESP32-S3 Xtensa LX7 TIE instructions
 * (ee.get_gpio_in / ee.wr_mask_gpio_out bypass the APB bus: ~1 cycle vs ~6).
 *
 * Input channels  (bit index in cpu_ll_read_dedic_gpio_in() result):
 *   Ch 0 = PHI2       (GPIO  1)
 *   Ch 1 = /IO1       (GPIO 41)  active LOW
 *   Ch 2 = /IO2       (GPIO 42)  active LOW
 *
 * Output channels (bit index in cpu_ll_write_dedic_gpio_mask() mask/val):
 *   Ch 0 = DEV_SEL_N  (GPIO 40)  active LOW — VERA registers
 *
 * The GeoRAM lives in the MCU and needs no select line: the data transceiver
 * (U19) output-enable gating uses DEV_SEL_N for VERA reads and /IO1 directly
 * for GeoRAM reads.
 * Input and output channel spaces are independent on ESP32-S3.
 */
#define DEDIC_IN_PHI2        (1u << 0)
#define DEDIC_IN_IO1N        (1u << 1)
#define DEDIC_IN_IO2N        (1u << 2)
#define DEDIC_IN_IO_MASK     (DEDIC_IN_IO1N | DEDIC_IN_IO2N)
#define DEDIC_OUT_DEVSELN    (1u << 0)
#define DEDIC_OUT_CTRL_MASK  0x01u
#define DEDIC_OUT_CTRL_IDLE  0x01u   /* HIGH = deasserted (active LOW) */

/* ===========================================================================
 * Compile-time Configuration
 * =========================================================================== */

/* C64 I/O map.  The GeoRAM registers sit at the top of IO2 ($DFFE/$DFFF), so
 * VERA uses the bottom of IO2 and the select latch sits just below them.
 * IO1 ($DE00-$DEFF) is entirely the GeoRAM data window.
 * Offsets below are within the IO2 page. */
#define VERA_REG_BASE       0xDF00u  /* VERA registers $DF00-$DF1F           */
#define VERA_REG_COUNT      0x20u
#ifndef CARD_SEL_LATCH
#define CARD_SEL_LATCH      0xFDu    /* $DFFD: VERA select, write != 0 selects, 0 deselects */
#endif
#define GEORAM_PAGE_REG     0xFEu    /* $DFFE: 256-byte page in block (0-63) */
#define GEORAM_BLOCK_REG    0xFFu    /* $DFFF: 16 KB block (0-15 for 256 KB) */

#define GEORAM_PAGE_MASK    0x3Fu
#define GEORAM_BLOCK_MASK   0x0Fu

/* Maximum wait for /IO1 or /IO2 after the PHI2 rising edge.  On CPU cycles the
 * PLA + 74LS139 assert /IOx a few tens of ns after PHI2 (AEC) rises; if neither
 * line is LOW within this window the cycle is not ours (or is a VIC-II fetch).
 * PHI2 high lasts ~490 ns: the remainder is left for the data bus drive. */
#ifndef IO_QUALIFY_NS
#define IO_QUALIFY_NS 200u
#endif
#define IO_QUALIFY_CYCLES   ((IO_QUALIFY_NS * 240u) / 1000u)   /* CPU @ 240 MHz */

/* Per-register trace (EVT_REG) costs ~1 us per access inside the bus loop:
 * enough to miss the next PHI2 edge or leave DEV_SEL_N asserted into the
 * following cycle (spurious VERA accesses).  Debug builds only. */
#ifndef VERA_TRACE_REGS
#define VERA_TRACE_REGS 0
#endif

/* Delay between CDONE high and the release of the C64 reset (VERA POR). */
#ifndef VERA_POST_CDONE_DELAY_US
#define VERA_POST_CDONE_DELAY_US 1000u
#endif

/* ===========================================================================
 * Log Ring (Core 0 bus loop → Core 1 loop(), which prints on Serial)
 *
 * Single producer / single consumer, lock-free: the producer only stores the
 * event and advances `head` (a few instructions).  xQueueSend() would take a
 * spinlock and a critical section (~1 us), losing the bus cycles that follow
 * the logged one.  When the ring is full new events are dropped and counted.
 * =========================================================================== */
#define LOG_RING_SIZE 64u   /* power of two */

#define EVT_LATCH 0   /* VERA select latch state change */
#define EVT_REG   1   /* VERA register ($DFxx) access */

/* flags: bit0=write(1)/read(0)  bit1=latch state (EVT_LATCH)  bit2=DEV_SEL asserted */
typedef struct
{
    uint32_t ts_ms;   /* FreeRTOS tick count (1 ms) on Core 0 */
    uint8_t  type;
    uint8_t  offset;  /* register offset: 0x00-0xFF within address range */
    uint8_t  data;
    uint8_t  flags;
} LogEvt;

/* ===========================================================================
 * Shared Data
 * =========================================================================== */

/* Hot-loop data lives in DRAM (data bus), not in IRAM (instruction bus). */
static DRAM_ATTR uint32_t lut_drive[256];   /* Lookup table for fast data bus drive */

/* 256 KB GeoRAM — IRAM BSS: resides in IRAM, zero Flash cost. */
static uint8_t georam_256k[256 * 1024] __attribute__((section(".iram0.bss")));

/*
 * GeoRAM registers (write-only on the real cartridge, not readable back).
 * The 256-byte window at $DE00-$DEFF maps to:
 *   offset = block * 16384 + page * 256 + (addr & 0xFF)
 * Both registers are cleared at power-on; their content survives a C64 reset,
 * like the original hardware.  MonitorTask keeps them, and the window base
 * pointer derived from them, in registers; these copies are for inspection.
 */
static DRAM_ATTR uint8_t georam_page  = 0u;
static DRAM_ATTR uint8_t georam_block = 0u;

static DRAM_ATTR LogEvt   log_ring[LOG_RING_SIZE];
static DRAM_ATTR uint32_t log_head = 0;     /* written by Core 0 only */
static DRAM_ATTR uint32_t log_tail = 0;     /* written by Core 1 only */
static DRAM_ATTR uint32_t log_dropped = 0;  /* written by Core 0 only */

/* ===========================================================================
 * Bus Drive/Release Logic
 * =========================================================================== */

/**
 * Precalculate bitmasks for each possible byte to avoid runtime logic.
 */
static void build_drive_lut(void)
{
    for (int v = 0; v < 256; v++)
    {
        uint32_t m = 0;
        for (int b = 0; b < 8; b++)
        {
            if (v & (1 << b))
            {
                m |= (1UL << DBUS_PINS[b]);
            }
        }
        lut_drive[v] = m;
    }
}

/**
 * Drive the data bus with a byte value.
 * GPIO.out covers Bank 0 entirely; writing lut_drive[val] sets D0-D7 (bits 4-11)
 * and zeros the remaining bits, which are all input-configured and ignore GPIO.out.
 * This saves one APB write compared to the w1tc+w1ts pattern.
 */
static inline void IRAM_ATTR bus_drive(uint8_t val)
{
    GPIO.out = lut_drive[val];
    GPIO.enable_w1ts = DBUS_MASK;
}

/**
 * Release the data bus (set to High-Z).
 */
static inline void IRAM_ATTR bus_release(void)
{
    GPIO.enable_w1tc = DBUS_MASK;
}

/* Push a log event into the ring without blocking (drops if full). */
static inline void IRAM_ATTR log_send(uint8_t type, uint8_t offset,
                                      uint8_t data, uint8_t flags)
{
    uint32_t h = log_head;
    if (h - __atomic_load_n(&log_tail, __ATOMIC_ACQUIRE) >= LOG_RING_SIZE)
    {
        log_dropped++;
        return;
    }
    LogEvt *e = &log_ring[h & (LOG_RING_SIZE - 1u)];
    e->ts_ms  = (uint32_t)xTaskGetTickCount();
    e->type   = type;
    e->offset = offset;
    e->data   = data;
    e->flags  = flags;
    __atomic_store_n(&log_head, h + 1u, __ATOMIC_RELEASE);
}

/* Base of the 256-byte GeoRAM page currently visible at $DE00. */
static inline uint8_t * IRAM_ATTR georam_window(uint8_t block, uint8_t page)
{
    return &georam_256k[((uint32_t)block << 14) | ((uint32_t)page << 8)];
}

/* ===========================================================================
 * MonitorTask -- Core 0, IRAM-resident
 *
 * Core 0 runs only this task (it never yields); Core 1 runs setup()/loop(),
 * Serial and its UART interrupt, and prints the events pushed into log_ring.
 * =========================================================================== */
static void IRAM_ATTR MonitorTask(void *arg)
{
    /*
     * Dedicated GPIO bundles — MUST be created on the executing core (Core 0).
     *
     * Input  bundle: [PHI2, /IO1, /IO2]   → input  ch 0-2 (bits 0-2 of ee.get_gpio_in)
     * Output bundle: [DEV_SEL_N]           → output ch 0 (bit 0 of ee.wr_mask_gpio_out)
     *
     * Input and output channel pools are independent; ch 0 means different pins
     * in each pool.
     */
    static const int dedic_in_pins[]  = { PIN_PHI2, PIN_IO1_N, PIN_IO2_N };
    static const int dedic_out_pins[] = { PIN_DEV_SEL_N };
    dedic_gpio_bundle_handle_t dedic_in_bundle, dedic_out_bundle;
    const dedic_gpio_bundle_config_t in_cfg =
    {
        .gpio_array = dedic_in_pins,
        .array_size = 3,
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

    bus_release();

    /* Card state, kept in registers. */
    bool     selected = false;
    uint8_t  page     = georam_page;
    uint8_t  block    = georam_block;
    uint8_t *win      = georam_window(block, page);   /* $DE00 window base */

    /*
     * Startup sync sequence — executed once before the hot loop:
     *  1. Release VERA FPGA from reset → starts loading bitstream from SPI flash.
     *  2. Poll CDONE until HIGH (ICE40UP5K typically < 100 ms).
     *  3. Release C64 from reset → bus goes live; hot loop must be ready.
     */
    GPIO.out1_w1ts.val = (1UL << (PIN_CRESET - 32));
    Serial.println("[VeraX16] VERA: released from reset, waiting CDONE...");
    {
        uint32_t elapsed_ms = 0u;
        while (!(GPIO.in1.val & (1UL << (PIN_CDONE - 32))))
        {
            vTaskDelay(1);
            elapsed_ms += portTICK_PERIOD_MS;
            if (elapsed_ms >= 5000u)
            {
                Serial.println("[VeraX16] VERA: CDONE timeout — FPGA not configured!");
                break;
            }
        }
        if (elapsed_ms < 5000u)
            Serial.printf("[VeraX16] VERA: CDONE OK (~%u ms)\n", elapsed_ms);
    }
    /* CDONE only says the bitstream is loaded: the VERA still runs its
     * internal power-on reset (128 clk25 cycles + reset synchroniser, a few
     * us).  Give it a comfortable margin before the 6510 can touch the bus. */
    delayMicroseconds(VERA_POST_CDONE_DELAY_US);
    GPIO.out1_w1ts.val = (1UL << (PIN_ARESET - 32));
    Serial.println("[VeraX16] C64: released from reset — bus active");

    for (;;)
    {
        /* 1. Wait for PHI2 rising edge.
         *    ee.get_gpio_in is a single Xtensa TIE instruction (~1 cycle),
         *    vs ~6 cycles for a GPIO.in read through the APB bus. */
        while (!(cpu_ll_read_dedic_gpio_in() & DEDIC_IN_PHI2));

        /* 2. Qualify the cycle: wait (bounded) for /IO1 or /IO2.  Only CPU
         *    accesses to $DExx/$DFxx assert them; any other cycle, including
         *    VIC-II fetches during PHI2 high, is skipped untouched.  The 6510
         *    address is on the port only once AEC is high, i.e. by the time
         *    /IOx is asserted, so the bus is sampled after this point. */
        uint32_t io_n;
        {
            uint32_t t0 = cpu_ll_get_cycle_count();
            do
            {
                io_n = ~cpu_ll_read_dedic_gpio_in() & DEDIC_IN_IO_MASK;
            }
            while (!io_n && (cpu_ll_get_cycle_count() - t0) < IO_QUALIFY_CYCLES);
        }
        if (!io_n)
        {
            /* Not ours: no /IOx. */
            while (cpu_ll_read_dedic_gpio_in() & DEDIC_IN_PHI2);
            continue;
        }

        uint32_t g_lo = GPIO.in;
        uint8_t  off8 = decode_addr_lo(g_lo);

        if (io_n & DEDIC_IN_IO1N)
        {
            /* 3a. IO1 $DE00-$DEFF: GeoRAM window (always active). */
            if (g_lo & (1UL << PIN_RW))
            {
                bus_drive(win[off8]);
                while (cpu_ll_read_dedic_gpio_in() & DEDIC_IN_PHI2);
                bus_release();
            }
            else
            {
                /* The 6510 write data is valid only up to ~200 ns after PHI2
                 * rise: keep re-reading GPIO.in (PHI2 is in the same
                 * register) and store the last snapshot taken with PHI2 high. */
                uint32_t last = g_lo, now;
                while ((now = GPIO.in) & (1UL << PIN_PHI2))
                    last = now;
                win[off8] = decode_data(last);
            }
            continue;
        }

        /* 3b. IO2 $DF00-$DFFF: VERA registers, select latch, GeoRAM registers.
         *     Select VERA with one ee.wr_mask_gpio_out instruction. */
        bool is_vera_range = selected && (off8 < VERA_REG_COUNT);
        if (is_vera_range)
            cpu_ll_write_dedic_gpio_mask(DEDIC_OUT_CTRL_MASK, (uint8_t)~DEDIC_OUT_DEVSELN);

        if (g_lo & (1UL << PIN_RW))
        {
#if VERA_TRACE_REGS
            if (is_vera_range)
            {
                /* VERA drives the bus: sample it just before PHI2 falls. */
                uint32_t last = g_lo, now;
                while ((now = GPIO.in) & (1UL << PIN_PHI2))
                    last = now;
                log_send(EVT_REG, off8, decode_data(last), 0x04u);
            }
#endif
            while (cpu_ll_read_dedic_gpio_in() & DEDIC_IN_PHI2);
            cpu_ll_write_dedic_gpio_mask(DEDIC_OUT_CTRL_MASK, DEDIC_OUT_CTRL_IDLE);
            continue;
        }

        /* Write cycle: last snapshot with PHI2 high (see 3a), then release
         * DEV_SEL_N after PHI2 falls and apply the side effects in PHI1. */
        uint32_t last = g_lo, now;
        while ((now = GPIO.in) & (1UL << PIN_PHI2))
            last = now;
        cpu_ll_write_dedic_gpio_mask(DEDIC_OUT_CTRL_MASK, DEDIC_OUT_CTRL_IDLE);
        uint8_t data = decode_data(last);

        if (off8 == CARD_SEL_LATCH)
        {
            bool new_sel = (data != 0u);
            if (new_sel != selected)
            {
                selected = new_sel;
                log_send(EVT_LATCH, off8, data, 0x01u | (selected ? 0x02u : 0x00u));
            }
        }
        else if (off8 == GEORAM_PAGE_REG)
        {
            page        = data & GEORAM_PAGE_MASK;
            georam_page = page;
            win         = georam_window(block, page);
        }
        else if (off8 == GEORAM_BLOCK_REG)
        {
            block        = data & GEORAM_BLOCK_MASK;
            georam_block = block;
            win          = georam_window(block, page);
        }
#if VERA_TRACE_REGS
        else if (is_vera_range)
        {
            log_send(EVT_REG, off8, data, 0x01u | 0x04u);
        }
#endif
    }
}

/* ===========================================================================
 * System Setup
 * =========================================================================== */
void setup(void)
{
    /* Reclaim JTAG pins (GPIO 39-42) for regular GPIO usage */
    gpio_reset_pin((gpio_num_t)PIN_CDONE);     /* GPIO 39 */
    gpio_reset_pin((gpio_num_t)PIN_DEV_SEL_N); /* GPIO 40 */
    gpio_reset_pin((gpio_num_t)PIN_IO1_N);     /* GPIO 41 */
    gpio_reset_pin((gpio_num_t)PIN_IO2_N);     /* GPIO 42 */

    /* Hold C64 and VERA in reset immediately — released by MonitorTask
     * only after CDONE confirms the FPGA bitstream is loaded. */
    pinMode(PIN_ARESET, OUTPUT);
    digitalWrite(PIN_ARESET, LOW);
    pinMode(PIN_CRESET, OUTPUT);
    digitalWrite(PIN_CRESET, LOW);

    /* Initialize Serial for Debug (UART0 default pins 43/44) */
    Serial.begin(115200, SERIAL_8N1, PIN_UART_RX, PIN_UART_TX);

    memset(georam_256k, 0x00, sizeof(georam_256k));

    build_drive_lut();

    Serial.printf("[VeraX16] Mode: C64 expansion port (VERA $%04X-$%04X, latch $DF%02X)\n",
                  VERA_REG_BASE, VERA_REG_BASE + VERA_REG_COUNT - 1u, CARD_SEL_LATCH);
    Serial.println("[VeraX16] GeoRAM 256K: $DE00 window, $DFFE/$DFFF regs (always active)");

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

    /* Output Signal Initialization */
    pinMode(PIN_DEV_SEL_N, OUTPUT);
    digitalWrite(PIN_DEV_SEL_N, HIGH);

    /* Start High-Priority Monitor Task on Core 0 (dedicated bus management).
     * It never yields, so the Core 0 idle task must leave the task watchdog.
     * setup()/loop() stay on Core 1 (ARDUINO_RUNNING_CORE) with Serial. */
    disableCore0WDT();
    xTaskCreatePinnedToCore(
        MonitorTask, "BusMonitor",
        4096, NULL,
        configMAX_PRIORITIES - 1,
        NULL, 0
    );

    Serial.println("[VeraX16] Bus Monitor active on Core 0");
}

/* ---------------------------------------------------------------------------
 * VERA register name lookup — Core 1 only (loop()), not IRAM-resident.
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
 * Main Loop -- Core 1: drain log_ring (filled by Core 0) and print
 * =========================================================================== */
void loop(void)
{
    /* Shadow of VERA_CTRL DCSEL bits [2:1]; updated on every write to $DF05. */
    static uint8_t  dcsel = 0;
    static uint32_t dropped_seen = 0;

    uint32_t t = log_tail;
    if (t == __atomic_load_n(&log_head, __ATOMIC_ACQUIRE))
    {
        vTaskDelay(pdMS_TO_TICKS(10));
        return;
    }
    while (t != __atomic_load_n(&log_head, __ATOMIC_ACQUIRE))
    {
        LogEvt evt = log_ring[t & (LOG_RING_SIZE - 1u)];
        __atomic_store_n(&log_tail, ++t, __ATOMIC_RELEASE);

        uint32_t sec = evt.ts_ms / 1000u;
        uint32_t ms  = evt.ts_ms % 1000u;
        if (evt.type == EVT_LATCH)
        {
            bool enabled = (evt.flags & 0x02) != 0;
            Serial.printf("[%5lu.%03lu] [SEL ] VERA %s ($%02X written to $DF%02X)\n",
                          sec, ms,
                          enabled ? "ENABLED " : "DISABLED", evt.data,
                          CARD_SEL_LATCH);
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
