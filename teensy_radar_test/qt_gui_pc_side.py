# -*- coding: utf-8 -*-
"""
Created on Fri Jun  5 22:32:45 2020
Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
@author: ER17450
"""

from pyqtgraph.Qt import QtCore, QtWidgets, QtGui
import pyqtgraph as pg
import sys,os,time

from teensy_radar_comm import RadarHandler
import threading

class RadarDisplay(QtWidgets.QWidget):
    def __init__(self, rh):
        super().__init__()
        self.title = 'Teensy USB Test'
        self.width = 2000
        self.height = 500

        self.rh = rh
        self.initUI()

        # Create the background update thread
        self.timer = QtCore.QTimer()
        self.timer.start(0.1*1000)
        self.timer.timeout.connect(self._update)

    def initUI(self):

        # Set up the plot
        self.glw = pg.GraphicsLayoutWidget()

        p1 = self.glw.addPlot()
        p1.setRange(xRange=(0,1023),yRange=(-500,500),disableAutoRange=True)
        p1.setLabel('bottom',text='Time')
        p1.setLabel('left',text='ADC Count')
        self.curve = p1.plot(pen='y')

        # Set up the log area
        self.log_area = QtWidgets.QPlainTextEdit()
        self.log_area.setFocusPolicy(QtCore.Qt.NoFocus)

        # Do the layout
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.glw)
        layout.addWidget(self.log_area)

        # Display the window
        self.setLayout(layout)
        self.show()

    def _update(self):
        # display the pulse data
        while not self.rh.pulse_queue.empty():
            pulse = self.rh.pulse_queue.get()
            print(pulse.header)
            self.curve.setData(pulse.data)
            self.rh.pulse_queue.task_done()

        # Display the log messages
        while not self.rh.log_queue.empty():
            log = self.rh.log_queue.get()
            #print(log)
            self.log_area.appendPlainText(str(log))
            self.rh.log_queue.task_done()


def test_commands(rh):
    time.sleep(3.0)
    reply = rh.send_command(b'V')
    #print(reply)

    for ii in range(0,10):
        time.sleep(3.0)
        reply = rh.send_command(b'S 20 %d 2350.000 2530.000 0.000' % (ii+1,))
        #print(reply)

        time.sleep(10.0)
        reply = rh.send_command(b'X')
        #print(reply)

    #QtCore.QCoreApplication.quit()
    print('Done.')

def main():

    app = QtGui.QApplication(sys.argv)
    # KLUDGE:
    # This fixes a problem with axis calculations when the primary
    # monitor and the display monitor have different resolution setting
    # in win10
    app.setAttribute(QtCore.Qt.AA_Use96Dpi)

    rh = RadarHandler('COM3')
    rd = RadarDisplay(rh)

    # Test a few commands
    cmd_th = threading.Thread(target=test_commands,args=(rh,))
    cmd_th.daemon = True
    cmd_th.start()

    sys.exit(app.exec_())

if __name__ == '__main__':
    main()

