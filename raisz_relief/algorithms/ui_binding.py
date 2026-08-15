# -*- coding: utf-8 -*-
"""
ui_binding.py -- wiring the grouped dialogs into Processing.

Written against the API as it actually is on QGIS 3.42.3 / Qt 5.15.13,
verified by introspection rather than from memory:

  * QgsGui.processingGuiRegistry() with addParameterWidgetFactory /
    removeParameterWidgetFactory;
  * QgsAbstractProcessingParameterWidgetWrapper: createWidget(),
    setWidgetValue(value, context), widgetValue(), createLabel(),
    postInitialize(wrappers), type();
  * QgsProcessingParameterWidgetFactoryInterface: parameterType() -> str,
    createWidgetWrapper(parameter, type),
    createModelerWidgetWrapper(model, childId, parameter, context);
  * QgsProcessingGui distinguishes Standard / Batch / Modeler -- the
    wrapper knows where it is being drawn, so we only interfere in the
    standard dialog;
  * the help panel on the right (a QTextBrowser named 'textShortHelp')
    accepts writes, so the live summary can go there too.

THE KEY DECISION. Existing parameters are NOT replaced by a composite.
Instead one service parameter is added per group, whose widget is a
summary line plus a "Configure..." button. The button edits the values of
the NEIGHBOURING wrappers, which arrive in postInitialize(wrappers).

Why not a composite parameter holding JSON: batch mode, the graphical
modeler and calls from scripts keep seeing ordinary parameters and keep
working. A composite would break all three for the sake of a tidier
dialog.
"""

from __future__ import annotations

from qgis.PyQt import QtWidgets
from qgis.core import (QgsProcessingContext, QgsProcessingParameterDefinition,
                       QgsProcessingParameterType, QgsApplication,
                       QgsMessageLog)
from qgis.gui import (QgsGui, QgsAbstractProcessingParameterWidgetWrapper,
                      QgsProcessingParameterWidgetFactoryInterface,
                      QgsProcessingGui)

from .ui_groups import GROUPS, GroupDialog, summarize, group_by_key

LOG = "RaiszRelief"
PARAM_TYPE = "raisz_group"          # our own type, so no other is hijacked

# Hide the original group fields in the STANDARD dialog. Not applied in
# batch mode or the modeler, where they stay available one by one. Setting
# this to False restores the previous look.
HIDE_ORIGINALS = True


def _log(msg):
    QgsMessageLog.logMessage(str(msg), LOG)


# --------------------------------------------------------- service param

class RaiszGroupParameter(QgsProcessingParameterDefinition):
    """A service parameter: it stores nothing and only anchors the widget
    with the button. It does not reach the algorithm -- the values still
    live in the ordinary parameters of the group."""

    def __init__(self, name, description="", group_key="", optional=True):
        super().__init__(name, description, None, optional)
        self.group_key = group_key

    def type(self):
        return PARAM_TYPE

    def clone(self):
        return RaiszGroupParameter(self.name(), self.description(),
                                   self.group_key)

    def checkValueIsAcceptable(self, value, context=None):
        return True

    def valueAsPythonString(self, value, context):
        return "None"


class RaiszGroupParameterType(QgsProcessingParameterType):
    """Type registration, so the modeler does not trip over an unknown
    parameter."""

    def create(self, name):
        return RaiszGroupParameter(name)

    def metadata(self):
        return {}

    def name(self):
        return "Raisz: parameter group"

    def id(self):
        return PARAM_TYPE

    def description(self):
        return ("A service parameter: the button that opens a group "
                "window. Values live in the ordinary group parameters.")


# ---------------------------------------------------------------- wrapper

class GroupWidgetWrapper(QgsAbstractProcessingParameterWidgetWrapper):
    """The service parameter's widget: a summary plus a Configure button."""

    _hide_reported = False

    def __init__(self, parameter, wtype):
        # IMPORTANT: the two-argument form. Passing a parent made C++ take
        # ownership, the Python half was garbage collected, and only the
        # bare base survived -- hence "setWidgetValue() is abstract" and
        # the loss of our own methods.
        super().__init__(parameter, wtype)
        self._group = group_by_key(getattr(parameter, "group_key", "")
                                   or parameter.name().lower())
        self._sibs = {}                 # parameter name -> wrapper
        self._btn = None
        self._lbl = None
        self._help_original = None

    # -- required contract ----------------------------------------------
    def createWidget(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self._lbl = QtWidgets.QLabel(w)
        lay.addWidget(self._lbl, 1)
        self._btn = QtWidgets.QPushButton("Configure...", w)
        # a closure rather than a bound method: it holds the wrapper
        # explicitly
        wrapper = self
        self._btn.clicked.connect(
            lambda checked=False, wr=wrapper: wr._open())
        lay.addWidget(self._btn, 0)
        self._refresh()
        return w

    def createLabel(self):
        if self._group is None:
            return None
        lbl = QtWidgets.QLabel(self._group.title)
        lbl.setToolTip(self._group.note or "")
        return lbl

    def setWidgetValue(self, value, context):
        return                          # the parameter has no value of its own

    def widgetValue(self):
        return None

    def value(self):
        return None

    def postInitialize(self, wrappers):
        """Every wrapper of the dialog arrives here -- this is how we read
        and write the real parameters of the group."""
        # wrappers may be a generator: materialise it ONCE, otherwise a
        # diagnostic count would consume the iterator and leave the loop
        # below with nothing
        wl = list(wrappers or [])
        if self._group is None:
            return
        want = {f.name for f in self._group.fields}
        for w in wl:
            try:
                nm = w.parameterDefinition().name()
            except Exception as e:
                _log("postInitialize: wrapper without a parameter name: %s" % e)
                continue
            if nm in want:
                self._sibs[nm] = w
                if HIDE_ORIGINALS and self.type() == QgsProcessingGui.Standard:
                    self._hide(w)
        self._refresh()

    # -- helpers ---------------------------------------------------------
    @classmethod
    def _hide(cls, wrapper):
        """Remove an original field from the STANDARD dialog. Never called
        for batch or the modeler, so there everything stays as it was.

        The accessor names for an already created widget were not part of
        the API introspection, so both are tried and the outcome is
        reported to the log once."""
        done = []
        for meth in ("wrappedWidget", "wrappedLabel"):
            try:
                w = getattr(wrapper, meth, None)
                w = w() if callable(w) else None
                if w is not None:
                    w.setVisible(False)
                    done.append(meth)
            except Exception as e:
                _log("hiding %s: %s" % (meth, e))
        if not cls._hide_reported:
            cls._hide_reported = True
            _log("hiding original fields: %s"
                 % (", ".join(done) if done
                    else "NOTHING worked -- fields will stay visible"))
        return bool(done)

    def _values(self):
        out = {}
        for f in self._group.fields:
            w = self._sibs.get(f.name)
            if w is None:
                out[f.name] = f.default
                continue
            try:
                v = w.widgetValue()
                out[f.name] = f.default if v is None else v
            except Exception as e:
                _log("reading %s: %s" % (f.name, e))
                out[f.name] = f.default
        return out

    def _apply(self, values):
        ctx = QgsProcessingContext()
        for name, v in values.items():
            w = self._sibs.get(name)
            if w is None:
                continue
            try:
                w.setWidgetValue(v, ctx)
            except Exception as e:
                _log("writing %s: %s" % (name, e))

    def _open(self):
        if self._group is None:
            return
        # only the fields that found a neighbouring wrapper: the two
        # algorithms have different parameter sets
        dlg = GroupDialog(self._group, self._values(), self._btn,
                          available=set(self._sibs))
        acc = (QtWidgets.QDialog.DialogCode.Accepted
               if hasattr(QtWidgets.QDialog, "DialogCode")
               else QtWidgets.QDialog.Accepted)
        if dlg.exec() == acc:
            self._apply(dlg.values())
            self._refresh()

    def _refresh(self):
        if self._lbl is None or self._group is None:
            return
        self._lbl.setText(summarize(self._group, self._values(),
                                    available=set(self._sibs) or None))
        self._lbl.setToolTip(self._group.note or "")
        self._help_summary()

    # -- summary in the help panel ---------------------------------------
    def _help_summary(self):
        """Append a summary to the help panel on the right.

        The QTextBrowser named 'textShortHelp' accepts writes, but that is
        dialog internals rather than public API: the object name may
        differ in another QGIS build. Everything is wrapped and skipped
        silently on failure -- the main summary sits next to the button and
        does not depend on the panel.

        The original HTML is remembered on first use, otherwise the
        summary would pile up with every change."""
        try:
            dlg = self.dialog() if hasattr(self, "dialog") else None
            if dlg is None:
                w = self._btn
                while w is not None and not isinstance(w, QtWidgets.QDialog):
                    w = w.parentWidget()
                dlg = w
            if dlg is None:
                return
            for br in dlg.findChildren(QtWidgets.QTextBrowser):
                if br.objectName() != "textShortHelp" or not br.isVisible():
                    continue
                if self._help_original is None:
                    self._help_original = br.toHtml()
                rows = []
                for g in GROUPS:
                    mark = "&#9654; " if g is self._group else ""
                    rows.append("<li>%s<b>%s:</b> %s</li>"
                                % (mark, g.title,
                                   summarize(g, self._values())
                                   if g is self._group else "..."))
                br.setHtml(self._help_original +
                           "<hr><p><b>Currently set</b></p><ul>" +
                           "".join(rows) + "</ul>")
        except Exception as e:
            _log("summary in the help panel: %s" % e)


# ---------------------------------------------------------------- factory

# The wrappers live here as well as in C++: without a strong Python
# reference the garbage collector takes the Python half of the object, C++
# is left with the bare base, and our overrides stop being visible
# (NotImplementedError on setWidgetValue, loss of our own attributes).
_LIVE = []


class GroupWidgetFactory(QgsProcessingParameterWidgetFactoryInterface):

    def parameterType(self):
        return PARAM_TYPE

    def createWidgetWrapper(self, parameter, wtype):
        w = GroupWidgetWrapper(parameter, wtype)
        _LIVE.append(w)
        return w

    def createModelerWidgetWrapper(self, model, childId, parameter, context):
        # the button is pointless in the modeler: there parameters are
        # wired one by one and grouping would only get in the way
        w = GroupWidgetWrapper(parameter, QgsProcessingGui.Modeler)
        _LIVE.append(w)
        return w


# ----------------------------------------------------------- registration

_factory = None
_ptype = None


def register():
    """Called once when the plugin loads."""
    global _factory, _ptype
    ok = {"type": False, "factory": False}
    try:
        if _ptype is None:
            _ptype = RaiszGroupParameterType()
            QgsApplication.processingRegistry().addParameterType(_ptype)
        ok["type"] = True
    except Exception as e:
        _log("registering the parameter type: %s" % e)
    try:
        if _factory is None:
            _factory = GroupWidgetFactory()
            QgsGui.processingGuiRegistry().addParameterWidgetFactory(_factory)
        ok["factory"] = True
    except Exception as e:
        _log("registering the widget factory: %s" % e)
    return ok


def unregister():
    """Symmetrically, when the plugin unloads: otherwise a factory from the
    previous session is left hanging after a reinstall."""
    global _factory, _ptype
    try:
        if _factory is not None:
            QgsGui.processingGuiRegistry().removeParameterWidgetFactory(_factory)
    except Exception as e:
        _log("removing the factory: %s" % e)
    _factory = None
    try:
        if _ptype is not None:
            QgsApplication.processingRegistry().removeParameterType(_ptype)
    except Exception as e:
        _log("removing the type: %s" % e)
    _ptype = None


def add_group_params(alg):
    """Add the service group parameters to an algorithm.

    Called at the END of initAlgorithm: the wrapper looks its neighbours up
    by name, so they must already be declared by the time postInitialize
    runs."""
    n = 0
    for g in GROUPS:
        try:
            p = RaiszGroupParameter("RZGRP_" + g.key.upper(), g.title, g.key)
            p.setFlags(p.flags() |
                       QgsProcessingParameterDefinition.FlagOptional)
            alg.addParameter(p)
            n += 1
        except Exception as e:
            _log("adding group %s: %s" % (g.key, e))
    return n
