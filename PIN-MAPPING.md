# Pin Mapping: VERA Module RBL-C64 (ESP32-S3FN8)

Target MCU: **ESP32-S3FN8** — QFN56 package, 45 GPIOs, 8 MB in-package Quad SPI flash,
512 KB SRAM, dual-core Xtensa LX7 @ 240 MHz.

Host: **Commodore 64**, porta di espansione (cartridge port). La scheda espone i registri
VERA e una GeoRAM 256 KB emulata nelle aree I/O `IO1`/`IO2`:

| Indirizzo | Linea C64 | Funzione |
|---|---|---|
| `$DE00–$DEFF` | `/IO1` | finestra GeoRAM (pagina da 256 byte) — ESP32 |
| `$DF00–$DF1F` | `/IO2` | registri VERA — FPGA (`DEV_SEL_N`) |
| `$DFFD` | `/IO2` | latch selezione VERA: ≠ 0 seleziona, `0` deseleziona (la GeoRAM è sempre attiva) |
| `$DFFE` / `$DFFF` | `/IO2` | GeoRAM registro pagina (0–63) / blocco (0–15), sola scrittura |

> **Documenti collegati:** requisiti e verifiche hardware in
> [`VERA-C64-HW-REQUIREMENTS.md`](VERA-C64-HW-REQUIREMENTS.md).
>
> **Origine e allineamento con RBL-XE.** Lo schema è quello di VERA Module RBL-XE (revisione del
> 2026-10-26: gating di `~OE` di `U19`, strapping dell'ESP32, IRQ open-drain, canali di riserva) con il
> foglio `cartridgeInterface.sch` riadattato alla porta di espansione del C64 (§ 9). I GPIO
> dell'ESP32-S3 sono gli stessi di RBL-XE, tranne GPIO 41/42, che qui sono gli **ingressi** `/IO1`/`/IO2`
> invece delle uscite `EXTSEL_N`/`MPD`. `U6` è il transceiver C64→scheda, `U16` quello scheda→C64.
> La netlist `VERA-MODULE-RBL.net` è allineata allo schema; **il PCB è ancora quello Atari** (§ 9).

---

## ⚠ Critical Boot-Time Warnings

| GPIO | QFN56 pin | Signal | Risk |
|------|-----------|--------|------|
| **GPIO 0** | 5 | BOOT0 | Strapping pin (boot mode) — **non è NC**: rete `BOOT0` con `R33` 4,7 kΩ → 3V3, pulsante `SW3`, `C61` 100 nF e `R54` 220 Ω verso `Q4` (auto-reset del programmatore). LOW al reset = modalità download (richiede anche GPIO 46 LOW). CHIP_PU ha `R31` 4,7 kΩ + `C25` **1 µF** (4,7 ms) contro 0,47 ms di BOOT0: GPIO 0 è già alto quando il reset viene rilasciato. |
| **GPIO 3** | 8 | — | Strapping pin (JTAG source, no internal pull) — **non usato dal firmware**. Pull-up **`R71` 10 kΩ → 3V3**, come richiesto dal datasheet (§3.4: senza pull interne, non può restare flottante). HIGH = JTAG sull'USB Serial/JTAG anche se un giorno si programmasse `EFUSE_STRAP_JTAG_SEL`: GPIO 39–42 non diventano mai pin JTAG. Con gli eFuse di fabbrica il valore è comunque ignorato. |
| **GPIO 26–32** | 28, 30–35 | — | SPI0/1 pins of the in-package memory (datasheet Table 2-14). On the FN8 the Quad SPI flash uses GPIO 27–32 (pins 30–35): **never connect externally**. GPIO 26 (pin 28, SPICS1) is the in-package PSRAM chip select, absent on the FN8; Espressif still advises against other uses. |
| **GPIO 45** | 51 | A14 | Strapping pin (VDD_SPI select) — pull-down interno debole (45 kΩ). Connesso ad A14 via `U3` (74LVC4245). Le linee indirizzo della porta sono **sempre pilotate** (dal 6510, anche in reset, o in φ1 dal VIC-II e dai pull-up della scheda madre), quindi il livello non può dipendere dal C64: `~OE` di `U3` (e di `U4`) è la rete **`~ABUS_OE`**, pilotata da **GPIO 47** e tenuta alta da `R7`/`R34` (10 kΩ → 3V3) mentre l'ESP32 è in reset. Con `U3` spento il pull-down interno dà **LOW → VDD_SPI = 3,3 V da VDD3P3_RTC** (Table 3-4), il valore richiesto dalla flash in-package della FN8. Vale a ogni reset del chip (accensione, CHIP_PU, programmatore). Il firmware abilita `U3`/`U4` in `setup()`, molto dopo i 3 ms di hold. Gli eFuse `VDD_SPI_FORCE`/`TIEH` non servono. |
| **GPIO 46** | 52 | A15 | Strapping pin (ROM messages on UART0, download mode) — pull-down interno debole (45 kΩ). Connesso ad A15 via `U3`, stesso gating di GPIO 45 → **LOW**: messaggi ROM disabilitati e, con GPIO 0 LOW, download boot valido (GPIO 0 LOW + GPIO 46 HIGH è una combinazione non valida). |

> **JTAG pins reclaimed (GPIO 39–42):** il firmware chiama `gpio_reset_pin()` su GPIO 39, 40,
> 41, 42 per de-registrarli dal controller JTAG e utilizzarli come GPIO normali. GPIO 41/42
> (MTDI/MTMS) sono ingressi anche in modalità JTAG: `U6` può pilotarli fin dall'accensione.

> **GPIO 19–20 (pin 25–26, USB D−/D+):** USB CDC disabilitato nel firmware
> (`ARDUINO_USB_CDC_ON_BOOT=0`). Questi pin sono usati come A7 e A8 sul bus indirizzi.

> **GPIO 15–16 (pin 21–22, XTAL\_32K\_P/N):** nessun quarzo da 32 kHz presente.
> Utilizzati come normali GPIO (A3 e A4 sul bus indirizzi).

---

## 0. Porta di espansione C64 (`CART1`)

Simbolo `RetroBitLab:C64-EXPANSION-PORT`, footprint `RetroBitLab:C64-EXPANSION-CARTRIDGE`:
contatti a pettine sul bordo della scheda, **2 × 22, passo 2,54 mm**; pin 1–22 sul lato
componenti (F.Cu), A–Z sul lato saldature (B.Cu), il pin A dietro il pin 1. Visti dal retro
del C64, 22/Z sono a sinistra e 1/A a destra.

| Pin | Segnale | Rete | Uso sulla scheda |
|---|---|---|---|
| 1, 22, A, Z | GND | `GND` | massa |
| 2, 3 | +5V | `5V` | alimentazione della scheda (senza diodo, § 4) |
| 4 | `/IRQ` | `~IRQ` | uscita IRQ della VERA, open-drain `U26` |
| 5 | `R/W` | `R~W` | `U6` → GPIO 2, gating `U24`, strobe VERA (`U5`); pull-up `R69` 10 kΩ → 5V |
| 6 | Dot Clock | — | non collegato |
| 7 | `/IO1` | `~IO1` | `U6` → GPIO 41 (`~mIO1`), gating `U24`, LED `LD5` |
| 8, 9 | `/GAME`, `/EXROM` | — | **non collegati**: la memory map del C64 resta quella standard |
| 10 | `/IO2` | `~IO2` | `U6` → GPIO 42 (`~mIO2`), LED `LD1` |
| 11, B | `/ROML`, `/ROMH` | — | non collegati |
| 12 | `BA` | `BA` | `U6` → `mBA`, solo test point `TP3` |
| 13 | `/DMA` | `~DMA` | `U6` → `~mDMA`, solo test point `TP2` (la scheda non fa DMA) |
| 14–21 | D7–D0 | `D7`…`D0` | `U19` → GPIO 11…4 |
| C | `/RESET` | `~RST` | uscita open-drain `U27` (GPIO 37) e ingresso `U6` → `~mRST`, test point `TP4` |
| D | `/NMI` | — | non collegato |
| E | φ2 | `PHI2` | `U6` → GPIO 1, gating `U25`, strobe VERA |
| F, H | A15, A14 | `A15`, `A14` | `U3` → GPIO 46, 45 (strapping) |
| J, K, L, M, N, P | A13…A8 | `A13`…`A8` | `U3` → GPIO 34, 33, 36, 35, 21, 20 |
| R…Y | A7…A0 | `A7`…`A0` | `U4` → GPIO 19…12 |

> **Audio.** La porta di espansione non ha un ingresso audio (sull'Atari c'era `AUDIO`, ECI pin 5).
> Il mix L+R della VERA (`R2`, `R6`, `C66`) resta sul test point **`TP5`** (rete `AUDIO`): se si vuole
> mixarlo col SID va portato a mano all'ingresso audio della presa A/V (DIN pin 5, EXT IN del SID).

---

## 1. Data Bus D0–D7  (bidirectional, Bank 0 bits 4–11)

Tutti via level shifter **74LVC4245APW_118 U19** (A side = C64 5 V, B side = ESP32 3,3 V) —
unico canale realmente **bidirezionale** del progetto: la direzione (pin DIR) è commutata
dinamicamente da un invertitore **SN74HCT04DR U23** pilotato da R/W\_; `~OE` viene dal gating di
`U24`/`U25`. Vedere § 6.

| C64 signal | Porta esp. | GPIO | QFN56 pin | IO MUX | Bank-0 bit | Notes |
|---|---|---|---|---|---|---|
| D0 | 21 | 4  | 9  | GPIO4  | 4  | 60 µs LOW glitch al power-up |
| D1 | 20 | 5  | 10 | GPIO5  | 5  | |
| D2 | 19 | 6  | 11 | GPIO6  | 6  | |
| D3 | 18 | 7  | 12 | GPIO7  | 7  | |
| D4 | 17 | 8  | 13 | GPIO8  | 8  | |
| D5 | 16 | 9  | 14 | GPIO9  | 9  | |
| D6 | 15 | 10 | 15 | GPIO10 | 10 | |
| D7 | 14 | 11 | 16 | GPIO11 | 11 | |

Firmware bitmask: `DBUS_MASK = 0x00000FF0`
Firmware data decode: `data = (GPIO.in >> 4) & 0xFF`

---

## 2. Address Bus A0–A15

> **Sul C64 il bus indirizzi della porta non è solo della CPU.** Durante PHI1, e con PHI2
> alto nelle badline e nei fetch sprite (`AEC` basso), sulla porta compaiono gli indirizzi
> del **VIC-II**, con A12–A15 che possono formare `$Dxxx`. L'indirizzo letto non basta
> quindi a dire se il ciclo è della CPU. Il firmware qualifica ogni ciclo con `/IO1` e
> `/IO2` (§ 3), che il PLA asserisce solo per accessi CPU. In più, la pagina (`$DE`/`$DF`)
> è implicita nella linea `/IOx` attiva: per la decodifica bastano **A0–A7**.
> A8–A15 restano cablati e configurati come ingressi, ma il firmware non li usa.

### A0–A7 (Bank 0, GPIO 12–19, via 74LVC4245APW_118 U4)

| C64 signal | Porta esp. | GPIO | QFN56 pin | IO MUX | Bank-0 bit | Notes |
|---|---|---|---|---|---|---|
| A0 | Y | 12 | 17 | GPIO12        | 12 | |
| A1 | X | 13 | 18 | GPIO13        | 13 | |
| A2 | W | 14 | 19 | GPIO14        | 14 | |
| A3 | V | 15 | 21 | XTAL\_32K\_P  | 15 | Pad RTC usato come GPIO; pin 20 = VDD3P3\_RTC |
| A4 | U | 16 | 22 | XTAL\_32K\_N  | 16 | Pad RTC usato come GPIO |
| A5 | T | 17 | 23 | GPIO17        | 17 | |
| A6 | S | 18 | 24 | GPIO18        | 18 | |
| A7 | R | 19 | 25 | USB\_D−       | 19 | USB disabilitato; pin condiviso con USB D− |

### A8–A15 (Bank 0/1, GPIO 20–21, 35–36, 33–34, 45–46, via 74LVC4245APW_118 U3)

Non usati dalla decodifica (vedere nota sopra), disponibili per debug o usi futuri.
A14/A15 sono comunque gli strapping di GPIO 45/46, resi sicuri dalla rete `~ABUS_OE`.

| C64 signal | Porta esp. | GPIO | QFN56 pin | IO MUX | Bank bit | Notes |
|---|---|---|---|---|---|---|
| A8  | P | 20 | 26 | USB\_D+ | Bank 0 bit 20 | USB disabilitato; pin condiviso con USB D+ |
| A9  | N | 21 | 27 | GPIO21  | Bank 0 bit 21 | |
| A10 | M | 35 | 40 | GPIO35  | Bank 1 bit 3  | |
| A11 | L | 36 | 41 | GPIO36  | Bank 1 bit 4  | |
| A12 | K | 33 | 38 | GPIO33  | Bank 1 bit 1  | |
| A13 | J | 34 | 39 | GPIO34  | Bank 1 bit 2  | |
| A14 | H | 45 | 51 | GPIO45  | Bank 1 bit 13 | Strapping pin (VDD_SPI); `U3` spento durante il reset (`~ABUS_OE`) → pull-down → LOW |
| A15 | F | 46 | 52 | GPIO46  | Bank 1 bit 14 | Strapping pin (ROM msgs / download); `U3` spento durante il reset → pull-down → LOW |

### Firmware: decode

Il loop del bus legge `/IO1` e `/IO2` sui canali di ingresso **Dedicated GPIO** e A0–A7
dall'unica lettura APB di `GPIO.in`. Le azioni di `IO2` per ogni offset sono in una tabella
precalcolata (`firmware/MCU/include/bus_decode.h`), una per stato del latch `$DFFD`.

```c
/* din = ee.get_gpio_in: bit 0 = PHI2, bit 1 = R/W, bit 2 = /IO1, bit 3 = /IO2 */
/* lo  = GPIO.in:        bit 12..19 = A0..A7                                   */
uint32_t off8 = (lo >> 12) & 0xFF;            /* A0-A7 */

/* /IO1 ($DE00-$DEFF): GeoRAM georam_256k[block<<14 | page<<8 | off8]  (sempre)      */
/* /IO2: c = bus_io2[selected][off8]                                                 */
/*   off8 $00-$1F : VERA, DEV_SEL_N                       (se VERA selezionata)      */
/*   off8 $FD     : latch selezione VERA, write != 0 seleziona, 0 deseleziona        */
/*   off8 $FE/$FF : GeoRAM pagina / blocco, solo scrittura          (sempre)         */
```

---

## 3. Control Signals

Il firmware decodifica gli indirizzi in software, qualificati dalle linee `/IO1` e `/IO2`
della porta di espansione. Legge PHI2, R/W\_, `/IO1` e `/IO2` tramite **Dedicated GPIO**
(istruzioni TIE Xtensa `ee.get_gpio_in` / `ee.wr_mask_gpio_out`, 1 ciclo CPU), poi A0–A7 da
`GPIO.in`.

### Sequenza per ciclo

1. Attesa fronte di salita di PHI2.
2. Attesa **limitata** (`IO_QUALIFY_NS`, default 200 ns) di `/IO1` o `/IO2` basso. Se
   nessuna delle due si attiva, il ciclo non è della scheda (altro indirizzo o fetch
   VIC-II) e viene saltato senza toccare bus o segnali.
3. Campionamento di A0–A7 (una lettura APB): a questo punto `AEC` è alto e l'indirizzo è
   quello del 6510.
4. Registri VERA: `DEV_SEL_N` asserito, risponde la FPGA. Finestra GeoRAM: nessun segnale
   (la GeoRAM è nella RAM dell'ESP32, `U19` è abilitato da `/IO1`); in lettura l'ESP32 pilota
   D0–D7 subito.
5. Scrittura: dato campionato `BUS_WR_SAMPLE_NS` (default 300 ns) dopo la salita di PHI2.
6. Al fronte di discesa di PHI2: bus rilasciato, segnali de-asseriti.

**Timing `/IO1`/`/IO2`.** Nel C64 sono generati dal 74LS139 (`U15` della scheda madre) a valle
del PLA, che le abilita solo con `AEC` alto: si attivano qualche decina di ns dopo il fronte di
salita di PHI2. PHI2 alto dura ~490 ns (PAL 0,985 MHz / NTSC 1,023 MHz) e il 6510 campiona il
dato 100 ns prima della discesa. `IO_QUALIFY_NS` e `BUS_WR_SAMPLE_NS` vanno verificati
all'oscilloscopio sulla scheda reale.

| Signal | Porta esp. | GPIO | QFN56 pin | IO MUX | Direction | Active | Level shift | Description |
|---|---|---|---|---|---|---|---|---|
| PHI2 | E | 1 | 6 | GPIO1 | Input | HIGH | via U6 | Clock fase 2 CPU 6510 — 0,985 MHz PAL / 1,023 MHz NTSC |
| R/W\_ | 5 | 2 | 7 | GPIO2 | Input | HIGH=read | via U6 | Read / Not-Write |
| /IO1 | 7 | 41 | 47 | MTDI | Input | LOW | via U6 | Accesso CPU a `$DE00–$DEFF`; abilita anche `U19` nelle letture GeoRAM (§ 6). Rete `~mIO1` (era `~mEXSEL` su RBL-XE). Ex-JTAG, reclaimed. |
| /IO2 | 10 | 42 | 48 | MTMS | Input | LOW | via U6 | Accesso CPU a `$DF00–$DFFF`. Rete `~mIO2` (era `~mMPD` su RBL-XE). Ex-JTAG, reclaimed. |
| DEV\_SEL\_N | — | 40 | 45 | MTDO | **Output** | LOW | **direct** | VERA chip select (3.3 V, rete `~mVCS0`) per `$DF00–$DF1F` con la VERA selezionata (`$DFFD`); pull-up `R36`. Ex-JTAG, reclaimed. |
| ARESET | C | 37 | 42 | GPIO37 | **Output** | LOW | via U27 | `/RESET` del C64 (rete `~C64_RESET` → `~RST`) attraverso il buffer **open-drain** `U27` SN74LVC1G07: la scheda tira solo in basso, la linea resta condivisa con la scheda madre e le altre cartucce. Pull-down `R70` 10 kΩ: C64 in reset anche mentre l'ESP32 si avvia; basso finché la FPGA non è configurata. Vedere `VERA-C64-HW-REQUIREMENTS.md` §2.12. |
| CRESET | — | 38 | 43 | GPIO38 | **Output** | LOW | **direct** | VERA FPGA Reset — 3.3 V, diretto al chip FPGA. |
| CDONE | — | 39 | 44 | MTCK | Input | HIGH | **direct** | VERA FPGA configured status — HIGH = configurazione completata. Ex-JTAG, reclaimed. |
| ABUS\_OE\_N | — | 47 | 37 | SPICLK\_P | **Output** | LOW | **direct** | Rete `~ABUS_OE`: `~OE` di `U3` (A8–A15) e `U4` (A0–A7), pull-up `R7`/`R34` 10 kΩ → 3V3. Alto (traslatori spenti) durante il reset dell'ESP32, così GPIO 45/46 leggono LOW; il firmware lo porta basso in `setup()`. Dominio VDD\_SPI = 3,3 V. |

Le pull-up 10 kΩ `R53` e `R65`, che su RBL-XE tenevano alti `EXTSEL_N`/`MPD`, restano su `~mIO1` e
`~mIO2`: sono innocue, perché le due reti sono pilotate da `U6`.

### Dedicated GPIO — canali usati

| Pool | Ch | GPIO | QFN56 pin | Segnale |
|------|----|------|-----------|---------|
| Input  | 0 | 1  | 6  | PHI2        |
| Input  | 1 | 2  | 7  | R/W\_       |
| Input  | 2 | 41 | 47 | /IO1        |
| Input  | 3 | 42 | 48 | /IO2        |
| Output | 0 | 40 | 45 | DEV\_SEL\_N |

I pool input e output Dedicated GPIO sono **indipendenti** su ESP32-S3: il canale 0 in lettura
e il canale 0 in scrittura puntano a pin fisici diversi.

---

## 4. Debug / Programming

| Function | GPIO | QFN56 pin | IO MUX | Notes |
|---|---|---|---|---|
| UART TX | 43 | 49 | U0TXD | Serial debug output — UART0 hardware pin |
| UART RX | 44 | 50 | U0RXD | Serial debug input  — UART0 hardware pin |

> **Programmazione e USB solo a scheda scollegata dal C64.** La rete 5 V della scheda è unita al +5 V del C64 (`CART1` pin 2 e 3) senza diodo: con il cavo USB (`J4`) o il jack (`J5`) collegati mentre la scheda è inserita, la scheda alimenterebbe il C64 (spento) o lavorerebbe in parallelo al suo alimentatore (acceso). Vale anche per il monitor seriale: con la scheda nel C64 usare un adattatore senza VBUS. Vedere `VERA-C64-HW-REQUIREMENTS.md` §2.11.

---

## 5. Crystal Oscillator (40 MHz)

The ESP32-S3FN8 requires an external **40 MHz crystal** to generate the
internal PLL reference that drives the CPU at 240 MHz, the Flash interface,
and the UART baud-rate dividers. Without it the chip does not boot.
The pins are **dedicated analog** — not GPIO, not software-configurable.

| QFN56 pin | Signal  | Notes                                          |
|-----------|---------|------------------------------------------------|
| 53        | XTAL\_N | Crystal − terminal (oscillator amplifier output) |
| 54        | XTAL\_P | Crystal + terminal (oscillator amplifier input)  |

### Schematic

```
           C1 (10 pF)
XTAL_P (54) ──┤├── GND
      │
    [X1  40 MHz]   ← Rs 0–33 Ω optional, in series with crystal
      │
XTAL_N (53) ──┤├── GND
           C2 (10 pF)
```

| Component | Value | Notes |
|-----------|-------|-------|
| X1 — crystal | 40 MHz, SMD 3225 or 2016 | ±10 ppm or better; note C\_L in datasheet |
| C1, C2 — load caps | 10 pF 0402 ±5 % | C\_ext = 2 × C\_L − C\_stray ; C\_stray ≈ 3–5 pF |
| Rs — series resistor | 0–33 Ω (optional) | Limits oscillator drive level; omit if crystal oscillates cleanly |

**PCB layout:**
- Keep XTAL\_P / XTAL\_N traces as short as possible (< 5 mm).
- Place C1 and C2 **at the chip pins**, not near the crystal body.
- Do not route other signals under or parallel to crystal traces.
- Solid ground plane under the entire crystal area.
- Keep away from PHI2 (~1 MHz), the 240 MHz CPU clock distribution, and D0–D7.

---

## 6. Level Shifting (74LVC4245APW_118, SN74HCT04DR, SN74LVC00A)

Cinque **74LVC4245APW,118** (NXP, dual-supply octal bus transceiver, TSSOP-24, LCSC C6091) più
un'unità di un **SN74HCT04DR** (hex inverter, `U23`) per la direzione dinamica del bus dati e
due **SN74LVC00A** (`U24`, `U25`) per l'abilitazione (`~OE`) di U19. Il 74LVC4245 **non ha
auto-sensing**: richiede che DIR e ~OE\_ siano pilotati esplicitamente.

**Pinout 74LVC4245APW,118 (TSSOP-24):**

| Pin | Nome | Funzione |
|---|---|---|
| 1 | VCCA | Alimentazione lato A — 5 V (C64); `DIR` e `~OE_` sono riferiti a VCCA (soglia TTL) |
| 2 | DIR | Direzione: A→B oppure B→A a seconda del verso cablato |
| 3–10 | A0–A7 | Canali lato A (5 V, C64) |
| 11, 12, 13 | GND | Massa |
| 14–21 | B7–B0 | Canali lato B (3,3 V, ESP32/FPGA; ordine invertito rispetto ad A0–A7) |
| 22 | ~OE\_ | Output enable, attivo basso |
| 23, 24 | VCCB | Alimentazione lato B — 3,3 V (entrambi i pin a 3V3) |

100 nF ceramico su VCCA→GND e VCCB→GND per ciascun chip. Sui bus a **direzione fissa**
(indirizzi, segnali di controllo) DIR è cablato staticamente al verso corretto; sul bus dati
**bidirezionale** (U19) DIR è invece pilotato dinamicamente. `~OE_` è fisso a GND (`R64`, `R66`
da 0 Ω) solo su U6 e U16: su U3 e U4 è la rete `~ABUS_OE` (GPIO 47, § 3), su U19 il gating di
`U24`/`U25`.

### U4 — Address bus A0–A7 (fisso, 6510 → MCU)

`~OE_` (pin 22) = `~ABUS_OE` (GPIO 47, pull-up `R34` 10 kΩ → 3V3), come U3: spento durante il reset
dell'ESP32. Oltre agli strapping di U3, evita che U4 piloti GPIO 12–19 durante i loro glitch di uscita
all'accensione (datasheet Table 2-2).

| Canale | Lato B (3,3 V, ESP32-S3) | Lato A (5 V, C64) |
|---|---|---|
| A0/B0 | GPIO 12 (pin 17) — A0 | C64 A0 (Y) |
| A1/B1 | GPIO 13 (pin 18) — A1 | C64 A1 (X) |
| A2/B2 | GPIO 14 (pin 19) — A2 | C64 A2 (W) |
| A3/B3 | GPIO 15 (pin 21) — A3 | C64 A3 (V) |
| A4/B4 | GPIO 16 (pin 22) — A4 | C64 A4 (U) |
| A5/B5 | GPIO 17 (pin 23) — A5 | C64 A5 (T) |
| A6/B6 | GPIO 18 (pin 24) — A6 | C64 A6 (S) |
| A7/B7 | GPIO 19 (pin 25) — A7 | C64 A7 (R) (pin condiviso USB D−) |

### U3 — Address bus A8–A15 (fisso, 6510 → MCU)

`~OE_` (pin 22) = `~ABUS_OE` (GPIO 47, pull-up `R7` 10 kΩ → 3V3). Durante il reset dell'ESP32
GPIO 47 è in alta impedenza (nessuna pull interna, nessun glitch), `R7` spegne U3 e GPIO 45/46
(A14/A15) leggono LOW dai pull-down interni: VDD\_SPI = 3,3 V e download boot valido a ogni reset
(§ Critical Boot-Time Warnings). Il firmware abilita U3/U4 in `setup()`.

> **Nota PCB:** tutte le tracce A12–A15 sono portate alla lunghezza della
> traccia più lunga (*length matching* con serpentine) per eliminare lo skew.

| Canale | Lato B (3,3 V, ESP32-S3) | Lato A (5 V, C64) |
|---|---|---|
| A0/B0 | GPIO 20 (pin 26) — A8  | C64 A8 (P) (pin condiviso USB D+) |
| A1/B1 | GPIO 21 (pin 27) — A9  | C64 A9 (N)  |
| A2/B2 | GPIO 35 (pin 40) — A10 | C64 A10 (M) |
| A3/B3 | GPIO 36 (pin 41) — A11 | C64 A11 (L) |
| A4/B4 | GPIO 33 (pin 38) — A12 | C64 A12 (K) |
| A5/B5 | GPIO 34 (pin 39) — A13 | C64 A13 (J) |
| A6/B6 | GPIO 45 (pin 51) — A14 | C64 A14 (H) |
| A7/B7 | GPIO 46 (pin 52) — A15 | C64 A15 (F) |

### U6 — Control signals, C64 → MCU (fisso, input)

Su RBL-XE i canali 0, 1, 2, 5, 6 portavano `D1XX`, `S4`, `S5`, `CCTL`, `REFRESH` a LED e test point;
qui portano i segnali C64 corrispondenti per funzione o per misura.

| Canale (pin A → B) | Lato A (5 V, C64) | Lato B (3,3 V) | Note |
|---|---|---|---|
| 0 (3 → 21) | `/IO1` (7) | `~mIO1` → GPIO 41, `U24` pin 4, LED `LD5`, `TP7` | Accesso a `$DExx` |
| 1 (4 → 20) | `BA` (12) | `mBA` → `TP3` | Solo misura |
| 2 (5 → 19) | `/DMA` (13) | `~mDMA` → `TP2` | Solo misura |
| 3 (6 → 18) | `R/W` (5) | `mR~W` → GPIO 2, `U24` pin 1, `U5` | |
| 4 (7 → 17) | `PHI2` (E) | `mPHI2` → GPIO 1, `U25` pin 4, `U5` | |
| 5 (8 → 16) | `/IO2` (10) | `~mIO2` → GPIO 42, LED `LD1`, `TP6` | Accesso a `$DFxx` |
| 6 (9 → 15) | `/RESET` (C) | `~mRST` → `TP4` | Solo misura |
| 7 (10 → 14) | GND con `R74` 0 Ω | non collegato | Canale di riserva |

### U16 — Control signals, MCU → C64 (fisso, output)

| Canale | Lato B (3,3 V, ESP32-S3) | Lato A (5 V, C64) | Note |
|---|---|---|---|
| — | GND con una 0 Ω ciascuno (pin 16 `R80`, 18 `R78`, 17 `R79`, 19 `R73`, 20 `R76`, 21 `R77`, 14 `R72`, 15 `R75`) | non collegati (pin 8, 6, 7, 5, 4, 3, 10, 9) | Canali di riserva: `U16` non pilota più nessuna linea del C64. I pin 18/17 erano `EXTSEL`/`MPD` su RBL-XE, il pin 16 → 8 il reset push-pull (ora `U27`) |
| — | GPIO 37 (pin 42) — `~C64_RESET` | `/RESET` (C) | **Non passa da `U16`**: buffer open-drain `U27` SN74LVC1G07DBVR (A pin 2 ← `~C64_RESET`, Y pin 4 → `~RST`), 3V3 con `C70` 100 nF. Vedere `VERA-C64-HW-REQUIREMENTS.md` §2.12 |
| — | `~mVIRQ` (FPGA `U2` pin 32) | `/IRQ` (4) | **Non passa da `U16`**: buffer open-drain `U26` SN74LVC1G07DBVR (A pin 2 ← `~mVIRQ`, Y pin 4 → `~IRQ`), 3V3 con `C69` 100 nF. Vedere `VERA-C64-HW-REQUIREMENTS.md` §2.3 |

### U19 — Data bus D0–D7 (bidirezionale, direzione dinamica)

DIR è pilotato da un invertitore **SN74HCT04DR U23** (pin 1→2) a partire da R/W\_ (direzione verso
il C64 durante i cicli di lettura del 6510, verso l'ESP32 durante i cicli di scrittura).

> **`~OE_` (pin 22) = `NAND(PHI2, NAND(R/W, DEV_SEL_N, /IO1))`**, realizzato con le due SN74LVC00A di
> RBL-XE (`U24`, `U25`): `U19` è acceso in scrittura, nelle letture VERA (`DEV_SEL_N`) e nelle letture
> della finestra GeoRAM (`/IO1`), spento in φ1 e in tutte le altre letture (RAM, ROM e I/O della scheda
> madre). Rispetto a RBL-XE l'ingresso `~mEXSEL` di `U24` (pin 4) è diventato `~mIO1` e `~mMPD` (pin 5)
> è fisso a 3V3. Dettaglio, piedinatura e tempi in `VERA-C64-HW-REQUIREMENTS.md` §2.1.
>
> **GeoRAM sempre attiva:** ogni lettura a `$DExx` abilita `U19` e l'ESP32 pilota D0–D7 con il
> byte della pagina GeoRAM corrente, indipendentemente dal latch `$DFFD`.

| Canale | Lato B (3,3 V, ESP32-S3) | Lato A (5 V, C64) |
|---|---|---|
| A0/B0 | GPIO 4  (pin  9) — D0 | C64 D0 (21) |
| A1/B1 | GPIO 5  (pin 10) — D1 | C64 D1 (20) |
| A2/B2 | GPIO 6  (pin 11) — D2 | C64 D2 (19) |
| A3/B3 | GPIO 7  (pin 12) — D3 | C64 D3 (18) |
| A4/B4 | GPIO 8  (pin 13) — D4 | C64 D4 (17) |
| A5/B5 | GPIO 9  (pin 14) — D5 | C64 D5 (16) |
| A6/B6 | GPIO 10 (pin 15) — D6 | C64 D6 (15) |
| A7/B7 | GPIO 11 (pin 16) — D7 | C64 D7 (14) |

**Connessioni dirette (senza level shifter):**

| Signal | GPIO | QFN56 pin | Collegato a |
|---|---|---|---|
| DEV\_SEL\_N | 40 | 45 | VERA FPGA pin /CS (3.3 V) e gating `~OE_` di U19 (`U24` pin 2) |
| CRESET | 38 | 43 | VERA FPGA pin /RESET (3.3 V) |
| CDONE | 39 | 44 | VERA FPGA pin CDONE (3.3 V) |
| ABUS\_OE\_N | 47 | 37 | `~OE_` di U3 e U4 (rete `~ABUS_OE`) |

---

## 7. GPIO disponibili (ESP32-S3FN8 QFN56)

Pin non assegnati al progetto, esclusi strapping e flash in-package.

| GPIO | QFN56 pin | IO MUX | Note |
|---|---|---|---|
| 48 | 36 | SPICLK\_N | Libero. Dominio VDD\_SPI (3.3 V sulla FN8, datasheet Table 1-1); usato dalla memoria solo in Octal SPI |
| 22–25 | — | — | Non esistono su ESP32-S3 |

> Resta libero solo GPIO 48 (pin 36), come su RBL-XE; GPIO 47 (pin 37) è `ABUS_OE_N`. GPIO 41 =
> /IO1, GPIO 42 = /IO2; GPIO 33, 34, 45, 46 = A12–A15. GPIO 3 non è usato ma è un pin di strapping:
> lo fissa `R71` (10 kΩ → 3V3). A8–A15 non servono alla decodifica: se occorressero altri ingressi
> (per esempio `BA` o `/DMA`, oggi solo su test point), A8–A13 (GPIO 20, 21, 35, 36, 33, 34) sono i
> candidati; GPIO 45/46 vanno lasciati su A14/A15.

**Pin esclusi (non utilizzabili):**

| GPIO / Funzione | QFN56 pin | Motivo |
|---|---|---|
| GPIO 26–32 | 28, 30–35 | Pin SPI0/1 della memoria in-package: GPIO 27–32 = flash della FN8, mai connettere esternamente; GPIO 26 = CS# PSRAM (assente sulla FN8), sconsigliato da Espressif |
| XTAL\_N / XTAL\_P | 53, 54 | Dedicated analog — quarzo 40 MHz. Vedere § 5. |
| VDDA1 / VDDA2 | 55, 56 | Alimentazione analogica — non GPIO, non connettere a segnali digitali |

---

## 8. QFN56 — Pinout completo

Riferimento rapido ESP32-S3FN8 QFN56 (56 pin + pad centrale 57 = GND). Nomi e numeri da
*ESP32-S3 Series Datasheet* v2.2, Table 2-1 "Pin Overview" (pag. 17); funzioni dei pin della
memoria da Table 2-14 "Pin Mapping Between Chip and Flash or PSRAM" (pag. 31).

| Pin | GPIO / Funzione | Uso in questo progetto |
|-----|-----------------|------------------------|
| 1   | LNA\_IN | Ingresso RF (Wi-Fi/Bluetooth) — non usato dal firmware |
| 2   | VDD3P3 | Alimentazione analogica 3.3 V |
| 3   | VDD3P3 | Alimentazione analogica 3.3 V |
| 4   | CHIP\_PU (EN) | `R31` 4,7 kΩ a 3V3 + `C25` 1 µF a GND (4,7 ms), reset `SW1`, auto-reset `Q3` |
| 5   | GPIO 0 | BOOT0 (pulsante BOOT / auto-reset, pull-up `R33`) — strapping |
| 6   | GPIO 1 | PHI2 input (via U6) |
| 7   | GPIO 2 | R/W\_ input (via U6) |
| 8   | GPIO 3 | Non usato — strapping JTAG source, pull-up `R71` 10 kΩ → 3V3 |
| 9   | GPIO 4 | D0 (via U19) |
| 10  | GPIO 5 | D1 (via U19) |
| 11  | GPIO 6 | D2 (via U19) |
| 12  | GPIO 7 | D3 (via U19) |
| 13  | GPIO 8 | D4 (via U19) |
| 14  | GPIO 9 | D5 (via U19) |
| 15  | GPIO 10 | D6 (via U19) |
| 16  | GPIO 11 | D7 (via U19) |
| 17  | GPIO 12 | A0 (via U4) |
| 18  | GPIO 13 | A1 (via U4) |
| 19  | GPIO 14 | A2 (via U4) |
| 20  | VDD3P3\_RTC | Alimentazione RTC — **non GPIO** |
| 21  | GPIO 15 / XTAL\_32K\_P | A3 (via U4) — nessun quarzo 32 kHz |
| 22  | GPIO 16 / XTAL\_32K\_N | A4 (via U4) — nessun quarzo 32 kHz |
| 23  | GPIO 17 | A5 (via U4) |
| 24  | GPIO 18 | A6 (via U4) |
| 25  | GPIO 19 / USB\_D− | A7 (via U4) — USB disabilitato |
| 26  | GPIO 20 / USB\_D+ | A8 (via U3) — USB disabilitato |
| 27  | GPIO 21 | A9 (via U3) |
| 28  | GPIO 26 (SPICS1) | CS# della PSRAM in-package (assente sulla FN8) — non usato |
| 29  | VDD\_SPI | Alimentazione flash — **non GPIO** |
| 30  | GPIO 27 (SPIHD)  | **Flash in-package (HOLD#) — NC esterno** |
| 31  | GPIO 28 (SPIWP)  | **Flash in-package (WP#) — NC esterno** |
| 32  | GPIO 29 (SPICS0) | **Flash in-package (CS#) — NC esterno** |
| 33  | GPIO 30 (SPICLK) | **Flash in-package (CLK) — NC esterno** |
| 34  | GPIO 31 (SPIQ)   | **Flash in-package (DO) — NC esterno** |
| 35  | GPIO 32 (SPID)   | **Flash in-package (DI) — NC esterno** |
| 36  | GPIO 48 (SPICLK\_N) | GPIO libero — usato dalla memoria solo in Octal SPI; non usato in questo progetto |
| 37  | GPIO 47 (SPICLK\_P) | ABUS\_OE\_N output → `~OE` di U3/U4 (rete `~ABUS_OE`, pull-up `R7`/`R34`) |
| 38  | GPIO 33 | A12 (via U3) |
| 39  | GPIO 34 | A13 (via U3) |
| 40  | GPIO 35 | A10 (via U3) |
| 41  | GPIO 36 | A11 (via U3) |
| 42  | GPIO 37 | ARESET output → C64 /RESET (open-drain U27) |
| 43  | GPIO 38 | CRESET output (diretto VERA) |
| 44  | GPIO 39 / MTCK | CDONE input (diretto VERA) — ex-JTAG |
| 45  | GPIO 40 / MTDO | DEV\_SEL\_N output (diretto VERA) — ex-JTAG |
| 46  | VDD3P3\_CPU | Alimentazione CPU — **non GPIO** |
| 47  | GPIO 41 / MTDI | /IO1 input (via U6) — ex-JTAG |
| 48  | GPIO 42 / MTMS | /IO2 input (via U6) — ex-JTAG |
| 49  | GPIO 43 / U0TXD | UART0 TX — debug seriale |
| 50  | GPIO 44 / U0RXD | UART0 RX — debug seriale |
| 51  | GPIO 45 | A14 (via U3) — strapping VDD\_SPI; U3 spento durante il reset → LOW (3,3 V) |
| 52  | GPIO 46 | A15 (via U3) — strapping ROM msgs / download; U3 spento durante il reset → LOW |
| 53  | XTAL\_N | Quarzo principale 40 MHz — dedicated analog |
| 54  | XTAL\_P | Quarzo principale 40 MHz — dedicated analog |
| 55  | VDDA1   | Alimentazione analogica — non GPIO |
| 56  | VDDA2   | Alimentazione analogica — non GPIO |
| EP  | GND (pad centrale) | GND |

---

## 9. Modifiche hardware rispetto alla versione Atari

Lo schema è stato copiato da RBL-XE (revisione del 2026-10-26) e adattato nel foglio
`cartridgeInterface.sch`. La netlist è stata aggiornata e confrontata con gli schemi da uno
script che ne ricava la connettività (246 reti, nessuna differenza).

| # | Modifica | Stato |
|---|---|---|
| 1 | `CART1` (cartuccia Atari) ed `ECI1` → **`CART1` porta di espansione C64**, 2 × 22 a pettine, passo 2,54 mm (simbolo e footprint nuovi in RetroBitLab-Library) | schema, netlist |
| 2 | `U6` canale 0: `/IO1` → `~mIO1` → GPIO 41 (era `~D1XX` → LED); canale 5: `/IO2` → `~mIO2` → GPIO 42 (era `~CCTL` → LED) | schema, netlist |
| 3 | `U6` canali 1, 2, 6: `BA`, `/DMA`, `/RESET` verso i test point `TP3`, `TP2`, `TP4` (erano `S4`, `S5`, `REFRESH`) | schema, netlist |
| 4 | Gating di `U19`: `U24` pin 4 = `~mIO1` (era `~mEXSEL`), pin 5 = 3V3 (era `~mMPD`) | schema, netlist |
| 5 | `U16` pin 18 e 17 (ex `EXTSEL`/`MPD`) a GND con `R78`/`R79` 0 Ω; uscite pin 6 e 7 non collegate | schema, netlist |
| 6 | `/RESET` C64 open-drain: `U27` SN74LVC1G07 (+ `C70`) fra `~C64_RESET` e `~RST`, come `U26` per l'IRQ; `U16` pin 16 a GND con `R80`, pin 8 non collegato; rete `~ATARI_RESET` rinominata `~C64_RESET` | schema, netlist |
| 7 | Test point `RD4`, `RD5`, `~HALT1` (segnali Atari): `RD4` eliminato, gli altri riusati (`TP6` = `~mIO2`, `TP5` = `AUDIO`); `TP2`–`TP7` rinumerati | schema, netlist |
| 8 | `/GAME`, `/EXROM`, `/ROML`, `/ROMH`, `/NMI`, Dot Clock: non collegati (flag NC) | schema, netlist |
| 9 | **PCB**: contorno scheda, posizione del connettore a pettine e sbroglio dei nuovi collegamenti vanno rifatti partendo dal PCB Atari con "Update PCB from netlist" | **da fare** |
| 10 | Loghi: `LOGO2` diventa `C64 READY` (footprint `c64_ready_8mm_REV`), `LOGO4` (logo del bus DUOCart Atari) eliminato; BOM `VERA-MODULE-RBL.csv` rigenerata dalla netlist | schema, netlist |
