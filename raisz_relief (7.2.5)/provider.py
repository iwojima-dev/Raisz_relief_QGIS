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
"""Processing provider of the "Raisz-style Relief" plugin."""

import os

from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider

from .algorithms.physiographic_algorithm import PhysiographicAlgorithm
from .algorithms.classic_algorithm import ClassicAlgorithm

PLUGIN_DIR = os.path.dirname(__file__)


class RaiszReliefProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        self.addAlgorithm(PhysiographicAlgorithm())
        self.addAlgorithm(ClassicAlgorithm())

    def id(self):
        return "raisz_relief"

    def name(self):
        return "Raisz-style Relief"

    def longName(self):
        return "Raisz-style Relief (physiographic method)"

    def icon(self):
        for ext in ("icon.png", "icon.svg"):
            path = os.path.join(PLUGIN_DIR, "resources", ext)
            if os.path.exists(path):
                return QIcon(path)
        return QgsProcessingProvider.icon(self)
