"""
Classes to layout elements in a `.Figure`.

Figures have a ``layout_engine`` property that holds a subclass of
`~.LayoutEngine` defined here (or *None* for no layout).  At draw time
``figure.get_layout_engine().execute()`` is called, the goal of which is
usually to rearrange Axes on the figure to produce a pleasing layout. This is
like a ``draw`` callback, however when printing we disable the layout engine
for the final draw and it is useful to know the layout engine while the figure
is being created, in particular to deal with colorbars.

Matplotlib supplies two layout engines, `.TightLayoutEngine` and
`.ConstrainedLayoutEngine`.  Third parties can create their own layout engine
by subclassing `.LayoutEngine`.
"""

from contextlib import nullcontext

import matplotlib as mpl
import matplotlib._api as _api

from matplotlib._constrained_layout import do_constrained_layout
from matplotlib._tight_layout import (get_subplotspec_list,
                                      get_tight_layout_figure)
from matplotlib.backend_bases import _get_renderer


class LayoutEngine:
    """
    Base class for Matplotlib layout engines.

    A layout engine can be passed to a figure at instantiation or at any time
    with `~.figure.Figure.set_layout_engine`.  Once attached to a figure, the
    layout engine ``execute`` function is called at draw time by
    `~.figure.Figure.draw`, providing a special draw-time hook.

    .. note ::

       However, note that layout engines affect the creation of colorbars, so
       `~.figure.Figure.set_layout_engine` should be called before any
       colorbars are created.

    Currently, there are two properties of `LayoutEngine` classes that are
    consulted while manipulating the figure:

    - ``engine.colorbar_gridspec`` tells `.Figure.colorbar` whether to make the
       axes using the gridspec method (see `.colorbar.make_axes_gridspec`) or
       not (see `.colorbar.make_axes`);
    - ``engine.adjust_compatible`` stops `.Figure.subplots_adjust` from being
        run if it is not compatible with the layout engine.

    To implement a custom `LayoutEngine`:

    1. override ``_adjust_compatible`` and ``_colorbar_gridspec``
    2. override `LayoutEngine.set` to update *self._params*
    3. override `LayoutEngine.execute` with your implementation

    """
    # override these is sub-class
    _adjust_compatible = None
    _colorbar_gridspec = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._params = {}

    def set(self, **kwargs):
        raise NotImplementedError

    @property
    def colorbar_gridspec(self):
        """
        Return a boolean if the layout engine creates colorbars using a
        gridspec.
        """
        if self._colorbar_gridspec is None:
            raise NotImplementedError
        return self._colorbar_gridspec

    @property
    def adjust_compatible(self):
        """
        Return a boolean if the layout engine is compatible with
        `~.Figure.subplots_adjust`.
        """
        if self._adjust_compatible is None:
            raise NotImplementedError
        return self._adjust_compatible

    def get(self):
        """
        Return copy of the parameters for the layout engine.
        """
        return dict(self._params)

    def execute(self, fig):
        """
        Execute the layout on the figure given by *fig*.
        """
        # subclasses must implement this.
        raise NotImplementedError


class TightLayoutEngine(LayoutEngine):
    """
    Implements the ``tight_layout`` geometry management.  See
    :doc:`/tutorials/intermediate/tight_layout_guide` for details.
    """
    _adjust_compatible = True
    _colorbar_gridspec = True

    def __init__(self, *, pad=1.08, h_pad=None, w_pad=None,
                 rect=(0, 0, 1, 1), **kwargs):
        """
        Initialize tight_layout engine.

        Parameters
        ----------
        pad : float, 1.08
            Padding between the figure edge and the edges of subplots, as a
            fraction of the font size.
        h_pad, w_pad : float
            Padding (height/width) between edges of adjacent subplots.
            Defaults to *pad*.
        rect : tuple[float, float, float, float], optional
            (left, bottom, right, top) rectangle in normalized figure
            coordinates that the subplots (including labels)
            will fit into. Defaults to using the entire figure.
        """
        super().__init__(**kwargs)
        for td in ['pad', 'h_pad', 'w_pad', 'rect']:
            # initialize these in case None is passed in above:
            self._params[td] = None
        self.set(pad=pad, h_pad=h_pad, w_pad=w_pad, rect=rect)

    def execute(self, fig):
        """
        Execute tight_layout.

        This decides the subplot parameters given the padding that
        will allow the axes labels to not be covered by other labels
        and axes.

        Parameters
        ----------
        fig : `.Figure` to perform layout on.

        See also: `.figure.Figure.tight_layout` and `.pyplot.tight_layout`.
        """
        info = self._params
        subplotspec_list = get_subplotspec_list(fig.axes)
        if None in subplotspec_list:
            _api.warn_external("This figure includes Axes that are not "
                               "compatible with tight_layout, so results "
                               "might be incorrect.")
        renderer = _get_renderer(fig)
        with getattr(renderer, "_draw_disabled", nullcontext)():
            kwargs = get_tight_layout_figure(
                fig, fig.axes, subplotspec_list, renderer,
                pad=info['pad'], h_pad=info['h_pad'], w_pad=info['w_pad'],
                rect=info['rect'])
        if kwargs:
            fig.subplots_adjust(**kwargs)

    def set(self, *, pad=None, w_pad=None, h_pad=None, rect=None):
        for td in self.set.__kwdefaults__:
            if locals()[td] is not None:
                self._params[td] = locals()[td]


class ConstrainedLayoutEngine(LayoutEngine):
    """
    Implements the ``constrained_layout`` geometry management.  See
    :doc:`/tutorials/intermediate/constrainedlayout_guide` for details.
    """

    _adjust_compatible = False
    _colorbar_gridspec = False

    def __init__(self, *, h_pad=None, w_pad=None,
                 hspace=None, wspace=None, **kwargs):
        """
        Initialize ``constrained_layout`` settings.

        Parameters
        ----------
        h_pad, w_pad : float
            Padding around the axes elements in figure-normalized units.
            Default to :rc:`figure.constrained_layout.h_pad` and
            :rc:`figure.constrained_layout.w_pad`.
        hspace, wspace : float
            Fraction of the figure to dedicate to space between the
            axes.  These are evenly spread between the gaps between the axes.
            A value of 0.2 for a three-column layout would have a space
            of 0.1 of the figure width between each column.
            If h/wspace < h/w_pad, then the pads are used instead.
            Default to :rc:`figure.constrained_layout.hspace` and
            :rc:`figure.constrained_layout.wspace`.
        """
        super().__init__(**kwargs)
        # set the defaults:
        self.set(w_pad=mpl.rcParams['figure.constrained_layout.w_pad'],
                 h_pad=mpl.rcParams['figure.constrained_layout.h_pad'],
                 wspace=mpl.rcParams['figure.constrained_layout.wspace'],
                 hspace=mpl.rcParams['figure.constrained_layout.hspace'])
        # set anything that was passed in (None will be ignored):
        self.set(w_pad=w_pad, h_pad=h_pad, wspace=wspace, hspace=hspace)

    def execute(self, fig):
        """
        Perform constrained_layout and move and resize axes accordingly.

        Parameters
        ----------
        fig : `.Figure` to perform layout on.
        """
        width, height = fig.get_size_inches()
        # pads are relative to the current state of the figure...
        w_pad = self._params['w_pad'] / width
        h_pad = self._params['h_pad'] / height

        return do_constrained_layout(fig, w_pad=w_pad, h_pad=h_pad,
                                     wspace=self._params['wspace'],
                                     hspace=self._params['hspace'])

    def set(self, *, h_pad=None, w_pad=None,
            hspace=None, wspace=None):
        """
        Set the pads for constrained_layout.

        Parameters
        ----------
        h_pad, w_pad : float
            Padding around the axes elements in figure-normalized units.
            Default to :rc:`figure.constrained_layout.h_pad` and
            :rc:`figure.constrained_layout.w_pad`.
        hspace, wspace : float
            Fraction of the figure to dedicate to space between the
            axes.  These are evenly spread between the gaps between the axes.
            A value of 0.2 for a three-column layout would have a space
            of 0.1 of the figure width between each column.
            If h/wspace < h/w_pad, then the pads are used instead.
            Default to :rc:`figure.constrained_layout.hspace` and
            :rc:`figure.constrained_layout.wspace`.
        """
        for td in self.set.__kwdefaults__:
            if locals()[td] is not None:
                self._params[td] = locals()[td]
