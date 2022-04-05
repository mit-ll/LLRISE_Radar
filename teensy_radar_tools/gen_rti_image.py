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

from teensy_radar_util import teensy_radar_file_reader, compress_real_pulses, extract_sar_dwells

#%%
def gen_rti_image(fname, start_sec, dur):
    tfr = teensy_radar_file_reader(fname)

    pl = tfr.pulse_length
    srate = tfr.sample_rate
    cfreq = tfr.freq_center
    bw = tfr.bandwidth

    pstart = round(start_sec/pl)
    pcount = round(dur/pl)
    if pstart + pcount > tfr.pulse_count:
        raise IOError('Not enough pulse in file')

    tfr.seek_pulse(pstart)
    trigger, if_voltage = tfr.read_if_voltage_pulses(pcount)
    pcount = if_voltage.shape[0]
    scount = if_voltage.shape[1]

    # Remove any remaining DC bias
    if_voltage = if_voltage - np.mean(if_voltage)

    # Transform extracted pulses to range gates
    osf=4
    #win = scipy.signal.windows.hann(scount)
    win = scipy.signal.windows.dpss(scount,NW=pi)
    #win = scipy.signal.windows.chebwin(scount,at=100.0)
    rti = compress_real_pulses(if_voltage/tfr.v_max, n=osf*scount, win=win)

    # Generate axis scales
    spec_freq = np.fft.rfftfreq(osf*scount,d=1.0/srate)
    spec_tau = spec_freq * pl / bw
    spec_range = spec_tau * speed_of_light / 2.0
    slow_time = np.arange(pstart,pstart+pcount)*pl

    return spec_range, slow_time, rti


#%%
def plot_rti_image(fig_num, title, spec_range, slow_time, rti):
    det = 20*np.log10(np.abs(rti)+1e-30)

    plt.figure(fig_num)
    plt.clf()
    extent=(spec_range[0],spec_range[-1],slow_time[0],slow_time[-1])

    # vmin and vmax are the color scale min and max
    plt.imshow(det,vmin =-100.0, vmax=-30.0,
               interpolation='bilinear',aspect='auto',cmap='jet',
               extent=extent,origin='lower')
    cbar=plt.colorbar()
    cbar.ax.set_ylabel('dBFS')
    plt.xlabel('Range (m)')
    plt.ylabel('Slow Time (s)')
    plt.title(title)

#%%
fname = r'./test1.dat'
start_sec = 0.0
dur = 30.0
spec_range, slow_time, rti = gen_rti_image(fname, start_sec, dur)

plot_rti_image(102, "RTI", spec_range, slow_time, rti)
plot_rti_image(103, "MTI", spec_range, slow_time[1:], np.diff(rti,axis=0))

#%%
plt.show()

