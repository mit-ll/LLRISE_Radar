# -*- coding: utf-8 -*-
"""
Created on Tue Jul  7 09:12:54 2020
Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
@author: ER17450
"""
import logging
import threading, queue
import struct,copy
import numpy as np
import scipy.signal
import scipy.linalg
from scipy.constants import speed_of_light
import sounddevice as sd
from math import ceil

PULSE_MODE_RAW = 1
PULSE_MODE_DEBIAS = 2
PULSE_MODE_MTI = 3

MAX_MTI_SIZE = 11


class RadarPulseProcessor(object):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(type(self).__name__)

        self.v_max=3.3
        self.adc_bits=16
        self.adc_enob=11
        self.adc_floor = -(1.76+6.02*self.adc_enob)
        self.v_scale = self.v_max/2.0**self.adc_bits
        # This has to do with the details of the driving circuit
        # v_center = 2.5*2.0/3.0
        self.v_center = 2.5*2.0/3.0 - 0.050
        self.v_bias = 0.0

        self.mti_coef = scipy.linalg.pascal(MAX_MTI_SIZE,kind='upper')
        self.mti_coef = self.mti_coef/np.sum(self.mti_coef,axis=0)

        # Set sensible defaults
        self.mode = PULSE_MODE_DEBIAS
        self.mti_size = 1
        self.filter_alpha = 0.0

        self.mti_history = None
        self.mti_history_idx = 0
        self.prev_msg_pulse = None
        self.prev_vsig = None



    def set_mode_params(self,mode,mti_size,filter_alpha):
        if mode != self.mode or mti_size != self.mti_size or \
            filter_alpha != self.filter_alpha:
                self.mode = mode
                self.mti_size = mti_size
                self.filter_alpha = filter_alpha
                self._setup_mti_win()
                #self.prev_vsig = None

    def add_msg_pulse(self, msg_pulse):

        if self._update_pulse_params(msg_pulse):
            self.logger.debug('New Pulse')
            self._setup_mti_history()
            self._setup_mti_win()
            self.prev_vsig = None

        if self.mode == PULSE_MODE_RAW:
            vsig = msg_pulse.data*self.v_scale
        elif self.mode == PULSE_MODE_DEBIAS:
            vsig = msg_pulse.data*self.v_scale - self.v_center - self.v_bias
        elif self.mode == PULSE_MODE_MTI:
            vsig = msg_pulse.data*self.v_scale - self.v_center - self.v_bias
            vsig = self._update_mti(vsig)
        else:
            raise ValueError('unrecognized pulse mode')

        if self.prev_vsig is not None:
            # Apply smoothing filter
            self.vsig = self.filter_alpha*self.prev_vsig + (1.0-self.filter_alpha)*vsig
            self.prev_vsig = self.vsig
            return False
        else:
            # Startup smoothing filter
            self.vsig = vsig
            self.prev_vsig = self.vsig
            return True

    def get_if_voltage(self):
        return self.vsig

    def get_fast_time_scale(self):
        return self.fast_time

    def _setup_mti_history(self):
        self.mti_history = np.zeros((self.data_size,2*MAX_MTI_SIZE))
        self.mti_history_idx = MAX_MTI_SIZE

    def _setup_mti_win(self):
        self.mti_win = self.mti_coef[0:self.mti_size,self.mti_size-1]
        self.mti_win = self.mti_win * (-1.0)**np.arange(0,self.mti_size)

    def _update_mti(self,vsig):
        self.mti_history[:,self.mti_history_idx]  = vsig
        self.mti_history_idx = self.mti_history_idx + 1
        if self.mti_history_idx >= 2*MAX_MTI_SIZE:
            self.mti_history[:,0:MAX_MTI_SIZE] = \
                self.mti_history[:,MAX_MTI_SIZE:(2*MAX_MTI_SIZE)]
            self.mti_history_idx = MAX_MTI_SIZE

        i0 = self.mti_history_idx - self.mti_size
        i1 = self.mti_history_idx
        vsig = np.sum(self.mti_history[:,i0:i1]*self.mti_win,axis=1)
        return vsig

    def _different_pulse_params(self, msg_pulse):
        # If no previous pulse, the this pulse is different
        if self.prev_msg_pulse is None:
            return True

        # The pulse number and pulse cycle_count change every pulse.
        # It is not enough just to compare headers
        ch = msg_pulse.header
        ph = self.prev_msg_pulse.header
        if ch.data_size != ph.data_size or \
            ch.gain != ph.gain or \
            ch.pulse_length_ms != ph.pulse_length_ms or \
            ch.freq_start != ph.freq_start or \
            ch.freq_stop != ph.freq_stop or \
            ch.freq_return != ph.freq_return:
                return True
        return False

    def get_pulse_params(self):
        return self.pl, self.cfreq, self.bw, self.data_size

    def _update_pulse_params(self, msg_pulse):
        if self._different_pulse_params(msg_pulse):
            self.prev_msg_pulse = copy.copy(msg_pulse)

            header = msg_pulse.header
            self.pl = header.pulse_length_ms/1000.0
            self.cfreq = (header.freq_stop + header.freq_start)*1e6/2.0
            self.bw = abs(header.freq_stop - header.freq_start)*1e6
            self.data_size = header.data_size

            self.srate = header.data_size/self.pl
            self.fast_time = np.arange(0.0,header.data_size)/self.srate

            return True

        return False


class RadarSpectrumProcessor(object):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(type(self).__name__)

        self.v_max=3.3

        self.history_secs = 6.0
        self.waterfall_arr = np.zeros((100,100))
        self.waterfall_idx = 0

        # Set sensible defaults
        self.win = 'hamming'
        self.osf = 2
        self.set_pulse_params(0.02,2450e6,100e6,1000)

    def set_waterfall_history(self,secs):
        self.history_secs = secs

    def set_mode_params(self,win,osf):
        if win != self.win or osf != self.osf:
            self.osf = osf
            self.win = win
            self.set_pulse_params(self.pl,self.cfreq,self.bw,self.data_size)

    def set_pulse_params(self, pl, cfreq, bw, data_size):
        self.pl = pl
        self.cfreq = cfreq
        self.bw = bw
        self.data_size = data_size

        self.spec_size = round(self.osf * data_size)
        self.win_arr = scipy.signal.get_window(self.win,self.data_size)
        self.win_arr = 2*self.win_arr/np.sum(self.win_arr)

        dt = pl/data_size
        lamb = speed_of_light / cfreq
        self.spec_freq = np.fft.rfftfreq(self.spec_size,d=dt)
        self.det_size = self.spec_freq.shape[0]
        self.logger.debug('bw %f' % (bw,))
        if abs(bw) > 0.0:
            self.spec_tau = self.spec_freq * pl / bw
            self.spec_range = self.spec_tau * speed_of_light / 2.0
            self.spec_rrate = None
        else:
            self.spec_tau = None
            self.spec_range = None
            self.spec_rrate = self.spec_freq * lamb / 2.0

        self.waterfall_len = int(self.history_secs/pl)
        self.slow_time = np.arange(0,self.waterfall_len) * pl

        # Only build a new array if the size has changes
        if self.waterfall_arr.shape != (self.det_size,2*self.waterfall_len):
            self.waterfall_arr = np.zeros((self.det_size,2*self.waterfall_len))
            self.waterfall_idx = self.waterfall_len


    def add_if_voltage(self, vsig):
        # TBD: this should zero pad appropriately to account for phase
        # It is not necessary if only plotting amplitude
        spec = np.fft.rfft(self.win_arr*vsig/self.v_max,n=self.spec_size)
        det = 20*np.log10(abs(spec)+1e-30)

        # Updata spectrum
        self.spec = det

        # Update waterfall
        self.waterfall_arr[:,self.waterfall_idx] = self.spec
        self.waterfall_idx = self.waterfall_idx + 1
        if self.waterfall_idx >= 2*self.waterfall_len:
            self.waterfall_arr[:,0:self.waterfall_len] = \
                self.waterfall_arr[:,self.waterfall_len:(2*self.waterfall_len)]
            self.waterfall_idx = self.waterfall_len


    def get_spectrum(self):
        return self.spec

    def get_waterfall(self):
        i0 = self.waterfall_idx-self.waterfall_len
        i1 = self.waterfall_idx
        return self.waterfall_arr[:,i0:i1]

    def get_slow_time_scale(self):
        return self.slow_time

    def get_frequency_scale(self):
        return self.spec_freq

    def get_tau_scale(self):
        return self.spec_tau

    def get_range_scale(self):
        return self.spec_range

    def get_rrate_scale(self):
        return self.spec_rrate




class RecordProcessor(object):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(type(self).__name__)

        self.th = None
        self.th_keep_running = True
        self.pulse_queue = queue.Queue(maxsize=1000)

        self.fh = None
        self.pulse_parameters_set = False
        self.sar_parameters_set = False
        self.file_parameters_set = False

    def set_pulse_parameters(self, pl, cfreq, bw):
        self.pl = pl
        self.cfreq = cfreq
        self.bw = bw

        self.pulse_parameters_set = True

    def set_sar_parameters(self, steps, dx, wtime, ctime):
        self.sar_steps = steps
        self.sar_dx = dx
        self.wtime = wtime
        self.ctime = ctime

        self.sar_parameters_set = True

    def set_file_parameters(self, fname, fmt, dur):
        self.file_fname = fname
        self.file_fmt = fmt
        self.file_dur = dur

        self.file_parameters_set = False
        self.logger.debug('opening file')
        try:
            self.fh = open(self.file_fname,'wb')
        except Exception as e:
            self.logger.debug(str(e))
            raise e

        self.file_parameters_set = True

    def start(self):
        if self.in_progress():
            raise RuntimeError('Collection already in progress')

        if not self.file_parameters_set:
            raise RuntimeError('Pulse parameters must be set')

        if not self.file_parameters_set:
            raise RuntimeError('File parameters must be set to record')

        if not self.sar_parameters_set:
            raise RuntimeError('SAR parameters must be set generate triggers')

        # zero dur record will continue until .stop()
        self.pulses_total = 0
        if self.file_dur > 0:
            self.pulses_total = ceil(self.file_dur/self.pl)
        self.pulses_written = 0

        try:
            self.th_keep_running = True
            self.th = threading.Thread(target=self._bg_thread,args=())
            self.th.daemon = True
            self.th.start()
        except Exception as e:
            self.logger.warning('Thread launch failed')
            raise e

        self.logger.debug('start done')

    def stop(self):
        if self.in_progress():
            self.logger.debug('stopping')
            self.th_keep_running = False
            self.logger.debug('join thread')
            self.th.join()
            self.th = None

        if self.fh is not None:
            self.fh.close()
            self.fh = None


    def in_progress(self):
        if self.th is not None and self.th.is_alive():
            return True
        return False

    def progress(self):
        # Access to pulses_written is atomic.
        # zero dur record will continue until .stop()
        if self.pulses_total == 0:
            return self.pulses_written, self.pulses_written
        else:
            return self.pulses_written, self.pulses_total

    def add_pulse(self, msg_pulse):
        header = msg_pulse.header

        # Qualify pulse
        pl = header.pulse_length_ms/1000.0
        cfreq = (header.freq_stop + header.freq_start)*1e6/2.0
        bw = abs(header.freq_stop - header.freq_start)*1e6
        if pl != self.pl or cfreq != self.cfreq or bw != self.bw:
            return

        if self.th_keep_running:
            self.pulse_queue.put(msg_pulse)

    def _bg_thread(self):
        self.logger.debug('_bg_thread started')

        # Write out a simple header
        self.pulses_written = 0
        self._write_header_to_file()

        while self.th_keep_running and (self.pulses_total == 0 or self.pulses_written < self.pulses_total):
            try:
                msg_pulse = self.pulse_queue.get(block=True, timeout=0.1)
            except queue.Empty:
                continue
            except Exception as e:
                self.th_keep_running = False
                raise e
            self._write_pulse_to_file(msg_pulse)
            self.pulse_queue.task_done()
            self.pulses_written = self.pulses_written + 1

        # Re-write the header with the correct number of pulses
        self.logger.debug('_bg_thread re-writing header')
        self._write_header_to_file()

        # Drain any remaining pulses from the queue
        # no more pulses can be added
        self.logger.debug('_bg_thread draining queue')
        while not self.pulse_queue.empty():
            self.pulse_queue.get()
            self.pulse_queue.task_done()

        self.logger.debug('_bg_thread exited')


    def _write_header_to_file(self):
        uw = 0xB1B2B3B4
        if self.sar_steps > 0:
            steps = self.sar_steps
            dx = self.sar_dx
            wcount = round(self.wtime/self.pl)
            ccount = round(self.ctime/self.pl)
        else:
            steps = 0
            dx = 0.0
            wcount = 0
            ccount = 0

        hdr = struct.pack('IIIfHH',uw,self.pulses_written,steps,dx,wcount,ccount)

        self.fh.seek(0)
        self.fh.write(hdr)
        self.fh.flush()

    def _write_pulse_to_file(self, msg_pulse):
        header = msg_pulse.header
        hdr = struct.pack('HHIIIHHfff',
                          header.hdr_size,
                          header.data_size,
                          header.pulse_number,
                          header.pulse_cycle_count,
                          header.status,
                          header.gain,
                          header.pulse_length_ms,
                          header.freq_start,
                          header.freq_stop,
                          header.freq_return)
        self.fh.write(hdr)
        self.fh.write(msg_pulse.data.tobytes())
        self.fh.flush()





class SarTriggerProcessor(object):
    def __init__(self, countdown_thunk=None, collect_thunk=None):
        super().__init__()
        self.logger = logging.getLogger(type(self).__name__)

        # Save callback functions
        # These will be called to inform the rest of the system
        # it is time to change to the indicated mode
        #
        # Set defaults so there is not need for if's in the
        # thread loop
        self._countdown_thunk = self._default_countdown_thunk
        if countdown_thunk is not None:
            self._countdown_thunk = countdown_thunk

        self._collect_thunk = self._default_collect_thunk
        if countdown_thunk is not None:
            self._collect_thunk = collect_thunk

        # No thread yet
        self.th_keep_running = False
        self.th = None

        self.audio_srate = 44100

        self.current = 0
        self.sar_parameters_set = False

    def set_sar_parameters(self,steps,dx,wtime,ctime):
        self.steps = steps
        self.dx = dx
        self.wtime = wtime
        self.ctime = ctime
        self._make_sar_sound_arrays(wtime, ctime)
        self.sar_parameters_set = True

    def start(self):
        if self.th is not None:
            raise RuntimeError('Collection already in progress')

        if not self.sar_parameters_set:
            raise RuntimeError('SAR parameters must be set generate triggers')

        try:
            self.th_keep_running = True
            self.th = threading.Thread(target=self._bg_thread,args=())
            self.th.daemon = True
            self.th.start()
        except Exception as e:
            self.logger.warning('Thread launch failed')
            raise e

        self.logger.debug('start done')

    def stop(self):
        if self.th is not None:
            self.th_keep_running = False
            self.th.join()
            self.th = None

    def in_progress(self):
        if self.th is not None and self.th.is_alive():
            return True
        return False

    def progress(self):
        return self.current, self.steps

    def _bg_thread(self):
        self.logger.debug('_bg_thread started')
        audio_out = sd.OutputStream(samplerate=self.audio_srate,channels=1,latency='low')
        audio_out.start()
        self.current = 0
        while self.th_keep_running and self.current < self.steps:
            self.logger.debug('_bg_thread %d or %d' % (self.current, self.steps))
            self._countdown_thunk()
            audio_out.write(self.sar_trigger_countdown)
            self._collect_thunk()
            audio_out.write(self.sar_trigger_collect)
            self.current = self.current + 1

        # Extra delay at the end to give time for data to work
        # its way thru various queues
        self._countdown_thunk()
        audio_out.write(self.sar_trigger_ended)
        audio_out.stop(ignore_errors=True)
        audio_out.close(ignore_errors=True)

        self.logger.debug('_bg_thread exited')


    def _default_countdown_thunk(self):
        self.logger.debug('default _countdown_thunk called')

    def _default_collect_thunk(self):
        self.logger.debug('default _collect_thunk called')

    def _make_sar_sound_arrays(self,wtime,ctime):
        btime = wtime/9.0
        boop = self._make_boop(440.00,btime)
        quiet = self._make_silence(btime)
        self.sar_trigger_countdown = np.hstack((boop,quiet,quiet,boop,quiet,quiet,boop,quiet,quiet))

        dtime = 0.25
        bep = self._make_boop(554.37,ctime-dtime)*0.5
        bap = self._make_boop(880.00,dtime)*0.5
        self.sar_trigger_collect = np.hstack((bep,bap))

        end1 = self._make_boop(659.25,btime)
        end2 = self._make_boop(554.37,btime)
        end3 = self._make_boop(440.00,btime)
        self.sar_trigger_ended = np.hstack((end1,end2,end3,end1,end2,end3,end1,end2,end3))



    def _make_boop(self,freq,dur):
        scount = int(round(dur*self.audio_srate))
        tt = np.arange(0,scount)/self.audio_srate
        boop = np.cos(2*np.pi*tt*freq,dtype=np.float32)

        envelope = np.zeros((scount,),dtype=np.float32)
        trans = 100
        envelope[(trans):(scount-trans-1)] = 1.0
        win = np.hanning(trans+1).astype(np.float32)
        win = win/np.sum(win)
        envelope = np.convolve(envelope,win,mode='same')

        return boop*envelope

    def _make_silence(self,dur):
        scount = int(round(dur*self.audio_srate))
        return np.zeros((scount,),dtype=np.float32)
