# Involucro stampabile (due gusci)

Involucro in due gusci sovrapponibili per il VERA Module, con spazio per la
**VERA-HDMI-Expansion** montata sopra. Si genera con **FreeCAD** dal PCB KiCad 5
e dal suo STEP, quindi si rifà uguale su qualsiasi PC e si aggiorna da solo quando
cambia la scheda.

| File | Contenuto |
|---|---|
| `VERA-RBL-C64-enclosure-bottom.stl` / `.step` | guscio inferiore, da stampare |
| `VERA-RBL-C64-enclosure-top.stl` / `.step` | guscio superiore, da stampare |
| `VERA-RBL-C64-enclosure.FCStd` | documento FreeCAD: gusci, scheda e HDMI |
| `VERA-RBL-C64-enclosure-assembly.gif` | simulazione dell'assemblaggio |
| `board.json` | dati presi dal PCB (contorno, fori, componenti) |

## Generarlo

```bash
./output_job.sh <versione>          # se manca images/VERA-MODULE-RBL.step
tools/make_enclosure.sh 151         # RBL-C64 (189 per RBL-XE)
tools/make_enclosure.sh 151 --no-anim   # solo i gusci, senza animazione
```

L'argomento è la **y KiCad (mm) dove finisce l'involucro** e inizia il pettine da
inserire nel computer: **189** per RBL-XE (pettini cartuccia ed ECI da y 190),
**151** per RBL-C64 (pettine della porta di espansione da y 152).

I passi, che si possono anche lanciare a mano:

1. `./run_pcbnew.sh tools/enclosure_data.py VERA-MODULE-RBL.kicad_pcb enclosure/board.json [HDMI.kicad_pcb]`
   legge dal PCB, con pcbnew di KiCad 5, il contorno (Edge.Cuts), lo spessore, i
   fori M3 (H1-H4), U7 (ESP32), U2 (FPGA), SW1 (RESET), SW3 (BOOT0) e i connettori
   sul lato porte. Con il PCB dell'HDMI calcola anche lo spostamento che porta i
   suoi fori sui fori del modulo.
2. `freecadcmd tools/make_enclosure.py`, con le variabili `ENC_DATA`, `ENC_STEP`,
   `ENC_HDMI`, `ENC_CUT`, `ENC_NAME`, `ENC_OUT`, costruisce i gusci. Richiede
   qualche minuto, quasi tutto per leggere gli STEP.
3. `xvfb-run ... freecad tools/enclosure_assembly.py`, con `ENC_DOC` ed
   `ENC_FRAMES`, renderizza i fotogrammi dell'assemblaggio, circa 15 minuti. Poi
   ffmpeg (o ImageMagick) li unisce nella GIF.

**Per vedere l'animazione in FreeCAD:** apri `enclosure/<nome>.FCStd`, poi esegui
`tools/enclosure_assembly.py` come macro (Macro → Macro… → seleziona il file, oppure
dalla console Python). Anima il documento aperto.

## Cosa serve

| Programma | Debian 11 | Debian 12 | Debian 13 |
|---|---|---|---|
| KiCad 5 (pcbnew) | `kicad` 5.1 di sistema | AppImage KiCad 5 come `kicad5` | AppImage KiCad 5 come `kicad5` |
| FreeCAD | 0.19 (`apt install freecad`) | 0.20 / 0.21 da backports | 1.0 |
| animazione | `apt install xvfb ffmpeg` (o `imagemagick`) | idem | idem |

**Memoria:** FreeCAD con lo STEP della scheda occupa circa 2 GB. Con 4 GB di RAM va lanciata **una sola istanza di FreeCAD alla volta**: due insieme (per esempio l'animazione e il documento aperto a schermo) vengono chiuse dal sistema per mancanza di memoria.

Gli script usano KiCad 5 di sistema se c'è, altrimenti l'AppImage (vedi
`run_pcbnew.sh`). Di FreeCAD usano solo il modulo Part: box, estrusioni, offset 2D,
operazioni booleane, `Part.read`, `exportStep`, `exportStl`. Per l'animazione
usano Placement, ViewObject e `saveImage`. Sono tutte funzioni presenti dalla 0.19.

## Come è fatto

- **Pianta:** il contorno della scheda fino a `ENC_CUT`, allargato di 0,5 mm
  (gioco) e poi di 1,5 mm (parete). Le pareti seguono la forma della scheda.
- **Spessore** di pareti, fondo e coperchio: **1,5 mm**.
- **Altezze dallo STEP:** il fondo sta 1 mm sotto il componente più basso del lato
  bottom, il coperchio 1 mm sopra il punto più alto, cioè il connettore HDMI
  dell'adattatore montato.
- **Divisione dei gusci** sul piano inferiore del PCB. Il guscio inferiore ha un
  bordino di 2 mm (metà esterna della parete) che entra nel guscio superiore.
- **Lato porte:** un'unica **finestra rettangolare** dal connettore più a sinistra
  a quello più a destra (dallo STEP e dalle impronte: il jack audio J7 ha solo il
  modello `.wrl` e nello STEP non c'è), dal fondo fino sopra il connettore HDMI.
  Una cornice di 1,5 mm resta ai lati e sotto il coperchio.
- **Pettini:** una fessura nella parete per ogni pettine che esce dall'involucro.
- **Aerazione:** griglia di fessure a **45°** (1,6 mm, passo 3,6 mm, area
  24 × 24 mm) sul coperchio sopra U7 (ESP32) e U2 (FPGA).
- **RESET e BOOT0:** un foro da 3 mm sul coperchio sopra SW1 e SW3, per premerli
  con una graffetta.
- **Fissaggio** sui fori M3 H1-H4 della scheda:
  - nel guscio inferiore, colonnine sotto la scheda, con viti M3 da sotto di
    circa 10 mm, avvitate nei distanziali;
  - tra le due schede, distanziali **M3 F/F da 14 mm** (come in
    `Documentation/MECHANICAL-BOM.md` dell'HDMI);
  - nel guscio superiore, colonnine che scendono fino all'HDMI, con viti M3 da
    sopra di circa 14 mm, avvitate nei distanziali.

  Senza HDMI, al posto della scheda HDMI si mette una rondella da 1,6 mm.

Per cambiare le misure si modificano le costanti in testa a
`tools/make_enclosure.py`: `WALL`, `GAP`, `LIP`, `CLEAR`, `STANDOFF`, `VENT_*`,
`PIN_HOLE`.

## Per un'altra scheda

Lo script non dipende dal VERA Module. Servono:
- lo STEP della scheda esportato da `output_job.sh` (kicad2step, `--grid-origin`).
  Lo script ritrova la scheda nello STEP confrontandone l'ingombro con il contorno;
- i fori di fissaggio come impronte `MountingHole` con riferimento `H*`;
- il lato porte sul bordo con la y KiCad più piccola. Per un altro lato va
  adattato il blocco "Port side" di `make_enclosure.py`;
- `ENC_CUT` oltre il bordo opposto, se la scheda non ha pettini;
- i riferimenti delle griglie e dei fori dei pulsanti: si cambiano in
  `enclosure_data.py` (`parts`) e in `make_enclosure.py` (`vent`, `SW1`/`SW3`).

## Stampa

- Si stampa in PLA o PETG, con 0,2 mm di layer e il coperchio/fondo appoggiato sul
  piatto: il guscio inferiore con il fondo sul piatto, quello superiore capovolto.
- Le griglie a 45° si stampano senza supporti.
- La finestra sul lato porte ha un ponte di 1,5 mm sopra: con il guscio superiore
  capovolto non serve supporto.
