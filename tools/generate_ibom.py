#!/usr/bin/env python3
"""Generate the interactive BOM (InteractiveHtmlBom plugin) without pcbnew's GUI.

The plugin's own command line ignores ibom.config.ini (it is read only by
its settings dialog), so the settings would have to be repeated as options.
This script loads ibom.config.ini from the board's directory, exactly as the
plugin started from pcbnew does, and writes the BOM where that file says
(ibom/ibom.html for this board), without opening a browser.

Needs the KiCad 5 pcbnew module: run it through run_pcbnew.sh.
The plugin is looked for in ~/.kicad/scripting/plugins/InteractiveHtmlBom
(IBOM_PLUGIN=/path/to/InteractiveHtmlBom to use another copy).

usage: ./run_pcbnew.sh tools/generate_ibom.py BOARD.kicad_pcb
"""
import os
import sys

os.environ.setdefault('INTERACTIVE_HTML_BOM_NO_DISPLAY', '1')
plugin = os.environ.get('IBOM_PLUGIN', os.path.expanduser('~/.kicad/scripting/plugins/InteractiveHtmlBom'))
if not os.path.isdir(os.path.join(plugin, 'InteractiveHtmlBom')):
    sys.exit('InteractiveHtmlBom plugin not found in %s (set IBOM_PLUGIN)' % plugin)
sys.path.insert(0, plugin)

import wx  # noqa: E402  the plugin reads its ini through wx.FileConfig
# wx.FileConfig needs an application object; a console one needs no display
app = wx.AppConsole()
if hasattr(wx, 'DisableAsserts'):
    wx.DisableAsserts()

from InteractiveHtmlBom.core import ibom  # noqa: E402
from InteractiveHtmlBom.core.config import Config  # noqa: E402
from InteractiveHtmlBom.ecad import get_parser_by_extension  # noqa: E402
from InteractiveHtmlBom.version import version  # noqa: E402

board = os.path.abspath(sys.argv[1])
config = Config(version, os.path.dirname(board))
if not os.path.isfile(config.local_config_file):
    sys.exit('%s not found' % config.local_config_file)
config.load_from_ini()
config.open_browser = False
logger = ibom.Logger(cli=True)
parser = get_parser_by_extension(board, config, logger)
ibom.main(parser, config, logger)
