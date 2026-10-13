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
"""The plugin's own dialog: parameters sorted into tabs, run in background.

The Processing algorithms stay exactly as they are -- the flat parameter
list remains available in the Processing Toolbox, batch mode and the
graphical modeler. This dialog is a second front end to the very same
algorithms:

  * fields are built from the algorithm's parameterDefinitions() at run
    time, with the native Processing widgets (layer pickers, field
    pickers, file destinations, spin boxes with the declared ranges), so
    labels, defaults and choice lists can never disagree with the
    algorithm;
  * only the placement into tabs is ours (gui/layout.py), and anything the
    layout does not mention lands in an "Other" tab;
  * the run goes through QgsProcessingAlgRunnerTask, i.e. the regular
    Processing machinery in a background thread, with a progress bar, a
    log and cancellation -- QGIS stays responsive;
  * values are remembered between sessions (QgsSettings);
  * fields the current settings leave unused are greyed out, never hidden
    (rules in gui/layout.py, DEPENDENCIES);
  * "Analyze DEM" reads the DEM quickly and suggests a contour interval
    before the first render (gui/analyze.py).
"""

import json
import math
import os

from qgis.PyQt.QtCore import Qt, QTimer, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (QApplication, QComboBox, QDialog,
                                 QDialogButtonBox, QFormLayout, QHBoxLayout,
                                 QInputDialog,
                                 QFrame, QGroupBox, QLabel, QMessageBox,
                                 QPlainTextEdit, QProgressBar, QPushButton,
                                 QScrollArea, QSplitter, QTabWidget,
                                 QTextBrowser, QVBoxLayout, QWidget)
from qgis.core import (Qgis, QgsApplication, QgsMapLayer, QgsMessageLog,
                       QgsProcessingAlgRunnerTask, QgsProcessingContext,
                       QgsProcessingFeedback, QgsProcessingParameterDefinition,
                       QgsProcessingParameters, QgsProject, QgsSettings)
from qgis.gui import (QgsGui, QgsProcessingGui,
                      QgsProcessingParameterWidgetContext)

from ..i18n import tr
from . import presets as presets_mod
from .layout import plan_tabs, DEPENDENCIES

LOG = "RaiszRelief"
SETTINGS_ROOT = "RaiszRelief/dialog"
PRESETS_ROOT = "RaiszRelief/presets"

# Scoped enum forms (required by Qt6 builds; QGIS >= 3.40 has them natively)
GUI_STANDARD = QgsProcessingGui.WidgetType.Standard
QUEUED = Qt.ConnectionType.QueuedConnection
SB = QDialogButtonBox.StandardButton
MSG_SUCCESS = Qgis.MessageLevel.Success
MSG_WARNING = Qgis.MessageLevel.Warning
MSG_CRITICAL = Qgis.MessageLevel.Critical
MB = QMessageBox.StandardButton
WAIT_CURSOR = Qt.CursorShape.WaitCursor
# same enum as FLAG_ADVANCED in algorithms/_base.py
FLAG_HIDDEN = QgsProcessingParameterDefinition.Flag.Hidden


def _log(msg, level=Qgis.MessageLevel.Info):
    QgsMessageLog.logMessage(str(msg), LOG, level)


# ----------------------------------------------------------------- feedback

class _Feedback(QgsProcessingFeedback):
    """Processing feedback that also forwards text to the dialog.

    The algorithm runs in a worker thread and calls these methods there;
    the signal is connected with a queued connection, so the text reaches
    the log widget in the GUI thread."""

    line = pyqtSignal(str, int)      # text, level: 0 info, 1 warning, 2 error

    def pushInfo(self, info):
        super().pushInfo(info)
        self.line.emit(info, 0)

    def pushCommandInfo(self, info):
        super().pushCommandInfo(info)
        self.line.emit(info, 0)

    def pushDebugInfo(self, info):
        super().pushDebugInfo(info)
        self.line.emit(info, 0)

    def pushConsoleInfo(self, info):
        super().pushConsoleInfo(info)
        self.line.emit(info, 0)

    def pushWarning(self, warning):
        super().pushWarning(warning)
        self.line.emit(warning, 1)

    def reportError(self, error, fatalError=False):
        super().reportError(error, fatalError)
        self.line.emit(error, 2)

    def setProgressText(self, text):
        super().setProgressText(text)
        self.line.emit(text, 0)


# ---------------------------------------------------------- value plumbing

def _get_value(wrapper):
    """Read a wrapper's current value (public API, protected as fallback)."""
    for meth in ("parameterValue", "widgetValue"):
        f = getattr(wrapper, meth, None)
        if callable(f):
            try:
                return f()
            except Exception as e:
                _log("reading %s via %s: %s"
                     % (wrapper.parameterDefinition().name(), meth, e))
    return None


def _set_value(wrapper, value, context):
    for meth in ("setParameterValue", "setWidgetValue"):
        f = getattr(wrapper, meth, None)
        if callable(f):
            try:
                f(value, context)
                return True
            except Exception as e:
                _log("writing %s via %s: %s"
                     % (wrapper.parameterDefinition().name(), meth, e))
    return False


def _encode(value):
    """Value -> JSON-able form for QgsSettings, or a sentinel to skip."""
    if isinstance(value, QgsMapLayer):
        return value.id()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return _SKIP


_SKIP = object()


# ------------------------------------------------------------------- dialog

class ReliefDialog(QDialog):
    """Tabbed front end for one Raisz-style Relief algorithm."""

    def __init__(self, iface, alg_id, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.alg_id = alg_id
        self.alg = QgsApplication.processingRegistry().algorithmById(alg_id)
        if self.alg is None:
            raise RuntimeError("algorithm not found: %s" % alg_id)

        self._wrappers = {}          # name -> wrapper (keeps them alive)
        self._dem_cache = None       # (key, read_dem result) for presets
        self._fields = {}            # name -> (widget, label, tooltip)
        self._task = None
        self._feedback = None
        self._context = None
        self._pctx = QgsProcessingContext()
        self._pctx.setProject(QgsProject.instance())

        self.setWindowTitle(tr("Raisz-style Relief — %s")
                            % self.alg.displayName())
        self.setMinimumSize(880, 640)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)

        self._build_ui()
        self._load_settings()
        self._refresh_dependencies()

    # -- construction ---------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.addLayout(self._build_preset_row())

        hsplit = QSplitter(Qt.Orientation.Horizontal, self)
        self.tabs = QTabWidget(hsplit)
        self.help = QTextBrowser(hsplit)
        self.help.setOpenExternalLinks(True)
        self.help.setHtml(self.alg.shortHelpString() or "")
        hsplit.setStretchFactor(0, 3)
        hsplit.setStretchFactor(1, 1)

        vsplit = QSplitter(Qt.Orientation.Vertical, self)
        vsplit.addWidget(hsplit)
        self.log = QPlainTextEdit(vsplit)
        self.log.setReadOnly(True)
        self.log.setPlaceholderText(tr("Processing log appears here."))
        vsplit.setStretchFactor(0, 4)
        vsplit.setStretchFactor(1, 1)
        root.addWidget(vsplit, 1)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        btns = QDialogButtonBox(self)
        self.btn_run = btns.addButton(tr("Run"),
                                      QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_cancel = btns.addButton(SB.Cancel)
        self.btn_cancel.setEnabled(False)
        self.btn_close = btns.addButton(SB.Close)
        self.btn_reset = btns.addButton(SB.RestoreDefaults)
        self.btn_proc = QPushButton(tr("Open in Processing…"), self)
        self.btn_proc.setToolTip(tr(
            "Open the standard Processing dialog with these values -- "
            "useful for batch runs or saving to the history."))
        btns.addButton(self.btn_proc, QDialogButtonBox.ButtonRole.ActionRole)
        self.btn_analyze = QPushButton(tr("Analyze DEM"), self)
        self.btn_analyze.setToolTip(tr(
            "Read the DEM quickly and suggest a contour interval for it, "
            "before the first render."))
        btns.addButton(self.btn_analyze,
                       QDialogButtonBox.ButtonRole.ActionRole)
        # buttons are wired explicitly: the box must not close the dialog
        self.btn_run.clicked.connect(self.run)
        self.btn_cancel.clicked.connect(self.cancel)
        self.btn_close.clicked.connect(self.close)
        self.btn_reset.clicked.connect(self.restore_defaults)
        self.btn_proc.clicked.connect(self.open_in_processing)
        self.btn_analyze.clicked.connect(self.analyze_dem)
        root.addWidget(btns)

        self._build_tabs()

    def _make_wrapper(self, param, wctx):
        reg = QgsGui.processingGuiRegistry()
        try:
            w = reg.createParameterWidgetWrapper(param, GUI_STANDARD)
        except Exception as e:
            _log("no widget for %s: %s" % (param.name(), e))
            w = None
        if w is None:
            return None, None, None
        try:
            w.setWidgetContext(wctx)
        except Exception as e:
            _log("widget context for %s: %s" % (param.name(), e))
        widget = w.createWrappedWidget(self._pctx)
        label = w.createWrappedLabel()
        return w, widget, label

    def _widget_context(self):
        wctx = QgsProcessingParameterWidgetContext()
        for meth, arg in (("setMapCanvas", self.iface.mapCanvas()),
                          ("setMessageBar", self.iface.messageBar()),
                          ("setProject", QgsProject.instance())):
            try:
                getattr(wctx, meth)(arg)
            except Exception as e:
                _log("widget context %s: %s" % (meth, e))
        return wctx

    def _build_tabs(self):
        wctx = self._widget_context()
        params = {p.name(): p for p in self.alg.parameterDefinitions()
                  if not (p.flags() & FLAG_HIDDEN)}
        plan, rest = plan_tabs(list(params))
        if rest:
            _log("parameters outside the tab layout: %s" % ", ".join(rest))

        for tab_title, boxes in plan:
            page = QWidget()
            pl = QVBoxLayout(page)
            for box_title, names in boxes:
                box = QGroupBox(tr(box_title), page)
                form = QFormLayout(box)
                form.setFieldGrowthPolicy(
                    QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
                for n in names:
                    p = params[n]
                    w, widget, label = self._make_wrapper(p, wctx)
                    if w is None:
                        form.addRow(QLabel(p.description()),
                                    QLabel(tr("(set it in the Processing "
                                              "dialog)")))
                        continue
                    self._wrappers[n] = w
                    tip = ""
                    try:
                        tip = p.help() or ""
                    except Exception:
                        tip = ""
                    self._fields[n] = (widget, label, tip)
                    if tip:
                        widget.setToolTip(tip)
                        if label is not None:
                            label.setToolTip(tip)
                    if label is not None:
                        label.setWordWrap(True)
                        form.addRow(label, widget)
                    else:
                        form.addRow(widget)      # checkbox carries its text
                pl.addWidget(box)
            pl.addStretch(1)
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.Shape.NoFrame)
            area.setWidget(page)
            self.tabs.addTab(area, tr(tab_title))

        # dependencies between widgets (a label field follows its layer)
        all_w = list(self._wrappers.values())
        for w in all_w:
            try:
                w.postInitialize(all_w)
            except Exception as e:
                _log("postInitialize %s: %s"
                     % (w.parameterDefinition().name(), e))

        # greying of fields the current settings make irrelevant
        self._params = params
        hooked = 0
        for w in all_w:
            sig = getattr(w, "widgetValueHasChanged", None)
            if sig is not None:
                try:
                    sig.connect(self._refresh_dependencies)
                    hooked += 1
                except Exception as e:
                    _log("change signal of %s: %s"
                         % (w.parameterDefinition().name(), e))
        if not hooked:
            # no change signal in this QGIS build: re-check twice a second
            self._dep_timer = QTimer(self)
            self._dep_timer.timeout.connect(self._refresh_dependencies)
            self._dep_timer.start(500)
        self.tabs.currentChanged.connect(self._refresh_dependencies)

    # -- values ---------------------------------------------------------
    def _refresh_dependencies(self, *_args):
        """Grey out fields the algorithm does not read with the current
        settings (gui/layout.py DEPENDENCIES). Greyed, never hidden: the
        value still reaches the algorithm, and a wrong rule cannot make a
        field unreachable."""
        values = {}

        def v(name):
            if name not in values:
                w = self._wrappers.get(name)
                values[name] = _get_value(w) if w is not None else None
            return values[name]

        def nopt(name):
            p = getattr(self, "_params", {}).get(name)
            try:
                return len(p.options())
            except Exception:
                return 0

        inactive = {}
        for names, test, reason in DEPENDENCIES:
            try:
                active = bool(test(v, nopt))
            except Exception as e:
                _log("dependency rule (%s): %s" % (reason, e))
                active = True
            if not active:
                for n in names:
                    inactive.setdefault(n, reason)
        for n, (widget, label, tip) in self._fields.items():
            reason = inactive.get(n)
            on = reason is None
            widget.setEnabled(on)
            if label is not None:
                label.setEnabled(on)
            note = tip if on else (
                tr("Not used with the current settings: %s.") % tr(reason)
                + ("\n\n" + tip if tip else ""))
            widget.setToolTip(note)
            if label is not None:
                label.setToolTip(note)

    def parameters(self):
        out = {}
        for n, w in self._wrappers.items():
            out[n] = _get_value(w)
        return out

    def restore_defaults(self):
        for n, w in self._wrappers.items():
            _set_value(w, w.parameterDefinition().defaultValue(), self._pctx)
        self._refresh_dependencies()

    def _key(self, name):
        return "%s/%s/%s" % (SETTINGS_ROOT, self.alg_id.replace(":", "_"),
                             name)

    def _save_settings(self):
        s = QgsSettings()
        for n, v in self.parameters().items():
            enc = _encode(v)
            if enc is _SKIP:
                continue
            s.setValue(self._key(n), json.dumps(enc))
        s.setValue(self._key("_geometry"), self.saveGeometry())

    def _load_settings(self):
        s = QgsSettings()
        for n, w in self._wrappers.items():
            raw = s.value(self._key(n), None)
            if raw is None:
                continue
            try:
                v = json.loads(raw)
            except (TypeError, ValueError) as e:
                _log("stored value of %s unreadable: %s" % (n, e))
                continue
            if isinstance(v, str) and v and w.parameterDefinition().type() in (
                    "raster", "vector", "source", "layer"):
                # a stored layer that is no longer in the project is dropped
                if QgsProject.instance().mapLayer(v) is None:
                    continue
            _set_value(w, v, self._pctx)
        geo = s.value(self._key("_geometry"), None)
        if geo is not None:
            try:
                self.restoreGeometry(geo)
            except Exception as e:
                _log("restoring window geometry: %s" % e)

    # -- presets --------------------------------------------------------
    def _build_preset_row(self):
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Relief preset:"), self))
        self.preset_box = QComboBox(self)
        self.preset_box.setMinimumContentsLength(28)
        self.preset_box.currentIndexChanged.connect(self._preset_selected)
        row.addWidget(self.preset_box, 1)
        self.btn_preset = QPushButton(tr("Apply"), self)
        self.btn_preset.setToolTip(tr(
            "Fill the stroke and relief fields from the preset. The DEM, "
            "output, layers, fill and sheet are not touched; every field "
            "stays editable afterwards."))
        self.btn_preset.clicked.connect(self.apply_preset)
        row.addWidget(self.btn_preset)
        self.btn_preset_save = QPushButton(tr("Save as…"), self)
        self.btn_preset_save.setToolTip(tr(
            "Save the current stroke and relief fields as your own preset."))
        self.btn_preset_save.clicked.connect(self.save_preset)
        row.addWidget(self.btn_preset_save)
        self.btn_preset_del = QPushButton(tr("Delete"), self)
        self.btn_preset_del.clicked.connect(self.delete_preset)
        row.addWidget(self.btn_preset_del)
        self._fill_preset_box()
        return row

    def _user_presets(self):
        s = QgsSettings()
        s.beginGroup(PRESETS_ROOT)
        try:
            names = sorted(s.childKeys(), key=str.lower)
        finally:
            s.endGroup()
        out = {}
        for n in names:
            v = presets_mod.from_json(s.value("%s/%s" % (PRESETS_ROOT, n)))
            if v is not None:
                out[n] = v
        return out

    def _fill_preset_box(self, select=None):
        box = self.preset_box
        box.blockSignals(True)
        box.clear()
        for p in presets_mod.BUILTIN:
            box.addItem(tr(p["title"]), ("builtin", p["id"]))
            box.setItemData(box.count() - 1, tr(p["description"]),
                            Qt.ItemDataRole.ToolTipRole)
        users = self._user_presets()
        if users:
            box.insertSeparator(box.count())
            for n in users:
                box.addItem(n, ("user", n))
        if select is not None:
            for i in range(box.count()):
                if box.itemData(i) == select:
                    box.setCurrentIndex(i)
                    break
        box.blockSignals(False)
        self._preset_selected()

    def _preset_selected(self, *_args):
        data = self.preset_box.currentData()
        kind = data[0] if data else None
        self.btn_preset_del.setEnabled(kind == "user")
        self.btn_preset.setEnabled(kind is not None)
        tip = ""
        if kind == "builtin":
            tip = tr(presets_mod.builtin(data[1])["description"])
        self.preset_box.setToolTip(tip)

    def _read_dem_cached(self, path):
        """Reduced DEM read for presets and analysis, cached per file and
        working size so applying presets one after another is instant."""
        from . import analyze
        vals = self.parameters()
        landform = "MAX_PX" in self._wrappers
        try:
            max_px = max(int(float(vals.get("MAX_PX") or 2000)), 100)
        except (TypeError, ValueError):
            max_px = 2000
        side = min(max_px, 3000) if landform else 2500
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        key = (path, mtime, side)
        if self._dem_cache is None or self._dem_cache[0] != key:
            self._dem_cache = (key, analyze.read_dem(path, side))
        d = self._dem_cache[1]
        W, H = d["size_native"]
        if landform:
            mpp_target = d["mpp_native"] * max(1.0, max(W, H) / float(max_px))
        else:
            mpp_target = d["mpp_native"]
        return d, mpp_target

    def _scene_stats(self, d, mpp_target, min_slope):
        from . import analyze
        vals = self.parameters()
        smooth = 0.0
        if "MAX_PX" in self._wrappers:
            try:
                smooth = float(vals.get("SMOOTH") or 1.6)
            except (TypeError, ValueError):
                smooth = 1.6
            smooth *= mpp_target / d["mpp_read"]
        return analyze.scene_stats(d["z"], d["valid"], d["mpp_read"],
                                   smooth, min_slope)

    def apply_preset(self):
        from . import analyze
        data = self.preset_box.currentData()
        if not data:
            return
        kind, key = data
        if kind == "builtin":
            values = presets_mod.builtin(key)["values"]
            title = tr(presets_mod.builtin(key)["title"])
        else:
            values = self._user_presets().get(key)
            title = key
            if values is None:
                return
        declared = set(self._wrappers)
        defaults = {n: w.parameterDefinition().defaultValue()
                    for n, w in self._wrappers.items()}
        mpp = interval_for = None
        needs_dem = "BASE_SCALE_M" in values or "BENCH_PX" in values
        path = self._dem_path() if needs_dem else None
        if path:
            # the interval is set for the typical hachured ground, taken
            # at the default 4 deg threshold even when the preset lowers
            # it: a 2 deg threshold would halve the interval and turn the
            # framework of a shield volcano into a dense mesh
            min_slope = float(defaults.get("MIN_SLOPE") or 4.0)
            QApplication.setOverrideCursor(WAIT_CURSOR)
            try:
                d, mpp = self._read_dem_cached(path)
                stats = self._scene_stats(d, mpp, min_slope)
                s = stats["slope_med"]

                def _interval(bench):
                    if s <= 0:
                        return None
                    return analyze.nice_interval(
                        bench * math.tan(math.radians(s)) * mpp)
                interval_for = _interval
            except Exception as e:
                _log("preset: reading the DEM: %s" % e, MSG_WARNING)
                self._append(tr("DEM analysis failed: %s") % e, 2)
                mpp = interval_for = None
            finally:
                QApplication.restoreOverrideCursor()
        fields, notes = presets_mod.resolve(values, defaults, declared,
                                            mpp, interval_for)
        for name, v in fields.items():
            _set_value(self._wrappers[name], v, self._pctx)
        self._refresh_dependencies()
        self._append("")
        self._append(tr("Preset \u201c%s\u201d applied.") % title)
        if "BASE_SCALE" in fields and "BASE_SCALE_M" in values and mpp:
            self._append("  " + tr("local basis %d px (%.1f km on the ground)")
                         % (fields["BASE_SCALE"],
                            fields["BASE_SCALE"] * mpp / 1000.0))
        if "INTERVAL" in fields and "BENCH_PX" in values:
            self._append("  " + tr("contour interval %g m (contours about "
                                   "%.0f px apart on the hachured ground)")
                         % (fields["INTERVAL"], values["BENCH_PX"]))
        if notes:
            self._append(tr("Choose a DEM and apply again to set the "
                            "local basis and the contour interval for it."),
                         1)

    def save_preset(self):
        name, ok = QInputDialog.getText(self, self.windowTitle(),
                                        tr("Preset name:"))
        name = (name or "").strip().replace("/", "-").replace("\\", "-")
        if not ok or not name:
            return
        users = self._user_presets()
        if name in users and QMessageBox.question(
                self, self.windowTitle(),
                tr("A preset named \u201c%s\u201d exists. Replace it?") % name
        ) != MB.Yes:
            return
        values = presets_mod.capture(self.parameters(), set(self._wrappers))
        QgsSettings().setValue("%s/%s" % (PRESETS_ROOT, name),
                               presets_mod.to_json(values))
        self._fill_preset_box(select=("user", name))
        self._append(tr("Preset \u201c%s\u201d saved.") % name)

    def delete_preset(self):
        data = self.preset_box.currentData()
        if not data or data[0] != "user":
            return
        if QMessageBox.question(
                self, self.windowTitle(),
                tr("Delete the preset \u201c%s\u201d?") % data[1]) != MB.Yes:
            return
        QgsSettings().remove("%s/%s" % (PRESETS_ROOT, data[1]))
        self._fill_preset_box()

    # -- DEM analysis ---------------------------------------------------
    def _dem_path(self):
        """File path of the DEM currently chosen, or None."""
        w = self._wrappers.get("DEM")
        if w is None:
            return None
        value = _get_value(w)
        if value in (None, ""):
            return None
        layer = None
        try:
            layer = QgsProcessingParameters.parameterAsRasterLayer(
                w.parameterDefinition(), {"DEM": value}, self._pctx)
        except Exception as e:
            _log("resolving the DEM: %s" % e)
        if layer is not None:
            return layer.source()
        if isinstance(value, QgsMapLayer):
            return value.source()
        return str(value)

    def analyze_dem(self):
        """Scene statistics and a suggested contour interval (gui/analyze.py),
        computed from a reduced read of the DEM before any render."""
        from . import analyze

        path = self._dem_path()
        if not path:
            QMessageBox.information(self, self.windowTitle(),
                                    tr("Choose a DEM first."))
            return
        vals = self.parameters()

        def num(name, default):
            try:
                return float(vals.get(name))
            except (TypeError, ValueError):
                return float(default)

        interval = num("INTERVAL", 40.0)
        rel_scale = bool(vals.get("REL_SCALE"))
        QApplication.setOverrideCursor(WAIT_CURSOR)
        try:
            d, mpp_target = self._read_dem_cached(path)
            stats = self._scene_stats(d, mpp_target, num("MIN_SLOPE", 4.0))
            rec = analyze.recommend(stats, mpp_target, interval, rel_scale)
            lines = analyze.report_lines(
                stats, rec, mpp_target, interval, d["geographic"],
                approximate=d["mpp_read"] > 1.05 * mpp_target)
        except Exception as e:
            _log("DEM analysis: %s" % e, MSG_WARNING)
            self._append(tr("DEM analysis failed: %s") % e, 2)
            return
        finally:
            QApplication.restoreOverrideCursor()

        self._append("")
        for line in lines:
            self._append(line)
        pid = presets_mod.suggest(stats)
        if pid:
            self._append("  " + tr("Suggested preset: \u201c%s\u201d (select it "
                                   "above and press Apply).")
                         % tr(presets_mod.builtin(pid)["title"]))
        new = rec["interval"]
        w = self._wrappers.get("INTERVAL")
        if (new is None or w is None or rel_scale
                or abs(float(new) - interval) < 1e-9):
            return
        new = max(float(new), 0.5)       # the parameter's minimum
        ans = QMessageBox.question(
            self, self.windowTitle(),
            tr("Set the contour interval to %g m (now %g m)?\n\n"
               "Contours would sit about %.0f px apart at the median slope.")
            % (new, interval, rec["bench_rec"] or 0.0),
            MB.Yes | MB.No, MB.Yes)
        if ans == MB.Yes and _set_value(w, new, self._pctx):
            self._append(tr("Contour interval set to %g m.") % new)

    # -- running --------------------------------------------------------
    def _set_running(self, running):
        self.btn_run.setEnabled(not running)
        self.btn_proc.setEnabled(not running)
        self.btn_reset.setEnabled(not running)
        self.btn_analyze.setEnabled(not running)
        self.btn_preset.setEnabled(not running)
        self.btn_cancel.setEnabled(running)
        self.tabs.setEnabled(not running)

    def _append(self, text, level=0):
        prefix = ("", tr("WARNING: "), tr("ERROR: "))[max(0, min(level, 2))]
        self.log.appendPlainText(prefix + str(text))

    def run(self):
        params = self.parameters()
        ok, msg = self.alg.checkParameterValues(params, self._pctx)
        if not ok:
            QMessageBox.warning(self, self.windowTitle(), msg)
            return
        self._save_settings()

        self.log.clear()
        self.progress.setValue(0)
        self._feedback = _Feedback()
        self._feedback.line.connect(self._append, QUEUED)
        self._feedback.progressChanged.connect(self._on_progress, QUEUED)
        try:
            from processing.tools import dataobjects
            self._context = dataobjects.createContext(self._feedback)
        except Exception as e:
            _log("processing context helper unavailable: %s" % e)
            self._context = QgsProcessingContext()
            self._context.setProject(QgsProject.instance())
            self._context.setFeedback(self._feedback)

        alg = QgsApplication.processingRegistry().createAlgorithmById(
            self.alg_id)
        self._task = QgsProcessingAlgRunnerTask(alg, params, self._context,
                                                self._feedback)
        self._task.executed.connect(self._done)
        self._set_running(True)
        self._append(tr("Running %s…") % self.alg.displayName())
        QgsApplication.taskManager().addTask(self._task)

    def _on_progress(self, p):
        # a progress event still in the queue after the run has ended must
        # not overwrite the final 100 %
        if self._task is not None:
            self.progress.setValue(int(p))

    def cancel(self):
        if self._feedback is not None:
            self._feedback.cancel()
            self._append(tr("Cancelling…"), 1)

    def _done(self, successful, results):
        # Progress and log lines come from the worker thread through queued
        # connections; some may still be waiting when the task reports
        # completion. Finishing on the next event-loop turn lets them land
        # first, so "Done" is the last log line and 100 % is not overwritten.
        QTimer.singleShot(0, lambda: self._finish(successful, results))

    def _finish(self, successful, results):
        self._task = None
        self._set_running(False)
        self.progress.setValue(100 if successful else 0)
        if not successful:
            canceled = self._feedback is not None and self._feedback.isCanceled()
            self._append(tr("Cancelled.") if canceled else tr("Failed."),
                         1 if canceled else 2)
            self.iface.messageBar().pushMessage(
                tr("Raisz-style Relief"),
                tr("Cancelled.") if canceled else
                tr("The run failed -- see the log in the plugin window."),
                level=MSG_WARNING if canceled else MSG_CRITICAL)
        else:
            out = (results or {}).get("OUTPUT")
            self._append(tr("Done: %s") % out)
            self._report_output(out)

    def _report_output(self, path):
        bar = self.iface.messageBar()
        if not path or not isinstance(path, str):
            bar.pushMessage(tr("Raisz-style Relief"), tr("Done."),
                            level=MSG_SUCCESS)
            return
        widget = bar.createMessage(tr("Raisz-style Relief"),
                                   tr("Saved: %s") % os.path.basename(path))
        b_open = QPushButton(tr("Open"), widget)
        b_open.clicked.connect(
            lambda _=False, p=path: QDesktopServices.openUrl(
                QUrl.fromLocalFile(p)))
        b_dir = QPushButton(tr("Show folder"), widget)
        b_dir.clicked.connect(
            lambda _=False, p=path: QDesktopServices.openUrl(
                QUrl.fromLocalFile(os.path.dirname(p))))
        widget.layout().addWidget(b_open)
        widget.layout().addWidget(b_dir)
        bar.pushWidget(widget, MSG_SUCCESS, 0)

    def open_in_processing(self):
        params = {k: v for k, v in self.parameters().items() if v is not None}
        self._save_settings()
        try:
            from processing import execAlgorithmDialog
            execAlgorithmDialog(self.alg_id, params)
        except Exception as e:
            _log("opening the Processing dialog: %s" % e, MSG_WARNING)
            QMessageBox.warning(self, self.windowTitle(),
                                tr("Could not open the Processing dialog: "
                                   "%s") % e)

    # -- lifecycle ------------------------------------------------------
    def closeEvent(self, event):
        if self._task is not None:
            r = QMessageBox.question(
                self, self.windowTitle(),
                tr("A run is still in progress. Cancel it and close?"))
            if r != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.cancel()
        try:
            self._save_settings()
        except Exception as e:
            _log("saving dialog settings: %s" % e)
        super().closeEvent(event)
