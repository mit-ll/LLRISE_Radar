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

from teensy_radar_util import teensy_radar_file_reader, compress_real_pulses, extract_sar_dwells

#%%
fname,pcount = './test1.dat', 10000
#fname,pcount = './sar1.dat', 10000

tfr = teensy_radar_file_reader(fname)

pl = tfr.pulse_length
srate = tfr.sample_rate
cfreq = tfr.freq_center
bw = tfr.bandwidth
v_max = tfr.v_max
adc_floor = -20*log10(2**16)

pcount = tfr.pulse_count
trigger, if_voltage = tfr.read_if_voltage_pulses(pcount)
pcount = if_voltage.shape[0]
scount = if_voltage.shape[1]

if_voltage_mean = np.mean(if_voltage,axis=0)
if_voltage_diff = if_voltage - if_voltage_mean

tt = np.arange(0,scount)/srate
st = np.arange(0,pcount)*pl

print('pcount=%d, collect_time = %.3f' % (pcount,pcount*pl))

#%%
#
# Time domain voltage plots
#
plt.figure(100)
plt.clf()
extent=(tt[0]*1000.0,tt[-1]*1000.0,0,pcount)
plt.imshow(if_voltage,vmin=-v_max/2.0,vmax=v_max/2.0,
           interpolation='bilinear',aspect='auto',cmap='bone',extent=extent)
cbar=plt.colorbar()
cbar.ax.set_ylabel('Voltage (V)')
plt.xlabel('Time (ms)')
plt.ylabel('Pulse Number')
plt.title('All Pulses in Time')

plt.figure(101)
plt.clf()
plt.plot(tt*1000.0,if_voltage_mean)
plt.grid()
plt.ylim((-v_max/2,v_max/2))
plt.xlabel('Time (ms)')
plt.ylabel('Sample (V)')
plt.title('Mean Pulse in Time')

plt.figure(102)
plt.clf()
extent=(tt[0]*1000.0,tt[-1]*1000.0,0,pcount)
plt.imshow(if_voltage_diff*1000,vmin=np.min(if_voltage_diff)*1000, vmax=np.max(if_voltage_diff)*1000,
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
rti = compress_real_pulses(if_voltage/v_max, n=osf*scount)

plt.figure(200)
plt.clf()
extent=(ff[0]/1000.0,ff[-1]/1000.0,0,pcount)
plt.imshow(20*np.log10(np.abs(rti)+1e-30),vmin=adc_floor-3.0,vmax=3.0,
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
plt.plot([ff[0]/1000.0,ff[-1]/1000.0],[adc_floor,adc_floor],'k--',label='ADC Floor')
plt.ylim((-97.0,3.0))
plt.grid()
plt.legend()
plt.xlabel('Frequency (KHz)')
plt.ylabel('dBFS')
plt.title('Mean Range Pulse')

#%%
plt.figure(900)
plt.clf()
plt.plot(st,trigger,'bo')
plt.plot(st[1:],np.diff(trigger),'rx')

steps = tfr.sar_steps
wtime = tfr.sar_wcount*pl
ctime = tfr.sar_ccount*pl

for ii in range(0,steps):
    wt = (wtime+ctime)*ii
    ct = wt + wtime
    plt.plot([wt,wt],[0,1],'b--')
    plt.plot([ct,ct],[0,1],'r--')

#%%

trig_on = np.where((np.diff(trigger) > 0))[0] + 1
trig_off = np.where((np.diff(trigger) < 0))[0] + 1

# Prune unexpected partial pulses at the beginning or end
if trig_off[0] < trig_on[0]:
    trig_off = trig_off[1:]
if trig_on[-1] > trig_off[-1]:
    trig_on = trig_on[0:-1]

obs_trig_loc = trig_on
obs_trig_time = obs_trig_loc*pl

exp_trig_loc = np.arange(0,steps)*(tfr.sar_wcount+tfr.sar_ccount)+tfr.sar_wcount

#%%
# Extract and average pulses
dwell_offset = round(0.1/pl)
dwell_dur = round(0.5/pl)
dwell_sig = np.zeros((steps,scount),dtype=float)
for ii in range(0,min(steps,obs_trig_loc.shape[0])):
    i0 = obs_trig_loc[ii] + dwell_offset
    i1 = i0 + dwell_dur
    dwell_sig[ii,:] = np.mean(if_voltage[i0:i1,:],axis=0)



#%%
plt.figure(901)
plt.clf()
plt.plot(exp_trig_loc[0:min(steps,obs_trig_loc.shape[0])]-obs_trig_loc,'bo')


#%%
plt.show()
#     Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
