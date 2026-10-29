# Vera-Module-RBL-C64 — Firmware MCU

## 1. Introduzione

Firmware per il microcontrollore **ESP32-S3FN8** (QFN-56, 8 MB flash integrata,
dual-core Xtensa LX7 @ 240 MHz) montato sul modulo Vera-Module-RBL-C64.

> **Requisito hardware:** il chip richiede un **quarzo esterno 40 MHz** collegato
> ai pin dedicati **XTAL\_P** (QFN56 pin 54) e **XTAL\_N** (QFN56 pin 53).
> Senza di esso il chip non si avvia. Vedere `PIN-MAPPING.md` § 5 per il
> circuito consigliato (condensatori di carico, resistenza serie, layout PCB).

Il modulo si collega alla **porta di espansione del Commodore 64**. Espone i
registri VERA in `IO2` (`$DF00–$DF1F`) e una **GeoRAM 256 KB** emulata
(finestra `$DE00–$DEFF` in `IO1`, registri `$DFFE`/`$DFFF`). La VERA si attiva
scrivendo un valore ≠ 0 nel latch `$DFFD` e si disattiva scrivendo `0`; la GeoRAM
è sempre attiva, come nella cartuccia originale.
Ogni ciclo è qualificato dalle linee `/IO1` (GPIO 41) e `/IO2` (GPIO 42) della
porta di espansione, che il PLA asserisce solo per accessi CPU: i fetch del VIC-II
vengono ignorati. La pagina è data dalla linea `/IOx` attiva, A0–A7 danno l'offset.

L'architettura è quella del firmware di VERA Module RBL-XE (loop del bus sul Core 1 a
interruzioni mascherate, percorso critico in assembly, tabelle di decodifica in
`bus_decode.h`, log senza lock), adattata al bus del C64: sull'Atari l'indirizzo è
valido già in φ1 e il loop decodifica in anticipo, sul C64 la porta porta l'indirizzo
del 6510 solo con φ2 alto (`AEC` alto), quindi il loop decodifica all'arrivo di `/IOx`.

---

## 2. Architettura del Firmware

### Sequenza di startup

`setup()` (Core 1) abbassa **ARESET** e **CRESET** immediatamente dopo il reclaim
dei pin JTAG, garantendo che C64 e FPGA VERA rimangano in reset per tutta la
durata dell'inizializzazione ESP32. Poi:

1. crea `LogTask` sul **Core 0**, che apre `Serial` (l'interrupt della UART va
   sul core che chiama `Serial.begin`);
2. costruisce le tabelle di decodifica, configura i GPIO e porta basso
   **`ABUS_OE_N`** (GPIO 47): da qui `U3`/`U4` passano gli indirizzi all'ESP32;
3. **CRESET → HIGH**: la FPGA VERA esce dal reset e carica il bitstream dalla
   flash SPI on-board;
4. **Poll CDONE** (GPIO 39) finché il pin va HIGH — ICE40UP5K tipicamente
   < 100 ms. Timeout 5 s con log di errore;
5. **Attesa `VERA_POST_CDONE_DELAY_US`** (default 1000 µs): copre il power-on
   reset interno della VERA, che parte solo dopo `CDONE`;
6. crea `MonitorTask` sul **Core 1** con priorità massima: il task prende il core
   e `setup()` non riprende più. `MonitorTask` crea i bundle Dedicated GPIO,
   disattiva il watchdog delle interruzioni, maschera le interruzioni e porta
   **ARESET → HIGH**: da questo momento il bus è live.

### Divisione dei core

| Core | Cosa gira | Interrupt |
|------|-----------|-----------|
| **0** | `LogTask`: svuota `log_ring` e stampa su `Serial`; tick FreeRTOS | tick, UART0 |
| **1** | solo `MonitorTask` (loop del bus, priorità `configMAX_PRIORITIES - 1`, non cede mai la CPU) | **nessuno** (mascherati) |

Il loop del bus gira a interruzioni mascherate (`portDISABLE_INTERRUPTS()`): il
tick di FreeRTOS a 1 kHz gli farebbe perdere alcuni cicli di bus ogni millisecondo
(la versione precedente girava sul Core 0 con il tick attivo). Il watchdog delle
interruzioni (MWDT1) controlla anche il Core 1 tramite il suo tick hook, che non gira
più: `MonitorTask` lo disattiva prima di mascherare le interruzioni.

Il loop passa gli eventi (cambio del latch `$DFFD`, registri VERA con
`-DVERA_TRACE_REGS=1`) a `LogTask` tramite `log_ring`, un ring buffer
single-producer/single-consumer senza lock: il push costa poche istruzioni e
non chiama FreeRTOS; il timestamp è aggiunto da `LogTask` quando stampa. Il cambio
di latch viene registrato nella coda di φ2 e inserito nel ring nel φ1 successivo.
Se il ring è pieno l'evento viene scartato e `LogTask` stampa quanti ne sono stati persi.

### Loop del bus (Core 1, interruzioni mascherate)

Ad ogni ciclo di clock del 6510 (PHI2 @ 0,985 MHz PAL / 1,023 MHz NTSC, PHI2 alto
≈ 490 ns, circa 117 cicli CPU a 240 MHz):

1. Attende il fronte di salita di PHI2 con **Dedicated GPIO in**
   (`ee.get_gpio_in`, 1 ciclo; il loop di attesa è di 3 cicli per campione) e
   annota l'istante con `CCOUNT`.
2. Attende, per al massimo `IO_QUALIFY_NS` (default 200 ns) dalla salita, che
   `/IO1` o `/IO2` vada basso (canali Dedicated GPIO 2 e 3, `bnall` in un solo
   salto). Se non succede, il ciclo non è della scheda (altro indirizzo o fetch
   VIC-II) e il loop passa all'attesa della discesa senza toccare nulla.
3. Legge A0–A7 con **una sola lettura APB** di `GPIO.in` (R/W è già nel canale
   Dedicated GPIO 1).
4. **`/IO2`:** `c = bus_io2[latch][A0-A7]` (`include/bus_decode.h`) e
   `DEV_SEL_N` per questo ciclo con un `ee.wr_mask_gpio_out`: per `$DF00–$DF1F`
   con la VERA selezionata risponde la FPGA.
5. **`/IO1` in lettura:** pilota subito D0–D7 con il byte `win[A0-A7]` (`win` è
   la pagina GeoRAM corrente, tenuta in un registro): `GPIO.out = byte << 4` e
   `GPIO.enable_w1ts`, due store "posted" senza `memw`. `U19` passa il dato al
   C64 perché `/IO1` lo abilita (gating hardware, `PIN-MAPPING.md` § 6).
6. **Scrittura:** campiona `GPIO.in` `BUS_WR_SAMPLE_NS` (default 300 ns) dopo la
   salita di PHI2 (dato del 6510 valido al più `t_MDS` = 200 ns dopo la salita,
   fino a 10 ns dopo la discesa) e applica subito gli effetti nella coda di φ2:
   byte GeoRAM, latch `$DFFD`, registri pagina/blocco `$DFFE`/`$DFFF` (il
   puntatore `win` viene ricalcolato solo qui).
7. Alla discesa di PHI2 (φ1, la porta è del VIC-II) rilascia il bus dati,
   de-asserisce `DEV_SEL_N` e inserisce nel ring l'eventuale evento di latch.

I passi 2–5 sono in **assembly inline**: tutti gli operandi in registro, costanti
caricate prima dell'attesa. Dal disassemblato, dopo che `/IOx` è visto basso:
**5 istruzioni + 1 lettura APB** fino a `DEV_SEL_N`, **~10 istruzioni + 1 lettura e
2 scritture APB** fino al byte GeoRAM sul bus. Il campione di `/IOx` arriva ogni
5 istruzioni. I dati del loop (`bus_io2`, `georam_256k`, `log_ring`, stato della
scheda) sono in DRAM, il codice in IRAM.

Non serve la previsione del fronte di discesa usata su RBL-XE: gli effetti delle
scritture durano poche decine di cicli e dopo la discesa di PHI2 resta tutto φ1
(~490 ns) prima del ciclo successivo.

`IO_QUALIFY_NS` e `BUS_WR_SAMPLE_NS` si regolano con `-D` dopo aver misurato il
bus reale.

La tabella di decodifica non dipende da ESP-IDF ed è verificata sul PC contro
una versione a confronti di range, per tutti gli offset e gli stati del latch:

```bash
cd test/host
cc -O2 -Wall -I../../include test_bus_decode.c -o test_bus_decode && ./test_bus_decode
```

### Dedicated GPIO (modulo ESP32-S3)

Il modulo Dedicated GPIO dell'ESP32-S3 assegna fino a 8 canali in ingresso e
8 in uscita per core. L'accesso avviene tramite le istruzioni Xtensa TIE:

| Istruzione TIE              | Helper C (IDF ≤ 5.0)                             | Latenza |
|-----------------------------|--------------------------------------------------|---------|
| `ee.get_gpio_in`            | `cpu_ll_read_dedic_gpio_in()`                    | 1 ciclo |
| `ee.wr_mask_gpio_out`       | `cpu_ll_write_dedic_gpio_mask(mask, val)`        | 1 ciclo |

I canali configurati nel firmware:

| Bundle  | Canale | GPIO           | Segnale     | Nota                  |
|---------|--------|----------------|-------------|-----------------------|
| Input   | bit 0  | GPIO 1 (pin 6) | PHI2        | Clock 6510            |
| Input   | bit 1  | GPIO 2 (pin 7) | R/W         |                       |
| Input   | bit 2  | GPIO 41 (pin 47)| /IO1       | Accesso CPU $DExx     |
| Input   | bit 3  | GPIO 42 (pin 48)| /IO2       | Accesso CPU $DFxx     |
| Output  | bit 0  | GPIO 40 (pin 45)| DEV\_SEL\_N | Chip-select VERA      |

I pin GPIO 39–42 erano originariamente riservati a JTAG; vengono liberati in
`setup()` tramite `gpio_reset_pin()` prima della creazione del bundle.

### Mappatura del bus (riepilogo)

| Segnale      | GPIO        | QFN-56 pin | Note                              |
|--------------|-------------|------------|-----------------------------------|
| PHI2         | 1           | 6          | Input dedicated                   |
| R/W          | 2           | 7          | Input dedicated                   |
| D0–D7        | 4–11        | 9–16       | Bus dati bidirezionale            |
| A0–A7        | 12–19       | 17–25      | Offset nella pagina I/O; GPIO 19=USB D− (USB disabilitato) |
| A8–A15       | 20–21, 33–36, 45–46 | 26–27, 38–41, 51–52 | Cablati, non usati dalla decodifica (A14/A15 = strapping) |
| ARESET       | 37          | 42         | `/RESET` del C64 (output, open-drain `U27`, pull-down R70) |
| BOOT0        | 0           | 5          | Pulsante BOOT / auto-reset (non usato dal firmware) |
| CRESET       | 38          | 43         | Chip reset VERA (output)          |
| CDONE        | 39          | 44         | VERA programmata (input)          |
| —            | 3           | 8          | Non usato; strapping (JTAG source), pull-up R71 10 kΩ |
| DEV\_SEL\_N  | 40          | 45         | Chip-select VERA (output, dedicated) |
| /IO1         | 41          | 47         | Input dedicated (su RBL-XE: `EXTSEL_N`) |
| /IO2         | 42          | 48         | Input dedicated (su RBL-XE: `MPD`) |
| ABUS\_OE\_N  | 47          | 37         | `~OE` di U3/U4 (output): alto durante il reset (pull-up R7/R34) per gli strapping di GPIO 45/46, basso da `setup()` |
| Debug TX     | 43          | 49         | UART0 TX (Serial)                 |
| Debug RX     | 44          | 50         | UART0 RX (Serial)                 |

Fino a quando `setup()` porta basso `PIN_ABUS_OE_N`, U3 e U4 sono spenti: GPIO 45/46
(A14/A15) leggono LOW dai pull-down interni a ogni reset del chip, quindi VDD\_SPI = 3,3 V
e il download boot funziona anche con il C64 acceso (`VERA-C64-HW-REQUIREMENTS.md` §2.9).

Per la mappatura completa GPIO→QFN-56, i level shifter e le modifiche rispetto alla
versione Atari vedere `PIN-MAPPING.md` nella root.

---

## 3. Struttura dei File

```
firmware/MCU/
├── platformio.ini               # Ambiente: esp32s3fn8 (C64)
├── include/
│   ├── bus_decode.h             # Tabelle di decodifica di IO2, senza dipendenze IDF
│   └── soc/                     # (vuota, segnaposto)
├── src/
│   └── main.cpp                 # Sorgente principale del firmware ESP32
└── test/host/
    └── test_bus_decode.c        # Test di equivalenza della decodifica (gcc sul PC)
```

---

## 4. Mappa I/O Commodore 64

Ambiente PlatformIO unico: `esp32s3fn8`. Opzioni di compilazione (`-D`):

| Macro | Default | Effetto |
|---|---|---|
| `CARD_SEL_LATCH` | `0xFD` | offset in `IO2` del latch di selezione VERA (`$DFFD`) |
| `IO_QUALIFY_NS` | 200 | attesa massima di `/IO1`/`/IO2` dopo il fronte di salita di PHI2 |
| `BUS_WR_SAMPLE_NS` | 300 | ritardo dalla salita di PHI2 al campionamento del dato in scrittura |
| `VERA_TRACE_REGS` | 0 | log di ogni accesso ai registri VERA. **Solo debug**: in lettura campiona il bus fino alla discesa di PHI2; con un evento per accesso il ring si riempie in fretta e gli eventi in eccesso vengono scartati |
| `VERA_POST_CDONE_DELAY_US` | 1000 | attesa tra `CDONE` e il rilascio del reset del C64 |

La scheda si collega alla porta di espansione del C64 e occupa le due aree I/O
`IO1` ($DE00–$DEFF) e `IO2` ($DF00–$DFFF), che sul C64 non hanno memoria interna:
non serve disabilitare nulla sulla scheda madre, basta pilotare il bus dati.

| Indirizzo | Accesso | Funzione | Chi risponde |
|---|---|---|---|
| `$DE00–$DEFF` | R/W | Finestra GeoRAM (pagina da 256 byte) | ESP32 → `georam_256k[]` |
| `$DF00–$DF1F` | R/W | Registri VERA | FPGA, `DEV_SEL_N` asserito |
| `$DFFD` | W | **Latch selezione VERA**: valore ≠ 0 seleziona, `0` deseleziona | snoop ESP32 |
| `$DFFE` | W | GeoRAM registro pagina (0–63) | snoop ESP32 |
| `$DFFF` | W | GeoRAM registro blocco (0–15) | snoop ESP32 |

La VERA risponde **solo se selezionata** tramite `$DFFD`. La GeoRAM (finestra e
registri `$DFFE`/`$DFFF`) è **sempre attiva**. Il latch è sempre attivo.

```
LDA #$04 : STA $DFFF   ; GeoRAM blocco 4 (sempre attiva)
LDA #$23 : STA $DFFE   ; GeoRAM pagina 35
LDA $DE45              ; byte GeoRAM $12345
LDA #$01 : STA $DFFD   ; seleziona la VERA a $DF00-$DF1F
LDA #$00 : STA $DFFD   ; deseleziona la VERA
```

### GeoRAM 256 KB

`offset = blocco × 16384 + pagina × 256 + (addr & $FF)`: 16 blocchi da 16 KB,
ognuno di 64 pagine da 256 byte. I registri sono a sola scrittura (in lettura la
scheda non pilota il bus), si azzerano all'accensione e sopravvivono al reset del
C64 come nell'hardware originale. Sono decodificati esattamente a `$DFFE`/`$DFFF`,
senza i mirror `$DF80–$DFFD` di alcune GeoRAM: per questo il latch a `$DFFD` non
va in conflitto.

`georam_256k[256 KB]` è `.bss` ordinaria in DRAM (zero Flash). Non può stare in
IRAM: il loop vi accede a byte, e una sezione fuori dal layout IRAM di ESP-IDF
(la versione precedente usava `.iram0.bss`) non viene riservata sul bus dati e si
sovrapporrebbe a `.data`, `.bss` e heap. Il loop tiene in un registro il puntatore
`win` alla pagina visibile a `$DE00`; i registri pagina/blocco e il latch stanno
nella struttura `card` in DRAM.

### Segnali di uscita

| Segnale | Uso sul C64 |
|---|---|
| `DEV_SEL_N` | chip select VERA per `$DF00–$DF1F` |
| `ARESET` | `/RESET` del C64, attraverso il buffer open-drain `U27` |
| `ABUS_OE_N` | abilitazione dei traslatori indirizzi `U3`/`U4` (strapping) |

### Limiti noti

- **Mai provato su hardware.** Il firmware compila ed è verificato solo dal test
  host della tabella di decodifica.
- **`IO_QUALIFY_NS` e `BUS_WR_SAMPLE_NS` da tarare.** Il ritardo di
  `/IO1`/`/IO2` rispetto a PHI2 (PLA + 74LS139, qualche decina di ns) e l'istante
  di campionamento delle scritture vanno misurati all'oscilloscopio. Se la finestra
  di `/IOx` è troppo corta la scheda perde cicli; la latenza di un accesso APB ai
  registri GPIO non è mai stata misurata (sull'Atari è il limite; sul C64, con
  ~490 ns di φ2, il margine è molto più ampio).
- **PCB ancora Atari.** Schema e netlist sono adattati alla porta di espansione
  (`PIN-MAPPING.md` § 9), il PCB va rifatto.

## 5. Compilazione e Flashing

È necessario avere **PlatformIO Core** installato (`pip install platformio`).

> ⚠ **Programmazione e USB solo a scheda scollegata dal C64.** La rete 5 V della scheda è unita al +5 V del C64 (`CART1` pin 2 e 3) senza diodo: con il cavo USB (`J4`) o il jack (`J5`) collegati mentre la scheda è inserita, la scheda alimenterebbe il C64 (spento) o lavorerebbe in parallelo al suo alimentatore (acceso). Vale anche per il monitor seriale: con la scheda nel C64 usare un adattatore senza VBUS. (`VERA-C64-HW-REQUIREMENTS.md` §2.11)

```bash
# Compila
pio run -e esp32s3fn8

# Carica il firmware — UART0: GPIO43=TX, GPIO44=RX
pio run -e esp32s3fn8 --target upload

# Monitor seriale (115200 baud)
pio device monitor
```

> **Nota:** USB CDC è disabilitato (`ARDUINO_USB_CDC_ON_BOOT=0`) perché
> GPIO 19 (USB D−) e GPIO 20 (USB D+) sono riutilizzati come linee indirizzo
> A7 e A8. Usare un adattatore UART esterno collegato ai pin GPIO 43/44.
