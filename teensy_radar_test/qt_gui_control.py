# -*- coding: utf-8 -*-
"""
Created on Fri Jun  5 22:32:45 2020
Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
@author: ER17450
"""

from pyqtgraph.Qt import QtCore, QtWidgets, QtGui
import pyqtgraph as pg
import sys,os,time,copy,struct
import threading, queue
from datetime import datetime

from teensy_radar_control.handler import BasicRadarHandler, ExtendedRadarHandler
import numpy as np

import signal

import serial.tools.list_ports

speed_of_light =  299792458.0 # m/s

class RadarDisplay(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        #self.rh = BasicRadarHandler()
        self.rh = ExtendedRadarHandler()

        signal.signal(signal.SIGINT, self.sigint_handler)

        self.initUI()

        self.write_queue = queue.Queue(100)
        self._th_write_data = threading.Thread(target=self._th_write_data,args=())
        self._th_write_data.daemon = True
        self._th_write_data.start()
        #self.write_fname = './pulses.dat'
        self.write_fname = None
        self.fh = None

        # Create the background update task
        self.timer = QtCore.QTimer()
        self.timer.start(0.1*1000)
        self.timer.timeout.connect(self._update)

    def sigint_handler(self, signum, frame):
        print('RadarDisplay sigint_handler called')
        self.close()

    def closeEvent(self, event):
        if self.rh is not None:
            self.rh.join()
        event.accept()

    def initUI(self):
        self.setWindowTitle('Teensy USB Test')
        #self.setMinimumSize(1000,500)

        # Set up IF Voltage plot
        glw1 = pg.GraphicsLayoutWidget()
        p1 = glw1.addPlot()
        p1.setRange(xRange=(-5.0e-3,25.0e-3),yRange=(-2.0,2.0),disableAutoRange=True)
        p1.setLabel('bottom',text='Time', units='s')
        p1.setLabel('left',text='ADC', units='V')
        p1.showGrid(x=True,y=True,alpha=0.5)
        self.curve = p1.plot(pen='y')

        # Set up IF Spectrum plot
        glw2 = pg.GraphicsLayoutWidget()
        self.spec_plot = glw2.addPlot()
        self.spec_plot.setRange(xRange=(0.0,25e3),yRange=(-70.0,0.0),disableAutoRange=True)
        self.spec_plot.setLabel('bottom',text='Frequency', units='Hz')
        self.spec_plot.setLabel('left',text='Power (dB)')
        self.spec_plot.showGrid(x=True,y=True,alpha=0.5)
        self.spec = self.spec_plot.plot(pen='y')
        self.prev_pulse = None

        # Set up IF Spectrum plot
        glw3 = pg.GraphicsLayoutWidget()
        self.waterfall_arr = np.zeros((100,100))
        self.waterfall_idx = 0
        self.waterfall_plot, self.waterfall_image = \
            create_image_overlay(self.waterfall_arr,
                                 0.0,25e3,'Frequency','Hz',
                                 0.0,6.0,'History','s',
                                 -70.0, 0.0)
        glw3.addItem(self.waterfall_plot)

        # Set up the log area
        self.log_area = QtWidgets.QPlainTextEdit()
        self.log_area.setFocusPolicy(QtCore.Qt.NoFocus)

        tabs = QtWidgets.QTabWidget()
        tabs.addTab(glw1,'IF Voltage')
        tabs.addTab(glw2,'IF Spectrum')
        tabs.addTab(glw3,'IF Waterfall')
        tabs.addTab(self.log_area,'Log Messages')


        # Do the layout
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self._create_connect_box())
        layout.addWidget(self._create_cfg_box())
        layout.addWidget(self._create_cmd_box())
        layout.addWidget(self._create_ctl_box())
        layout.addWidget(tabs)
        #layout.addWidget(self.log_area)

        # Display the window
        self.setLayout(layout)
        self.show()

    def _create_connect_box(self):
        # Set up the connnect box
        rescan_button = QtWidgets.QPushButton('Rescan')
        rescan_button.clicked.connect(self._on_rescan)

        self.connect_port_cbox = QtWidgets.QComboBox()

        self.connect_button = QtWidgets.QPushButton('Connect')
        self.connect_button.setCheckable(True)
        self.connect_button.setChecked(False)
        self.connect_button.clicked.connect(self._on_connect)

        self.connect_status = QtWidgets.QLineEdit('')
        self.connect_status.setFocusPolicy(QtCore.Qt.NoFocus)

        # Set up the command box
        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(rescan_button)
        layout.addWidget(self.connect_port_cbox)
        layout.addWidget(self.connect_button)
        layout.addWidget(self.connect_status)

        connect_box = QtWidgets.QGroupBox('Connection')
        connect_box.setLayout(layout)

        # Make sure scan happens at lease once
        self.ports = None
        self._on_rescan()

        return connect_box

    @QtCore.pyqtSlot()
    def _on_rescan(self):
        print('rescan pushed')
        self.connect_port_cbox.clear()
        self.ports = serial.tools.list_ports.comports()
        for ii in range(0,len(self.ports)):
            self.connect_port_cbox.addItem(self.ports[ii].description)

    @QtCore.pyqtSlot()
    def _on_connect(self):
        if self.connect_button.isChecked():
            # Get selected port
            idx = self.connect_port_cbox.currentIndex()
            port = self.ports[idx].device
            print('connect pushed, port is ' + str(port))
            self.rh.connect(port)
            self.connect_button.setText('Disconnect')
        else:
            print('connect pushed, disconnect')
            self.rh.disconnect()
            self.connect_button.setText('Connect')

    def _create_cfg_box(self):
        # Set up the configure box
        cfg_layout = QtWidgets.QGridLayout()
        cfg_layout.addWidget(QtWidgets.QLabel('Pulse Length (ms)'),0,0)
        self.pulse_length_edit = QtWidgets.QLineEdit('20')
        cfg_layout.addWidget(self.pulse_length_edit,1,0)

        cfg_layout.addWidget(QtWidgets.QLabel('Gain'),0,1)
        self.gain_edit = QtWidgets.QLineEdit('1')
        cfg_layout.addWidget(self.gain_edit,1,1)

        cfg_layout.addWidget(QtWidgets.QLabel('FStart (MHz)'),0,2)
        self.fstart_edit = QtWidgets.QLineEdit('2350.000')
        cfg_layout.addWidget(self.fstart_edit,1,2)

        cfg_layout.addWidget(QtWidgets.QLabel('FStop (MHz)'),0,3)
        self.fstop_edit = QtWidgets.QLineEdit('2450.000')
        cfg_layout.addWidget(self.fstop_edit,1,3)

        cfg_layout.addWidget(QtWidgets.QLabel('FReturn (MHz)'),0,4)
        self.freturn_edit = QtWidgets.QLineEdit('0.000')
        cfg_layout.addWidget(self.freturn_edit,1,4)

        cfg_box = QtWidgets.QGroupBox('Configuration')
        cfg_box.setLayout(cfg_layout)

        return cfg_box

    def _create_cmd_box(self):
        version_button = QtWidgets.QPushButton('Version')
        version_button.clicked.connect(self._on_version)

        start_button = QtWidgets.QPushButton('Start')
        start_button.clicked.connect(self._on_start)

        stop_button = QtWidgets.QPushButton('Stop')
        stop_button.clicked.connect(self._on_stop)

        trigger_on_button = QtWidgets.QPushButton('Trig On')
        trigger_on_button.clicked.connect(self._on_trigger_on)

        trigger_off_button = QtWidgets.QPushButton('Trig Off')
        trigger_off_button.clicked.connect(self._on_trigger_off)

        # Set up the command box
        cmd_layout = QtWidgets.QHBoxLayout()
        cmd_layout.addWidget(version_button)
        cmd_layout.addWidget(start_button)
        cmd_layout.addWidget(stop_button)
        cmd_layout.addWidget(trigger_on_button)
        cmd_layout.addWidget(trigger_off_button)

        cmd_box = QtWidgets.QGroupBox('Commands')
        cmd_box.setLayout(cmd_layout)

        return cmd_box


    @QtCore.pyqtSlot()
    def _on_version(self):
        reply = self.rh.cmd_version()

    @QtCore.pyqtSlot()
    def _on_start(self):
        # Prepare to write data file
        if self.write_fname is not None:
            if self.fh is None:
                print('Opening file: ', self.write_fname)
                self.fh = open(self.write_fname,mode='wb')
            else:
                print('Emptying write queue')
                self.write_queue.join()
                print('Re-Opening file: ', self.write_fname)
                self.fh.close()
                self.fh = open(self.write_fname,mode='wb')
            print(self.fh)

        pulse_length = int(self.pulse_length_edit.text())
        gain = int(self.gain_edit.text())
        fstart = float(self.fstart_edit.text())
        fstop = float(self.fstop_edit.text())
        freturn = float(self.freturn_edit.text())
        reply = self.rh.cmd_start(pulse_length,gain,fstart,fstop,freturn)

    @QtCore.pyqtSlot()
    def _on_stop(self):
        # Close data file
        if self.fh is not None:
            print('Emptying write queue')
            self.write_queue.join()
            print('Closing file: ', self.write_fname)
            self.fh.close()
            self.fh = None

        reply = self.rh.cmd_stop()

    def _on_trigger_on(self):
        reply = self.rh.cmd_trigger_on()

    def _on_trigger_off(self):
        reply = self.rh.cmd_trigger_off()

    def _create_ctl_box(self):
        pm = QtWidgets.QGroupBox('Pulse Modifications')
        self.debias_check = QtWidgets.QCheckBox('Debias ADC')
        self.debias_check.setChecked(True)
        self.pcancel_check = QtWidgets.QCheckBox('Pulses Cancel')
        self.pcancel_check.setChecked(False)
        pm_layout = QtWidgets.QHBoxLayout()
        pm_layout.addWidget(self.debias_check)
        pm_layout.addWidget(self.pcancel_check)
        pm.setLayout(pm_layout)

        sa = QtWidgets.QGroupBox('Spectral Axis')
        self.spec_freq_rb = QtWidgets.QRadioButton('Frequency')
        self.spec_freq_rb.toggled.connect(self._on_spec_axis_change)
        self.spec_tau_rb = QtWidgets.QRadioButton('Roundtrip Delay')
        self.spec_tau_rb.toggled.connect(self._on_spec_axis_change)
        self.spec_range_rb = QtWidgets.QRadioButton('Range')
        self.spec_range_rb.toggled.connect(self._on_spec_axis_change)
        self.spec_rrate_rb = QtWidgets.QRadioButton('Range Rate')
        self.spec_rrate_rb.toggled.connect(self._on_spec_axis_change)
        sa_layout = QtWidgets.QHBoxLayout()
        sa_layout.addWidget(self.spec_freq_rb)
        sa_layout.addWidget(self.spec_tau_rb)
        sa_layout.addWidget(self.spec_range_rb)
        sa_layout.addWidget(self.spec_rrate_rb)
        sa.setLayout(sa_layout)
        self.spec_freq = np.array([0.0,25e3])
        self.spec_tau = np.array([0.0,1e-6])
        self.spec_range = np.array([0.0,100])
        self.spec_rrate = np.array([0.0,100])
        self.st = np.array([0.0,6.0])
        self.spec_freq_rb.setChecked(True)

        ctl_layout = QtWidgets.QHBoxLayout()
        #ctl_layout.addWidget(self.debias_check)
        #ctl_layout.addWidget(self.pcancel_check)
        #ctl_layout.addWidget(self.spec_freq_rb)
        #ctl_layout.addWidget(self.spec_tau_rb)
        #ctl_layout.addWidget(self.spec_range_rb)
        #ctl_layout.addWidget(self.spec_rrate_rb)
        ctl_layout.addWidget(pm)
        ctl_layout.addWidget(sa)

        ctl_box = QtWidgets.QGroupBox('Control')
        ctl_box.setLayout(ctl_layout)

        return ctl_box

    @QtCore.pyqtSlot()
    def _on_spec_axis_change(self):
        # Set plot axis for spectrums dynamically
        if self.spec_tau_rb.isChecked():
            self.spec_scale = self.spec_tau
            self.spec_plot.setLabel('bottom',text='Delay', units='s')
            self.waterfall_plot.setLabel('bottom',text='Delay',units='s')
        elif self.spec_range_rb.isChecked():
            self.spec_scale = self.spec_range
            self.spec_plot.setLabel('bottom',text='Range', units='m')
            self.waterfall_plot.setLabel('bottom',text='Range',units='m')
        elif self.spec_rrate_rb.isChecked():
            self.spec_scale = self.spec_rrate
            self.spec_plot.setLabel('bottom',text='Range Rate', units='m/s')
            self.waterfall_plot.setLabel('bottom',text='Range Rate',units='m/s')
        else:
            self.spec_scale = self.spec_freq
            self.spec_plot.setLabel('bottom',text='Frequency', units='Hz')
            self.waterfall_plot.setLabel('bottom',text='Frequency',units='Hz')

        self.spec_plot.setRange(xRange=(min(self.spec_scale),max(self.spec_scale)),
                                disableAutoRange=True)
        set_image_overlay_axes(self.waterfall_plot,self.waterfall_image,
                               min(self.spec_scale),max(self.spec_scale),
                               max(self.st),min(self.st),
                               -70.0,0.0)


    def _th_write_data(self):
        while True:
            pulse = self.write_queue.get()
            if self.fh is not None:
                hdr = struct.pack('HHLLHHfff',
                                  pulse.header.hdr_size,
                                  pulse.header.data_size,
                                  pulse.header.pulse_number,
                                  pulse.header.pulse_cycle_count,
                                  pulse.header.gain,
                                  pulse.header.pulse_length_ms,
                                  pulse.header.freq_start,
                                  pulse.header.freq_stop,
                                  pulse.header.freq_return)
                self.fh.write(hdr)
                self.fh.write(pulse.data.tobytes())
                self.fh.flush()
            self.write_queue.task_done()

        if not self.connect_button.isChecked():
            # Get selected port
            idx = self.connect_port_cbox.currentIndex()
            port = self.ports[idx].device
            print('connect pushed, port is ' + str(port))
            rh = RadarHandler(port)
            self.connect_button.setText('Disconnect')
        else:
            print('connect pushed, disconnect')
            self.connect_button.setText('Connect')

    def _different_pulse_params(self, pulse):
        # If no previous pulse, the this pulse is different
        if self.prev_pulse is None:
            return True

        # The pulse number and pulse cycle_count change every pulse.
        # It is not enough just to compare headers
        ch = pulse.header
        ph = self.prev_pulse.header
        if ch.data_size != ph.data_size or \
            ch.gain != ph.gain or \
            ch.pulse_length_ms != ph.pulse_length_ms or \
            ch.freq_start != ph.freq_start or \
            ch.freq_stop != ph.freq_stop or \
            ch.freq_return != ph.freq_return:
                return True
        return False

    def _update(self):
        if self.rh.is_alive():
            dt = self.rh.time_since_heartbeat()
            if dt is not None:
                txt = 'Time since heartbeat %5.2f' % dt
            else:
                txt = 'No heartbeats'
            self.connect_status.setText(txt)
        else:
            self.connect_status.setText('Disconnected')
            # Connection mush have crashed
            if self.connect_button.isChecked():
                self.connect_button.setChecked(False)
                self._on_connect()

        v_max=3.3
        adc_bits=16
        adc_enob=11
        adc_floor = -(1.76+6.02*adc_enob)
        v_scale = v_max/2.0**adc_bits
        # This has to do with the details of the driving circuit
        # v_center = 2.5*2.0/3.0
        v_center = 2.5*2.0/3.0 - 0.050
        v_bias = 0.0

        # display the pulse data
        while True:
            try:
                pulse = self.rh.get_pulse(block=False)
            except queue.Empty:
                break

            # Write pulses to file if required
            # TBD: does this need to be a copy?
            self.write_queue.put(copy.copy(pulse))

            # Scale the data is a voltage
            if self.debias_check.isChecked():
                sig = pulse.data*v_scale - v_center - v_bias
            else:
                sig = pulse.data*v_scale

            alpha = 0.99
            v_bias = alpha*v_bias + (1.0-alpha)*np.mean(pulse.data*v_scale - v_center)

            # Check for first time seeing a pulse in this radar configuration
            if self._different_pulse_params(pulse):
                self.prev_pulse = copy.copy(pulse)

                # Save the scaled sig so that it does not need to be recalculated
                self.prev_sig = copy.copy(sig)

                self.pl = pulse.header.pulse_length_ms/1000.0
                self.cfreq = (pulse.header.freq_stop + pulse.header.freq_start)*1e6/2.0
                self.lamb = speed_of_light / self.cfreq
                self.bw = abs(pulse.header.freq_stop - pulse.header.freq_start)*1e6
                self.srate = pulse.header.data_size/self.pl
                self.tt = np.arange(0.0,pulse.header.data_size)/self.srate

                arr_time = 6.0
                osf = 4.0
                self.spec_size = int(osf*pulse.header.data_size)
                self.win = np.hanning(pulse.header.data_size)
                self.spec_freq = np.fft.rfftfreq(self.spec_size,d=1.0/self.srate)
                self.spec_tau = self.spec_freq * self.pl / self.bw
                self.spec_range = self.spec_tau * speed_of_light / 2.0
                self.spec_rrate = self.spec_freq * self.lamb / 2.0

                self.waterfall_len = int(arr_time/self.pl)
                self.st = np.arange(0,self.waterfall_len) * self.pl

                if self.waterfall_arr.shape != (self.spec_freq.shape[0],2*self.waterfall_len):
                    self.waterfall_arr = np.zeros((self.spec_freq.shape[0],2*self.waterfall_len))
                    self.waterfall_idx = self.waterfall_len

                self.waterfall_image.setImage(self.waterfall_arr[:,0:self.waterfall_len],
                                          autoLevels=False,autoDownsample=True)

                # Reset the spectrum axes
                self._on_spec_axis_change()
                continue

            # Change pen color on trigger setting
            if pulse.header.status & 0x1:
                pen = 'y'
            else:
                pen = 'g'

            # Pulse cancel?
            if self.pcancel_check.isChecked():
                bg_sub = 1.0
            else:
                bg_sub = 0.0

            # Plot voltage
            self.curve.setData(self.tt,sig - bg_sub*self.prev_sig, pen=pen)

            # Plot Spectrum
            spec = np.fft.rfft(self.win*(sig - bg_sub*self.prev_sig)/v_max,n=self.spec_size)
            spec = spec/(2.0*self.spec_size/pulse.header.data_size)
            det = 20*np.log10(abs(spec)+1e-30)
            self.spec.setData(self.spec_scale,det,pen=pen)

            # Update waterfall
            self.waterfall_arr[:,self.waterfall_idx] = det
            self.waterfall_idx = self.waterfall_idx + 1
            if self.waterfall_idx >= 2*self.waterfall_len:
                self.waterfall_arr[:,0:self.waterfall_len] = \
                    self.waterfall_arr[:,self.waterfall_len:(2*self.waterfall_len)]
                self.waterfall_idx = self.waterfall_len

            img = self.waterfall_arr[:,(self.waterfall_idx-self.waterfall_len):self.waterfall_idx]
            self.waterfall_image.setImage(img,autoLevels=False,autoDownsample=True)

            # Look for missing pulses
            pulse_number_diff = \
                pulse.header.pulse_number - self.prev_pulse.header.pulse_number
            if pulse_number_diff != 1:
                if pulse_number_diff == 0:
                    print('Received repeated pulse')
                else:
                    print('Dropped %d pulses' % (pulse_number_diff,))

            #print(pulse.header, srate)
            self.prev_pulse = copy.copy(pulse)
            self.prev_sig = copy.copy(sig)

        # Display the log messages
        while True:
            try:
                log_msg = self.rh.get_log_msg(block=False)
            except queue.Empty:
                break
            time_str = datetime.now().isoformat()
            msg_str = '%s %s' % (time_str, str(log_msg))
            self.log_area.appendPlainText(msg_str)


from turbo_colormap import turbo_colormap_data
def create_image_overlay(arr,
                         xmin, xmax, xlabel, xunits,
                         ymin, ymax, ylabel, yunits,
                         cmin, cmax):

    ## Create overlay plot
    plot_item = pg.PlotItem()
    plot_item.setLabel('bottom',text=xlabel,units=xunits)
    plot_item.setLabel('left',text=ylabel,units=yunits)
    #plot_item.invertY(True)

    ## Create lut, or colormap
    lut = np.round(np.array(turbo_colormap_data)*255).astype(np.byte)

    ## Create image item
    image_item = pg.ImageItem(axisOrder='col-major')
    image_item.setLookupTable(lut)
    image_item.setZValue(-100) # put on bottom layer
    image_item.setImage(arr,autoLevels=False,autoDownsample=True)
    view = plot_item.getViewBox()
    view.addItem(image_item)

    set_image_overlay_axes(plot_item, image_item,
                           xmin,xmax,ymin,ymax,cmin,cmax)

    return plot_item, image_item

def set_image_overlay_axes(plot_item, image_item,
                         xmin, xmax,
                         ymin, ymax,
                         cmin, cmax):
    plot_item.setXRange(xmin,xmax)
    plot_item.setYRange(ymin,ymax)
    image_item.setLevels([cmin,cmax])
    image_item.setRect(QtCore.QRectF(xmin, ymin, xmax-xmin, ymax-ymin))


def main():
    app = QtGui.QApplication(sys.argv)
    # KLUDGE:
    # This fixes a problem with axis calculations when the primary
    # monitor and the display monitor have different resolution setting
    # in win10
    app.setAttribute(QtCore.Qt.AA_Use96Dpi)
    app.setQuitOnLastWindowClosed(True)

    rd = RadarDisplay()

    sys.exit(app.exec_())

if __name__ == '__main__':
    main()

#     Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
