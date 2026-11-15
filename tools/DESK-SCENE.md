# Desk scene of the video (computer + monitors)

The same files are in Vera-Module-RBL-XE and Vera-Module-RBL-C64 and are kept
identical: copy every change to both repos.

At the end of the assembly animation the computer (Atari 130XE or Commodore 64
breadbin) comes in behind the module and plugs in (side view). Then a cut to a
high front view with two monitors that switch on: left a CRT with the BASIC
screen, right a flat HDMI monitor with the VERA 256-colour palette. Credits and
the end card follow as before.

## Files

| File | What |
|---|---|
| `tools/render_enclosure.py` | `RENDER_MODE=desk`: the desk shots, frames `d%04d.png` (timing, cameras, lights) |
| `tools/desk_scene.py` | Blender module: `build_xe`, `build_c64`, the CRT and the flat monitor |
| `tools/make_screens.py OUT` | the screens (Atari/C64 BASIC, VERA palette) and the key legend textures |
| `tools/keyboards/` | KLE layouts (XE from A130KB_MX, GPL; C64 own), `keycap-1u.stl` (A130KB_MX, DSA) |
| `tools/fonts/C64Keyboard-Regular.otf` | C64 legends, "C64 Keyboard" by Levente Szabadkai, CC0 |
| `tools/models/c64-case.zip` | C64 repo only: the C64 case, 4 STL (no licence given; the owner takes the risk) |
| `tools/make_video.sh` | assembly frames + desk frames, fade at the end of the desk, then credits |
| `.github/workflows/video.yml` | jobs `screens`, frames chunks `fN-M` (assembly) and `dN-M` (desk) |

## The computers

**130XE.** The covers are the owner's models in the private repo
`gianlucarenzi/3DRepo`:
- `Atari/XE/Top_Case_Model_A/A130XE-top-big.stl`;
- `Atari/XE/Bottom_Case/A130XE-bottom-big.stl`;
- `AtariXE-Func-5.55-4.25-1.53.stl`, the 5 rhomboid function keys.

The workflow checks them out with the read-only deploy key in the secret
`THREEDREPO_KEY`.

Placement, set by hand in FreeCAD:
- bottom turned 90 degrees about Z;
- top moved by `XE["top_offset"]` = (0, -3, 12);
- keyboard `kb_z0` 41.1, function keys `fn_z` 44.0.

Keycaps are DSA, every row the same, as on the owner's A130KB_MX keyboard. Keep
them DSA (the original 130XE keys are Cherry profile).

Colours:
- covers and function keys #9DA09A (RAL 7038, 13% darker);
- keys #CDCCC6.

Legends, DejaVu Sans regular:
- black on the keys;
- white on the function keys, written "Help", "Start", "Select", "Option",
  "Reset", all at one size.

**C64.** The case comes from `tools/models/c64-case.zip`, turned 180 degrees and
moved by `C64["case_shift"]` = (0, 103, 1.9).

Keys:
- SA profile, one profile per row (`row_profile`: height in mm, top angle);
- raised by hand in FreeCAD: `kb_z0` 68.5, function keys 2 mm more (`fn_dz`).

Colours:
- keys #2A211C (almost black brown);
- F keys #5E5C5A;
- case #A0957F.

Legends are white, in the C64 Keyboard font at scale 1.6, with no outline. The
font has capitals only, so the lower case "f1" … "f8" of the function keys and
the ↕ ↔ arrows are drawn in DejaVu.

The expansion port is at `slot_cart_x` -122.5.

Do not use Gorton: it is non-commercial only.

## Fixing placements by hand (FreeCAD)

The owner prefers to place the parts himself in FreeCAD:
1. Build a `.FCStd` with the covers (STEP) at the placement used here.
2. Add the keys, exported from Blender as STL meshes: the vertices of the
   `xe_keys`/`c64_keys` and `xe_fn*`/`c64_fn` objects, in the parent's mm
   coordinates.
3. He moves them (Placement only) and saves.
4. Read the placements back and add the differences to the constants of
   `desk_scene.py`.

## Running it

**Local preview.** Run `python3 tools/make_screens.py <dir>` first, then
`blender -b -P <script>` with a script that imports `desk_scene`. Use Blender 4.2
LTS (`~/packages/blender-4.2.23-linux-x64`, symlink `~/.local/bin/blender`). With
2 cores a 960x540 frame at 16 samples takes about 8 minutes.

**GitHub.**
1. Run the "Video" action (input `desk_seconds`, default 10.5).
2. Run the "Teaser" action with the Video run id and the music:
   - `music=https://incompetech.com/music/royalty-free/mp3-royaltyfree/Echoes%20of%20Time%20v2.mp3`
   - `music_start=70`
   - `music_credit='"Echoes of Time v2" by Kevin MacLeod (incompetech.com)|Licensed under Creative Commons: By Attribution 4.0|creativecommons.org/licenses/by/4.0/'`
3. Update `docs/teaser.mp4` and `images/teaser-poster.jpg`; the GitHub Pages
   page is `docs/teaser.html`.
