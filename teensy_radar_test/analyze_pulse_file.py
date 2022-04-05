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

def read_pulses(fname, pcount):
    fh = open(fname,mode='rb');

    # Read the first pulse header as assume the rest ar the same size for now
    buf = fh.read(2+2+4+4+2+2+4+4+4);
    hdr_size, data_size, pulse_number, pulse_cycle_count, gain, pulse_len_ms, \
        freq_start, freq_stop, freq_return = struct.unpack('HHLLHHfff',buf)

    fh.seek(0)
    print(hdr_size, data_size)

    pulses = np.zeros((pcount,data_size),dtype=float,order='F')
    for ii in range(0,pcount):
        buf = fh.read(hdr_size)
        buf = fh.read(data_size*2)
        pulses[ii,:] = np.frombuffer(buf,dtype=np.dtype('<u2'))

    return pulse_len_ms/1000.0, freq_start, freq_stop, freq_return, pulses

def compress_real_pulses(sig_data, n=-1, win='hanning'):
    pcount,scount = sig_data.shape
    if n < scount: n = scount

    # if win is not a str assume it is the actual 1D window array
    if isinstance(win, str):
        win = scipy.signal.windows.get_window(win,scount)

    # Window the data
    win = win/np.sum(win)
    win = np.tile(win,(pcount,1))
    win_data = win * sig_data

    # Zero pad appropriately
    pad_data = np.zeros((pcount,n),np.float)
    lo = floor(n/2.0)-floor(scount/2.0)
    pad_data[:,lo:(lo+scount)]=win_data

    # Do the FFT
    range_gates = np.fft.rfft(np.fft.ifftshift(pad_data,axes=(1,)),n=n,axis=1)

    return range_gates*(n/scount)*2.0

def compute_doppler_map(rti_data, n=-1, win='hanning'):
    pcount,scount = rti_data.shape
    if n < pcount: n = pcount

    # if win is not a str assume it is the actual 1D window array
    if isinstance(win, str):
        win = scipy.signal.windows.get_window(win,pcount)

    # Window the data
    win = win/np.sum(win)
    win = np.tile(win,(scount,1)).T
    win_data = win * rti_data

    # Zero pad appropriately
    pad_data = np.zeros((n,scount),np.complex)
    lo = floor(n/2.0)-floor(pcount/2.0)
    pad_data[lo:(lo+pcount),:]=win_data

    # Do the FFT
    rd_map = np.fft.fftshift(np.fft.fft(np.fft.ifftshift(pad_data,axes=(0,)),n=n,axis=0),axes=(0,))

    #return range_gates
    return rd_map

#%%
#fname,pcount = './pulses_5ms.dat', 2000
#fname,pcount = './pulses_10ms.dat', 2000
#fname,pcount = './pulses_20ms.dat', 1200
fname,pcount = './pulses_20ms_linear.dat', 1200
#fname,pcount = './pulses_20ms_short_vgnd_g32.dat', 1200
#fname,pcount = './pulses_20ms_short_vgnd_g22.dat', 1200
#fname,pcount = './pulses_20ms_short_vgnd_g22_v2.dat', 1200
#fname,pcount = './pulses_20ms_short_vgnd_g22_v3.dat', 1200
#fname,pcount = './pulses_20ms_short_vgnd_g22_v4.dat', 1200
#fname,pcount = './pulses_20ms_short_vgnd_g22_adc_cap.dat', 1200
#fname,pcount = './pulses_20ms_short_vgnd_g22_adc_cap_v2.dat', 1200
#fname,pcount = './pulses_40ms.dat', 800

# Teensy ADC as it is configured
v_max=3.3
adc_bits=16
adc_enob=11
adc_floor = -(1.76+6.02*adc_enob)
v_scale = v_max/2.0**adc_bits
# This has to do with the details of the driving circuit
# v_center = 2.5*2.0/3.0
v_center = 2.5*2.0/3.0 - 0.050

# Read first pulse to get parameters
pl, f_start, f_stop, f_return, sig = read_pulses(fname,1)

# First pulses are drifting in bias
stable_time = 1.0
stable_idx = int(stable_time/pl)
pl, f_start, f_stop, f_return, sig = read_pulses(fname,pcount+stable_idx)
sig = sig[stable_idx:,:]
sig = sig*v_scale - v_center

bw = fabs(f_stop-f_start)*1e6
scount = sig.shape[1]
srate = scount/pl

# Remove DC bias
sig = sig - np.mean(sig)

# Compute the mean pulse
sig_mean = np.mean(sig,axis=0)
sig_diff = sig-sig_mean

tt = np.arange(0,scount)/srate

#%%
#
# Time domain voltage plots
#
plt.figure(100)
plt.clf()
extent=(tt[0]*1000.0,tt[-1]*1000.0,0,pcount)
plt.imshow(sig,vmin=-v_max/2.0,vmax=v_max/2.0,
           interpolation='bilinear',aspect='auto',cmap='bone',extent=extent)
cbar=plt.colorbar()
cbar.ax.set_ylabel('Voltage (V)')
plt.xlabel('Time (ms)')
plt.ylabel('Pulse Number')
plt.title('All Pulses in Time')

plt.figure(101)
plt.clf()
plt.plot(tt*1000.0,sig_mean)
plt.grid()
plt.ylim((-v_max/2,v_max/2))
plt.xlabel('Time (ms)')
plt.ylabel('Sample (V)')
plt.title('Mean Pulse in Time')

plt.figure(102)
plt.clf()
extent=(tt[0]*1000.0,tt[-1]*1000.0,0,pcount)
plt.imshow(sig_diff*1000,vmin=np.min(sig_diff)*1000, vmax=np.max(sig_diff)*1000,
           interpolation='bilinear',aspect='auto',cmap='bone',extent=extent)
cbar=plt.colorbar()
cbar.ax.set_ylabel('Voltage (mV)')
plt.xlabel('Time (ms)')
plt.ylabel('Pulse Number')
plt.title('All Pulses in Time with Mean Subtracted')

#%%
#
# Fast frequency (range) plots of signal
#
osf=4
ff = np.fft.rfftfreq(osf*scount,d=1.0/srate)
rti = compress_real_pulses(sig/v_max, osf*scount)

plt.figure(200)
plt.clf()
extent=(ff[0]/1000.0,ff[-1]/1000.0,0,pcount)
plt.imshow(20*np.log10(np.abs(rti)),vmin=adc_floor-3.0,vmax=3.0,
           interpolation='bilinear',aspect='auto',cmap='jet',extent=extent)
cbar=plt.colorbar()
cbar.ax.set_ylabel('dBFS')
plt.xlabel('Frequency (KHz)')
plt.ylabel('Pulse Number')
plt.title('RTI of All Pulses')

plt.figure(201)
plt.clf()
plt.plot(ff/1000.0,10*np.log10(np.mean(np.abs(rti)**2.0,axis=0)),'r',label='Non-Coherent')
plt.plot(ff/1000.0,20*np.log10(np.abs(np.mean(rti,axis=0))),'b',label='Coherent')
plt.plot([ff[0]/1000.0,ff[-1]/1000.0],[adc_floor,adc_floor],'k--',label='ADC ENOB')
plt.ylim((-97.0,3.0))
plt.grid()
plt.legend()
plt.xlabel('Frequency (KHz)')
plt.ylabel('dBFS')
plt.title('Mean RTI')

peak_idx = np.argmax(np.mean(np.abs(rti)**2.0,axis=0))
plt.figure(202)
plt.clf()
plt.title('Pulses Peak Characteristics')
plt.subplot(2,1,1)
plt.plot(np.arange(0,pcount),20*np.log10(np.abs(rti[:,peak_idx])),'b')
plt.grid()
plt.xlabel('Pulse Number')
plt.ylabel('dBFS')
plt.subplot(2,1,2)
plt.plot(np.arange(0,pcount),np.angle(rti[:,peak_idx])*180.0/pi,'b')
plt.grid()
plt.xlabel('Pulse Number')
plt.ylabel('Phase (Degrees)')


#
# Fast frequency (range) plots of noise
#
rti_diff = compress_real_pulses(sig_diff/v_max, osf*scount)

plt.figure(250)
plt.clf()
extent=(ff[0]/1000.0,ff[-1]/1000.0,0,pcount)
plt.imshow(20*np.log10(np.abs(rti_diff)),vmin=adc_floor-10.0,vmax=adc_floor+20.0,
           interpolation='bilinear',aspect='auto',cmap='jet',extent=extent)
cbar=plt.colorbar()
cbar.ax.set_ylabel('dBFS')
plt.xlabel('Frequency (KHz)')
plt.ylabel('Pulse Number')
plt.title('RTI of All Pulses After Removing Mean Pulse')

plt.figure(252)
plt.clf()
plt.plot(ff/1000.0,10*np.log10(np.mean(np.abs(rti_diff)**2.0,axis=0)),'r',label='Non-Coherent')
plt.plot([ff[0]/1000.0,ff[-1]/1000.0],[adc_floor,adc_floor],'k--',label='ADC ENOB')
plt.ylim((-97.0,3.0))
plt.grid()
plt.legend()
plt.xlabel('Frequency (KHz)')
plt.ylabel('dBFS')
plt.title('Mean RTI of All Pulses After Removing Mean Pulse')


#%%
#
# Slow frequency (Doppler) plots
#
df = np.fft.fftshift(np.fft.fftfreq(osf*pcount,d=pl))
rd = compute_doppler_map(rti, n=osf*pcount)

plt.figure(300)
plt.clf()
extent=(ff[0]/1000.0,ff[-1]/1000.0,df[0],df[-1])
plt.imshow(20*np.log10(np.abs(rd)),vmin=adc_floor-10*log10(pcount)-3.0,vmax=3.0,
           interpolation='bilinear',aspect='auto',cmap='jet', extent=extent)
cbar=plt.colorbar()
cbar.ax.set_ylabel('dBFS')
plt.xlabel('Fast Frequency (KHz)')
plt.ylabel('Slow Frequency (Hz)')
plt.title('Range Doppler Map')

plt.figure(301)
plt.clf()
plt.plot(df,10*np.log10(np.mean(np.abs(rd)**2.0,axis=1)*(pcount/osf)),'r',label='Non-Coherent')
plt.plot(df,20*np.log10(np.abs(np.mean(rd,axis=1))*(pcount/osf)),'b',label='Coherent')
plt.grid()
plt.legend()
plt.ylabel('dBFS')
plt.xlabel('Slow Frequency (Hz)')
plt.title('Mean Doppler')

#
# Slow frequency (Doppler) plots of noise
#
rd_diff = compute_doppler_map(rti_diff, n=osf*pcount)

plt.figure(350)
plt.clf()
extent=(ff[0]/1000.0,ff[-1]/1000.0,df[0],df[-1])
#,vmin=adc_floor-10.0,vmax=adc_floor+20.0,
plt.imshow(20*np.log10(np.abs(rd_diff)),
           interpolation='bilinear',aspect='auto',cmap='jet', extent=extent)
cbar=plt.colorbar()
cbar.ax.set_ylabel('dBFS')
plt.xlabel('Fast Frequency (KHz)')
plt.ylabel('Slow Frequency (Hz)')
plt.title('Range Doppler Map After Subtracting Mean Pulse')

plt.figure(351)
plt.clf()
plt.plot(df,10*np.log10(np.mean(np.abs(rd_diff)**2.0,axis=1)*(pcount/osf)),'r',label='Non-Coherent')
plt.plot(df,20*np.log10(np.abs(np.mean(rd_diff,axis=1))*(pcount/osf)),'b',label='Coherent')
plt.grid()
plt.legend()
plt.ylabel('dBFS')
plt.xlabel('Slow Frequency (Hz)')
plt.title('Mean Doppler After Subtracting Mean Pulse')


#%%
#
# Cable test for ramp linearity
#
delay_elen = 25.0*1.3 # electrical length m
tau = delay_elen/speed_of_light
delay_freq = (bw/pl)*tau

tt = np.arange(0,scount)*pl/scount
cf = np.fft.fftfreq(scount,d=1.0/srate)
hfilt = np.zeros((scount,))
#hfilt[(ff>=500.0) & (ff<=3000.0)]=2.0
hfilt[np.abs(cf-delay_freq)<=15/pl]=2.0
win = scipy.signal.windows.get_window('hanning',15)
win = win/np.sum(win)
hfilt=scipy.signal.fftconvolve(hfilt,win,mode='same')

# Do the band limited hilbert transform
asig = np.fft.ifft(hfilt*np.fft.fft(sig_mean));

plt.figure(400)
plt.clf()
plt.plot(tt*1000.0,20*np.log10(np.abs(asig)))
#plt.plot(tt,np.real(asig),'r')
#plt.plot(tt,np.imag(asig),'b')
plt.grid()
plt.ylabel('dBFS')
plt.xlabel('Time (ms)')
plt.title('Ramp Cable Test Instantaneous Power')

plt.figure(401)
plt.clf()
plt.plot(tt[1:]*1000.0,np.diff(np.unwrap(np.angle(asig)))*srate/2/pi)
for bi in range(0,floor(scount/2)-1):
    bf = (bi+0.5)/pl
    plt.plot([tt[0]*1000.0,tt[-1]*1000.0],[bf,bf],'k--')
plt.ylim((delay_freq-500.0,delay_freq+500.0))
plt.ylabel('Frequency (Hz)')
plt.xlabel('Time (ms)')
plt.title('Ramp Cable Test Instantaneous Frequency')

plt.figure(402)
plt.clf()
plt.plot(cf,hfilt,'b.')
plt.grid()
plt.ylabel('dB')
plt.xlabel('Fast Frequency (Hz)')
plt.title('Cable Test Hilbert and Noise Reduction Filter')

#%%
plt.show()
