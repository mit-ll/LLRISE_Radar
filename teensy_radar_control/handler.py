# -*- coding: utf-8 -*-
"""
Created on Fri Jun  5 22:32:45 2020
Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
@author: ER17450
"""
import logging
import copy, time

import threading, queue

from teensy_radar_control import message, packet
import numpy as np

class BasicRadarHandler(object):
    def __init__(self):
        self.logger = logging.getLogger(type(self).__name__)

        self.reply_queue = queue.Queue(maxsize=10)
        self.log_queue = queue.Queue(maxsize=1000)
        self.pulse_queue = queue.Queue(maxsize=1000)

        self.sph = None
        self.th = None

        # Heartbeat tracking
        self.heartbeat_lock = threading.Lock()
        self.heartbeat_clock = None
        self.heartbeat_msg = None

    def join(self):
        self.disconnect()

    def connect(self,port):
        self.logger.debug('Connect called')
        if self.is_alive():
            self.logger.debug('Radar Already running')
            return

        # Make sure everything is shutdown first
        self.disconnect()

        # Connect up to radar
        if self.heartbeat_lock.acquire(blocking=True, timeout=1.0):
            self.heartbeat_clock = None
            self.heartbeat_msg = None
            self.heartbeat_lock.release()
        else:
            # This should not happen
            raise RuntimeError('connect cant acquire heartbeat lock')

        try:
            self.sph = packet.SerialPacketHandler(port,max_log_level=100)
        except Exception as e:
            self.logger.debug('RadarHandler: error starting SerialPortHandler, aborting.')
            self.logger.debug(str(e))
            return

        self.th_keep_running = True
        self.th = threading.Thread(target=self._bg_thread,args=())
        self.th.daemon = True
        self.th.start()
        self.logger.debug('Connect done')

    def disconnect(self):
        self.logger.debug('Disconnect called')
        self.th_keep_running = False
        if self.th is not None and self.th.is_alive():
            self.th.join()
            self.th = None
        self.logger.debug('Disconnect sph')
        if self.sph is not None and self.sph.is_alive():
            self.sph.join()
            self.sph = None
        self.logger.debug('Disconnect done')

    def time_since_heartbeat(self):
        dt = None
        if self.heartbeat_lock.acquire(blocking=True, timeout=1.0):
            if self.heartbeat_clock is not None:
                dt = time.perf_counter() - self.heartbeat_clock
            self.heartbeat_lock.release()
        else:
            # This should not happen
            raise RuntimeError('time_since_heartbeat cant acquire heartbeat lock')
        return dt

    def is_alive(self):
        sph_alive = False
        if self.sph is not None:
            sph_alive = self.sph.is_alive()
        th_alive = False
        if self.th is not None:
            th_alive = self.th.is_alive()
        watchdog = False
        dt = self.time_since_heartbeat()
        if dt is None or dt < 10.0:
            watchdog = True
        return sph_alive and th_alive and watchdog

    def cmd_version(self):
        cmd = b'V'
        reply = self._send_command(cmd)
        return reply

    def cmd_start(self, pulse_length, gain, fstart, fstop, freturn):
        cmd = b'S %3d %3d %8.3f %8.3f %8.3f \x00' % \
            (pulse_length, gain, fstart, fstop, freturn)

        reply = self._send_command(cmd)
        return reply

    def cmd_stop(self):
        cmd = b'X'
        reply = self._send_command(cmd)
        return reply

    def cmd_trigger_on(self):
        cmd = b'A'
        reply = self._send_command(cmd)
        return reply

    def cmd_trigger_off(self):
        cmd = b'L'
        reply = self._send_command(cmd)
        return reply

    def get_pulse(self, block=True, timeout=0):
        try:
            pulse = self.pulse_queue.get(block=block, timeout=timeout)
        except Exception as e:
            raise e
        pulse = copy.copy(pulse)
        self.pulse_queue.task_done()
        return pulse

    def get_log_msg(self, block=True, timeout=0):
        try:
            log_msg = self.log_queue.get(block=block, timeout=timeout)
        except Exception as e:
            raise e
        log_msg = copy.copy(log_msg)
        self.log_queue.task_done()
        return log_msg

    def _send_command(self,cmd):
        if not self.is_alive():
            return None
        # TBD: Still can get cmd, reply out of sync?

        # Remove any unread messages
        while not self.reply_queue.empty():
            reply = self.reply_queue.get()
            self.reply_queue.task_done()

        # Send command
        try:
            self.sph.write_packet(cmd, block=True, timeout=0.1)
        except Exception as e:
            log_cmd = message.msg_log(0,0,'COMMAND: Enqueue failed.  Continuing')
            return

        log_cmd = message.msg_log(0,0,'COMMAND: "%s"' % (cmd,))
        self.log_queue.put(log_cmd)

        # Wait for reply
        try:
            reply = copy.copy(self.reply_queue.get(timeout=0.1))
            self.reply_queue.task_done()
        except queue.Empty:
            log_cmd = message.msg_log(0,0,'COMMAND: "%s" never got a reply' % (cmd,))
            reply = None

        return reply

    def _bg_thread(self):
        # Look forever
        while self.th_keep_running:
            # Read messages from serial port handler
            try:
                msg = self.sph.read_packet(block=True, timeout=0.1)
            except queue.Empty:
                continue
            except ValueError:
                self.logger.debug('SerialPortHandler crashed, disconnecting.')
                self.disconnect()
            except Exception as e:
                self.logger.debug('read_packet() error, aborting.')
                self.logger.debug(str(e))
                self.disconnect()

            # Try to parse message
            try:
                parsed_msg = message.parse_message(msg)
            except Exception as e:
                self.logger.debug('RadarHandler: parse_message() error, continuing.')
                self.logger.debug(str(e))
                continue

            if isinstance(parsed_msg, message.msg_heartbeat):
                self.logger.debug(str(parsed_msg))
                if self.heartbeat_lock.acquire(blocking=True, timeout=1.0):
                    self.heartbeat_clock = time.perf_counter()
                    self.heartbeat_msg = parsed_msg
                    self.heartbeat_lock.release()
                else:
                    # This should not happen
                    raise RuntimeError('Thread cant acquire heartbeat lock')
            elif isinstance(parsed_msg, message.msg_log):
                self.log_queue.put(parsed_msg)
            elif isinstance(parsed_msg, message.msg_reply):
                self.reply_queue.put(parsed_msg)
                # Send the reply to the log too
                self.log_queue.put(parsed_msg)
            elif isinstance(parsed_msg, message.msg_pulse):
                self.pulse_queue.put(parsed_msg)
            else:
                err = 'Unexpected packed type.  Ignoring: "%s"' % (str(parsed_msg),)
                log_msg = message.msg_log(message.LOG_ERROR,0,err)
                self.log_queue.put(log_msg)
                self.logger.debug(err)

        # Make sure the thread gives up the lock
        if self.heartbeat_lock.locked():
            self.heartbeat_lock.release()


class ExtendedRadarHandler(BasicRadarHandler):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(type(self).__name__)

        self.extended_pulse_queue = queue.Queue(maxsize=1000)

        # Pulse concatenation (used for longer doppler pulses)
        self.pulse_cat_count = 1

        self.extended_pulse_keep_running = True
        self.extended_pulse_th = threading.Thread(target=self._extended_pulse_bg,args=())
        self.extended_pulse_th.daemon = True
        self.extended_pulse_th.start()

    def join(self):
        self.extended_pulse_keep_running = False
        self.extended_pulse_th.join()
        super().join()

    def disconnect(self):
        self.pulse_cat_count = 1
        return super().disconnect()

    def cmd_start(self, pulse_length, gain, fstart, fstop, freturn):
        bw = abs(fstop-fstart)
        if bw < 1e-6 and pulse_length > 40:
            # doppler mode
            self.pulse_cat_count = round(pulse_length/40)
            self.logger.debug('pulse_cat_count %d' % self.pulse_cat_count)
            pulse_length = 40
        else:
            # range mode
            self.pulse_cat_count = 1

        reply = super().cmd_stop()
        reply = super().cmd_start(pulse_length, gain, fstart, fstop, freturn)
        return reply

    def cmd_stop(self):
        self.pulse_cat_count = 1
        return super().cmd_stop()

    def get_pulse(self, block=True, timeout=0):
        try:
            pulse = self.extended_pulse_queue.get(block=block, timeout=timeout)
        except Exception as e:
            raise e
        pulse = copy.copy(pulse)
        self.extended_pulse_queue.task_done()
        return pulse

    def _extended_pulse_bg(self):
        while self.extended_pulse_keep_running:
            # Short circuit for the common case
            if self.pulse_cat_count == 1:
                try:
                    pulse = super().get_pulse(block=True,timeout=0.1)
                except queue.Empty:
                    continue
                self.extended_pulse_queue.put(pulse,block=True,timeout=0.1)
                continue

            # Must be concatenating pulses
            try:
                # Find a starting pulse with.
                # Consume a few pulses until pulse number divides evenly
                try:
                    pulse = super().get_pulse(block=True,timeout=0.1)
                except queue.Empty:
                    continue
                pulse_number = pulse.header.pulse_number
                cat_count = self.pulse_cat_count
                consume = (cat_count - (pulse_number % cat_count))%cat_count
                for ii in range(0,consume):
                    pulse = super().get_pulse(block=True,timeout=0.1)

                # Use this header as the header for the concatenated pulse.
                # Modify some of the fields as we go.
                pulse_number = pulse.header.pulse_number//self.pulse_cat_count
                data_size = pulse.header.data_size
                pulse_length_ms = pulse.header.pulse_length_ms
                data = [pulse.data]
                for ii in range(1,self.pulse_cat_count):
                    npulse = super().get_pulse(block=True,timeout=0.1)
                    data.append(npulse.data)
                    data_size = data_size + npulse.header.data_size
                    pulse_length_ms = pulse_length_ms + npulse.header.pulse_length_ms

                # Build the new pulse
                pulse.header.pulse_number = pulse_number
                pulse.header.data_size = data_size
                pulse.header.pulse_length_ms = pulse_length_ms
                pulse.data = np.concatenate(data)

                self.extended_pulse_queue.put(pulse,block=True,timeout=0.1)
            except Exception as e:
                self.logger.debug('Problem assembling a concatenated pulse.')
                self.logger.debug(str(e))
                continue

#     Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
