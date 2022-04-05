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
def gen_sar_image(fname, grid_range, min_range, max_angle):
    tfr = teensy_radar_file_reader(fname)

    pl = tfr.pulse_length
    srate = tfr.sample_rate
    cfreq = tfr.freq_center
    bw = tfr.bandwidth

    pcount = tfr.pulse_count
    trigger, if_voltage = tfr.read_if_voltage_pulses(pcount)
    pcount = if_voltage.shape[0]
    scount = if_voltage.shape[1]

    # Remove any remaining DC bias
    if_voltage = if_voltage - np.mean(if_voltage)

    # Get the dwells
    dwell_voltage = extract_sar_dwells(pl,trigger,if_voltage)
    dwell_steps = dwell_voltage.shape[0]

    # Transform extracted pulses to range gates
    #
    osf=32
    spec_freq = np.fft.rfftfreq(osf*scount,d=1.0/srate)
    spec_tau = spec_freq * pl / bw
    spec_range = spec_tau * speed_of_light / 2.0

    win = scipy.signal.windows.dpss(scount,NW=pi)
    #win = scipy.signal.windows.chebwin(scount,at=100.0)
    rti = compress_real_pulses(dwell_voltage/tfr.v_max, osf*scount, win=win)

    # Define imaging grid
    lam = speed_of_light/cfreq
    sar_dx = tfr.sar_dx
    dr = speed_of_light/bw/2.0
    dx = dr/4.0
    dy = dr/4.0
    grid_size = round(grid_range/dx)
    loc_x = np.arange(-grid_size,grid_size)*dx
    loc_y = np.arange(0,grid_size)*dy
    loc_xv, loc_yv = np.meshgrid(loc_x, loc_y, sparse=False, indexing='xy')

    # numpy.interp does not like 2D arrays
    loc_xv = np.reshape(loc_xv,(grid_size*2*grid_size,),order='F')
    loc_yv = np.reshape(loc_yv,(grid_size*2*grid_size,),order='F')
    crng = np.sqrt(loc_xv**2+loc_yv**2)
    cang = np.arctan2(loc_xv,loc_yv)

    dwell_win = np.hanning(dwell_steps)
    #dwell_win = np.ones((dwell_steps,))
    dwell_win = dwell_win/np.sum(dwell_win)
    img = np.zeros(loc_xv.shape,dtype=np.complex128,order='F')
    for ii in range(0,dwell_steps):
        ant_x = (ii-(dwell_steps-1)/2.0)*sar_dx
        rng = np.sqrt((loc_xv-ant_x)**2+loc_yv**2) + 0*.25
        pcor = np.exp(-4j*pi*rng/lam)
        dwell_gates = rti[ii,:] * spec_range**(1/2)
        #dwell_gates[spec_range<=min_range] = 0.0
        upd = np.interp(rng,spec_range,dwell_gates)
        img = img + dwell_win[ii]*upd*pcor

    # Remove reference phase
    img = img * np.exp(4j*pi*crng/lam)
    img[np.abs(cang) > max_angle] = 0.0
    img[crng <= min_range] = 0.0
    img = np.reshape(img,(grid_size,2*grid_size),order='F')

    return img


#%%
def plot_sar_image(fig_num, img,grid_range):
    det = 20*np.log10(np.abs(img)+1e-30)
    #det = np.angle(img)

    plt.figure(fig_num)
    plt.clf()
    extent=(-grid_range,grid_range,0,grid_range)
    #,vmin=adc_floor-3.0,vmax=3.0,
    #vmin=-175.0,vmax=-125,
    det_max = np.max(det)
    plt.imshow(det,vmin=det_max-40.0,vmax=det_max,
               interpolation='bilinear',aspect='auto',cmap='jet',extent=extent,origin='lower')
    cbar=plt.colorbar()
    #cbar.ax.set_ylabel('dBFS')
    plt.xlabel('Cross Range (m)')
    plt.ylabel('Down Range (m)')
    plt.title('SAR Image of Dwell Pulses')

#%%
grid_range = 20.0
fname = r'.\yard3.dat'
img = gen_sar_image(fname, grid_range, 2.0, 90.0*pi/180)

#%%
plot_sar_image(102,img,grid_range)

#%%
plt.show()

