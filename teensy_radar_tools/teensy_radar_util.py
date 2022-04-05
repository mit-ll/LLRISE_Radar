# -*- coding: utf-8 -*-
"""
Created on Mon Jun 22 22:02:47 2020
Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
@author: ER17450
"""

import struct
import numpy as np
import pylab as plt
from math import floor, fabs, log10, sqrt, pi
from scipy.constants import speed_of_light
import scipy.signal

from dataclasses import dataclass
from teensy_radar_control import message

# Common packet
FILE_UNIQUE_WORD = 0xB1B2B3B4

@dataclass
class teensy_radar_file_header:
    unique_word: int
    pulse_count: int
    sar_steps: int
    sar_dx: float
    sar_wcount: int
    sar_ccount: int


class teensy_radar_file_reader(object):
    FILE_HEADER_BYTES = 4+4+4+4+2+2
    PULSE_HEADER_BYTES = 2+2+4+4+4+2+2+4+4+4

    # Teensy ADC as it is configured
    v_max=3.3
    adc_bits=16
    v_scale = v_max/2.0**adc_bits
    v_center = 2.5*2.0/3.0 - 0.050

    def __init__(self,fname):
        super().__init__()
        self.fh = open(fname,mode='rb')

        self.file_header = self._read_file_header()
        self.proto_header = self._read_pulse_header()

        # From the file header
        self.pulse_count = self.file_header.pulse_count
        self.sar_steps = self.file_header.sar_steps
        self.sar_dx = self.file_header.sar_dx/100.0 # cm->m
        self.sar_wcount = self.file_header.sar_wcount
        self.sar_ccount = self.file_header.sar_ccount

        # From the pulse header with some unit conversions
        self.pulse_length = self.proto_header.pulse_length_ms/1000.0
        self.freq_start = self.proto_header.freq_start*1e6
        self.freq_stop = self.proto_header.freq_stop*1e6
        self.freq_return = self.proto_header.freq_return*1e6
        self.data_size = self.proto_header.data_size

        # Derived
        self.freq_center = (self.freq_start + self.freq_stop)/2.0
        self.bandwidth = fabs(self.freq_stop-self.freq_start)
        self.sample_rate = self.data_size/self.pulse_length

        self.seek_pulse(0)

    def seek_pulse(self,pnum):
        bl = pnum*(self.proto_header.hdr_size+2*self.proto_header.data_size)+self.FILE_HEADER_BYTES
        self.fh.seek(bl)

    def get_pulse_params(self):
        pulse_length = self.proto_header.pulse_length_ms/1000.0
        freq_start = self.proto_header.freq_start*1e6
        freq_stop = self.proto_header.freq_stop*1e6
        freq_return = self.proto_header.freq_return*1e6
        return pulse_length, freq_start, freq_stop, freq_return

    def read_if_adc_pulses(self,pcount):
        status_arr = np.zeros((pcount,),dtype=np.uint32,order='F')
        adc_arr = np.zeros((pcount,self.proto_header.data_size),dtype=float,order='F')
        for ii in range(0,pcount):
            try:
                header = self._read_pulse_header()
                sig = self._read_pulse_data()
                status_arr[ii] = header.status
                adc_arr[ii,:] = sig
            except Exception as e:
                print(str(e))
                pcount = ii
                break
            status_arr = status_arr[0:pcount]
            adc_arr = adc_arr[0:pcount,:]
            trigger_arr = (status_arr&0x1).astype(int)
        return trigger_arr, adc_arr

    def read_if_voltage_pulses(self,pcount):
        trigger, adc = self.read_if_adc_pulses(pcount)
        vsig = adc*self.v_scale - self.v_center
        return trigger, vsig

    def _read_file_header(self):
        buf = self.fh.read(self.FILE_HEADER_BYTES)
        file_header = teensy_radar_file_header(*struct.unpack('IIIfHH',buf))
        if file_header.unique_word != FILE_UNIQUE_WORD:
            raise IOError('File has wrong unique word.  Is it a teensy radar binary file?')
        return file_header

    def _read_pulse_header(self):
        buf = self.fh.read(self.PULSE_HEADER_BYTES)
        pulse_header = message.msg_pulse_header(*struct.unpack('HHIIIHHfff',buf))
        return pulse_header

    def _read_pulse_data(self):
        buf = self.fh.read(2*self.data_size)
        data = np.frombuffer(buf,dtype=np.dtype('<u2'))
        return data


def compress_real_pulses(sig_data, n=-1, win='hanning'):
    pcount,scount = sig_data.shape
    if n < scount: n = scount

    # if win is not a str assume it is the actual 1D window array
    if isinstance(win, str):
        win = scipy.signal.windows.get_window(win,scount)

    # Window the data
    win = 2*win/np.sum(win)
    win = np.tile(win,(pcount,1))
    win_data = win * sig_data

    # Zero pad appropriately
    pad_data = np.zeros((pcount,n),np.float)
    lo = floor(n/2.0)-floor(scount/2.0)
    pad_data[:,lo:(lo+scount)]=win_data

    # Do the FFT
    range_gates = np.fft.rfft(np.fft.ifftshift(pad_data,axes=(1,)),n=n,axis=1)

    return range_gates



def extract_sar_dwells(pulse_length,trigger,if_voltage):
    # Extract and average pulses
    trig_on = np.where((np.diff(trigger) > 0))[0] + 1
    trig_off = np.where((np.diff(trigger) < 0))[0] + 1

    # Prune unexpected partial pulses at the beginning or end
    if trig_off[0] < trig_on[0]:
        trig_off = trig_off[1:]
    if trig_on[-1] > trig_off[-1]:
        trig_on = trig_on[0:-1]

    mean_dwell_count = np.mean(trig_off-trig_on)

    steps = trig_on.shape[0]
    scount = if_voltage.shape[1]

    dwell_offset = int(round(0.1/pulse_length))
    dwell_dur = int(round(mean_dwell_count - 0.5/pulse_length))
    dwell_voltage = np.zeros((steps,scount),dtype=float)
    for ii in range(0,steps):
        i0 = trig_on[ii] + dwell_offset
        i1 = i0 + dwell_dur
        dwell_voltage[ii,:] = np.mean(if_voltage[i0:i1,:],axis=0)

    return dwell_voltage

