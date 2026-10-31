#!/usr/bin/env python3
"""
Makes the JLCPCB CPL agree with the JLCPCB BOM, so the upload does not stop
with "designators don't exist in the BOM/CPL file".

- A CPL row whose designator is not in the BOM is a part that is not to be
  assembled (no LCSC code, DNP, hand-soldered jumper...): it is removed and
  listed.
- A BOM designator missing from the CPL is a real error (the part is in the
  schematic but not placed on the PCB, or the two are out of sync): the
  designators are listed and the script exits with an error.

Only the standard library is used.

Usage: jlcpcb-sync-cpl.py <bom.csv> <cpl.csv>     (the CPL is rewritten)
"""
import csv
import re
import sys


def ref_key(ref):
    m = re.match(r'(.*?)(\d*)$', ref)
    return (m.group(1), int(m.group(2) or 0))


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: %s <bom.csv> <cpl.csv>" % sys.argv[0])
    bom_file, cpl_file = sys.argv[1], sys.argv[2]

    bom = set()
    with open(bom_file, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            bom.update(r.strip() for r in row["Designator"].split(",")
                       if r.strip())

    with open(cpl_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    kept = [row for row in rows if row["Designator"] in bom]
    dropped = sorted((row["Designator"] for row in rows
                      if row["Designator"] not in bom), key=ref_key)
    missing = sorted(bom - {row["Designator"] for row in rows}, key=ref_key)

    with open(cpl_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames,
                                quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writeheader()
        writer.writerows(kept)

    if dropped:
        print("CPL: not assembled (not in the BOM), removed: %s"
              % ", ".join(dropped))
    print("CPL: %d placements, same designators as the BOM." % len(kept))
    if missing:
        sys.exit("Error: in the BOM but not on the PCB (CPL): %s"
                 % ", ".join(missing))


if __name__ == "__main__":
    main()
