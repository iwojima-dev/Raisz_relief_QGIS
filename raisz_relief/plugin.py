# -*- coding: utf-8 -*-
# This file is part of <Raisz Relief Plugin>.
#
# Copyright (C) 2026 <Maksim Boiko>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""Plugin entry point.

Registers the Processing provider (the flat parameter list stays available
in the Processing Toolbox, batch mode and the modeler) and adds the
plugin's own tabbed dialogs: two toolbar buttons and two entries in the
Raster menu, one per algorithm.
"""

import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import Qgis, QgsApplication, QgsMessageLog

from .i18n import N_, install_translator, remove_translator, tr
from .provider import RaiszReliefProvider

PLUGIN_DIR = os.path.dirname(__file__)
MENU = N_("&Raisz-style Relief")
LOG = "RaiszRelief"

# (algorithm id, button / menu text, icon file)
ENTRIES = [
    ("raisz_relief:landform", N_("Landform map…"), "icon_landform.png"),
    ("raisz_relief:classic", N_("Classic physiographic…"),
     "icon_classic.png"),
]


def _icon(name):
    for fn in (name, "icon.png", "icon.svg"):
        p = os.path.join(PLUGIN_DIR, "resources", fn)
        if os.path.exists(p):
            return QIcon(p)
    return QIcon()


class RaiszReliefPlugin:
    def __init__(self, iface):
        self.iface = iface
        # before anything builds its texts: the provider and the
        # algorithms translate their labels when they are created
        self.translator = install_translator()
        self.menu = tr(MENU)
        self.provider = None
        self.toolbar = None
        self.actions = []
        self.dialogs = {}            # algorithm id -> ReliefDialog

    def initProcessing(self):
        self.provider = RaiszReliefProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()
        self.toolbar = self.iface.addToolBar(tr("Raisz-style Relief"))
        self.toolbar.setObjectName("RaiszReliefToolbar")
        for alg_id, text, icon in ENTRIES:
            text = tr(text)
            act = QAction(_icon(icon), text, self.iface.mainWindow())
            act.setToolTip(tr("Raisz-style Relief: %s") % text.rstrip("…"))
            act.triggered.connect(
                lambda _=False, a=alg_id: self.open_dialog(a))
            self.toolbar.addAction(act)
            self.iface.addPluginToRasterMenu(self.menu, act)
            self.actions.append(act)

    def open_dialog(self, alg_id):
        dlg = self.dialogs.get(alg_id)
        if dlg is None:
            try:
                from .gui.relief_dialog import ReliefDialog
                dlg = ReliefDialog(self.iface, alg_id)
            except Exception as e:
                QgsMessageLog.logMessage(
                    "plugin dialog unavailable, opening Processing: %s" % e,
                    LOG, Qgis.MessageLevel.Warning)
                self._fallback(alg_id)
                return
            self.dialogs[alg_id] = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _fallback(self, alg_id):
        """If our dialog cannot be built, the standard Processing dialog
        still gives access to every parameter."""
        try:
            from processing import execAlgorithmDialog
            execAlgorithmDialog(alg_id, {})
        except Exception as e:
            QgsMessageLog.logMessage(
                "Could not open the Processing dialog: %s" % e,
                LOG, Qgis.MessageLevel.Warning)

    def unload(self):
        for dlg in self.dialogs.values():
            try:
                dlg.close()
                dlg.deleteLater()
            except Exception as e:
                QgsMessageLog.logMessage("closing dialog: %s" % e, LOG)
        self.dialogs = {}
        for act in self.actions:
            self.iface.removePluginRasterMenu(self.menu, act)
            if self.toolbar is not None:
                self.toolbar.removeAction(act)
        self.actions = []
        if self.toolbar is not None:
            self.toolbar.deleteLater()
            self.toolbar = None
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
        remove_translator(self.translator)
        self.translator = None
