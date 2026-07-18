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
"""Plugin entry point: registers the Processing provider and a menu item."""

import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsApplication

from .provider import RaiszReliefProvider

PLUGIN_DIR = os.path.dirname(__file__)


class RaiszReliefPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.action = None

    def initProcessing(self):
        self.provider = RaiszReliefProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()
        ipath = os.path.join(PLUGIN_DIR, "resources", "icon.png")
        if not os.path.exists(ipath):
            ipath = os.path.join(PLUGIN_DIR, "resources", "icon.svg")
        icon = QIcon(ipath)
        self.action = QAction(icon, "Raisz-style Relief",
                              self.iface.mainWindow())
        self.action.triggered.connect(self.open_dialog)
        self.iface.addPluginToMenu("&Raisz-style Relief", self.action)
        self.iface.addToolBarIcon(self.action)

    def open_dialog(self):
        try:
            from processing import execAlgorithmDialog
            execAlgorithmDialog("raisz_relief:landform", {})
        except Exception:
            try:
                from qgis.utils import iface as _iface
                _iface.actionShowProcessingToolbox().trigger()
            except Exception:
                pass

    def unload(self):
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
        if self.action is not None:
            self.iface.removePluginMenu("&Raisz-style Relief", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None
