#!/usr/bin/env python3
"""
Plots the Gerber, Gerber job and drill files of a board with the KiCad 5
pcbnew module, as "File > Plot" and "Generate Drill Files" in pcbnew do.

KiCad 5 is used on purpose: kicad-cli 7+ reads a KiCad 5 board but does not
support its zone fill strategy any more, so its copper planes could differ
from what pcbnew 5 shows.

Gerbers: the layers, options and output directory saved in the board plot
settings (pcbplotparams), with the Protel extensions when enabled there.
Drill:   Excellon, inch, decimal, absolute, PTH and NPTH in separate files,
         PostScript drill maps and the drill report (the same files the
         pcbnew dialog gave so far).

The zones are plotted as saved in the board. With --refill-zones they are
filled again first (the board file itself is never written).

Run with the KiCad 5 Python (see run_pcbnew.sh).

Usage: generate_gerbers.py [--refill-zones] <board.kicad_pcb>
"""
import os
import sys

import pcbnew


def copy_plot_options(src, dst):
    """PLOT_CONTROLLER starts from the default options, not from the board
    ones: copy every option that has a Get/Set pair without arguments."""
    for name in dir(src):
        if not name.startswith("Get") or not hasattr(dst, "Set" + name[3:]):
            continue
        try:
            getattr(dst, "Set" + name[3:])(getattr(src, name)())
        except (TypeError, ValueError, AttributeError):
            pass


def plot_gerbers(board, outdir):
    pctl = pcbnew.PLOT_CONTROLLER(board)
    popt = pctl.GetPlotOptions()
    copy_plot_options(board.GetPlotOptions(), popt)
    popt.SetOutputDirectory(outdir)
    popt.SetFormat(pcbnew.PLOT_FORMAT_GERBER)

    jobfile = popt.GetCreateGerberJobFile()
    job = pcbnew.GERBER_JOBFILE_WRITER(board) if jobfile else None

    layers = [l for l in popt.GetLayerSelection().Seq()
              if board.IsLayerEnabled(l)]
    # The Edge.Cuts layer is plotted alone, never added to the others
    if popt.GetExcludeEdgeLayer() is False:
        sys.exit("Error: 'Exclude PCB edge layer from other layers' must be "
                 "set in the board plot settings")

    written = []
    for layer in layers:
        name = board.GetLayerName(layer)
        suffix = name.replace(".", "_")
        pctl.SetLayer(layer)
        if not pctl.OpenPlotfile(suffix, pcbnew.PLOT_FORMAT_GERBER, name):
            sys.exit("Error: cannot open the plot file for %s" % name)
        plotted = pctl.GetPlotFileName()
        if not pctl.PlotLayer():
            sys.exit("Error: plotting %s failed" % name)
        pctl.ClosePlot()
        # OpenPlotfile already uses the Protel extension when it is enabled
        final = plotted
        if job is not None:
            job.AddGbrFile(layer, os.path.basename(final))
        written.append(os.path.basename(final))

    if job is not None:
        job_name = os.path.join(outdir, "%s-job.gbrjob" % board_stem(board))
        job.CreateJobFile(job_name)
        written.append(os.path.basename(job_name))
    return written


def plot_drill(board, outdir):
    drill = pcbnew.EXCELLON_WRITER(board)
    # mirror, minimal header, offset (no aux origin), merge PTH and NPTH
    drill.SetOptions(False, False, pcbnew.wxPoint(0, 0), False)
    # inch, decimal format (the precision is unused with decimal)
    drill.SetFormat(False, pcbnew.EXCELLON_WRITER.DECIMAL_FORMAT, 2, 4)
    drill.SetMapFileFormat(pcbnew.PLOT_FORMAT_POST)
    drill.CreateDrillandMapFilesSet(outdir, True, True)
    report = os.path.join(outdir, "%s-drl.rpt" % board_stem(board))
    drill.GenDrillReportFile(report)


def board_stem(board):
    return os.path.splitext(os.path.basename(board.GetFileName()))[0]


def main():
    args = sys.argv[1:]
    refill = "--refill-zones" in args
    args = [a for a in args if a != "--refill-zones"]
    if len(args) != 1:
        sys.exit("Usage: %s [--refill-zones] <board.kicad_pcb>" % sys.argv[0])

    pcb_file = os.path.abspath(args[0])
    board = pcbnew.LoadBoard(pcb_file)

    if refill:
        print("Filling the zones again...")
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())

    outdir = board.GetPlotOptions().GetOutputDirectory() or "."
    outdir = os.path.join(os.path.dirname(pcb_file), outdir)
    os.makedirs(outdir, exist_ok=True)

    written = plot_gerbers(board, outdir)
    plot_drill(board, outdir)
    print("Gerbers: %s" % ", ".join(written))
    print("Drill files and report written to '%s'." % outdir)


if __name__ == "__main__":
    main()
