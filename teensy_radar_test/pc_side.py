# -*- coding: utf-8 -*-
"""
Created on Fri Jun  5 22:32:45 2020
Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
@author: ER17450
"""
from teensy_radar_comm import RadarHandler
import time

def main():
    port='COM3'
    rh = RadarHandler(port)

    for ii in range(0,200):
        if ii==5:
            reply = rh.send_command(b'V')
            print(reply)
        if ii==10:
            reply = rh.send_command(b'S 20 6 2350.000 2530.000 0.000')
            print(reply)
        # if ii==15:
        #     reply = rh.send_command(b'X')
        #     print(reply)

        while not rh.log_queue.empty():
            log = rh.log_queue.get()
            print(log)

        while not rh.pulse_queue.empty():
            pulse = rh.pulse_queue.get()
            print(pulse.header)

        time.sleep(1.0)


if __name__ == '__main__':
    main()
