# VERA RBL-XE — Requisiti e verifiche hardware (dal lavoro su driver ed emulatore)

Documento di passaggio dal progetto software (`VERA_ATARI_PBI`: handler PBI, driver
`VERA.SYS`, test, emulatore `atari800`) al progetto della scheda reale.
Data: 2026-10-06.

## 0. Fonti e limiti

| Fonte | Cosa ho usato |
|---|---|
| HDL VERA 47.0.2 (`VERA_ATARI_PBI/fpga-vera/47.0.2/.../fpga/source/top.v`) | protocollo del bus, reset, IRQ, mappa registri |
| `VERA_ATARI_PBI` (`vera_pbi_handler.s`, `vera_common.inc`, `vera-tests/`) | cosa il software si aspetta dall'hardware |
| `atari800/src/pbi_verax16.c`, `pbi.c` | modello di riferimento (ora allineato all'HDL) |
| Questo repo: `PIN-MAPPING.md`, `firmware/MCU/README.md`, netlist `VERA-MODULE-RBL.net` (2026-09-01) | stato della scheda |

**Limiti.** I punti della sezione 2 sono ricavati dalla *netlist*: nessuna simulazione elettrica
e nessuna misura. La netlist è del 2026-09-01 e l'ultimo commit del repo ("deleted all tracks and
imported from schematics") può averla resa non allineata. Ogni punto marcato **VERIFICA** va
controllato sullo schema aggiornato, sui datasheet e con l'oscilloscopio.

Il software è stato provato solo in emulazione. La scheda reale non è mai stata vista dal
driver.

---

## 1. Cosa fa la VERA sul bus (dall'HDL 48.0.1)

Firmware di riferimento: **48.0.1** (`VERA_ATARI_PBI/fpga-vera/48.0.1`). Rispetto alla 47.0.2 l'HDL
cambia solo in tre punti: l'indirizzo di scrittura è catturato direttamente all'inizio di WR (prima
passava da un registro intermedio), i byte di versione restituiscono anche minor e build, e le onde
sawtooth/triangle del PSG sono in XOR con `~pulsewidth`. I requisiti per la scheda non cambiano.

Questi sono i vincoli che l'hardware deve rispettare, indipendentemente dal progetto.

| Aspetto | Comportamento reale (`top.v`) | Conseguenza per la scheda |
|---|---|---|
| Strobe | `bus_read = !cs_n && wr_n && !rd_n`, `bus_write = !cs_n && !wr_n` | servono RD_n e WR_n **distinti**; `rd_n` è ignorato se `wr_n` è basso |
| Scrittura | l'indirizzo è campionato sul fronte di **salita** di `bus_write` (inizio); il **dato** sul fronte di **discesa** (`negedge bus_write`, cioè fine scrittura) | il dato deve restare stabile fino **dopo** la salita di WR_n / CS_n (hold) |
| Lettura | `extbus_d` pilotato solo mentre `bus_read`; effetti collaterali (autoincremento, prefetch) sul fronte di discesa di `bus_read`, dopo 3 cicli di `clk25` (~120 ns) | un'attivazione di RD_n = un evento di lettura. Cicli doppi (RMW, dummy read) li duplicano |
| Reset | solo POR interno (`por_cnt_r`, 128 cicli di `clk25`); **nessun pin di reset** | il RESET Atari non resetta la VERA |
| CTRL bit 7 (`$D105`) | `fpga_reconfigure` → ricarica l'intero bitstream: VRAM persa, bus morto ~100 ms | scrittura distruttiva; vedi §3 |
| IRQ | `extbus_irq_n = (irq_status & irq_enable) == 0`: **push-pull**, a livello | non può pilotare direttamente una linea IRQ condivisa |
| Registri FX | in sola scrittura (la lettura di `$D109-$D10C` con DCSEL≥2 restituisce i byte di identità del firmware, `'V',48,0,1` sulla 48.0.1, tranne FX_CTRL e POLY_FILL_L/H) | niente read-back di FX |

---

## 2. Verifiche e modifiche sulla scheda attuale

Priorità: **A** = da risolvere prima del primo test sul bus, **B** = da risolvere prima del
rilascio, **C** = da decidere.

### 2.1 [A] Il bus dati può fare contesa su letture non destinate alla scheda — VERIFICA

Dalla netlist:
- `U19` (74LVC4245, bus dati): `~OE_` (pin 22) è collegato **solo** a `NOT(PHI2)` (`U23` pin 3→4);
  `DIR` (pin 2) è `NOT(R/W)` (`U23` pin 1→2).
- Quindi `U19` è abilitato in **ogni** ciclo con PHI2 alto, qualunque sia l'indirizzo.

In un ciclo di lettura (R/W = 1) `DIR` = 0, cioè verso l'Atari (nella netlist `VCCA` è a 5 V,
quindi il lato A di `U19` è quello Atari e il lato B quello 3,3 V della scheda). In un ciclo di
lettura di **altra** memoria (RAM, ROM OS, cartuccia) `U19` pilota comunque il bus dati
dell'Atari dal lato scheda, dove i GPIO dell'ESP32 e le uscite dell'FPGA sono Hi-Z e non
pilotati. Un 74LVC4245 non ha bus-hold, quindi la contesa con RAM/ROM sul bus è probabile,
con possibili errori di lettura in tutto il sistema.

Richiesta: `~OE_` di `U19` deve essere attivo **solo** quando la scheda risponde in lettura
(registri VERA, RAM `$D600-$D7FF`, ROM `$D800-$DFFF`, finestra RAMbo), oppure in scrittura
(Atari→scheda, dove `U19` pilota solo il lato scheda). **Non** va collegato a `CDONE`: quello
segnala solo la configurazione dell'FPGA ed è già usato per rilasciare `ARESET`. Il gating è
ciclo per ciclo.

I segnali che indicano "la scheda risponde" esistono già: il firmware abbassa `DEV_SEL_N` (registri
VERA), `EXTSEL_N` (RAM `$D6xx`, RAMbo) e `MPD` (ROM `$D800`) quando la scheda risponde, e li rialza a
fine ciclo. Quindi:

```
~OE_ = NOT( PHI2 AND ( NOT R/W   OR   ~DEV_SEL_N OR ~EXTSEL_N OR ~MPD ) )
```

Con porte a 3,3 V:

```
A    = AND3(DEV_SEL_N, EXTSEL_N, MPD)    ; 1 quando nessuno risponde
B    = NAND(R/W, A)                       ; 1 se scrittura oppure la scheda risponde
~OE_ = NAND(PHI2, B)                      ; verso U19 pin 22 (al posto di NOT(PHI2))
```

Parti: un `74LVC11` (AND a tre ingressi) e due NAND. Una NAND è la quarta porta libera di `U5`
(pin 12 e 13, oggi a GND) se `U5` diventa un 74LVC00 come richiesto in §2.2; l'altra può essere un
`74LVC1G00`. `NOT R/W` esiste già (`U23` pin 2, che pilota `DIR`); `DIR` resta invariato.
Il pin 22 non deve più essere collegato a `U23` pin 4.

Da controllare:
- **Tempi.** `DEV_SEL_N`, `EXTSEL_N` e `MPD` vengono asseriti dall'ESP32 dopo la salita di PHI2
  (latenza del firmware più i ritardi di porta): `~OE_` si abbassa in ritardo. Il dato in
  lettura deve comunque essere valido alla CPU prima della discesa di PHI2 meno il suo tempo di
  setup. Da misurare con l'oscilloscopio.
- **`$D1FF` in lettura non abilita `U19`** (nessun segnale di risposta è asserito): è voluto, vedere §2.4.
- **Scritture.** `U19` resta abilitato in ogni scrittura: l'ESP32 deve vedere tutte le scritture
  (`$D301`, `$D303`, latch `$D1FF`, finestra RAMbo).

### 2.2 [A] Hold del dato sul fronte di salita di WR_n — VERIFICA

- `~mWE` e `~mRE` sono generati da `U5` (74HC00): `~mRE = NAND(PHI2, R/W)`,
  `~mWE = NAND(PHI2, NOT R/W)` (la negazione è un'altra porta NAND di `U5`).
- La VERA campiona il dato in scrittura alla **salita di WR_n**, cioè circa un ritardo di
  porta dopo la discesa di PHI2.
- Lo stesso evento (discesa di PHI2) disabilita `U19` tramite `U23` (inverter HCT04) e il
  buffer: il dato verso la VERA può diventare non valido più o meno nello stesso istante in cui
  WR_n sale. In più il 6502C mantiene il dato per un tempo minimo dopo PHI2 (verificare il valore sul
  datasheet SALLY/6502C).

Richieste:
1. Usare una porta più veloce di 74HC00 a 3,3 V (per esempio 74LVC00 / 74AHC00).
2. Rendere il rilascio di `U19` **più lento** della salita di WR_n (per esempio ritardare `~OE_`),
   oppure usare un solo percorso di ritardo per strobe e dato, così che il margine di hold sia
   positivo.
3. Verificare con analizzatore logico/oscilloscopio: dato stabile ≥ 5 ns dopo la salita di
   `~mWE` e `~mVCS0` al pin FPGA.

### 2.3 [A] Linea IRQ push-pull verso il bus Atari — VERIFICA

- `~mVIRQ` (FPGA, pin 32) va a `U16` pin 18 → `~IRQ` (`U16` pin 6) → `ECI1` pin B. C'è un
  pull-up `R65` sulla rete `~mVIRQ`.
- L'uscita VERA è push-pull (§1). Il bus Atari ha una linea IRQ **open-collector** condivisa
  con POKEY, PIA e altri device: un'uscita push-pull in alto contro un altro device che tira
  in basso crea contesa.

Richiesta: tra FPGA e ECI usare uno stadio open-drain/open-collector con uscita tollerante a
5 V. Una linea IRQ open-collector è un OR cablato: ogni device può solo **tirarla in basso**,
mai in alto; il livello alto lo dà l'unico pull-up sul computer. Aggiungere un proprio stadio
open-drain dà esattamente questo comportamento con POKEY, PIA e gli altri device.

**Soluzione consigliata (un componente).** `74LVC1G07` (buffer non invertente open-drain, SOT-23-5
o SC-70-5), alimentato a 3,3 V:

```
 3V3 ──┬── Vcc (pin 5)
       └── 100 nF ── GND
 ~mVIRQ (FPGA, 3,3 V, attivo basso) ──► A (pin 2)      GND (pin 3)
 Y (pin 4, open-drain) ──► ECI1 pin B (~IRQ, 5 V)   [nessun pull-up proprio verso 5 V]
```

- Uscita bassa quando l'FPGA chiede IRQ, alta impedenza altrimenti: non invertente, quindi la
  polarità resta quella di `~mVIRQ` (basso = IRQ).
- L'uscita open-drain dell'LVC1G07 tollera 5,5 V (Ioff), quindi il pull-up da 5 V sul computer non
  la danneggia, anche con la scheda spenta.
- VOL tipico < 0,4 V a qualche mA: la corrente tipica del pull-up IRQ Atari (circa 1-1,5 mA con
  3,3-4,7 kΩ, **verificare sul computer di prova**) è ampiamente entro i limiti.
- **Modifica sulla scheda attuale:** (1) staccare `U16` pin 6 dalla rete `~IRQ` (altrimenti resta
  l'uscita push-pull in parallelo); (2) collegare `Y` a `ECI1` pin B; (3) lasciare l'ingresso di
  `U16` pin 18 collegato a `~mVIRQ` (innocuo, uscita non utilizzata). `R65` (10 kΩ sul lato
  3,3 V) può restare come pull-up dell'ingresso dello stadio.

**Alternative.** (a) `BSS138`/`2N7002` con gate pilotato da `NOT(~mVIRQ)`, per esempio da un
`74LVC1G04`: due componenti; (b) diodo Schottky (BAT54) con anodo su `~IRQ` e catodo su
`~mVIRQ`: funziona come OR cablato, ma il livello basso risulta VOL(FPGA) + Vf (circa 0,6-0,7 V)
vicino al limite TTL di 0,8 V, quindi sconsigliato.

**Gestione dell'IRQ.** Con lo stadio open-drain basta un gancio software sul vettore IRQ (vedere §2.4):
non serve nessun collegamento aggiuntivo all'ESP32.

**Cosa NON fare.** Non lasciare l'uscita push-pull verso il bus, non aggiungere un pull-up a
5 V sulla scheda (la linea ha già il suo) e non usare un 74LVC4245 per questo segnale: non ha
uscite open-drain.

### 2.4 [A] Identificazione dell'IRQ: via software, non tramite `$D1FF`

**Perché non tramite `$D1FF`.** Il PBI prevede che ogni device pilota il proprio bit (la VERA: D7) in
lettura di `$D1FF`, con gli altri bit Hi-Z, e che l'OS legga `$D1FF & PDIMSK` per scegliere la ROM da
chiamare. Con la scheda attuale non è realizzabile:
- `U19` è un 74LVC4245: abilita **tutti e otto** i canali o nessuno. Pilotare solo D7 dal lato ESP32
  lascerebbe D0-D6 del lato scheda non pilotati, e `U19` li porterebbe sul bus Atari a un livello
  casuale, in contesa con i bit di eventuali altri device PBI. Con la regola di §2.1 `U19` non viene
  nemmeno abilitato per `$D1FF`.
- Tutti i GPIO dell'ESP32 sono assegnati (`PIN-MAPPING.md` §7): `~mVIRQ` non arriva all'ESP32, salvo
  un filo su GPIO0 (rete `BOOT0`, pin di strapping), che richiederebbe comunque un buffer tri-state
  separato per D7. Per questo il filo `~mVIRQ`→GPIO0 e l'opzione firmware `VERA_HAS_VIRQ_SENSE` sono
  stati **eliminati** (il documento `HW-MOD-GPIO0-VIRQ.md` non esiste più).

**Soluzione adottata: gancio software sul vettore IRQ.** I registri VERA sono sempre leggibili
(§2.5b). Un programma che usa gli IRQ della VERA aggancia `VIMIRQ` (`$0216`): legge `ISR` e `IEN`,
se `ISR & IEN` ha bit attivi conferma VSYNC/LINE/SPRCOL scrivendo 1 in `ISR` e maschera AFLOW in
`IEN`, altrimenti passa il controllo al gestore precedente. Serve solo lo stadio open-drain di §2.3 sulla
linea IRQ. L'OS **non** viene più usato per smistare l'IRQ: `PDIMSK` (`$0249`) resta a 0 e
`IRQVECTOR` della ROM PBI (`$D808`) non verrà chiamato.

Stato: **scritto e provato in emulatore**. Il gancio è in `VERA_ATARI_PBI/vera-tests/vera_irq.s`
(interfaccia C in `vera_irq.h`: `vera_irq_install`, `vera_irq_enable`, `vera_irq_disable`,
`vera_irq_take`, `vera_irq_set_line`, `vera_irq_set_callback`, `vera_irq_remove`). Il test
`TESTIRQ.COM` verifica VSYNC (circa 59,94 Hz anche con Atari PAL), LINE, il mascheramento di AFLOW,
la catena verso l'OS e la rimozione: 13 PASS, 0 FAIL in NTSC e in PAL. Sulla scheda reale va
provato dopo il montaggio dello stadio open-drain. Guida d'uso: `VERA_ATARI_PBI/Documentation/VERA-IRQ.md`.

### 2.5 [B] Scrittura `$D1FF`: solo il proprio bit — **corretto nel firmware**

Il latch di selezione deve usare solo **D7** (bit del device): con D7 = 1 la scheda si seleziona,
con D7 = 0 si deseleziona, qualunque sia il valore degli altri bit. L'emulatore si comporta
così (`byte & mask`) e ora anche `main.cpp` (`(data & PBI_DEV_ID) != 0`, prima `== 0x80`), sia in
modalità PBI sia CCTL.

### 2.5b [A] I registri VERA devono rispondere anche con il latch a 0 — **corretto nel firmware**

Il firmware asseriva `DEV_SEL_N` per `$D100-$D11F` **solo con la scheda selezionata** (latch
`$D1FF` = `0x80`). Ma l'OS deseleziona la scheda (`$D1FF` = 0) subito dopo l'`INIT`, e il driver
non la riseleziona mai: selezionarla mappa la ROM e disattiva il Math Pack (`MPD`), cosa che rompe
la virgola mobile del BASIC. Risultato: dopo il boot i registri VERA non sarebbero più
raggiungibili (il banner di boot compare perché l'`INIT` gira a scheda selezionata).

Ora `DEV_SEL_N` ed `EXTSEL_N` vengono asseriti per `$D100-$D11F` **sempre** (come
nell'emulatore e come presuppone il software); `MPD` e `EXTSEL_N` per `$D600-$DFFF` restano
legati alla selezione.

### 2.5c [A] Il log dei registri nel loop del bus faceva perdere cicli — **corretto nel firmware**

Per ogni accesso ai registri VERA il loop chiamava `log_send()` (`xQueueSend` + `esp_timer_get_time`,
circa 1 µs) mentre `DEV_SEL_N` era ancora asserito. Con un ciclo 6502 di 558 ns si poteva
superare la fine di PHI2: `DEV_SEL_N` restava basso nel ciclo successivo (accessi spuri alla
VERA con l'indirizzo sbagliato) oppure si perdeva il ciclo seguente. Ora il log dei registri è
compilato solo con `-DVERA_TRACE_REGS=1` (debug, mai in produzione); resta attivo il log dei
cambi di latch (rari).

### 2.6 [B] Header ROM PBI — **ROM allineata**

La ROM `vera_pbi_handler.rom` (2 KB, assemblata da `vera_pbi_handler.s`) ha l'header:
`$D803 = $80`, `$D80B = $91`, `$D80C = 'V'`, vettori `$D805` (SIO, restituisce C=0 = non
gestito) e `$D808` (IRQ). Il contenuto deve essere esattamente quello servito dalla scheda a
`$D800-$DFFF`. La copia in `firmware/MCU/6502/src/vera_pbi_handler.s` (+ `inc/vera_common.inc`) è stata
sostituita con l'handler corrente di `VERA_ATARI_PBI` e rigenerata con `make -C 6502`
(`vera_pbi_handler.bin`, `include/vera_pbi_handler.h`, `FPGA/pbi_rom_pkg.vhd`): il binario è identico
a `vera_pbi_handler.rom` di `VERA_ATARI_PBI`. Contiene il nuovo `IRQVECTOR` e l'attesa lunga di
`WAIT_VERA`.

---

## 3. Reset e configurazione FPGA

| # | Requisito | Stato nel firmware attuale |
|---|---|---|
| 1 | Tenere l'Atari in reset (`ARESET` basso) fino a CONFIG_DONE della VERA | **già così**: `ARESET`, `CRESET` bassi in `setup()`; `CRESET` alto, attesa `CDONE`, poi `ARESET` alto |
| 2 | Il blocco vale **solo al power-on** | la sequenza è eseguita una volta: **non** deve essere rieseguita se `CDONE` scende dopo una riconfigurazione (CTRL bit 7) |
| 3 | Ritardo dopo `CDONE` prima di rilasciare `ARESET` (~1 ms) | **fatto**: `delayMicroseconds(VERA_POST_CDONE_DELAY_US)`, default 1000 µs (la VERA ha un POR interno di 128 cicli di `clk25`, ~5 µs, più `reset_sync`) |
| 4 | `ARESET` open-drain con pull-up | il tasto RESET Atari deve continuare a funzionare; mai pilotare la linea in alto |
| 5 | Timeout se `CDONE` non arriva (oggi 5 s, solo log) | decidere: rilasciare comunque `ARESET`? Il software ha un timeout di ~0,7 s in `WAIT_VERA`: prosegue senza VERA ed emette **tre beep** dall'altoparlante della console (un colore sullo schermo ANTIC non resta: l'OS reimposta i colori dopo l'`INIT` PBI) |
| 6 | Scrittura di `$80` in CTRL (`$D105`) | **protezione consigliata**: far mascherare al firmware/glue il bit 7 delle scritture a `$D105`, perché la riconfigurazione distrugge VRAM e blocca il bus ~100 ms. In alternativa il software non deve mai scriverlo (i test già non lo fanno). **Non implementato nel firmware ESP32**: il dato è valido solo a metà di PHI2, quindi `DEV_SEL_N` andrebbe asserito in ritardo solo per `$D105`; ritirarlo dopo la lettura non basta, perché la VERA registra la scrittura alla fine di `bus_write` comunque. Senza hardware per misurarlo, un errore di temporizzazione farebbe perdere scritture legittime a CTRL (cambi di DCSEL): rischio peggiore del problema |

Durante una riconfigurazione il bus VERA non è pilotato: le letture danno valori casuali.
L'emulatore la simula con 100 ms di bus morto (`-verax16-config-ms`, 0 = RESET tenuto fino a
CDONE).

---

## 4. Livelli, alimentazioni e temporizzazioni

- **Livelli.** VERA, ESP32 e FPGA sono a 3,3 V; il bus Atari è a 5 V TTL. Tutti i segnali verso
  l'Atari passano da 74LVC4245. Controllare che le uscite 3,3 V rispettino VIH dei ricevitori
  sul bus (TTL ≥ 2,0 V) e che gli ingressi sul lato 5 V non superino i limiti dell'FPGA.
- **Alimentazioni.** Nella netlist `U16` e `U19` hanno `VCCA` (pin 1) a **5 V**, mentre
  `PIN-MAPPING.md` descrive il lato A come 3,3 V (ESP32). Le due descrizioni non coincidono:
  verificare il lato corretto per ogni chip (per `U16` e `U19` il lato A risulta quello
  dell'Atari).
- **Tempo di risposta in lettura.** In lettura la VERA risponde da registri e dati già pronti
  (prefetch): alla scheda basta il tempo di propagazione attraverso `U4/U3`, FPGA e `U19`
  (circa 30-50 ns stimati, da misurare). Per la ROM/RAM `$D600-$DFFF` servite dall'ESP32 il
  margine è molto più stretto (fetch di istruzioni: tutti i cicli): il firmware ha ~279 ns per
  ciclo, vedi `Vera_Module_Analisys.ITA.tex`.
- **Frequenza di quadro.** La VERA gira a 59,94 Hz fisso, asincrona rispetto al VBI Atari. Non
  è un problema hardware, ma il software non può assumere sincronismo fra i due.

---

## 5. Regole software da rispettare con l'hardware reale

Il driver e i test già le seguono, ma valgono per qualunque programma futuro:

1. **Mai** `inc`, `dec`, `asl`, `lsr`, `rol`, `ror` su `$D100-$D11F`: le istruzioni RMW fanno
   due accessi e duplicano l'evento (autoincremento due volte su `DATA0/DATA1`).
2. **Mai** indirizzamento indicizzato su `$D100-$D11F` (una dummy read al cambio di pagina
   colpisce `DATA0/DATA1`), né `sta abs,x` / `sta (zp),y` con base nella pagina `$D1`.
3. Non scrivere `$80` in `$D105` (riconfigurazione dell'FPGA).
4. Non leggere i registri FX: sono in sola scrittura (restituiscono i byte di identità del firmware, `'V',48,0,1` sulla 48.0.1).
5. Niente sincronismo supposto con il VBI Atari.
6. Gli IRQ della VERA si gestiscono agganciando `VIMIRQ` (`$0216`), non via `$D1FF`/`PDIMSK` (§2.4).
7. Dopo il reset Atari la VERA mantiene tutto lo stato: l'handler `INIT` ne riscrive solo una
   parte. Un programma che lascia FX o IEN attivi lascia lo stato anche al riavvio.

---

## 6. Piano di bring-up consigliato

1. **Senza Atari**: alimentare la scheda, verificare `CDONE`, la sequenza `CRESET`→`ARESET`
   (tempi) e i livelli sul bus con `ARESET` scollegato.
2. **Con l'Atari, scheda scollegata dal bus dati** (`U19` disabilitato): verificare che
   l'Atari parta normalmente con `ARESET` rilasciato dalla scheda.
3. **Con `U19` abilitato**: controllare con l'oscilloscopio che non ci sia contesa nelle letture
   di RAM/ROM (§2.1) e il margine di hold sulle scritture (§2.2).
4. **Rilevamento**: dal DOS, `vera_detect()` (CTRL=`$7E`, `$D109`=`'V'`, `$D10A`=47) via
   un programma minimo; poi `$D1FF`/ROM (`$D803=$80`, `$D80B=$91`).
5. **Test funzionali** in questo ordine: da `disk3-standalone.atr` `TESTFX.COM` (atteso
   **PASS: 36, FAIL: 0**, e la riga `VERA firmware 48.0.1`); da `disk2-veratests-*.atr` `TEST8.COM`, `TESTGS8.COM`, `TESTMAZ8.COM`,
   `TESTMTX8.COM` (ESC per uscire); da `disk3-standalone.atr` `TESTPLR.COM`; poi `RUNCPM.COM`
   (`disk1-runcpm.atr`) con FujiNet.
6. **IRQ** solo quando §2.3 (stadio open-drain) è montato: `TESTIRQ.COM` da `disk3-standalone.atr` (atteso PASS 13, FAIL 0).
7. Ogni anomalia va riprodotta in emulatore con `-verax16-config-ms` (0 e 100) per separare
   problemi software da problemi di scheda.

---

## 7. Punti aperti da decidere

- Architettura: la documentazione descrive **due** soluzioni per RAM/ROM PBI: servite
  dall'ESP32 (`PIN-MAPPING.md`, `firmware/MCU`) oppure dalla BRAM di un'FPGA di interfaccia
  (`firmware/FPGA`, `C6502_Interface.vhd`). Va stabilita quale è quella attuale e allineata la
  documentazione.
- Presenza o meno di una decodifica hardware (`addressdecoder.sch`: 74LVC138, `~dD1XX`,
  `~dROMSEL`, `~dRAMSEL`) accanto alla decodifica software dell'ESP32.
- Compatibilità ECI del 130XE: confermare che l'ECI porti `MPD`, `EXTSEL`, `IRQ` e `D1XX`, e che
  l'OS XE esegua la scansione PBI (`$D1FF`, `$D803`, `$D80B`) come l'OS XL.
