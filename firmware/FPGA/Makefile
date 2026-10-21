# =============================================================================
# Makefile -- iCE40UP5K FPGA build (VHDL via GHDL + Yosys + nextpnr)
#
# Requirements:
#   ghdl              https://github.com/ghdl/ghdl
#   yosys             https://github.com/YosysHQ/yosys
#   ghdl-yosys-plugin https://github.com/ghdl/ghdl-yosys-plugin
#   nextpnr-ice40     https://github.com/YosysHQ/nextpnr
#   icestorm          https://github.com/YosysHQ/icestorm  (icepack, iceprog)
#   openFPGALoader    https://github.com/trabucayre/openFPGALoader
#
# Commodore 64 expansion port, VERA only (no GeoRAM):
#
#   make               -- build C6502_Interface.bin
#   make flash         -- flash the bitstream via openFPGALoader
#   make flash-iceprog -- flash the bitstream via iceprog (FTDI FT2232H)
#
#   make doc           -- regenerate PDF documentation
#   make clean         -- remove all generated files
# =============================================================================

TOP      = C6502_Interface
PCF      = board-pin-mapping.pcf
DEVICE   = up5k
PKG      = sg48
DOC      = build-and-programming-guide

VHDL_SRCS = \
    C6502_Interface.vhd

GHDL_STD = --std=08

.PHONY: all flash flash-iceprog doc clean

all: $(TOP).bin

# =============================================================================
# Synthesis, place & route, pack
# =============================================================================
$(TOP).json: $(VHDL_SRCS)
	yosys -m ghdl -p \
	    "ghdl $(GHDL_STD) $(VHDL_SRCS) -e $(TOP); \
	     synth_ice40 -top $(TOP) -json $@"

$(TOP).asc: $(TOP).json $(PCF)
	nextpnr-ice40 \
	    --$(DEVICE) \
	    --package $(PKG) \
	    --json $< \
	    --pcf  $(PCF) \
	    --asc  $@

$(TOP).bin: $(TOP).asc
	icepack $< $@

# =============================================================================
# Flash programming
# =============================================================================
flash: $(TOP).bin
	openFPGALoader -b ice40_generic $<

flash-iceprog: $(TOP).bin
	iceprog $<

# =============================================================================
# Documentation
# =============================================================================
doc: $(DOC).pdf

$(DOC).pdf: $(DOC).tex
	pdflatex -interaction=nonstopmode $<
	pdflatex -interaction=nonstopmode $<

# =============================================================================
# Cleanup
# =============================================================================
clean:
	$(RM) $(TOP).json $(TOP).asc $(TOP).bin
	$(RM) $(DOC).aux $(DOC).log $(DOC).out $(DOC).toc $(DOC).pdf
