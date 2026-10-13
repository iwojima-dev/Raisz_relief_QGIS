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
"""Interface language.

The source is English only. Other languages come from Qt translation
files in this folder, raisz_relief_<lang>.qm, chosen by the QGIS interface
language; with no file for it the plugin stays in English.

All strings share one translation context, "Relief" -- the one the
algorithms have always used in self.tr() -- so a phrase is translated once
wherever it appears.

  tr(text)  translate now. For a message with values, translate the
            template and format afterwards: tr("%d strips") % n. A string
            formatted first never matches the catalogue.
  N_(text)  only mark for translation. For lists built at import time,
            before the translator is installed (option lists, tab titles);
            they are passed through tr() where they are shown.

The .ts source is kept up to date with tools/update_translations.py in the
repository and compiled to .qm with lrelease (Qt Linguist).
"""

import os

from qgis.PyQt.QtCore import QCoreApplication, QLocale, QTranslator

CONTEXT = "Relief"
I18N_DIR = os.path.dirname(os.path.abspath(__file__))


def tr(text):
    return QCoreApplication.translate(CONTEXT, text)


def N_(text):
    return text


def tr_list(items):
    return [tr(s) for s in items]


def ui_language():
    """Two-letter code of the QGIS interface language."""
    loc = ""
    try:
        from qgis.core import QgsApplication
        loc = QgsApplication.locale()
    except Exception:
        loc = ""
    if not loc:
        try:
            from qgis.core import QgsSettings
            loc = QgsSettings().value("locale/userLocale", "") or ""
        except Exception:
            loc = ""
    if not loc:
        loc = QLocale.system().name()
    return str(loc)[:2].lower()


def install_translator():
    """Install the translator for the QGIS language; None when the plugin
    has no translation for it (English then stays)."""
    path = os.path.join(I18N_DIR, "raisz_relief_%s.qm" % ui_language())
    if not os.path.exists(path):
        return None
    translator = QTranslator()
    if not translator.load(path):
        return None
    QCoreApplication.installTranslator(translator)
    return translator


def remove_translator(translator):
    if translator is not None:
        QCoreApplication.removeTranslator(translator)
