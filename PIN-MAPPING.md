# Pin Mapping: VERA Module RBL-C64 (ESP32-S3FN8)

Target MCU: **ESP32-S3FN8** — QFN56 package, 45 GPIOs, 8 MB in-package Quad SPI flash,
512 KB SRAM, dual-core Xtensa LX7 @ 240 MHz.

Host: **Commodore 64**, porta di espansione (cartridge port). La scheda espone i registri
VERA e una GeoRAM 256 KB emulata nelle aree I/O `IO1`/`IO2`:

| Indirizzo | Linea C64 | Funzione |
|---|---|---|
| `$DE00–$DEFF` | `/IO1` | finestra GeoRAM (pagina da 256 byte) — ESP32 |
| `$DF00–$DF1F` | `/IO2` | registri VERA — FPGA (`DEV_SEL_N`) |
| `$DFFD` | `/IO2` | latch selezione scheda: ≠ 0 seleziona VERA + GeoRAM, `0` deseleziona |
| `$DFFE` / `$DFFF` | `/IO2` | GeoRAM registro pagina (0–63) / blocco (0–15), sola scrittura |

> **Origine:** il progetto deriva dalla versione Atari (VERA Module RBL-XE). Schema e PCB
> sono ancora quelli Atari: le modifiche hardware necessarie per il C64 sono raccolte in
> [§ 9](#9-modifiche-hardware-rispetto-alla-versione-atari). I riferimenti `U*` seguono la
> netlist Atari (2026-09-01): `U6` è il transceiver host→scheda, `U16` quello scheda→host.

---

## ⚠ Critical Boot-Time Warnings

| GPIO | QFN56 pin | Signal | Risk |
|------|-----------|--------|------|
| **GPIO 0** | 5 | BOOT0 | Strapping pin (boot mode) — **non è NC**: rete `BOOT0` con `R33` 4,7 kΩ → 3V3, pulsante `SW3`, `C61` 100 nF e `R54` 220 Ω verso `Q4` (auto-reset del programmatore). LOW al reset = modalità download. |
| **GPIO 3** | 8 | — | Strapping pin (JTAG source, **nessun pull interno**) — **non usato dal firmware**, nessun segnale collegato. Resta solo la resistenza esterna 10 kΩ (ex `RAMBO_EN`, meglio verso 3V3): il datasheet vieta l'alta impedenza durante lo strapping. Con eFuse di default il livello è comunque ignorato. |
| **GPIO 26–32** | 28, 30–35 | — | SPI0/1 pins of the in-package memory (datasheet Table 2-14). On the FN8 the Quad SPI flash uses GPIO 27–32 (pins 30–35): **never connect externally**. GPIO 26 (pin 28, SPICS1) is the in-package PSRAM chip select, absent on the FN8; Espressif still advises against other uses. |
| **GPIO 45** | 51 | A14 | Strapping pin (VDD_SPI select) — internal weak pull-down (~5 kΩ). Connesso ad A14 via `U3`. Al power-on il 6510 è in reset → A14 alta impedenza → `U3` flotta → pull-down → **LOW → VDD_SPI = 3.3 V da VDD3P3_RTC** (datasheet v2.2 Table 3-4), il valore richiesto dalla flash in-package della FN8 (Table 1-1). **Con A14 HIGH al reset VDD_SPI = 1.8 V e il chip non si avvia**: A14 deve essere LOW al power-on (da verificare), oppure programmare `EFUSE_VDD_SPI_FORCE` = 1 e `EFUSE_VDD_SPI_TIEH` = 1 (irreversibile) per fissare 3.3 V. |
| **GPIO 46** | 52 | A15 | Strapping pin (ROM messages on UART0) — internal weak pull-down (~5 kΩ). Connesso ad A15 via `U3`. Stesso scenario di GPIO 45 → **LOW → messaggi ROM disabilitati** (corretto per produzione). |

> **JTAG pins reclaimed (GPIO 39–42):** il firmware chiama `gpio_reset_pin()` su GPIO 39, 40,
> 41, 42 per de-registrarli dal controller JTAG e utilizzarli come GPIO normali.

> **GPIO 19–20 (pin 25–26, USB D−/D+):** USB CDC disabilitato nel firmware
> (`ARDUINO_USB_CDC_ON_BOOT=0`). Questi pin sono usati come A7 e A8 sul bus indirizzi.

> **GPIO 15–16 (pin 21–22, XTAL\_32K\_P/N):** nessun quarzo da 32 kHz presente.
> Utilizzati come normali GPIO (A3 e A4 sul bus indirizzi).

---

## 1. Data Bus D0–D7  (bidirectional, Bank 0 bits 4–11)

Tutti via level shifter **74LVC4245APW_118 U19** (B side = C64 5 V, A side = ESP32 3.3 V) —
unico canale realmente **bidirezionale** del progetto: la direzione (pin DIR) è commutata
dinamicamente da due invertitori **SN74HCT04DR U23**, pilotati da R/W\_ e PHI2. Vedere § 6.

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
A14/A15 restano comunque necessari come rete di strapping definita su GPIO 45/46.

| C64 signal | Porta esp. | GPIO | QFN56 pin | IO MUX | Bank bit | Notes |
|---|---|---|---|---|---|---|
| A8  | P | 20 | 26 | USB\_D+ | Bank 0 bit 20 | USB disabilitato; pin condiviso con USB D+ |
| A9  | N | 21 | 27 | GPIO21  | Bank 0 bit 21 | |
| A10 | M | 35 | 40 | GPIO35  | Bank 1 bit 3  | |
| A11 | L | 36 | 41 | GPIO36  | Bank 1 bit 4  | |
| A12 | K | 33 | 38 | GPIO33  | Bank 1 bit 1  | |
| A13 | J | 34 | 39 | GPIO34  | Bank 1 bit 2  | |
| A14 | H | 45 | 51 | GPIO45  | Bank 1 bit 13 | Strapping pin (VDD_SPI); pull-down → LOW al boot (sicuro FN8) |
| A15 | F | 46 | 52 | GPIO46  | Bank 1 bit 14 | Strapping pin (ROM msgs); pull-down → LOW al boot (corretto) |

### Firmware: decode

```c
/* La pagina arriva da /IO1 ($DE) o /IO2 ($DF): servono solo A0-A7 */
uint8_t off8 = (GPIO.in >> 12) & 0xFF;            /* A0-A7 — Bank 0 bits 12-19 */

/* /IO1 ($DE00-$DEFF): GeoRAM georam_256k[block<<14 | page<<8 | off8]  (se selezionata) */
/* /IO2 off8 $00-$1F : VERA, DEV_SEL_N                                (se selezionata) */
/* /IO2 off8 $FD     : latch selezione, write != 0 seleziona, 0 deseleziona (sempre)   */
/* /IO2 off8 $FE/$FF : GeoRAM pagina / blocco, solo scrittura          (se selezionata) */
```

---

## 3. Control Signals

Il firmware decodifica gli indirizzi in software, qualificati dalle linee `/IO1` e `/IO2`
della porta di espansione. Legge PHI2, `/IO1` e `/IO2` tramite **Dedicated GPIO**
(istruzioni TIE Xtensa `ee.get_gpio_in` / `ee.wr_mask_gpio_out`, 1 ciclo CPU), poi
A0–A7 e R/W\_ da `GPIO.in`.

### Sequenza per ciclo

1. Attesa fronte di salita di PHI2.
2. Attesa **limitata** (`IO_QUALIFY_NS`, default 200 ns) di `/IO1` o `/IO2` basso. Se
   nessuna delle due si attiva, il ciclo non è della scheda (altro indirizzo o fetch
   VIC-II) e viene saltato senza toccare bus o segnali.
3. Campionamento di A0–A7 e R/W\_: a questo punto `AEC` è alto e l'indirizzo è quello del
   6510.
4. Registri VERA: `DEV_SEL_N` asserito, risponde la FPGA. Finestra GeoRAM: nessun segnale
   (la GeoRAM è nella RAM dell'ESP32); in lettura l'ESP32 pilota D0–D7.
5. Al fronte di discesa di PHI2: bus rilasciato, segnali de-asseriti.

**Timing `/IO1`/`/IO2`.** Nel C64 sono generati dal 74LS139 (`U15`) a valle del PLA, che
le abilita solo con `AEC` alto: si attivano qualche decina di ns dopo il fronte di salita
di PHI2. PHI2 alto dura ~490 ns (PAL 0,985 MHz / NTSC 1,023 MHz). Dopo i 200 ns massimi di
attesa restano ~290 ns per pilotare il bus, più della finestra totale disponibile sull'Atari.
`IO_QUALIFY_NS` va verificato all'oscilloscopio sulla scheda reale.

| Signal | Porta esp. | GPIO | QFN56 pin | IO MUX | Direction | Active | Level shift | Description |
|---|---|---|---|---|---|---|---|---|
| PHI2 | E | 1 | 6 | GPIO1 | Input | HIGH | via U6 | Clock fase 2 CPU 6510 — 0,985 MHz PAL / 1,023 MHz NTSC |
| R/W\_ | 5 | 2 | 7 | GPIO2 | Input | HIGH=read | via U6 | Read / Not-Write |
| /IO1 | 7 | 41 | 47 | MTDI | Input | LOW | via U6 | Accesso CPU a `$DE00–$DEFF`; abilita anche `U19` nelle letture GeoRAM (§ 6). Ex `EXTSEL_N`, ex-JTAG, reclaimed. |
| /IO2 | 10 | 42 | 48 | MTMS | Input | LOW | via U6 | Accesso CPU a `$DF00–$DFFF`. Ex-JTAG, reclaimed. |
| DEV\_SEL\_N | — | 40 | 45 | MTDO | **Output** | LOW | **direct** | VERA chip select (3.3 V) per `$DF00–$DF1F` a scheda selezionata. Ex-JTAG, reclaimed. |
| ARESET | C | 37 | 42 | GPIO37 | **Output** | LOW | via U16 | `/RESET` del C64 — tenuto basso finché la FPGA non è configurata (open-drain consigliato). |
| CRESET | — | 38 | 43 | GPIO38 | **Output** | LOW | **direct** | VERA FPGA Reset — 3.3 V, diretto al chip FPGA. |
| CDONE | — | 39 | 44 | MTCK | Input | HIGH | **direct** | VERA FPGA configured status — HIGH = configurazione completata. Ex-JTAG, reclaimed. |

### Dedicated GPIO — canali usati

| Pool | Ch | GPIO | QFN56 pin | Segnale |
|------|----|------|-----------|---------|
| Input  | 0 | 1  | 6  | PHI2        |
| Input  | 1 | 41 | 47 | /IO1        |
| Input  | 2 | 42 | 48 | /IO2        |
| Output | 0 | 40 | 45 | DEV\_SEL\_N |

I pool input e output Dedicated GPIO sono **indipendenti** su ESP32-S3: il canale 0 in lettura
e il canale 0 in scrittura puntano a pin fisici diversi.

### Porta di espansione — linee non usate

| Linea | Pin | Stato richiesto |
|---|---|---|
| `/GAME`, `/EXROM` | 8, 9 | **non collegate** (restano alte per i pull-up del C64): la scheda non mappa ROM, la memory map resta quella standard |
| `/ROML`, `/ROMH` | 11, B | non collegate |
| `BA`, `/DMA` | 12, 13 | non collegate (la scheda non fa DMA) |
| `/NMI` | D | non collegata |
| Dot Clock | 6 | non collegata |
| `/IRQ` | 4 | uscita IRQ della VERA, **open-drain** (vedere § 6, `U16`) |

---

## 4. Debug / Programming

| Function | GPIO | QFN56 pin | IO MUX | Notes |
|---|---|---|---|---|
| UART TX | 43 | 49 | U0TXD | Serial debug output — UART0 hardware pin |
| UART RX | 44 | 50 | U0RXD | Serial debug input  — UART0 hardware pin |

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

## 6. Level Shifting (74LVC4245APW_118 + SN74HCT04DR)

Cinque **74LVC4245APW,118** (NXP, dual-supply octal bus transceiver, TSSOP-24, LCSC C6091)
più due unità di un **SN74HCT04DR** (hex inverter) usate per la direzione dinamica del bus
dati. Il 74LVC4245 **non ha auto-sensing**: DIR e ~OE\_ vanno pilotati esplicitamente.

**Pinout 74LVC4245APW,118 (TSSOP-24):**

| Pin | Nome | Funzione |
|---|---|---|
| 1 | VCCA | Alimentazione lato A — 3.3 V (ESP32-S3) |
| 2 | DIR | Direzione: A→B oppure B→A a seconda del verso cablato |
| 3–10 | A0–A7 | Canali lato A (3.3 V) |
| 11, 12, 13 | GND | Massa |
| 14–21 | B7–B0 | Canali lato B (5 V, ordine invertito rispetto ad A0–A7) |
| 22 | ~OE\_ | Output enable, attivo basso |
| 23, 24 | VCCB | Alimentazione lato B — 5 V (C64) |

100 nF ceramico su VCCA→GND e VCCB→GND per ciascun chip.

### U4 — Address bus A0–A7 (fisso, 6510 → MCU)

| Canale | Lato A (3.3 V, ESP32-S3) | Lato B (5 V, C64) |
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

| Canale | Lato A (3.3 V, ESP32-S3) | Lato B (5 V, C64) |
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

| Lato A (3.3 V, ESP32-S3) | Lato B (5 V, C64) | Note |
|---|---|---|
| GPIO 1 (pin 6) — PHI2 | PHI2 (E) | Clock fase 2 |
| GPIO 2 (pin 7) — R/W\_ | R/W (5) | Read / Not-Write |
| GPIO 41 (pin 47) — /IO1 | /IO1 (7) | **nuovo** — usa un canale ex `D1XX_N`/`S4_N`/…; il lato B va anche al gating `~OE_` di `U19` |
| GPIO 42 (pin 48) — /IO2 | /IO2 (10) | **nuovo** — usa un canale ex `D1XX_N`/`S4_N`/… |
| — | — | Canali rimanenti liberi |

### U16 — Control signals, MCU → C64 (fisso, output)

| Lato A (3.3 V, ESP32-S3) | Lato B (5 V, C64) | Note |
|---|---|---|
| GPIO 37 (pin 42) — ARESET | /RESET (C) | Output, active LOW (open-drain consigliato) |
| `~mVIRQ` (FPGA, pin 18 lato 3,3 V) | /IRQ (4) | Uscita FPGA push-pull: da sostituire con uno stadio open-drain (74LVC1G07), vedere `VERA-ATARI-HW-REQUIREMENTS.md` §2.3 |
| — | — | Canali ex `EXTSEL`, `MPD`, `RD4`, `RD5`, `HALT`: **nessuna linea C64 corrispondente**, lasciare scollegati dal connettore |

### U19 — Data bus D0–D7 (bidirezionale, direzione dinamica)

DIR è pilotato da due invertitori **SN74HCT04DR U23** a partire da R/W\_ e PHI2 (direzione
verso il C64 durante i cicli di lettura del 6510, verso l'ESP32 durante i cicli di scrittura).

> **`~OE_` (pin 22): da modificare.** `U19` deve pilotare il bus del C64 solo nelle letture a
> cui la scheda risponde, altrimenti va in conflitto con RAM, ROM e I/O della scheda madre.
> Con l'interfaccia C64 il gating diventa
> `~OE_ = NAND(PHI2, NAND(R/W, AND(DEV_SEL_N, /IO1)))`: attivo in scrittura, nelle letture
> VERA (`DEV_SEL_N`) e nelle letture della finestra GeoRAM (`/IO1` direttamente dal C64, lato
> 5 V). Il terzo ingresso dell'AND3 Atari (ex `MPD`) va legato a HIGH. Tempi e parti in
> `VERA-ATARI-HW-REQUIREMENTS.md` §2.1.
>
> **Scheda deselezionata:** una lettura a `$DExx` abilita comunque `U19`, ma l'ESP32 non pilota
> D0–D7 e il valore letto è indeterminato. Sul C64 senza cartuccia quegli indirizzi sono già
> open bus, quindi il comportamento è equivalente.

| Canale | Lato A (3.3 V, ESP32-S3) | Lato B (5 V, C64) |
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
| DEV\_SEL\_N | 40 | 45 | VERA FPGA pin /CS (3.3 V) e gating `~OE_` di U19 |
| CRESET | 38 | 43 | VERA FPGA pin /RESET (3.3 V) |
| CDONE | 39 | 44 | VERA FPGA pin CDONE (3.3 V) |

---

## 7. GPIO disponibili (ESP32-S3FN8 QFN56)

Pin non assegnati al progetto, esclusi strapping e flash in-package.

| GPIO | QFN56 pin | IO MUX | Note |
|---|---|---|---|
| 47 | 37 | SPICLK\_P | Libero. Dominio VDD\_SPI (3.3 V sulla FN8, datasheet Table 1-1); usato dalla memoria solo in Octal SPI |
| 48 | 36 | SPICLK\_N | Libero. Come GPIO 47 |
| 22–25 | — | — | Non esistono su ESP32-S3 |

> GPIO 47 e 48 (pin 37 e 36) sono liberi. GPIO 3 (pin 8) è libero ma è uno strapping pin senza pull interno: va usato solo come
> ingresso pilotato o con la sua resistenza esterna. GPIO 41 = /IO1, GPIO 42 = /IO2;
> GPIO 33, 34, 45, 46 = A12–A15. A8–A15 non servono alla decodifica: se occorressero altri
> ingressi (per esempio `BA` o `/DMA`), A8–A13 (GPIO 20, 21, 35, 36, 33, 34) sono i candidati.
> GPIO 45/46 vanno lasciati su A14/A15 per la rete di strapping.

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
| 4   | CHIP\_PU (EN) | Pull-up 10 kΩ a 3.3 V |
| 5   | GPIO 0 | BOOT0 (pulsante BOOT / auto-reset, pull-up `R33`) — strapping |
| 6   | GPIO 1 | PHI2 input (via U6) |
| 7   | GPIO 2 | R/W\_ input (via U6) |
| 8   | GPIO 3 | Non usato — strapping, solo resistenza esterna 10 kΩ |
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
| 37  | GPIO 47 (SPICLK\_P) | GPIO libero — usato dalla memoria solo in Octal SPI; non usato in questo progetto |
| 38  | GPIO 33 | A12 (via U3) |
| 39  | GPIO 34 | A13 (via U3) |
| 40  | GPIO 35 | A10 (via U3) |
| 41  | GPIO 36 | A11 (via U3) |
| 42  | GPIO 37 | ARESET output → C64 /RESET (via U16) |
| 43  | GPIO 38 | CRESET output (diretto VERA) |
| 44  | GPIO 39 / MTCK | CDONE input (diretto VERA) — ex-JTAG |
| 45  | GPIO 40 / MTDO | DEV\_SEL\_N output (diretto VERA) — ex-JTAG |
| 46  | VDD3P3\_CPU | Alimentazione CPU — **non GPIO** |
| 47  | GPIO 41 / MTDI | /IO1 input (via U6) — ex-JTAG |
| 48  | GPIO 42 / MTMS | /IO2 input (via U6) — ex-JTAG |
| 49  | GPIO 43 / U0TXD | UART0 TX — debug seriale |
| 50  | GPIO 44 / U0RXD | UART0 RX — debug seriale |
| 51  | GPIO 45 | A14 (via U3) — strapping VDD\_SPI; pull-down → LOW al boot (FN8 safe) |
| 52  | GPIO 46 | A15 (via U3) — strapping ROM msgs; pull-down → LOW al boot |
| 53  | XTAL\_N | Quarzo principale 40 MHz — dedicated analog |
| 54  | XTAL\_P | Quarzo principale 40 MHz — dedicated analog |
| 55  | VDDA1   | Alimentazione analogica — non GPIO |
| 56  | VDDA2   | Alimentazione analogica — non GPIO |
| EP  | GND (pad centrale) | GND |

---

## 9. Modifiche hardware rispetto alla versione Atari

| # | Modifica | Motivo |
|---|---|---|
| 1 | Connettore PBI/ECI → **porta di espansione C64** (2×22, passo 3,96 mm), pinout come nelle tabelle sopra | host diverso |
| 2 | **GPIO 41**: scollegarlo da `U16` (ex `EXTSEL_N`) e collegarlo a `/IO1` tramite un canale libero di `U6` | ingresso `/IO1` |
| 3 | **GPIO 42**: scollegarlo da `U16` (ex `MPD`) e collegarlo a `/IO2` tramite un canale libero di `U6` | ingresso `/IO2` |
| 4 | **GPIO 3**: nessun segnale; mantenere la resistenza 10 kΩ (ex `RAMBO_EN`), preferibilmente verso 3V3 | strapping definito |
| 5 | Gating `~OE_` di `U19`: `AND(DEV_SEL_N, /IO1)`, terzo ingresso dell'AND3 (ex `MPD`) legato a HIGH | la GeoRAM non ha un segnale di select: usa `/IO1` |
| 6 | `/GAME`, `/EXROM`, `/ROML`, `/ROMH`, `BA`, `/DMA`, `/NMI`, Dot Clock: non collegati | la scheda non mappa ROM e non fa DMA |
| 7 | `/RESET` e `/IRQ` open-drain verso il C64 | linee wired-OR sulla scheda madre |
