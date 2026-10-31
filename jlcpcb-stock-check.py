#!/usr/bin/env python3
"""
Checks the JLCPCB BOM against the live JLCPCB parts library, with the same
search service the jlcpcb.com parts page uses (no account needed).

For every BOM row: whether the LCSC code is in the JLCPCB assembly library,
its stock against the quantity needed for N boards, Basic / Preferred /
Extended and the cost. For a part that cannot be assembled it lists
candidates with enough stock: same JLCPCB category and package, the same
value for the passives, Basic first.

Status of a row:
  OK       stock enough (more than LOW_FACTOR times what is needed)
  LOW      stock enough now, but less than LOW_FACTOR times what is needed
  SHORT    0 < stock < needed                                     (error)
  OUT      stock 0                                                (error)
  MISSING  the code is not in the JLCPCB library                  (error)
  GLOBAL   OUT, SHORT or MISSING, but listed in the Global Sourcing file:
           JLCPCB buys it from another distributor, so it is not an error

Global Sourcing file (default jlcpcb-global-sourcing.txt next to the
script, if present): one LCSC code per line, '#' starts a comment.

The jlcparts database (yaqwsx) was tried first and dropped: it misses parts
that JLCPCB has (e.g. C2913196 ESP32-S3FN8, C2798196), so it gave false
"missing" errors.

Exit status: 0 no errors, 1 at least one error, 2 bad input or service
not reachable.

Only the standard library is used.

Usage: jlcpcb-stock-check.py [--boards N] [--global-sourcing FILE] <bom.csv>
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

API = ("https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/"
       "smtGood/selectSmtComponentList")
LOW_FACTOR = 5
ALTERNATIVES = 5
DELAY = 0.3          # seconds between requests, to be polite with the service
# Attributes that must be equal for a passive to be a substitute
KEY_ATTRS = ("Resistance", "Capacitance", "Inductance", "Frequency",
             "Impedance @ Frequency")


class ServiceError(Exception):
    pass


def search(payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(API, data=data, headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (jlcpcb-stock-check)"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.load(r)
            info = (body.get("data") or {}).get("componentPageInfo")
            if info is None:
                raise ServiceError("unexpected answer: %s" % str(body)[:200])
            time.sleep(DELAY)
            return info.get("list") or []
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            if attempt == 2:
                raise ServiceError(str(e))
            time.sleep(2)
    return []


def lookup(code):
    for part in search({"keyword": code, "currentPage": 1, "pageSize": 5}):
        if part.get("componentCode", "").upper() == code.upper():
            return part
    return None


def attrs(part):
    return {a.get("attribute_name_en"): a.get("attribute_value_name")
            for a in part.get("attributes") or []}


def lib_type(part):
    if part.get("componentLibraryType") == "base":
        return "Basic"
    return "Preferred" if part.get("preferredComponentFlag") else "Extended"


def needed_qty(per_board, boards, part):
    """Parts JLCPCB takes from stock: the quantity plus the attrition
    (lossNumber), at least the minimum for the placement (leastPatchNumber)."""
    qty = per_board * boards + int(part.get("lossNumber") or 0)
    return max(qty, int(part.get("leastPatchNumber") or 0))


def unit_price(part, qty):
    best = None
    for step in part.get("componentPrices") or []:
        if qty >= int(step.get("startNumber") or 0):
            best = step.get("productPrice")
    return best


def keyword_for(part):
    """Search key for the alternatives: the value of a passive (10kΩ,
    2.2uF...), otherwise the start of the part number (WM8524CGEDT ->
    WM8524)."""
    a = attrs(part)
    for k in KEY_ATTRS:
        if a.get(k):
            return a[k]
    m = re.match(r"[A-Za-z]*-?\d+", part.get("componentModelEn") or "")
    return m.group(0) if m else ""


def alternatives(part, need):
    ref = attrs(part)
    keys = {k: v for k, v in ref.items() if k in KEY_ATTRS}
    found = search({
        "keyword": keyword_for(part), "currentPage": 1, "pageSize": 50,
        "firstSortAccessId": part.get("firstSortAccessId"),
        "componentSpecificationList": [part.get("componentSpecificationEn")],
        "presaleType": "stock", "sortMode": "STOCK_SORT", "sortASC": "DESC"})
    scored = []
    for c in found:
        if c.get("componentCode") == part.get("componentCode"):
            continue
        # The service does not always apply the category filter
        if c.get("firstSortName") != part.get("firstSortName"):
            continue
        if int(c.get("stockCount") or 0) < need:
            continue
        a = attrs(c)
        if any(a.get(k) != v for k, v in keys.items()):
            continue
        same = sum(1 for k, v in ref.items() if a.get(k) == v)
        scored.append(((c.get("componentLibraryType") == "base",
                        bool(c.get("preferredComponentFlag")), same,
                        int(c.get("stockCount") or 0)), c))
    scored.sort(key=lambda s: s[0], reverse=True)
    return [c for _, c in scored[:ALTERNATIVES]]


def read_global_sourcing(path):
    codes = {}
    if not path or not os.path.exists(path):
        return codes
    with open(path, encoding="utf-8") as f:
        for line in f:
            note = line.split("#", 1)
            code = note[0].strip().upper()
            if code:
                codes[code] = note[1].strip() if len(note) > 1 else ""
    return codes


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--boards", type=int, default=5,
                    help="boards to assemble (default 5)")
    ap.add_argument("--global-sourcing", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "jlcpcb-global-sourcing.txt"),
        help="LCSC codes bought by JLCPCB Global Sourcing "
             "(default jlcpcb-global-sourcing.txt)")
    ap.add_argument("bom", help="JLCPCB BOM (Comment,Designator,Footprint,LCSC)")
    args = ap.parse_args()

    with open(args.bom, newline="", encoding="utf-8") as f:
        bom = list(csv.DictReader(f))

    global_codes = read_global_sourcing(args.global_sourcing)
    global_used = []
    errors = 0
    extended = 0
    total = 0.0
    report = []
    print("JLCPCB stock check for %d boards, %s\n"
          % (args.boards, time.strftime("%Y-%m-%d %H:%M")))
    print("%-8s %-10s %-9s %7s %9s %7s  %s" % (
        "STATUS", "LCSC", "TYPE", "NEED", "STOCK", "USD", "PART"))
    try:
        for b in bom:
            code = b["LCSC"].strip()
            refs = [r for r in b["Designator"].split(",") if r.strip()]
            label = "%s (%s)" % (b["Comment"], ",".join(refs))
            part = lookup(code)
            if part is None:
                status = "MISSING"
                if code.upper() in global_codes:
                    status = "GLOBAL"
                    global_used.append((code, label))
                    print("%-8s %-10s %-9s %7d %9s %7s  %s" % (
                        status, code, "-", len(refs) * args.boards, "-", "-",
                        label))
                    continue
                errors += 1
                print("%-8s %-10s %-9s %7d %9s %7s  %s" % (
                    status, code, "-", len(refs) * args.boards, "-", "-",
                    label))
                report.append((code, label, None, []))
                continue

            need = needed_qty(len(refs), args.boards, part)
            stock = int(part.get("stockCount") or 0)
            price = unit_price(part, need)
            if price is not None:
                total += price * need
            if lib_type(part) == "Extended":
                extended += 1
            if stock == 0:
                status = "OUT"
            elif stock < need:
                status = "SHORT"
            elif stock < need * LOW_FACTOR:
                status = "LOW"
            else:
                status = "OK"
            if status in ("OUT", "SHORT") and code.upper() in global_codes:
                status = "GLOBAL"
                global_used.append((code, label))
            print("%-8s %-10s %-9s %7d %9d %7s  %s" % (
                status, code, lib_type(part), need, stock,
                "%.2f" % (price * need) if price is not None else "-", label))
            if status in ("OUT", "SHORT"):
                errors += 1
                report.append((code, label, part, alternatives(part, need)))
    except ServiceError as e:
        print("\nError: the JLCPCB parts service did not answer (%s)" % e)
        return 2

    print("\n%d rows, %d Extended (setup fee each, Preferred and Basic have "
          "none), parts about %.2f USD" % (len(bom), extended, total))

    if global_used:
        print("\nGlobal Sourcing (choose it for these rows when ordering):")
        for code, label in global_used:
            note = global_codes.get(code.upper())
            print("  %s %s%s" % (code, label, "  # " + note if note else ""))

    if report:
        print("\nParts to change:")
        for code, label, part, alt in report:
            if part is None:
                print("\n  %s %s: not in the JLCPCB assembly library"
                      % (code, label))
                print("    search on jlcpcb.com/parts or use Global Sourcing")
                continue
            print("\n  %s %s: %s %s, stock %s" % (
                code, label, part.get("componentModelEn"),
                part.get("componentSpecificationEn"), part.get("stockCount")))
            print("    %s" % part.get("describe"))
            if alt:
                print("    candidates with enough stock (check the specs):")
                for c in alt:
                    print("      %-10s %-9s stock %-8s %s" % (
                        c.get("componentCode"), lib_type(c),
                        c.get("stockCount"), c.get("describe")))
            else:
                print("    no candidate found: search on jlcpcb.com/parts")
        print("\n%d part(s) cannot be assembled: change them in the "
              "schematic before running output_job.sh." % errors)
        return 1
    print("\nAll parts available.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
