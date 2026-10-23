# Vera-Module-RBL-C64 — Firmware MCU

## 1. Introduzione

Firmware per il microcontrollore **ESP32-S3FN8** (QFN-56, 8 MB flash integrata,
dual-core Xtensa LX7 @ 240 MHz) montato sul modulo Vera-Module-RBL-XE.

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

---

## 2. Architettura del Firmware

### Sequenza di startup (prima del hot loop)

`setup()` abbassa **ARESET** e **CRESET** immediatamente dopo il reclaim dei pin
JTAG — prima ancora di `Serial.begin` — garantendo che C64 e FPGA VERA rimangano
in reset per tutta la durata dell'inizializzazione ESP32.

`setup()` (Core 1) crea `MonitorTask` sul **Core 0** con priorità massima, dopo
aver tolto l'idle task del Core 0 dal task watchdog (`disableCore0WDT()`): il hot
loop non cede mai la CPU. Prima di entrare nel hot loop il task esegue la
sequenza di sincronizzazione:

1. **CRESET → HIGH** (`GPIO.out1_w1ts`): la FPGA VERA esce dal reset e inizia il
   caricamento del bitstream dalla flash SPI on-board.
2. **Poll CDONE** (GPIO 39): attesa con `vTaskDelay(1)` finché il pin va HIGH —
   ICE40UP5K tipicamente < 100 ms. Timeout 5 s con log di errore.
3. **Attesa `VERA_POST_CDONE_DELAY_US`** (default 1000 µs): copre il power-on reset
   interno della VERA, che parte solo dopo `CDONE`.
4. **ARESET → HIGH** (`GPIO.out1_w1ts`): il C64 esce dal reset. Da questo momento
   il bus è live e il hot loop deve rispondere ad ogni ciclo PHI2.

### Divisione dei core

| Core | Cosa gira | Interrupt |
|------|-----------|-----------|
| **0** | solo `MonitorTask` (hot loop del bus, priorità `configMAX_PRIORITIES - 1`, non cede mai la CPU) | tick FreeRTOS |
| **1** | `setup()`, `loop()`: svuota `log_ring` e stampa su `Serial` | tick, UART0 |

Il hot loop passa gli eventi (cambio del latch `$DFFD`, registri VERA con
`-DVERA_TRACE_REGS=1`) a `loop()` tramite `log_ring`, un ring buffer
single-producer/single-consumer senza lock: l'inserimento costa poche istruzioni
(timestamp = tick FreeRTOS in ms). `xQueueSend()` + `esp_timer_get_time()`
costavano circa 1 µs nel loop del bus; inoltre il loop girava sul Core 1, lo
stesso di `loop()`, che quindi non riusciva mai a stampare. Se il ring è pieno
l'evento viene scartato e `loop()` stampa quanti ne sono stati persi.

### Hot loop (Core 0, priorità massima FreeRTOS)

Ad ogni ciclo di clock del 6510 (PHI2 @ 0,985 MHz PAL / 1,023 MHz NTSC, finestra
utile con PHI2 alto ≈ 490 ns, circa 117 cicli CPU a 240 MHz):

1. Attende il fronte di salita di PHI2 tramite **Dedicated GPIO in**
   (`ee.get_gpio_in`, 1 ciclo CPU anziché ~6 cicli via APB).
2. Attende, per al massimo `IO_QUALIFY_NS` (default 200 ns), che `/IO1` o
   `/IO2` vada basso (sempre via Dedicated GPIO). Se non succede, il ciclo non è
   della scheda (altro indirizzo o fetch VIC-II): salta all'attesa del fronte di
   discesa senza toccare nulla.
3. Legge A0–A7 e R/W da `GPIO.in` (una lettura APB): ora `AEC` è alto e
   l'indirizzo sulla porta è quello del 6510. La pagina `$DE`/`$DF` è data da
   quale delle due linee `/IOx` è attiva (`decode_addr_lo()`).
4. **`/IO1` (GeoRAM):** in lettura guida D0–D7 con `bus_drive(win[off8])`, dove
   `win` punta alla pagina GeoRAM corrente; il puntatore è tenuto in un registro e
   ricalcolato solo quando si scrive `$DFFE`/`$DFFF`.
5. **`/IO2`:** per `$DF00–$DF1F` con la VERA selezionata asserisce `DEV_SEL_N`
   (**Dedicated GPIO out**, `ee.wr_mask_gpio_out`): risponde la FPGA.
6. **Scritture:** il dato del 6510 è valido fino a ~200 ns dopo la salita di
   PHI2. Il loop rilegge `GPIO.in` finché PHI2 è alto (PHI2 è nello stesso
   registro) e usa l'ultimo campione; poi, durante PHI1, aggiorna GeoRAM, latch e
   registri pagina/blocco.
7. Al fronte di discesa di PHI2 rilascia il bus e de-asserisce `DEV_SEL_N`.

Percorso critico, dal disassemblato della ELF, a partire dalla lettura di
`GPIO.in`: **~9 istruzioni** fino a `DEV_SEL_N` (prima ~23) e **~18** fino al dato
GeoRAM sul bus (prima ~40). I dati del loop (`lut_drive`, registri GeoRAM,
`log_ring`) sono in DRAM, il codice in IRAM.

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
| Input   | bit 1  | GPIO 41 (pin 47)| /IO1       | Accesso CPU $DExx     |
| Input   | bit 2  | GPIO 42 (pin 48)| /IO2       | Accesso CPU $DFxx     |
| Output  | bit 0  | GPIO 40 (pin 45)| DEV\_SEL\_N | Chip-select VERA      |

I pin GPIO 39–42 erano originariamente riservati a JTAG; vengono liberati in
`setup()` tramite `gpio_reset_pin()` prima della creazione del bundle.

### Mappatura del bus (riepilogo)

| Segnale      | GPIO        | QFN-56 pin | Note                              |
|--------------|-------------|------------|-----------------------------------|
| PHI2         | 1           | 6          | Input dedicated                   |
| R/W          | 2           | 7          | Input                             |
| D0–D7        | 4–11        | 9–16       | Bus dati bidirezionale            |
| A0–A7        | 12–19       | 17–25      | Offset nella pagina I/O; GPIO 19=USB D− (USB disabilitato) |
| A8–A15       | 20–21, 35–36, 33–34, 45–46 | 26–27, 40–41, 38–39, 51–52 | Cablati, non usati dalla decodifica (A14/A15 = strapping) |
| /IO1         | 41          | 47         | Input dedicated (ex EXTSEL\_N)    |
| /IO2         | 42          | 48         | Input dedicated                   |
| ARESET       | 37          | 42         | System reset C64 (output)         |
| BOOT0        | 0           | 5          | Pulsante BOOT / auto-reset (non usato dal firmware) |
| CRESET       | 38          | 43         | Chip reset VERA (output)          |
| CDONE        | 39          | 44         | VERA programmata (input)          |
| DEV\_SEL\_N  | 40          | 45         | Chip-select VERA (output, dedicated) |
| Debug TX     | 43          | 49         | UART0 TX (Serial)                 |
| Debug RX     | 44          | 50         | UART0 RX (Serial)                 |

Per la mappatura completa GPIO→QFN-56, i level shifter e le modifiche hardware
rispetto alla versione Atari vedere
`PIN-MAPPING.md` nella root.

---

## 3. Struttura dei File

```
firmware/MCU/
├── platformio.ini               # Ambiente: esp32s3fn8 (C64)
├── include/
│   └── soc/                     # (vuota, segnaposto)
└── src/
    └── main.cpp                 # Sorgente principale del firmware ESP32
```

---

## 4. Mappa I/O Commodore 64

Ambiente PlatformIO unico: `esp32s3fn8`. Opzioni di compilazione (`-D`):

| Macro | Default | Effetto |
|---|---|---|
| `CARD_SEL_LATCH` | `0xFD` | offset in `IO2` del latch di selezione scheda (`$DFFD`) |
| `IO_QUALIFY_NS` | 200 | attesa massima di `/IO1`/`/IO2` dopo il fronte di salita di PHI2 |
| `VERA_TRACE_REGS` | 0 | log di ogni accesso ai registri VERA tramite `log_ring`. **Solo debug**: con un evento per accesso il ring si riempie in fretta e gli eventi in eccesso vengono scartati |
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

La memoria è `georam_256k[256 KB]` in IRAM BSS (zero Flash), sempre presente:
la GeoRAM è interamente software e si attiva con il latch. I registri pagina e
blocco sono tenuti dal hot loop in registri, insieme al puntatore `win` alla
pagina visibile a `$DE00`; le copie globali `georam_page`/`georam_block` (DRAM)
servono solo per ispezione.

### Segnali di uscita

| Segnale | Uso sul C64 |
|---|---|
| `DEV_SEL_N` | chip select VERA per `$DF00–$DF1F` |
| `ARESET` | `/RESET` del C64 |

### Limiti noti

- **`IO_QUALIFY_NS` da tarare.** Il ritardo di `/IO1`/`/IO2` rispetto a PHI2
  (PLA + 74LS139, qualche decina di ns) va misurato all'oscilloscopio. Se la
  finestra è troppo corta la scheda perde cicli; se è troppo lunga resta meno tempo
  per pilotare il bus nelle letture GeoRAM.
- L'hardware è ancora quello della versione Atari. In particolare GPIO 41
  (ex `EXTSEL_N`) e GPIO 42 (ex `MPD`) vanno ricablati su `/IO1` e `/IO2`: vedere `PIN-MAPPING.md` § 9.

## 5. Compilazione e Flashing

È necessario avere **PlatformIO Core** installato (`pip install platformio`).

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
