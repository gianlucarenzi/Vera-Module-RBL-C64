# Involucro stampabile (due gusci)

Involucro in due gusci sovrapponibili per il VERA Module, con spazio per la
**VERA-HDMI-Expansion** montata sopra. Si genera con **FreeCAD** dal PCB KiCad 5
e dal suo STEP, quindi si rifà uguale su qualsiasi PC e si aggiorna da solo quando
cambia la scheda.

Ogni build produce **due varianti**:
- **aperta**: sul lato porte un'unica finestra;
- **con pannello posteriore** (`-backpanel`): gli stessi gusci, con la finestra
  chiusa da un pannello separato che ha un foro per ogni porta e si aggancia a
  scatto. Si può montare anche dopo, a involucro chiuso.

| File | Contenuto |
|---|---|
| `VERA-RBL-C64-enclosure-bottom.stl` / `.step` | guscio inferiore, da stampare |
| `VERA-RBL-C64-enclosure-top.stl` / `.step` | guscio superiore, da stampare |
| `VERA-RBL-C64-enclosure.FCStd` | documento FreeCAD: gusci, scheda e HDMI |
| `VERA-RBL-C64-enclosure-light.FCStd` | lo stesso, con le schede semplificate: si apre subito anche su un PC poco potente |
| `VERA-RBL-C64-enclosure-assembly.gif` | simulazione dell'assemblaggio |
| `VERA-RBL-C64-enclosure-backpanel-bottom.stl` / `.step` | guscio inferiore della variante con pannello |
| `VERA-RBL-C64-enclosure-backpanel-top.stl` / `.step` | guscio superiore della variante con pannello |
| `VERA-RBL-C64-enclosure-backpanel-panel.stl` / `.step` | pannello posteriore a scatto |
| `VERA-RBL-C64-enclosure-backpanel.FCStd` | documento FreeCAD della variante con pannello |
| `VERA-RBL-C64-enclosure-backpanel-light.FCStd` | lo stesso, con le schede semplificate |
| `VERA-RBL-C64-enclosure-backpanel-assembly.gif` | assemblaggio, con il pannello che entra |
| `board.json` | dati presi dal PCB (contorno, fori, componenti) |
| `VERA-RBL-C64-module.FCStd` | il modulo come un'unica App::Part: scheda, HDMI, distanziali, gusci e pannello (variante `-backpanel`); origine sulla punta del pettine |
| `VERA-RBL-C64-in-C64.FCStd` | il modulo inserito nel C64: case e tastiera della scena del teaser, scheda madre sulle torrette del case, pettine nella porta di espansione. Serve a controllare gli ingombri |

## Generarlo

### Su GitHub (consigliato su un PC poco potente)

Il workflow `.github/workflows/enclosure.yml` fa tutto in un container
`debian:latest`: FreeCAD da apt, KiCad 5 dall'AppImage di
[kicad_appimage_builder](https://github.com/gianlucarenzi/kicad_appimage_builder),
la VERA-HDMI-Expansion dal suo repository. Parte:
- **a mano**: Actions → Enclosure → Run workflow (con o senza animazione);
- **a ogni push su `master`** che cambia il PCB, il suo STEP o gli script
  dell'involucro.

Il risultato va in due artifact, `…-enclosure-open` e `…-enclosure-backpanel`, e
viene committato in `enclosure/` dal workflow stesso.

### In locale

```bash
./output_job.sh <versione>          # se manca images/VERA-MODULE-RBL.step
tools/make_enclosure.sh 151         # taglio a y = 151 mm
tools/make_enclosure.sh 151 --no-anim   # solo i gusci, senza animazione
```

L'argomento è la **y KiCad (mm) dove finisce l'involucro** e inizia il pettine da
inserire nel computer: **151** per questa scheda (pettine della porta di espansione da y 152).

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
   `ENC_FRAMES`, renderizza i fotogrammi dell'assemblaggio, circa 15 minuti per
   variante. Poi ffmpeg (o ImageMagick) li unisce nella GIF.

**Per vedere l'animazione in FreeCAD:** apri `enclosure/<nome>.FCStd`, meglio la
versione `-light`, poi esegui `tools/enclosure_assembly.py` come macro (Macro →
Macro… → seleziona il file, oppure dalla console Python). Anima il documento aperto.

**Documenti `-light`:** gusci e pannello sono quelli veri; le schede sono
semplificate (contorno del PCB e un parallelepipedo per ogni componente). Pesano
circa 0,5 MB contro 2,6 MB e si aprono e ruotano subito anche con 4 GB di RAM.

## Ingombri nel C64 (FreeCAD)

```bash
tools/fc_assembly.sh
```

Rifà `VERA-RBL-C64-module.FCStd` e `VERA-RBL-C64-in-C64.FCStd` dal guscio
attuale (`VERA-RBL-C64-enclosure-backpanel.FCStd`): dopo aver cambiato
l'involucro, prima `tools/make_enclosure.sh` (o il workflow Enclosure), poi questo.
Ci vuole circa mezzo minuto.

- **C64**: case e tastiera della scena del teaser (`tools/fc_context.py` li
  esporta da Blender senza renderizzare). Coordinate del computer: retro a
  y 0, fronte verso +Y, tavolo a z 0.
- **Scheda madre**: `images/C64-Motherboard-Replice.wrl`, convertito in un mesh
  per colore da `tools/wrl2stl.py`. I suoi sette fori da 4 mm stanno sugli assi
  delle torrette del case (scarto sotto 1 mm) e la faccia inferiore sulla loro
  sommità (z 9). Si usa solo qui, non nei render.
- **Modulo**: il pettine centrato nel connettore della porta di espansione
  (ad angolo retto, feritoia verso il retro), il piano medio della scheda su
  quello della feritoia, la punta a 0,5 mm dal fondo. Nel teaser la posa è
  un'altra (`tools/desk_scene.py`).

Servono Blender 4.2 (`BLENDER=...`, predefinito `blender-4.2`), FreeCAD,
`xvfb-run`, python3 con numpy e Pillow, i file LFS (`git lfs pull`).

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
- **Appoggi vicino ai pettini:** i fori M3 sono tutti dal lato porte, quindi
  vicino ai pettini, cioè dove si fa forza inserendo la scheda nel computer, la
  scheda è stretta tra una **colonnina** del guscio inferiore (Ø 6 mm, fino alla
  faccia inferiore del PCB) e un **piolo** del coperchio (Ø 5 mm, fino alla faccia
  superiore). Lo script cerca da solo fino a 3 punti, distribuiti sulla larghezza
  nella fascia tra 3 e 35 mm prima di `ENC_CUT`, ad almeno 5 mm dal bordo. Sceglie
  punti dove sotto e sopra la scheda non c'è alcun componente (ingombri dello STEP
  più 1 mm) e stampa le coordinate KiCad dei punti scelti.

## Pannello posteriore

- **Finestra:** come nella variante aperta, ma scende fino al fondo.
- **Pannello:**
  - un tassello che entra nella finestra con 0,2 mm di gioco per lato;
  - una cornice esterna di 1,5 mm, spessa 1,2 mm, che appoggia sulla parete e
    fa da battuta;
  - un **foro per ogni porta**, con 0,5 mm di tolleranza per lato. Il foro è
    l'ingombro, visto di fronte, di tutto ciò che del connettore sta davanti
    alla faccia interna della parete; per un connettore arretrato, dei suoi
    1,5 mm anteriori;
  - un connettore senza modello 3D (il jack audio J7) ha un foro grande come la
    sua impronta e alto 6 mm.
- **Aggancio a scatto:** 2 linguette sul fondo e 2 sotto il coperchio
  (6 × 10 mm, spesse 1 mm), che entrano nell'involucro. In punta hanno un dente
  con rampa d'invito che scatta in una feritoia del fondo (o del coperchio):
  - il pannello **si monta da fuori a involucro chiuso**, spingendolo finché
    scatta;
  - **si toglie** premendo i denti attraverso le feritoie con una punta e
    tirandolo fuori.
- **Posizione delle linguette:** lo script le mette dove la linguetta, anche
  piegata dal dente, non tocca componenti, colonnine o appoggi, e dove il
  pannello non ha fori. Stampa le coordinate KiCad x scelte.
- **Stampa:** il pannello si stampa con la cornice sul piatto e le linguette in
  verticale. Le linguette si flettono lungo gli strati, quindi è meglio il
  **PETG** (o l'ABS): il PLA è più fragile.

## Misure

Per cambiare le misure si modificano le costanti in testa a
`tools/make_enclosure.py`: `WALL`, `GAP`, `LIP`, `CLEAR`, `STANDOFF`, `VENT_*`,
`PIN_HOLE`, `SUP_*` (appoggi), `PANEL_TOL`, `PORT_TOL`, `FLANGE*`, `SNAP_*`,
`MIN_RIB` (pannello).

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

Tutti i pezzi si stampano **appoggiati sul piatto e senza supporti**, in PLA o
PETG con layer da 0,2 mm:

| Pezzo | Sul piatto | Note |
|---|---|---|
| guscio inferiore | il fondo | finestra, fessura del pettine e bordino sono aperti verso l'alto; le feritoie degli agganci sono fori passanti |
| guscio superiore | il coperchio (capovolto) | la finestra arriva al coperchio, quindi non c'è un ponte; colonnine, pioli, griglie a 45° e feritoie partono dal piatto |
| pannello | la cornice | i fori sono passanti e le linguette crescono in verticale; l'unico sbalzo è la faccia di ritenuta del dente (0,9 mm) |

Tra un foro del pannello e il bordo del tassello non restano strisce sottili
(meno di `MIN_RIB` = 1,2 mm): in quel caso il foro arriva fino al bordo, e la
cornice resta intera. Per il pannello è meglio il PETG, vedi sopra.
