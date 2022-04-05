# -*- coding: utf-8 -*-
"""
Created on Fri Jun  5 22:32:45 2020
Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
@author: ER17450
"""

import logging
import sys,queue
from datetime import datetime
import signal
import pathlib

from pyqtgraph.Qt import QtCore, QtWidgets, QtGui
import serial.tools.list_ports

from teensy_radar_control.handler import ExtendedRadarHandler
import RadarProcessors



# If the controls are modified in designer.exe, need to run
# pyuic5 RadarGUI.ui -o RadarGUI.py
import RadarGUI
class RadarDisplay(QtWidgets.QMainWindow, RadarGUI.Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(type(self).__name__)
        self.logger.info('Starting Application')

        #self.rh = BasicRadarHandler()
        self.rh = ExtendedRadarHandler()
        self.rpp = RadarProcessors.RadarPulseProcessor()
        self.rsp = RadarProcessors.RadarSpectrumProcessor()
        self.rcp = RadarProcessors.RecordProcessor()
        self.stp = RadarProcessors.SarTriggerProcessor(countdown_thunk=self._on_trigger_off,
                                                       collect_thunk=self._on_trigger_on)

        self.parameter_changes_disabled = False
        self.record_collection_running = False
        self.sar_trigger_collection_running = False
        self.trigger_mutex = QtCore.QMutex()

        self.setupUi()

        signal.signal(signal.SIGINT, self.sigint_handler)

        # Create the com port scanner
        self.connect_list = None
        self._connect_rescan()
        self.connect_timer = QtCore.QTimer()
        self.connect_timer.setSingleShot(True)
        self.connect_timer.setInterval(1000)
        self.connect_timer.timeout.connect(self._connect_rescan)

        # Create the background update task
        self.update_timer = QtCore.QTimer()
        self.update_timer.start(0.1*1000)
        self.update_timer.timeout.connect(self._update)

        self.pulse_writer = None

    def setupUi(self):
        super().setupUi(self)
        self.setWindowTitle('Teensy Radar USB Control')

        # Radar Controls
        ######################################################################
        self.connect_pb.clicked.connect(self._on_connect)

        # DEBUG LIST:
        # self.gain_list = [ch*10+idx for ch in range(1,7) for idx in range(1,9)]
        # gain_default_idx = 0
        #
        # 2020 LIST:
        # self.gain_list = [1,2,4,5,8,10,16,22,32,44,55,88,110,176,352]
        # gain_default_idx = 0
        #
        # 2021 LIST:
        self.gain_list = [1,2,4,5,8,10,16,20,32,40,50,80,100,160,320]
        gain_default_idx = 5

        self._setupDial(self.gain_dial,self._on_gain_dial,self.gain_list,gain_default_idx)

        self.pulse_length_list = [5,10,15,20,25,30,40,80,160,320]
        self.pulse_length_ramp_max = 6
        self._setupDial(self.pulse_length_dial,self._on_pulse_length_dial,self.pulse_length_list,3)
        self.trigger_on_rb.clicked.connect(self._on_trigger_on)
        self.trigger_off_rb.clicked.connect(self._on_trigger_off)

        self.frequency_list = list(range(2410,2431))
        self._setupDial(self.frequency_dial,self._on_frequency_dial,self.frequency_list,len(self.frequency_list)//2)

        self.bandwidth_list = list(range(25,325,25))
        self._setupDial(self.bandwidth_dial,self._on_bandwidth_dial,self.bandwidth_list,0)
        self.bandwidth_gb.clicked.connect(self._on_bandwidth_enable)

        # DSP Controls
        ######################################################################
        # Pulse Processing
        self.filter_alpha_list = [0.5,0.75,0.9,0.95,0.99]
        for fa in self.filter_alpha_list:
            self.pulse_filter_cb.addItem('%4.2f'%(fa,),fa)

        self.mti_size_list = list(range(2,12))
        for ms in self.mti_size_list:
            self.pulse_mti_cb.addItem('%4d'%(ms,),ms)

        # Spectral Processing
        self.spectrum_window_list = ['boxcar','triang','hanning','flattop','hamming','blackmanharris']
        for win in self.spectrum_window_list:
            self.spectrum_window_cb.addItem(win,win)
        self.spectrum_window_cb.setCurrentIndex(2)

        self.spectrum_oversample_list = [1,2,4]
        for osf in self.spectrum_oversample_list:
            self.spectrum_oversample_cb.addItem('%3d'%(osf,),osf)
        self.spectrum_oversample_cb.setCurrentIndex(1)

        # Collection Controls
        ######################################################################
        # Record Data
        self.record_data_format_list = ['raw voltage','wav voltage','dsp_spectrum']
        for fmt in self.record_data_format_list:
            self.record_data_format_cb.addItem(fmt,fmt)

        # Hook up browse button
        self.record_data_browse_pb.clicked.connect(self._on_record_data_browse)

        # SAR Trigger settings
        self.sar_trigger_steps_sb.setValue(72)

        self.sar_trigger_pace_list = [(1.5,1.0),(2.0,1.0),(3.0,1.0)]
        for stp in self.sar_trigger_pace_list:
            txt = '%3.1f:%3.1f' % stp
            self.sar_trigger_pace_cb.addItem(txt,stp)

        # Progress bar
        self.collect_progress_bar.setMaximum(100)
        self.collect_progress_bar.setValue(0)

        # Hook up collection start button
        self.collection_toggle_pb.setChecked(False)
        self.collection_toggle_pb.setText('Start')
        self.collection_toggle_pb.clicked.connect(self._on_collection_toggle)

    def _setupDial(self,dial,handler,value_list,default_idx):
        dial.setMinimum(0)
        dial.setMaximum(len(value_list)-1)
        dial.setWrapping(False)
        dial.valueChanged.connect(handler)
        dial.setValue(default_idx)
        handler(default_idx)

    def sigint_handler(self, signum, frame):
        self.logger.debug('RadarDisplay sigint_handler called')
        self.close()

    def closeEvent(self, event):
        self.logger.debug('Shut down started')
        self.stp.stop()
        self.rcp.stop()
        self.logger.debug('Shut radar handler')
        if self.rh is not None:
            self.rh.join()
        self.logger.debug('Shut timers')
        self.connect_timer.stop()
        self.update_timer.stop()
        self.logger.debug('Shut down done')
        self.logger.info('Application Exited')
        event.accept()

    def _connect_rescan(self):
        self.logger.debug('rescan')
        connect_list = serial.tools.list_ports.comports()
        if connect_list != self.connect_list:
            self.connect_list = connect_list
            self.connect_cb.clear()
            for ci in self.connect_list:
                self.connect_cb.addItem(ci.description,ci.device)
            self.connect_cb.setCurrentIndex(len(self.connect_list)-1)

    @QtCore.pyqtSlot()
    def _on_connect(self):
        if self.connect_pb.isChecked():
            # Get selected port
            port = self.connect_cb.currentData()
            self.logger.info('Trying to connect on: ' + str(port))
            try:
                self.rh.connect(port)
                reply = self.rh.cmd_stop()
                reply = self.rh.cmd_version()
            except:
                self.connect_pb.setChecked(False)

            self.connect_pb.setText('Disconnect')
            self.connect_timer.stop()
            self._change_radar_settings()

        else:
            self.logger.info('Disconnecting')
            self.rh.disconnect()
            self.connect_pb.setText('Connect')

    @QtCore.pyqtSlot(int)
    def _on_gain_dial(self, idx):
        self.gain = self.gain_list[idx]
        self.gain_lcd.display(self.gain)
        self._change_radar_settings()

    @QtCore.pyqtSlot(int)
    def _on_pulse_length_dial(self, idx):
        if self.bandwidth_gb.isChecked() and idx > self.pulse_length_ramp_max:
            idx = self.pulse_length_ramp_max
            self.pulse_length_dial.setValue(idx)
        self.pulse_length = self.pulse_length_list[idx]
        self.pulse_length_lcd.display(self.pulse_length)
        self._change_radar_settings()

    @QtCore.pyqtSlot()
    def _on_trigger_on(self):
        with QtCore.QMutexLocker(self.trigger_mutex):
            self.logger.debug('_on_trigger_on called')
            self.trigger_on_rb.setChecked(True)
            self.rh.cmd_trigger_on()

    @QtCore.pyqtSlot()
    def _on_trigger_off(self):
        with QtCore.QMutexLocker(self.trigger_mutex):
            self.logger.debug('_on_trigger_off called')
            self.trigger_off_rb.setChecked(True)
            self.rh.cmd_trigger_off()

    @QtCore.pyqtSlot(int)
    def _on_frequency_dial(self, idx):
        self.center_frequency = self.frequency_list[idx]
        self.frequency_lcd.display(self.center_frequency)
        self._change_radar_settings()

    @QtCore.pyqtSlot(int)
    def _on_bandwidth_dial(self, idx):
        self.bandwidth = self.bandwidth_list[idx]
        self.bandwidth_lcd.display(self.bandwidth)
        self._change_radar_settings()

    @QtCore.pyqtSlot()
    def _on_bandwidth_enable(self):
        pidx = self.pulse_length_dial.value()
        if self.bandwidth_gb.isChecked():
            if pidx > self.pulse_length_ramp_max:
                self.pulse_length_dial.setValue(self.pulse_length_ramp_max)
            self._on_trigger_on()
        else:
            self._on_trigger_off()
        self._change_radar_settings()

    @QtCore.pyqtSlot()
    def _on_record_data_browse(self):
        #home = pathlib.Path.home()
        #fname = QtWidgets.QFileDialog.getSaveFileName(directory=str(home))
        fname = QtWidgets.QFileDialog.getSaveFileName()
        fname = fname[0]
        self.record_data_filename_le.setText(fname)

    @QtCore.pyqtSlot()
    def _on_collection_toggle(self):
        if self.rh.is_alive() and self.collection_toggle_pb.isChecked():
            self.collection_toggle_pb.setText('Stop')
            self.collection_toggle_pb.setChecked(True)

            record = self.record_data_gb.isChecked()
            sar_triggers = self.sar_trigger_gb.isChecked()

            if record or sar_triggers:
                try:
                    # Disable GUI changes
                    self._disable_parameter_changes()

                    # Configure the sar trigger processor
                    if sar_triggers:
                        steps = self.sar_trigger_steps_sb.value()
                        dx = self.sar_trigger_dx_sb.value()
                        wtime,ctime = self.sar_trigger_pace_cb.currentData()
                        self.stp.set_sar_parameters(steps,dx,wtime,ctime)
                        # Set zero dur, trigger steps will stop the recording
                        self.record_data_duration_sb.setValue(0)
                        self._on_trigger_off()
                    else:
                        steps = 0
                        dx = 0
                        wtime, ctime = 0.0, 0.0

                    # Configure the record processor
                    if record:
                        # Save the sar state in the headers
                        # zero steps means not a sar file
                        self.rcp.set_sar_parameters(steps,dx,wtime,ctime)

                        # What pulse to expect
                        pl = self.pulse_length/1000.0
                        cfreq = self.center_frequency*1e6
                        if self.bandwidth_gb.isChecked():
                            bw = self.bandwidth*1e6
                        else:
                            bw = 0.0
                        self.rcp.set_pulse_parameters(pl,cfreq,bw)

                        # What filename and length to expect
                        fname = self.record_data_filename_le.text()
                        fmt = self.record_data_format_cb.currentData()
                        dur = self.record_data_duration_sb.value()
                        self.rcp.set_file_parameters(fname,fmt,dur)

                    # Start data streaming before launcing the processors
                    # This may let a few pulses slip by, but it is better
                    # than a long delay.
                    self._change_radar_settings()

                    # Start the processors
                    self.logger.info('Starting collection')
                    if record:
                        self.logger.debug('Starting record')
                        self.record_collection_running = True
                        self.rcp.start()
                    if sar_triggers:
                        self.logger.debug('Starting sar triggers')
                        self.sar_trigger_collection_running = True
                        self.stp.start()
                except Exception as e:
                    self.logger.warning('Collection failed to start')
                    self.logger.debug(str(e))
                    self._set_collection_stopped()

            else:
                # Start in live streaming mode
                self._change_radar_settings()

        else:
            self._set_collection_stopped()


    def _set_collection_stopped(self):
        self.logger.info('Stopping collection')

        # Turn off collection modes
        self.record_data_gb.setChecked(False)
        self.sar_trigger_gb.setChecked(False)

        # Set triggers according to BW mode
        if self.bandwidth_gb.isChecked():
            self._on_trigger_on()
        else:
            self._on_trigger_off()

        # This may pause until all of the data is flushed to disk
        # It should be safe to call .stop() on non-running processors
        self.logger.debug('Stopping sar triggers')
        self.stp.stop()
        self.sar_trigger_collection_running = False

        self.logger.debug('Stopping record')
        self.rcp.stop()
        self.record_collection_running = False

        self.collect_progress_bar.setMaximum(100)
        self.collect_progress_bar.setValue(0)

        self.collection_toggle_pb.setText('Start')
        self.collection_toggle_pb.setChecked(False)

        # Enable user GUI changes again
        self._enable_parameter_changes()

        # Will send start and stop commands as necessary
        self._change_radar_settings()



    def _change_radar_settings(self):
        try:
            pulse_length = self.pulse_length
            gain = self.gain
            if self.bandwidth_gb.isChecked():
                # Range mode => Ramp
                flo = self.center_frequency - self.bandwidth/2.0
                fhi = self.center_frequency + self.bandwidth/2.0
                if self.ramp_up_rb.isChecked():
                    fstart = flo
                    fstop = fhi
                else:
                    fstart = fhi
                    fstop = flo
                freturn = 0.0
            else:
                # Range rate mode => No ramp
                fstart = self.center_frequency
                fstop = self.center_frequency
                freturn = 0.0
        except:
            # Parameters don't make sense
            return
        if self.collection_toggle_pb.isChecked():
            self.rh.cmd_start(pulse_length,gain,fstart,fstop,freturn)
        else:
            self.rh.cmd_stop()

    def _disable_parameter_changes(self):
        self.radar_controls_group.setEnabled(False)
        self.dsp_controls_group.setEnabled(False)
        self.record_data_gb.setEnabled(False)
        self.sar_trigger_gb.setEnabled(False)
        self.parameter_changes_disabled = True

    def _enable_parameter_changes(self):
        self.radar_controls_group.setEnabled(True)
        self.dsp_controls_group.setEnabled(True)
        self.record_data_gb.setEnabled(True)
        self.sar_trigger_gb.setEnabled(True)
        self.parameter_changes_disabled = False

    def _update(self):
        if self.rh.is_alive():
            dt = self.rh.time_since_heartbeat()
            if dt is not None:
                self.connect_status_le.setStyleSheet('background-color: green; color: white;')
                txt = '%5.2f' % dt
                self.connect_status_le.setText(txt)
            else:
                self.connect_status_le.setStyleSheet('background-color: yellow; color: black;')
                txt = 'Wait'
                self.connect_status_le.setText(txt)
        else:
            self.connect_status_le.setStyleSheet('background-color: red; color: black;')
            self.connect_status_le.setText('None')
            # Connection must have crashed
            if self.connect_pb.isChecked():
                # Shut down any collections
                self.collection_toggle_pb.setChecked(False)
                self._on_collection_toggle()
                # Shut down connection
                self.connect_pb.setChecked(False)
                self._on_connect()
            # Single shot timer to rescan the com ports
            if not self.connect_timer.isActive():
                self.connect_timer.start()

        # Process the pulse queue
        while True:
            try:
                pulse = self.rh.get_pulse(block=False)
            except queue.Empty:
                break

            # If a record is in progress, add the pulse
            if self.record_collection_running and self.rcp.in_progress():
                try:
                    self.rcp.add_pulse(pulse)
                except Exception as e:
                    self.logger.warning('Failed to add pulse to collection, continuing.')
                    self.logger.warning(str(e))

            # If there is a timed collection running, check if is is still running
            if self.parameter_changes_disabled == True:
                if (self.record_collection_running and not self.rcp.in_progress()) or \
                        (self.sar_trigger_collection_running and not self.stp.in_progress()):
                    # collection was stopped by the processor
                    self._set_collection_stopped()
                elif self.rcp.in_progress() == True and self.stp.in_progress() == False:
                    # update progress bar using record progress
                    complete, total = self.rcp.progress()
                    self.collect_progress_bar.setMaximum(total)
                    self.collect_progress_bar.setValue(complete)
                else:
                    # update progress bar using sar trigger progress
                    complete, total = self.stp.progress()
                    self.collect_progress_bar.setMaximum(total)
                    self.collect_progress_bar.setValue(complete)

            # This realy only need to happen when the values change
            # Configure the pulse processor
            mti_size = self.pulse_mti_cb.currentData()
            filter_alpha = self.pulse_filter_cb.currentData()
            if not self.pulse_filter_ck.isChecked():
                filter_alpha = 0.0

            if self.pulse_raw_rb.isChecked():
                self.rpp.set_mode_params(RadarProcessors.PULSE_MODE_RAW,1,filter_alpha)
            elif self.pulse_debias_rb.isChecked():
                self.rpp.set_mode_params(RadarProcessors.PULSE_MODE_DEBIAS,1,filter_alpha)
            elif self.pulse_mti_rb.isChecked():
                self.rpp.set_mode_params(RadarProcessors.PULSE_MODE_MTI,mti_size,filter_alpha)

            # Configure the spectral processor
            win = self.spectrum_window_cb.currentData()
            osf = self.spectrum_oversample_cb.currentData()
            self.rsp.set_mode_params(win,osf)

            # use the pulse processor and check for a new pulse
            new_pulse_type = self.rpp.add_msg_pulse(pulse)
            pl, cfreq, bw, data_size = self.rpp.get_pulse_params()
            if new_pulse_type:
                self.rsp.set_pulse_params(pl, cfreq, bw, data_size)

            # Pump through the processors
            vsig = self.rpp.get_if_voltage()
            self.rsp.add_if_voltage(vsig)
            spectrum = self.rsp.get_spectrum()
            waterfall = self.rsp.get_waterfall()

            # Update IF Voltage plot
            ft = self.rpp.get_fast_time_scale()
            self.if_voltage_pgw.set_fast_time_scale(ft)
            self.if_voltage_pgw.set_voltage(vsig)

            # Update IF Spectrum
            if self.spectrum_xscale_m_rb.isChecked():
                if abs(bw)>0.0:
                    scale = self.rsp.get_range_scale()
                    self.if_spectrum_pgw.set_range_scale(scale)
                else:
                    scale = self.rsp.get_rrate_scale()
                    self.if_spectrum_pgw.set_rrate_scale(scale)
            else:
                scale = self.rsp.get_frequency_scale()
                self.if_spectrum_pgw.set_frequency_scale(scale)
            self.if_spectrum_pgw.set_spectrum(spectrum)

            # Update IF Waterfall
            self.if_waterfall_pgw.set_waterfall(waterfall)

            # Update waterfall axes (Note: has to be done after set_waterfall)
            st = self.rsp.get_slow_time_scale()
            self.if_waterfall_pgw.set_slow_time_scale(st)
            if self.spectrum_xscale_m_rb.isChecked():
                if abs(bw)>0.0:
                    scale = self.rsp.get_range_scale()
                    self.if_waterfall_pgw.set_range_scale(scale)
                else:
                    scale = self.rsp.get_rrate_scale()
                    self.if_waterfall_pgw.set_rrate_scale(scale)
            else:
                scale = self.rsp.get_frequency_scale()
                self.if_waterfall_pgw.set_frequency_scale(scale)


        # Display the log messages
        while True:
            try:
                log_msg = self.rh.get_log_msg(block=False)
            except queue.Empty:
                break
            time_str = datetime.now().isoformat()
            msg_str = '%s %s' % (time_str, str(log_msg))
            self.log_area.appendPlainText(msg_str)

#%%
def main():
    app = QtGui.QApplication(sys.argv)
    # KLUDGE:
    # This fixes a problem with axis calculations when the primary
    # monitor and the display monitor have different resolution setting
    # in win10
    #app.setAttribute(QtCore.Qt.AA_Use96Dpi)
    app.setQuitOnLastWindowClosed(True)

    rd = RadarDisplay()
    rd.show()

    exit_code = app.exec_()
    sys.exit(exit_code)

if __name__ == '__main__':
    #log_level = logging.DEBUG
    log_level = logging.INFO

    logging.basicConfig(format='%(asctime)s %(name)-24s %(levelname)-8s %(message)s',
                        datefmt="%Y-%m-%dT%H:%M:%S",
                        level=log_level)

    main()


