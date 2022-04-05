# -*- coding: utf-8 -*-
"""
Created on Sun Jul  5 20:44:14 2020
Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
@author: ER17450
"""

from pyqtgraph.Qt import QtCore, QtWidgets, QtGui
import pyqtgraph as pg
import sys,os,time,copy,struct
import numpy as np

from turbo_colormap import turbo_colormap_data

class IFVoltagePlotWidget(pg.GraphicsLayoutWidget):
    def __init__(self,parent):
        super().__init__(parent)

        self.p1 = self.addPlot()
        self.p1.setRange(xRange=(-5.0e-3,25.0e-3),yRange=(-2.0,2.0),disableAutoRange=True)
        self.p1.setLabel('bottom',text='Time', units='s')
        self.p1.setLabel('left',text='ADC', units='V')
        self.p1.showGrid(x=True,y=True,alpha=0.5)
        self.curve = self.p1.plot(pen='y')

    def set_fast_time_scale(self,fast_time_scale):
        self.fast_time_scale = fast_time_scale
        #self.p1.setXRange(np.min(fast_time_scale),np.max(fast_time_scale))

    def set_voltage(self,vsig,pen='y'):
        self.curve.setData(self.fast_time_scale,vsig, pen=pen)


class IFSpectrumPlotWidget(pg.GraphicsLayoutWidget):
    def __init__(self,parent):
        super().__init__(parent)

        self.spec_plot = self.addPlot()
        self.spec_plot.setRange(xRange=(0.0,25e3),yRange=(-100.0,-30.0),disableAutoRange=True)
        self.spec_plot.setLabel('bottom',text='Frequency', units='Hz')
        self.spec_plot.setLabel('left',text='Power (dB)')
        self.spec_plot.showGrid(x=True,y=True,alpha=0.5)
        self.spec_curve = self.spec_plot.plot(pen='y')

        self.xscale = None
        self.label = None
        self.units = None
        #self.set_frequency_scale(np.array([0.0,25e3]))

    def set_spectrum(self, spectrum, pen='y'):
        self.spec_curve.setData(self.xscale, spectrum, pen=pen)

    def set_frequency_scale(self, frequency_scale):
        self._new_x_axis(frequency_scale,'Frequency','Hz')

    def set_tau_scale(self, tau_scale):
        self._new_x_axis(tau_scale,'Delay','s')

    def set_range_scale(self, range_scale):
        self._new_x_axis(range_scale,'Range','m')

    def set_rrate_scale(self, rrate_scale):
        self._new_x_axis(rrate_scale,'Range Rate','m/s')

    def _new_x_axis(self, xscale, label, units):
        if label == self.label and units == self.units and \
                xscale.shape == self.xscale.shape and \
                np.min(xscale) == np.min(self.xscale) and \
                np.max(xscale) == np.max(self.xscale):
            return
        self.xscale = xscale
        self.label = label
        self.units = units
        self.spec_plot.setLabel('bottom',text=label,units=units)
        self.spec_plot.setXRange(np.min(xscale),np.max(xscale))


class IFWaterfallPlotWidget(pg.GraphicsLayoutWidget):
    def __init__(self,parent):
        super().__init__(parent)

        ## Create image and overlay overlay plot
        self.waterfall_image = pg.ImageItem(axisOrder='col-major')
        self.waterfall_plot = pg.PlotItem()
        vb = self.waterfall_plot.getViewBox()
        vb.addItem(self.waterfall_image)
        self.addItem(self.waterfall_plot)

        ## Create lut, or colormap
        lut = np.round(np.array(turbo_colormap_data)*255).astype(np.byte)

        # Set the colormap
        self.waterfall_image.setLookupTable(lut)
        self.waterfall_image.setZValue(-100) # put on bottom layer
        cmin,cmax=-100.0,-30.0
        self.waterfall_image.setLevels([cmin,cmax])

        # Set up a dummy plot, so the GUI draws something
        self.xscale = None
        self.label = None
        self.units = None
        self.set_waterfall(np.zeros((100,100)))
        self.set_slow_time_scale(np.array([0.0,6.0]))
        self.set_frequency_scale(np.array([0.0,25e3]))

    def set_waterfall(self,waterfall_arr):
        self.waterfall_image.setImage(waterfall_arr,
                                      autoLevels=False,autoDownsample=True)

    def set_slow_time_scale(self,slow_time_scale):
        self.slow_time_scale = slow_time_scale
        ymin = np.max(self.slow_time_scale)
        ymax = np.min(self.slow_time_scale)
        self.waterfall_plot.setLabel('left',text='History',units='s')
        self.waterfall_plot.setYRange(ymin,ymax)

    def set_frequency_scale(self,frequency_scale):
        self._new_x_axis(frequency_scale,'Frequency','Hz')

    def set_tau_scale(self,tau_scale):
        self._new_x_axis(tau_scale,'Delay','s')

    def set_range_scale(self,range_scale):
        self._new_x_axis(range_scale,'Range','m')

    def set_rrate_scale(self,rrate_scale):
        self._new_x_axis(rrate_scale,'Range Rate','m/s')

    def _new_x_axis(self,xscale,label,units):
        if label == self.label and units == self.units and \
                xscale.shape == self.xscale.shape and \
                np.min(xscale) == np.min(self.xscale) and \
                np.max(xscale) == np.max(self.xscale):
            return
        self.xscale = xscale
        self.label = label
        self.units = units
        self.waterfall_plot.setLabel('bottom',text=label,units=units)
        xmin = np.min(xscale)
        xmax = np.max(xscale)
        ymin = np.max(self.slow_time_scale)
        ymax = np.min(self.slow_time_scale)
        self.waterfall_plot.setXRange(xmin,xmax)
        self.waterfall_image.setRect(QtCore.QRectF(xmin, ymin, xmax-xmin, ymax-ymin))
