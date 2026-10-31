#!/usr/bin/env python3
"""
Writes the XML that eeschema's "Generate Bill of Materials" would write,
reading the KiCad 5 schematic files directly, so output_job.sh no longer
needs a manual export from Eeschema (and never uses a stale XML).

kicad-cli 7+ cannot do it: on a KiCad 5 .sch "sch export python-bom" writes
an XML with no components.

The hierarchy is followed from the root sheet, so a sheet file that is not
used by the project (e.g. an old sheet left in the folder) is ignored. The
reference of each component is taken from its "AR Path" for that sheet
instance, as eeschema does; power symbols (#...) are skipped.

Only <components> is written, with value, footprint, datasheet and the
user fields: that is all generate_bom.py reads.

Only the standard library is used, so it runs with any Python 3.

Usage: sch2bomxml.py <root.sch> <output.xml>
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

FIELD_RE = re.compile(
    r'^F (\d+) "((?:[^"\\]|\\.)*)"[^\n]*?(?:"((?:[^"\\]|\\.)*)")?[ \t]*$',
    re.M)


def unescape(text):
    return text.replace('\\"', '"').replace('\\\\', '\\')


def read_sheet(path, sheet_path, comps, stack):
    if path in stack:
        sys.exit("Error: recursive sheet '%s'" % path)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    base = os.path.dirname(path)

    for block in re.findall(r'^\$Comp\n(.*?)^\$EndComp', text, re.S | re.M):
        fields = {}
        named = {}
        for m in FIELD_RE.finditer(block):
            fields[int(m.group(1))] = unescape(m.group(2))
            if m.group(3):
                named[unescape(m.group(3))] = unescape(m.group(2))
        ref = fields.get(0, "")
        unit = re.search(r'^U \d+ \d+ ([0-9A-Fa-f]+)', block, re.M)
        if unit:
            ar = re.search(r'^AR Path="%s/%s" Ref="([^"]+)"'
                           % (re.escape(sheet_path), unit.group(1)),
                           block, re.M)
            if ar:
                ref = ar.group(1)
        if not ref or ref.startswith("#"):
            continue
        if "?" in ref:
            sys.exit("Error: component '%s' in %s is not annotated"
                     % (ref, path))
        comp = {
            "value": fields.get(1, ""),
            "footprint": fields.get(2, ""),
            "datasheet": fields.get(3, ""),
            "fields": named,
            "sheet": path,
        }
        # Multi-unit parts appear once per unit: keep the first one, but
        # two different parts with the same reference are an error
        old = comps.get(ref)
        if old is None:
            comps[ref] = comp
        elif (old["value"], old["footprint"]) != (comp["value"],
                                                  comp["footprint"]):
            sys.exit("Error: reference %s is used twice (%s: %s, %s: %s)"
                     % (ref, old["sheet"], old["value"],
                        path, comp["value"]))

    for block in re.findall(r'^\$Sheet\n(.*?)^\$EndSheet', text, re.S | re.M):
        stamp = re.search(r'^U ([0-9A-Fa-f]+)', block, re.M).group(1)
        name = re.search(r'^F1 "([^"]+)"', block, re.M).group(1)
        read_sheet(os.path.join(base, name), "%s/%s" % (sheet_path, stamp),
                   comps, stack + [path])


def ref_key(ref):
    m = re.match(r'(.*?)(\d*)$', ref)
    return (m.group(1), int(m.group(2) or 0))


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: %s <root.sch> <output.xml>" % sys.argv[0])
    root_sch, xml_file = sys.argv[1], sys.argv[2]

    comps = {}
    read_sheet(root_sch, "", comps, [])

    root = ET.Element("export", version="D")
    design = ET.SubElement(root, "design")
    ET.SubElement(design, "source").text = os.path.abspath(root_sch)
    ET.SubElement(design, "tool").text = os.path.basename(sys.argv[0])
    components = ET.SubElement(root, "components")
    for ref in sorted(comps, key=ref_key):
        comp = comps[ref]
        node = ET.SubElement(components, "comp", ref=ref)
        ET.SubElement(node, "value").text = comp["value"]
        if comp["footprint"]:
            ET.SubElement(node, "footprint").text = comp["footprint"]
        if comp["datasheet"] and comp["datasheet"] != "~":
            ET.SubElement(node, "datasheet").text = comp["datasheet"]
        if comp["fields"]:
            fields = ET.SubElement(node, "fields")
            for name, value in comp["fields"].items():
                ET.SubElement(fields, "field", name=name).text = value
    ET.indent(root) if hasattr(ET, "indent") else None
    ET.ElementTree(root).write(xml_file, encoding="UTF-8",
                               xml_declaration=True)
    print("BOM XML: %d components written to '%s'." % (len(comps), xml_file))


if __name__ == "__main__":
    main()
