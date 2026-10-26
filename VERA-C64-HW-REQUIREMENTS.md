# VERA RBL-C64 — Requisiti e verifiche hardware

Documento derivato da `VERA-ATARI-HW-REQUIREMENTS.md` di VERA Module RBL-XE. La scheda C64 usa lo schema di RBL-XE della revisione del 2026-10-26, con il foglio
del connettore riadattato alla porta di espansione del Commodore 64 (`PIN-MAPPING.md` § 9). Qui
sono riportati i requisiti che valgono anche per il C64, con i riferimenti alla netlist C64, e quelli
propri del C64.
Data: 2026-10-26.

## 0. Fonti e limiti

| Fonte | Cosa ho usato |
|---|---|
| HDL VERA 48.0.1 (`top.v`, da `VERA_ATARI_PBI/fpga-vera/`) | protocollo del bus, reset, IRQ, mappa registri |
| VERA Module RBL-XE, `VERA-ATARI-HW-REQUIREMENTS.md` (2026-10-26) | verifiche sulla parte di scheda in comune |
| Questo repo: `PIN-MAPPING.md`, `firmware/MCU/README.md`, schemi e netlist `VERA-MODULE-RBL.net` (2026-10-26) | stato della scheda C64 |

**Limiti.** I punti della sezione 2 sono ricavati dagli schemi e dalla netlist: nessuna simulazione
elettrica e nessuna misura. Nessuna scheda è stata costruita e **il PCB è ancora quello Atari**. Non
esiste ancora un driver C64 provato: le regole software della sezione 5 vengono dall'HDL e dal lavoro
sulla versione Atari. Ogni punto marcato **VERIFICA** va controllato sui datasheet e con l'oscilloscopio.

---

## 1. Cosa fa la VERA sul bus (dall'HDL 48.0.1)

Questi sono i vincoli che l'hardware deve rispettare, indipendentemente dal computer.

| Aspetto | Comportamento reale (`top.v`) | Conseguenza per la scheda |
|---|---|---|
| Strobe | `bus_read = !cs_n && wr_n && !rd_n`, `bus_write = !cs_n && !wr_n` | servono RD_n e WR_n **distinti**; `rd_n` è ignorato se `wr_n` è basso |
| Scrittura | l'indirizzo è campionato sul fronte di **salita** di `bus_write` (inizio); il **dato** sul fronte di **discesa** (`negedge bus_write`, cioè fine scrittura) | il dato deve restare stabile fino **dopo** la salita di WR_n / CS_n (hold) |
| Lettura | `extbus_d` pilotato solo mentre `bus_read`; effetti collaterali (autoincremento, prefetch) sul fronte di discesa di `bus_read`, dopo 3 cicli di `clk25` (~120 ns) | un'attivazione di RD_n = un evento di lettura. Cicli doppi (RMW, dummy read) li duplicano |
| Reset | solo POR interno (`por_cnt_r`, 128 cicli di `clk25`); **nessun pin di reset** | il RESET del C64 non resetta la VERA |
| CTRL bit 7 (`$DF05`) | `fpga_reconfigure` → ricarica l'intero bitstream: VRAM persa, bus morto ~100 ms | scrittura distruttiva; vedi §3 |
| IRQ | `extbus_irq_n = (irq_status & irq_enable) == 0`: **push-pull**, a livello | non può pilotare direttamente la linea `/IRQ` condivisa |
| Registri FX | in sola scrittura (la lettura di `$DF09-$DF0C` con DCSEL≥2 restituisce i byte di identità del firmware, `'V',48,0,1` sulla 48.0.1, tranne FX_CTRL e POLY_FILL_L/H) | niente read-back di FX |

---

## 2. Verifiche e modifiche sulla scheda

Priorità: **A** = da risolvere prima del primo test sul bus, **B** = da risolvere prima del
rilascio, **C** = da decidere.

### 2.1 [A] Il bus dati non deve fare contesa sulle letture non destinate alla scheda — **nello schema**

`U19` (74LVC4245, bus dati) ha `DIR` = `NOT(R/W)` (`U23` pin 1→2) e `~OE_` (pin 22) dal gating di
`U24`/`U25` (due SN74LVC00A), ereditato da RBL-XE. `U19` deve essere acceso solo quando la scheda
risponde in lettura oppure in scrittura (C64→scheda, dove pilota solo il lato scheda); in ogni altra
lettura (RAM, ROM, I/O della scheda madre, altre cartucce) deve restare spento.

Sul C64 la scheda risponde in lettura in due casi: registri VERA (`DEV_SEL_N` asserito dall'ESP32)
e finestra GeoRAM (`/IO1`, asserito dal PLA del C64). Quindi:

```
~OE_ = NOT( PHI2 AND ( NOT R/W   OR   ~DEV_SEL_N OR ~/IO1 ) )
```

Stessa rete di RBL-XE, con l'ingresso `~mEXSEL` sostituito da `~mIO1` e `~mMPD` fisso a 3V3:

```
n1  = NAND(mR~W,  ~mVCS0)        U24 pin 1, 2  → 3
n2  = NAND(~mIO1, 3V3)           U24 pin 4, 5  → 6     (= NOT ~mIO1)
a1  = NAND(n1, n1)               U24 pin 9, 10 → 8     (= AND)
a2  = NAND(n2, n2)               U24 pin 12, 13 → 11   (= AND)
B   = NAND(a1, a2)               U25 pin 1, 2  → 3     (1 se scrittura o la scheda risponde)
~OE = NAND(mPHI2, B)             U25 pin 4, 5  → 6     → U19 pin 22
```

| Pin | U24 | U25 |
|---|---|---|
| 1 | `mR~W` (U6.18 / U7.7 / U5) | a1 (U24.8) |
| 2 | `~mVCS0` (U7.45 / U2.28, pull-up `R36`) | a2 (U24.11) |
| 3 | n1 → U24.9, U24.10 | B → U25.5 |
| 4 | `~mIO1` (U6.21 / U7.47, pull-up `R53`) | `mPHI2` (U6.17 / U7.6 / U5) |
| 5 | 3V3 | B (U25.3) |
| 6 | n2 → U24.12, U24.13 | **`~OE` → U19 pin 22** |
| 7 | GND | GND |
| 8 | a1 → U25.1 | libero |
| 9, 10 | n1 | GND (porta libera) |
| 11 | a2 → U25.2 | libero |
| 12, 13 | n2 | GND (porta libera) |
| 14 | 3V3, 100 nF `C67` | 3V3, 100 nF `C68` |

| mPHI2 | mR~W | ~mVCS0 / ~mIO1 | B | ~OE | U19 |
|---|---|---|---|---|---|
| 0 | x | x | x | 1 | spento (φ1, la porta è del VIC-II) |
| 1 | 0 (scrittura) | x | 1 | 0 | acceso, C64 → scheda |
| 1 | 1 (lettura) | entrambi a 1 | 0 | 1 | spento: niente contesa |
| 1 | 1 (lettura) | almeno uno a 0 | 1 | 0 | acceso, scheda → C64 |

Note:
- `~mIO1` arriva da `U6` già a 3,3 V: `/IO1` è un'uscita del 74LS139 del C64 e vale solo per accessi
  CPU, quindi `U19` non si accende mai durante i fetch del VIC-II.
- I cicli in cui il VIC-II tiene il bus con PHI2 alto (badline, sprite: `AEC` basso) hanno R/W alto e
  nessun `/IOx`: `U19` resta spento.
- `$DFFD`–`$DFFF` in lettura non abilitano `U19` (nessun segnale di risposta): i registri sono a sola
  scrittura, come nella GeoRAM originale.
- **Tempi — VERIFICA.** `DEV_SEL_N` arriva dall'ESP32 dopo `/IO2` (qualche decina di ns dopo la salita
  di PHI2, più la latenza del loop); `~OE` lo segue di ≤ 18 ns (quattro porte LVC) più l'abilitazione
  del 4245. Con ~490 ns di PHI2 alto e 100 ns di setup del 6510 il margine è ampio, ma va misurato.

### 2.2 [A] Hold del dato sul fronte di salita di WR_n — VERIFICA

- `~mWE` e `~mRE` sono generati da `U5` (74HC00): `~mRE = NAND(PHI2, R/W)`,
  `~mWE = NAND(PHI2, NOT R/W)`.
- La VERA campiona il dato in scrittura alla **salita di WR_n**, cioè circa un ritardo di porta dopo la
  discesa di PHI2. Lo stesso evento spegne `U19` tramite `U25` (una porta LVC): il dato verso la VERA
  può diventare non valido più o meno nello stesso istante in cui WR_n sale. Il 6510 tiene il dato
  almeno `t_HW` = 10 ns dopo la discesa di PHI2.

Richieste (come su RBL-XE): porta più veloce di 74HC00 a 3,3 V per `U5`, oppure rilascio di `U19` più
lento della salita di WR_n; verificare con l'oscilloscopio che il dato resti stabile ≥ 5 ns dopo la
salita di `~mWE` e `~mVCS0` al pin FPGA.

### 2.3 [A] Linea IRQ verso il C64 (open-collector) — **nello schema**

L'uscita VERA è push-pull (§1). La linea `/IRQ` del C64 è un OR cablato condiviso con il CIA 1, il
VIC-II e le altre cartucce, con un solo pull-up sulla scheda madre: ogni device la può solo tirare in
basso.

`U26` SN74LVC1G07DBVR (TI, buffer non invertente open-drain, SOT-23-5, LCSC C7829), alimentato a 3,3 V,
come su RBL-XE:

```
 3V3 ──┬── VCC (pin 5)              C69 100 nF fra 3V3 e GND, vicino al chip
 ~mVIRQ (FPGA U2 pin 32, 3,3 V, attivo basso) ──► A (pin 2)      GND (pin 3), pin 1 NC
 Y (pin 4, open-drain) ──► ~IRQ, CART1 pin 4 (5 V)   [nessun pull-up proprio verso 5 V]
```

- L'uscita open-drain tollera 5,5 V anche a chip spento (Ioff): il pull-up a 5 V del C64 non la
  danneggia. VOL < 0,4 V a qualche mA; la corrente del pull-up del C64 va **verificata** sulla
  scheda madre di prova.
- Non aggiungere un pull-up sulla scheda e non usare un 74LVC4245 per questo segnale.

### 2.4 [A] Gestione dell'IRQ della VERA: via software

Il C64 non ha un meccanismo di identificazione dei device come il PBI Atari: chi usa gli IRQ della VERA
aggancia il vettore IRQ del KERNAL (`CINV`, `$0314/$0315`). Il gestore seleziona la VERA (`$DFFD`, §2.5),
legge `ISR` e `IEN`: se `ISR & IEN` ha bit attivi conferma VSYNC/LINE/SPRCOL scrivendo 1 in `ISR` (e
maschera AFLOW in `IEN`), altrimenti passa il controllo al gestore precedente. Deve ripristinare lo stato
del latch `$DFFD` trovato all'ingresso. Non serve nessun collegamento dell'IRQ all'ESP32.

Stato: **da scrivere**; il gancio per l'Atari (`VERA_ATARI_PBI/vera-tests/vera_irq.s`) è il modello.

### 2.5 [A] Latch `$DFFD`: i registri VERA rispondono solo con la VERA selezionata — **nel firmware**

`$DF00–$DF1F` è un'area usata anche da altre cartucce (per esempio la REU Commodore ha i registri a
`$DF00–$DF0A`). Per poter convivere con loro la VERA risponde solo dopo una scrittura ≠ 0 in `$DFFD`
e smette con una scrittura di `0`; all'accensione è deselezionata. Il latch e i registri GeoRAM
rispondono sempre. Tabella `bus_io2[latch][A0-A7]` in `firmware/MCU/include/bus_decode.h`, verificata
dal test host.

### 2.6 [B] GeoRAM: registri a sola scrittura, decodifica esatta — **nel firmware**

`$DFFE` (pagina, 0–63) e `$DFFF` (blocco, 0–15) sono decodificati esattamente, senza i mirror
`$DF80–$DFFD` di alcune GeoRAM (altrimenti il latch a `$DFFD` andrebbe in conflitto). Si azzerano
all'accensione e sopravvivono al reset del C64. In lettura la scheda non pilota il bus.

### 2.7 [A] VCCB (pin 23) dei 74LVC4245 — **nello schema**

Il pin 23 di `U3`, `U4`, `U6`, `U16` e `U19` è collegato al pin 24 (3V3), come su RBL-XE.

### 2.8 [B] Ingressi liberi — **nello schema**

- `U23` pin 3, 5, 9, 11, 13 a GND (uscite 4, 6, 8, 10, 12 libere).
- Canali di riserva dei 74LVC4245, ciascuno con una propria 0 Ω (CREZ0805, LCSC C328378) verso GND:
  `U6` pin 10 → `R74`; `U16` pin 14 → `R72`, 15 → `R75`, 16 → `R80`, 17 → `R79`, 18 → `R78`, 19 → `R73`,
  20 → `R76`, 21 → `R77`. `R78`/`R79` sono nuove: `U16` pin 18 e 17 erano `~mEXSEL`/`~mMPD`, che sul
  C64 non hanno una linea; `R80` è nuova perché il reset passa ora da `U27` (§2.12). Le uscite corrispondenti (`U6` pin 14, `U16` pin 3, 4, 5, 6, 7, 9, 10) restano
  libere (anche il pin 8, ex reset).
- I canali di `U6` che su RBL-XE portavano `S4`, `S5`, `REFRESH` ora portano `BA`, `/DMA`, `/RESET`
  ai test point `TP3`, `TP2`, `TP4`: ingressi sempre pilotati dal C64.

### 2.9 [A] Strapping dell'ESP32-S3 — **nello schema e nel firmware**

L'ESP32-S3 campiona GPIO 0, 3, 45 e 46 a ogni reset del chip; i livelli devono essere validi alla
salita di CHIP_PU e per 3 ms dopo (datasheet v2.2, §3).

| Pin | Funzione | Problema | Correzione |
|---|---|---|---|
| GPIO 3 (pin 8) | sorgente JTAG | senza pull interne (il datasheet vieta l'alta impedenza) | `R71` 10 kΩ → 3V3 |
| GPIO 0 (pin 5) | modo di boot | CHIP_PU e BOOT0 avevano la stessa costante di tempo | `C25` → 1 µF (4,7 ms contro 0,47 ms) |
| GPIO 45 (pin 51) | VDD_SPI | è A14 attraverso `U3`. Le linee indirizzo della porta sono sempre pilotate (dal 6510, anche in reset; in φ1 dal VIC-II e dai pull-up della scheda madre): A14 alto → VDD_SPI 1,8 V e la flash della FN8 non parte | `~OE` di `U3` sulla rete `~ABUS_OE` |
| GPIO 46 (pin 52) | messaggi ROM / download | è A15: A15 alto con GPIO 0 basso è una combinazione non valida → programmazione fallita a caso con il C64 acceso | come GPIO 45 |

**Rete `~ABUS_OE`.** `~OE` (pin 22) di `U3` (A8–A15) e `U4` (A0–A7) è pilotato da **GPIO 47** (pin 37),
con pull-up `R7` e `R34` (10 kΩ → 3V3). Durante il reset dell'ESP32 le pull-up spengono `U3`/`U4` e i
pull-down interni danno GPIO 45 = GPIO 46 = LOW a ogni reset, qualunque cosa faccia il C64. Il firmware
(`PIN_ABUS_OE_N` in `main.cpp`) porta GPIO 47 basso in `setup()`, molto dopo i 3 ms di hold e prima di
avviare il loop del bus. Spegnere anche `U4` evita la contesa con i glitch di uscita di GPIO 12–19
all'accensione.

Resta aperto, come su RBL-XE: anche GPIO 1, 2 (PHI2, R/W da `U6`), GPIO 41, 42 (`/IO1`, `/IO2` da `U6`)
e GPIO 4–11 (dati) hanno glitch di uscita all'accensione; `U6` resta sempre abilitato.

### 2.10 [—] `~HALT`, `RD4`, `RD5` — **non applicabile**

Su RBL-XE `U16` portava questi segnali Atari. Sul C64 non esistono: i test point `RD4` è stato tolto,
`RD5` e `~HALT1` sono stati riusati (`TP6` = `~mIO2`, `TP5` = `AUDIO`).

### 2.11 [A] Il 5 V della scheda è collegato al 5 V del C64 senza diodo — **regola d'uso**

La rete `5V` della scheda unisce `CART1` pin 2 e 3 (+5 V del C64, collegato direttamente), `U18`
(MAX40200) da VBUS dell'USB (`J4`) e `U17` (MAX40200) dal 7805 `U15` alimentato dal jack `J5`. I due
MAX40200 proteggono USB e 7805, ma niente impedisce alla scheda di alimentare il C64.

Decisione (come su RBL-XE): nessun diodo sul ramo del computer. **Programmazione e USB solo a scheda
scollegata dal C64.** Vale anche per il monitor seriale: con la scheda nel C64 usare un adattatore senza
VBUS. Il jack e l'USB servono per programmare l'ESP32 e la flash della VERA e per le prove a banco.

Il 5 V della porta di espansione arriva dal regolatore del C64, con una corrente disponibile limitata:
**VERIFICA** del consumo della scheda (FPGA, ESP32, traslatori) prima dell'uso con l'alimentatore
originale.

### 2.12 [A] `/RESET` del C64 open-drain — **nello schema**

Sul C64 `/RESET` è una linea condivisa (circuito di reset della scheda madre, porta utente, bus seriale,
cartucce con pulsante di reset) con il pull-up sulla scheda madre: ogni device la può solo tirare in
basso. Su RBL-XE `ARESET` passava da `U16` (pin 16 → 8) in push-pull: una cartuccia o un pulsante che
tirano in basso mentre `U16` tiene la linea alta creano contesa.

**Realizzazione:** `U27` SN74LVC1G07DBVR, identico a `U26` (§2.3), alimentato a 3,3 V:

```
 3V3 ──┬── VCC (pin 5)              C70 100 nF fra 3V3 e GND, vicino al chip
 ~C64_RESET (GPIO 37, R70 10 kΩ verso GND) ──► A (pin 2)      GND (pin 3), pin 1 NC
 Y (pin 4, open-drain) ──► ~RST, CART1 pin C (5 V)   [nessun pull-up proprio]
```

- Buffer non invertente: GPIO 37 basso → `/RESET` basso; GPIO 37 alto → alta impedenza, la linea
  torna alta per il pull-up del C64 (o resta bassa se un altro device la tiene).
- Durante il reset e il boot dell'ESP32 GPIO 37 è un ingresso: `R70` tiene `~C64_RESET` basso, quindi
  il C64 resta in reset fino a quando il firmware lo rilascia (§3). Con l'ESP32 non alimentato `U27`
  è spento e la sua uscita, tollerante a 5,5 V (Ioff), non carica la linea.
- `U16` pin 16 va a GND con `R80` (0 Ω) e il pin 8 resta libero; il canale 6 di `U6` continua a
  riportare `/RESET` al test point `TP4`, così si può misurare (e in futuro leggere) anche il reset dato
  dal C64 o da un'altra cartuccia.
- Firmware invariato: `PIN_ARESET` resta GPIO 37, attivo basso.

### 2.13 [A] PCB — DA FARE

Il PCB è ancora quello Atari. Vanno rifatti il contorno (la scheda è una cartuccia che si inserisce
nella porta di espansione), la posizione del connettore a pettine `C64-EXPANSION-CARTRIDGE` e lo
sbroglio dei collegamenti nuovi, partendo da "Update PCB from netlist". Verificare sul footprint la
lunghezza dei contatti e lo spessore della scheda (1,6 mm) con una cartuccia reale.

---

## 3. Reset e configurazione FPGA

| # | Requisito | Stato nel firmware attuale |
|---|---|---|
| 1 | Tenere il C64 in reset (`ARESET` basso) fino a CONFIG_DONE della VERA | **già così**: `ARESET`, `CRESET` bassi in `setup()`; `CRESET` alto, attesa `CDONE`, poi `ARESET` alto da `MonitorTask` |
| 2 | Il blocco vale **solo al power-on** | la sequenza è eseguita una volta: **non** deve essere rieseguita se `CDONE` scende dopo una riconfigurazione (CTRL bit 7) |
| 3 | Ritardo dopo `CDONE` prima di rilasciare `ARESET` (~1 ms) | **fatto**: `VERA_POST_CDONE_DELAY_US`, default 1000 µs |
| 4 | `ARESET` open-drain | **nello schema**: `U27` SN74LVC1G07, §2.12 |
| 5 | Timeout se `CDONE` non arriva (oggi 5 s, solo log) | decidere: oggi il C64 viene rilasciato comunque |
| 6 | Scrittura di `$80` in CTRL (`$DF05`) | il software non deve mai scriverlo (§5); il firmware non lo filtra, per gli stessi motivi di RBL-XE |

---

## 4. Livelli, alimentazioni e temporizzazioni

- **Livelli.** VERA, ESP32 e FPGA sono a 3,3 V; il bus del C64 è a 5 V TTL. Tutti i segnali verso
  il C64 passano da 74LVC4245 o dagli open-drain `U26` (IRQ) e `U27` (`/RESET`).
- **Alimentazioni.** In tutti e cinque i 74LVC4245 `VCCA` (pin 1) è a 5 V (lato A = C64) e `VCCB`
  (pin 23, 24) a 3,3 V (lato B = ESP32/FPGA); `DIR` e `~OE` sono riferiti a VCCA con soglia TTL.
  `PIN-MAPPING.md` è stato corretto: prima descriveva i due lati invertiti.
- **Tempo di risposta in lettura.** PHI2 alto dura ~490 ns e il 6510 vuole il dato 100 ns prima della
  discesa. L'indirizzo della CPU è valido solo con `AEC` alto: `/IOx` arriva qualche decina di ns dopo
  la salita di PHI2, poi il firmware asserisce `DEV_SEL_N` o pilota il byte GeoRAM in poche decine di
  cicli CPU (`firmware/MCU/README.md`). Da misurare, ma il margine è molto più ampio dei ~229 ns
  disponibili sull'Atari.
- **Frequenza di quadro.** La VERA gira a 59,94 Hz fisso, asincrona rispetto al raster del VIC-II.

---

## 5. Regole software da rispettare con l'hardware reale

1. Selezionare la VERA scrivendo un valore ≠ 0 in `$DFFD` prima di accedere a `$DF00–$DF1F`; con altre
   cartucce in `IO2` (per esempio una REU) deselezionarla scrivendo `0` prima di usarle.
2. **Mai** `inc`, `dec`, `asl`, `lsr`, `rol`, `ror` su `$DF00-$DF1F`: le istruzioni RMW fanno due
   accessi e duplicano l'evento (autoincremento due volte su `DATA0/DATA1`).
3. **Mai** indirizzamento indicizzato con base nella pagina `$DF` che possa produrre una dummy read su
   `DATA0/DATA1`.
4. Non scrivere `$80` in `$DF05` (riconfigurazione dell'FPGA).
5. Non leggere i registri FX: sono in sola scrittura.
6. Niente sincronismo supposto con il raster del VIC-II.
7. Gli IRQ della VERA si gestiscono agganciando `CINV` (`$0314`), §2.4.
8. Dopo il reset del C64 la VERA mantiene tutto lo stato, e anche la GeoRAM.

---

## 6. Piano di bring-up consigliato

1. **Senza C64**: alimentare la scheda, verificare `CDONE`, la sequenza `CRESET`→`ARESET` (tempi), il
   livello di `ABUS_OE_N` durante il reset dell'ESP32 e la programmazione con GPIO 0.
2. **Con il C64**, latch a 0: verificare che il C64 parta normalmente con `ARESET` rilasciato dalla
   scheda e che non ci sia contesa nelle letture di RAM/ROM (§2.1, oscilloscopio su `U19` pin 22).
3. **Tempi**: misurare il ritardo di `/IO1`/`/IO2` dalla salita di PHI2 e regolare `IO_QUALIFY_NS` e
   `BUS_WR_SAMPLE_NS`; margine di hold sulle scritture VERA (§2.2).
4. **GeoRAM** da BASIC: `POKE 57343,4 : POKE 57342,35 : POKE 56901,170 : PRINT PEEK(56901)` (blocco 4,
   pagina 35, byte `$DE45`), poi cambiare pagina e controllare che il valore non compaia altrove.
5. **VERA** da BASIC: `POKE 57341,1` (seleziona), `POKE 57093,126` (CTRL = `$7E`, DCSEL = 63),
   `PRINT PEEK(57097), PEEK(57098)` → atteso `86 48` (`'V'`, 48).
6. **IRQ** dopo aver scritto il gancio di §2.4.

---

## 7. Punti aperti da decidere

- Architettura: `firmware/FPGA` descrive una variante con GeoRAM su SRAM esterna e registri nell'FPGA
  di interfaccia (`C6502_Interface.vhd`); lo schema attuale serve la GeoRAM dall'ESP32. Va stabilita
  quale è quella di riferimento.
- `addressdecoder.sch` (74LVC138, decodifica `$D1xx`/`$D6xx`/`$D8xx` Atari) è fuori dalla gerarchia:
  non serve al C64.
- PCB (§2.13).
