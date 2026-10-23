# FPGA Firmware — iCE40UP5K

Commodore 64 expansion-port bus interface for the VERA module (Rev 6):
VERA registers in `IO2` plus a **GeoRAM 256 KB** on an external
**AS6C4008** SRAM, with the bank registers implemented in the FPGA.
Single bitstream, no generics to choose.

## Memory map

| Address | Size | Function | Implementation |
|---------|------|----------|----------------|
| `$DE00–$DEFF` | 256 B | GeoRAM data window (one page of 256 KB) | External SRAM |
| `$DF00–$DF1F` | 32 B | VERA registers — `VERA_CS` asserted | Combinational |
| `$DFFD` | 1 B | VERA select latch (write only): `≠ $00` selects, `$00` deselects | Register |
| `$DFFE` | 1 B | GeoRAM page register (write only, 0–63, D5–D0) | Register |
| `$DFFF` | 1 B | GeoRAM block register (write only, 0–15, D3–D0) | Register |

The VERA responds **only while selected** through `$DFFD` (`VERA_CS` per cycle:
`/IO2`, `$DF00–$DF1F`, latch set, PHI2 high).  The GeoRAM window and registers
are **always active**, like the original cartridge; the latch always responds.
Latch and GeoRAM registers power up at zero (VERA deselected) and are not
cleared by a C64 reset, like the original GeoRAM.

```
LDA #$04 : STA $DFFF   ; GeoRAM block 4 (always active)
LDA #$23 : STA $DFFE   ; GeoRAM page 35
LDA $DE45              ; GeoRAM byte $12345
LDA #$01 : STA $DFFD   ; select the VERA at $DF00-$DF1F
LDA #$00 : STA $DFFD   ; deselect the VERA
```

**Qualification by `/IO1` and `/IO2`.**  Every access is qualified by the C64
`/IO1` (port pin 7) and `/IO2` (port pin 10) lines.  The PLA asserts them only for
CPU accesses (`AEC` high), so VIC-II fetches, whose addresses also appear on the
port, never reach VERA or the SRAM.  `/IOx` already decodes A15–A8, so only
**A7–A0** are wired to the FPGA.

**Register write timing.**  The 6510 drives write data during PHI2 high, up to
~150 ns after the rising edge.  Latch and GeoRAM registers are sampled
`SAMPLE_CLKS` cycles after the synchronised PHI2 rising edge (generic, default
6 × 40 ns = 240 ns, i.e. ~280–320 ns after the real edge), well inside the
~490 ns PHI2-high window (PAL 0.985 MHz / NTSC 1.023 MHz).

**BRAM usage**: 0 of 30 EBR blocks.

## Hardware

### FPGA
**Lattice iCE40UP5K-SG48** (QFN-48, 39 user I/O, 5280 LUTs, 120 Kbit BRAM,
1 Mbit SPRAM).

### External SRAM — GeoRAM 256 KB
**AS6C4008-55** (Alliance Memory, 512K×8, 55 ns, 2.7–5.5 V), lower 256 KB used.

| SRAM pin | Connection |
|----------|-----------|
| A[7:0] | C64 A[7:0] — **direct PCB net**, no FPGA I/O pin used |
| A[13:8] | FPGA `SRAM_PAGE[5:0]` (page register `$DFFE`) |
| A[17:14] | FPGA `SRAM_BLOCK[3:0]` (block register `$DFFF`) |
| A18 | **GND** (use lower 256 KB of the 512 KB chip) |
| DQ[7:0] | C64 D[7:0] — **direct PCB net**, shared with FPGA D[7:0] |
| CE# | FPGA `SRAM_CE_N` |
| OE# | FPGA `SRAM_OE_N` |
| WE# | FPGA `SRAM_WE_N` |

`offset = block × 16384 + page × 256 + A[7:0]`

The SRAM sits on the 3.3 V side of the level shifters, on the same nets as the
FPGA, and is powered at 3.3 V.

**Control timing** (combinational, gated by PHI2):

| Signal | Active when |
|--------|-------------|
| `SRAM_CE_N` | `/IO1` low, PHI2 high |
| `SRAM_OE_N` | as `CE#`, and R/W = read |
| `SRAM_WE_N` | as `CE#`, and R/W = write — data latched by the SRAM on the WE# rising edge (PHI2 fall) |

- Read: `/IO1` goes low ~50–80 ns after PHI2 rises; tAA = 55 ns; the 6510
  samples at PHI2 fall (~490 ns): ample margin.
- Write: WE# pulse ~400 ns ≫ tWP = 40 ns; tDH = 0 ns is covered by the 6510
  data hold after PHI2 fall.
- `SRAM_PAGE`/`SRAM_BLOCK` change only on `$DFFE`/`$DFFF` writes (IO2 cycles),
  never while CE# is low.

**Data transceiver.**  The board must drive the C64 data bus during GeoRAM
reads.  `SRAM_CE_N` is the GeoRAM term of the data transceiver output enable:
`~OE_ = NAND(PHI2, NAND(R/W, AND(VERA_CS, SRAM_CE_N)))`: every `$DExx` read
is driven from the SRAM (GeoRAM always active), `$DF00–$DF1F` reads only with
the VERA selected.

### SPI flash (FPGA configuration)
Any **SPI NOR flash** compatible with the iCE40 boot protocol, e.g.
Winbond W25Q16 (2 MB) or W25Q32 (4 MB).

The flash is shared between the FPGA (reads bitstream at power-up) and the
programmer (writes the bitstream).  During programming the FPGA is held in
reset via `CRESET_B`.

### Programmer hardware
Any of the following work with `openFPGALoader` or `iceprog`:

| Hardware | Interface | Tool |
|----------|-----------|------|
| FTDI FT232H breakout | SPI bitbang | `iceprog`, `openFPGALoader` |
| FTDI FT2232H breakout | MPSSE SPI | `iceprog`, `openFPGALoader` |
| Tigard | JTAG/SPI | `openFPGALoader` |
| Raspberry Pi (GPIO) | SPI bitbang | `openFPGALoader` |
| dirtyJTAG (STM32F103) | JTAG | `openFPGALoader` |

Programmer SPI wiring to SPI flash and FPGA:

```
Programmer    iCE40UP5K     W25Qxx flash
MOSI  ──────── SPI_SI ────── DI
MISO  ──────── SPI_SO ────── DO
SCK   ──────── SPI_SCK ───── CLK
CS#   ─────────────────────── CS#
CRST# ──────── CRESET_B
CDONE ──────── CDONE
```

### Reset sequencer — 74LVC1G08

A single **74LVC1G08** (SOT-23-5, 2-input AND gate) sequences the
power-on boot without any MCU or firmware.

**Boot sequence:**

| Phase | FPGA\_CDONE | VERA\_CDONE | VERA\_RESET# | C64\_RESET# |
|-------|------------|------------|-------------|--------------|
| Power-on / FPGA loading | 0 | 0 | 0 (reset) | 0 (reset) |
| FPGA ready, VERA loading | 1 | 0 | 1 (free) | 0 (reset) |
| System ready | 1 | 1 | 1 (free) | 1 (free) |

Logic equations:
- `VERA_RESET#  = FPGA_CDONE`
- `C64_RESET# = FPGA_CDONE AND VERA_CDONE`

Circuit:

```
VCC --[4k7]--+-------- FPGA_CDONE (open-drain)
             |
             +--[33R]- VERA_RESET#
             |
             +-- A -\
                     +--- 74LVC1G08 ---[33R]--- C64_RESET#
             +-- B -/
             |
VCC --[4k7]--+-------- VERA_CDONE (open-drain)
```

The natural SPI flash loading times provide all delays
(~50–100 ms for the FPGA, ~200–500 ms for VERA). No RC timer needed.

**Why 74LVC and not 74HC?** The 74LVC family has 5V-tolerant inputs at
3.3V VCC. The CDONE signals are at 3.3V; the C64 /RESET line is 5V TTL.
The 74LVC 3.3V output is a valid HIGH for 5V TTL (V_IH = 2.0V).

BOM: 1× 74LVC1G08 SOT-23-5, 2× 4.7kΩ 0402 (CDONE pullups),
2× 33Ω 0402 (RESET series) — under 0.30 EUR total.

---

## Toolchain

### FPGA toolchain

The recommended way to set up the toolchain is using the **OSS CAD Suite**, as the packages available in Debian 11 repositories are outdated and do not include the necessary GHDL plugin for Yosys.

#### Installing OSS CAD Suite (Recommended for Debian 11)

1. Download the latest Linux x64 archive from [OSS CAD Suite Releases](https://github.com/YosysHQ/oss-cad-suite-build/releases/latest).
2. Extract the archive (e.g., to `$HOME/oss-cad-suite`).
3. Add the bin directory to your PATH:

```bash
export PATH="$HOME/oss-cad-suite/bin:$PATH"
```

This suite includes `yosys`, `nextpnr-ice40`, `icepack`, `iceprog`, and `ghdl` with the `ghdl-yosys-plugin` already integrated.

#### Alternative: Manual installation via apt (Debian 12+)

```bash
# Debian / Ubuntu
sudo apt install fpga-icestorm nextpnr-ice40 yosys ghdl
```

The `ghdl-yosys-plugin` is required for VHDL synthesis and is usually not
packaged — build it from source:

```bash
git clone https://github.com/ghdl/ghdl-yosys-plugin
cd ghdl-yosys-plugin && make && sudo make install
```

### Flash programming tools

On modern distributions (e.g. Debian 12+), `openFPGALoader` can be installed via package manager:

```bash
sudo apt install openFPGALoader
```

On older distributions like **Debian 11 (Bullseye)**, it must be built from source:

```bash
# Install dependencies
sudo apt install git cmake make g++ pkg-config libusb-1.0-0-dev \
                 libhidapi-dev libgpiod-dev libusbmuxd-dev

# Build and install
git clone https://github.com/trabucayre/openfpgaloader
cd openfpgaloader && mkdir build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=$HOME
make -j$(nproc)
make install
```

`iceprog` is already included in `fpga-icestorm`.

### Tool roles

| Tool | Input | Output | Purpose |
|------|-------|--------|---------|
| `ghdl` | VHDL sources | RTLIL | VHDL elaboration (via Yosys plugin) |
| `yosys` | RTLIL | `.json` netlist | Synthesis for iCE40 |
| `nextpnr-ice40` | `.json` + `.pcf` | `.asc` | Place & route |
| `icepack` | `.asc` | `.bin` | Pack ASCII bitstream into binary |
| `openFPGALoader` / `iceprog` | `.bin` | SPI flash | Write bitstream to board |

---

## Build

### 1. Synthesise, place & route, pack bitstream

```bash
cd firmware/FPGA
make        # builds C6502_Interface.bin
```

Step by step:

```bash
# Synthesis: VHDL -> JSON netlist
yosys -m ghdl -p \
    "ghdl --std=08 C6502_Interface.vhd -e C6502_Interface; \
     synth_ice40 -top C6502_Interface -json C6502_Interface.json"

# Place & route: JSON + PCF -> ASCII bitstream
nextpnr-ice40 --up5k --package sg48 \
    --json C6502_Interface.json \
    --pcf board-pin-mapping.pcf \
    --asc C6502_Interface.asc

# Pack binary bitstream  <-- this is what gets flashed
icepack C6502_Interface.asc C6502_Interface.bin
```

### 2. Flash the bitstream

```bash
make flash           # openFPGALoader -b ice40_generic C6502_Interface.bin
make flash-iceprog   # iceprog C6502_Interface.bin (FTDI FT2232H)
```

### 3. Clean

```bash
make clean      # removes .json, .asc, .bin and LaTeX intermediates
```

### Measured synthesis results

OSS CAD Suite 2025-10-08 (Yosys + GHDL plugin, nextpnr-ice40):

| Resource | Used | Available |
|----------|------|-----------|
| ICESTORM\_LC | 40 | 5280 |
| EBR (BRAM) | 0 | 30 |
| User I/O | 35 | 39 |
| Fmax (CLK) | **89.54 MHz** (post-route) | target 25 MHz |
| Bitstream size | ~104 KB | — |

---

## Pin assignment

Edit `board-pin-mapping.pcf` to match your schematic before running
`nextpnr-ice40`.  All pin numbers in the file are **placeholders**.

The CLK signal must be assigned to a **Global Buffer (GB) input** pin.
Valid GB pins on the iCE40UP5K SG48 package: 20, 28, 31, 38, 41, 43, 48.

**Valid user I/O pin numbers for SG48** (39 total):
```
2 3 4 6 9 10 11 12 13 14 15 16 17 18 19 20 21
23 25 26 27 28 31 32 34 35 36 37 38 39
40 41 42 43 44 45 46 47 48
```
Pins 1, 5, 7, 8, 22, 24, 29, 30, 33 are power/ground or reserved —
nextpnr rejects them with an error.

**I/O budget:** the design uses 35 of the 39 available pins; 4 are free.

### Pin table

| Signal | Dir | PCF pin\* | C64 port | Description |
|--------|-----|-----------|----------|-------------|
| `CLK` | In | 35 | — | 25 MHz system clock — must be on a GB pin |
| `A[0]` | In | 40 | Y | address bit 0 — also wired to SRAM A[0] (same for A1–A7) |
| `A[1]` | In | 41 | X | address bit 1 |
| `A[2]` | In | 42 | W | address bit 2 |
| `A[3]` | In | 43 | V | address bit 3 |
| `A[4]` | In | 44 | U | address bit 4 |
| `A[5]` | In | 45 | T | address bit 5 |
| `A[6]` | In | 46 | S | address bit 6 |
| `A[7]` | In | 47 | R | address bit 7 |
| `D[0]` | In | 11 | 21 | data bit 0 (register writes) — shared net with SRAM DQ[0] (same for D1–D7) |
| `D[1]` | In | 12 | 20 | data bit 1 |
| `D[2]` | In | 13 | 19 | data bit 2 |
| `D[3]` | In | 14 | 18 | data bit 3 |
| `D[4]` | In | 15 | 17 | data bit 4 |
| `D[5]` | In | 16 | 16 | data bit 5 |
| `D[6]` | In | 17 | 15 | data bit 6 |
| `D[7]` | In | 18 | 14 | data bit 7 |
| `PHI2` | In | 34 | E | phase-2 clock — synchronised internally, not used as FPGA clock |
| `RNW` | In | 36 | 5 | Read/Not-Write: high = read, low = write |
| `IO1_N` | In | 26 | 7 | `/IO1`, CPU access to `$DE00–$DEFF` (active low) |
| `IO2_N` | In | 27 | 10 | `/IO2`, CPU access to `$DF00–$DFFF` (active low) |
| `VERA_CS` | Out | 32 | — | VERA chip select (active low): `$DF00–$DF1F`, VERA selected (`$DFFD`), PHI2 high |
| `SRAM_PAGE[0]` | Out | 2 | — | SRAM A[8] — page bit 0 |
| `SRAM_PAGE[1]` | Out | 3 | — | SRAM A[9] — page bit 1 |
| `SRAM_PAGE[2]` | Out | 4 | — | SRAM A[10] — page bit 2 |
| `SRAM_PAGE[3]` | Out | 6 | — | SRAM A[11] — page bit 3 |
| `SRAM_PAGE[4]` | Out | 9 | — | SRAM A[12] — page bit 4 |
| `SRAM_PAGE[5]` | Out | 10 | — | SRAM A[13] — page bit 5 |
| `SRAM_BLOCK[0]` | Out | 19 | — | SRAM A[14] — block bit 0 |
| `SRAM_BLOCK[1]` | Out | 20 | — | SRAM A[15] — block bit 1 |
| `SRAM_BLOCK[2]` | Out | 21 | — | SRAM A[16] — block bit 2 |
| `SRAM_BLOCK[3]` | Out | 38 | — | SRAM A[17] — block bit 3 |
| `SRAM_CE_N` | Out | 23 | — | SRAM chip enable (active low); also gates the data transceiver |
| `SRAM_OE_N` | Out | 39 | — | SRAM output enable (active low) — read cycles only |
| `SRAM_WE_N` | Out | 25 | — | SRAM write enable (active low) — write cycles only |

\* Placeholder numbers — replace with actual schematic pad numbers.

---

## Source files

| File | Description |
|------|-------------|
| `C6502_Interface.vhd` | Top-level entity (Rev 6, C64 expansion port, VERA + GeoRAM) |
| `board-pin-mapping.pcf` | Pin constraints for iCE40UP5K SG48 (edit before use) |
| `Makefile` | Build and flash targets |
