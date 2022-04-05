# -*- coding: utf-8 -*-
"""
Created on Sun Jun 28 22:49:07 2020
Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
@author: ER17450
"""
import logging
import sys, platform, os, time

import serial
from cobs import cobs

import psutil
import threading, queue

# The Spyder IDE does not work consistantly with multiprocessing.
# If launched from cmd it works.  Some other IDEs are also reported to work.
# To use multiprocessing on widows, define RADAR_USE_MULTIPROCESSING in the
# environment.
logger = logging.getLogger(__name__)
if platform.system() == 'Windows':
    try:
        # Look for environment variable
        val = os.environ['RADAR_USE_MULTIPROCESSING']
        # Use the real multiprocessing
        logger.info('Using multiprocessing')
        import multiprocessing as mp
    except KeyError:
        # Substitue an API compatible layer
        logger.info('Using multiprocessing replacement in IDE')
        import multiprocessing.dummy as mp
else:
    # Use the real multiprocessing
    logger.info('Using multiprocessing')
    import multiprocessing as mp

class SerialPacketHandler(object):
    def __init__(self, port, max_log_level=0):
        self.logger = logging.getLogger(type(self).__name__)

        self.port = port
        self.max_log_level = max_log_level

        # Launch a seperate process that only manages the serial port,
        # and communicates through three Queues
        #
        # NOTE: It is necessary that the process is launched before other
        #       parent threads in the class.
        #
        self.write_queue = mp.Queue(maxsize=1)
        self.read_queue = mp.Queue(maxsize=1000)
        self.log_queue = mp.Queue(maxsize=1000)

        self._sp_keep_running = mp.Value('i',1)

        try:
            self.logger.debug('Processes: Launching child process')
            self._sp = mp.Process(target=self._sp_startup,args=(port,),name='SerialMonitor')
            self._sp.daemon = True
            self._sp.start()
        except Exception as e:
            self.logger.warning('Process: Launch failed.')
            raise e

        # Launch a thread in the parent process that processed log messages
        # from the serial port process.  This is very useful when debugging.
        #
        self._log_keep_running = True
        self._log_th = threading.Thread(target=self._log_thread,args=())
        self._log_th.daemon = True
        self._log_th.start()

        time.sleep(1.0)
        if not self.is_alive():
            err = 'Process: DOA exit = %d' % self._sp.exitcode
            self.logger.warning(err)
            raise RuntimeError(err)

    def read_packet(self, block=True, timeout=None):
        try:
            packet = self.read_queue.get(block,timeout)
        except (ValueError, OSError):
            self.logger.debug('Read from closed queue')
            raise ValueError('Read from closed queue')
        return packet

    def write_packet(self, packet, block=True, timeout=None):
        try:
            self.write_queue.put(packet, block=True, timeout=None)
        except (ValueError, AssertionError):
            self.logger.debug('Write to closed queue')
            raise ValueError('Write to closed queue')
        except queue.Full:
            # Drop the packet
            self.logger.debug('Write times out on queue full')

        return

    def is_alive(self):
        #self.logger.debug('Process: is_alive Called')
        sp_alive = self._sp.is_alive()
        #self.logger.debug('Process: log is_alive Called')
        log_th_alive = self._log_th.is_alive()
        # The log thread can out live the process.  Make sure it is dead too.
        if not sp_alive and log_th_alive:
            self.logger.debug('Process: log join Called')
            self.join()
        #self.logger.debug('Process: is_alive Done')
        return sp_alive

    def join(self):
        self.logger.debug('Process: Join Called')

        # TBD: Use a timeout and check return code
        self.logger.debug('Process: Stopping process')
        if self._sp.is_alive():
            #self._sp.terminate()
            self._sp_keep_running.value = 0
            self._sp.join()

        self.logger.debug('Process: Stopping log thread')
        if self._log_th.is_alive():
            self._log_keep_running = False
            self._log_th.join()

        # Drain and shutdown queues
        self.logger.debug('Process: Draining queues')
        for q in (self.write_queue,self.read_queue,self.log_queue):
            try:
                while True: q.get(block=False)
            except (OSError, queue.Empty):
                # OSError if already closes
                pass
            try:
                q.close()
                q.join_thread()
            except Exception as e:
                self.logger.debug('Process: Problem shutting down queue, continuing')
                self.logger.debug(str(e))

        self.logger.debug('Process: Join Done')

    def _sp_startup(self,port):
        self._sp_log_message(0,'Process: startup() called')

        # Change process priority
        try:
            p = psutil.Process()
            self._sp_log_message(0,'Process: Child ' + str(p))

            self._sp_log_message(0,'Process: Child  initial priority: ' + str(p.nice()))
            if platform.system() == 'Windows':
                p.nice(psutil.HIGH_PRIORITY_CLASS)
            else:
                p.nice(20)
            self._sp_log_message(0,'Process: Child modified priority: ' + str(p.nice()))
        except Exception as e:
            self._sp_log_message(0,'Process: Failed to modify process priority, continuing.')
            self._sp_log_message(0,str(e))

        # Open serial port handler
        try:
            self._sp_serial_port = serial.Serial(port=port, baudrate=2000000, timeout=0.1, write_timeout=0.1)
            # Adjust os buffer size if avaliable
            if platform.system() == 'Windows':
                self._sp_serial_port.set_buffer_size(16384)
        except Exception as e:
            self._sp_log_message(0,'Packet: Serial port failed to open, aborting.')
            self._sp_log_message(1,str(e))
            return
        self._sp_log_message(1,'Packet: Serial port open')

        # Setup an empty read buffer
        self._packet_sep = b'\x00'
        self._max_buf_len = 6000
        self._buf = b''

        self._sp_run_loop()

    def _sp_write_packet(self,packet):
        try:
            self._sp_serial_port.write(cobs.encode(packet) + b'\x00')
            self._sp_serial_port.flush()
        except serial.SerialTimeoutException:
            self._sp_log_message(0,'Packet: Serial port write_packet() timeout, continuing')
        except serial.SerialException as e:
            self._sp_log_message(0,'Packet: Serial port error in write_packet(), aborting')
            raise e

    def _sp_read_packet(self):
        # Set the default return if no new packet is available
        dat = b''

        try:
            # Look for a packet in buffered data. Extract it if it exists
            dat,sep,rest = self._buf.partition(self._packet_sep)
            if sep == self._packet_sep:
                self._buf = rest
            else:
                # If there is any room in the buffer, do a read with timeout
                got_size = 0
                if len(self._buf) < self._max_buf_len:
                    read_size = self._max_buf_len - len(self._buf)
                    read_bytes = self._sp_serial_port.read(read_size)
                    got_size = len(read_bytes)

                # If data was available append and try again to find a packet
                if got_size > 0:
                    self._buf = self._buf + read_bytes

                    # Look for a packet in buffered data. Extract it if it exists
                    dat,sep,rest = self._buf.partition(self._packet_sep)
                    if sep == self._packet_sep:
                        self._buf = rest
                    else:
                        # Check if buffer is full
                        if len(self._buf) >= self._max_buf_len:
                            # Out of room, drop buffer
                            self._buf = b''

        except serial.SerialException as e:
            self._sp_log_message(0,'Packet: Serial port error in read_packet(), aborting')
            raise e
        except Exception as e:
            self._sp_log_message(0,'Packet: Error in read_packet(), continuing')
            self._sp_log_message(1,str(e))

        try:
            if dat != b'':
                packet = cobs.decode(dat)
            else:
                packet = b''
        except cobs.DecodeError as e:
            self._sp_log_message(0,'Packet: COBS decode error, continuing')
            self._sp_log_message(1,str(e))
            packet = b''

        return packet

    def _sp_run_loop(self):
        self._sp_log_message(0,'Process: run_loop running')

        try:
            ct = time.perf_counter()
            ct0 = ct
            self._sp_serial_port.reset_input_buffer()
            self._sp_serial_port.reset_output_buffer()

            # Loop forever
            while self._sp_keep_running.value != 0:
                nt = time.perf_counter()
                if nt-ct >= 5.0:
                    self._sp_log_message(0,'Process: Alive (%.1f)' % (nt-ct0,))
                    ct = nt

                # If there is data to send send it
                if not self.write_queue.empty():
                    try:
                        packet = self.write_queue.get(block=True, timeout=0.1)
                    except queue.Empty:
                        self._sp_log_message(0,'Process: write_queue.get() timeout, continuing')
                    else:
                        self._sp_write_packet(packet)

                # Returns b'' of no new packet is available after timeout
                packet = self._sp_read_packet()
                if packet != b'':
                    try:
                        self.read_queue.put(packet, block=True, timeout=0.1)
                    except queue.Full:
                        # Drop the packet
                        continue

        except Exception as e:
            self._sp_log_message(0,'Process: Error in run_loop, aborting')
            self._sp_log_message(1,str(e))

        self._sp_log_message(1,'Packet: Closing serial port')
        try:
            self._sp_serial_port.close()
        except serial.SerialException:
            self._sp_log_message(0,'Process: Serial port close failed')

        self._sp_log_message(0,'Process: run_loop process ended')

    def _sp_log_message(self, level, msg):
        if self.log_queue is not None and level <= self.max_log_level:
            try:
                self.log_queue.put(msg, block=True, timeout=0.1)
            except queue.Full:
                # This message probably won't go anywhere
                self.logger.warning('log_queue full timeout, continuing')
            except (ValueError, OSError):
                # This message probably won't go anywhere
                self.logger.warning('Read from closed queue')

    def _log_thread(self):
        # This thread oly exists on the parent side of the connection
        while self._log_keep_running:
            try:
                msg = self.log_queue.get(block=True, timeout=1.0)
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.debug('Process: _log_thread error, aborting thread.')
                self.logger.debug(str(e))
            if msg is None:
                self.logger.debug('_log_thead got None message')
            else:
                self.logger.debug(msg)
            sys.stdout.flush()

        self.logger.debug('_log_thead exited')
        sys.stdout.flush()

