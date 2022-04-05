# -*- coding: utf-8 -*-
"""
Created on Sun Jun 28 22:43:56 2020
Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
@author: ER17450
"""
import logging
from dataclasses import dataclass
import numpy as np
import struct

logger = logging.getLogger(__name__)

# Common packet
MSG_UNIQUE_WORD = 0xF1F2F3F4

# Message types
MSG_TYPE_HEARTBEAT = 0
MSG_TYPE_LOG = 1
MSG_TYPE_REPLY = 2
MSG_TYPE_PULSE = 3

# Logging levels
LOG_DEBUG = 0,
LOG_INFO = 1,
LOG_WARN = 2,
LOG_ERROR = 3

@dataclass
class msg_common_header:
    unique_word: int
    msg_size: int
    msg_type: int

@dataclass
class msg_heartbeat:
    time_stamp: int

@dataclass
class msg_log:
    category: int
    level: int
    message: str

@dataclass
class msg_reply:
    status: int
    message: str

@dataclass
class msg_pulse_header:
    hdr_size: int
    data_size: int
    pulse_number: int
    pulse_cycle_count: int
    status: int
    gain: int
    pulse_length_ms: int
    freq_start: float
    freq_stop: float
    freq_return: float

@dataclass
class msg_pulse:
    header: msg_pulse_header
    data: np.ndarray

def parse_payload(msg_type, payload):
    # Create class by type
    if msg_type == MSG_TYPE_HEARTBEAT:
         return msg_heartbeat(*struct.unpack('I',payload[0:4]))
    elif msg_type == MSG_TYPE_LOG:
        category, level = struct.unpack('BB',payload[0:2])
        message = payload[2:]
        return msg_log(category,level,message)
    elif msg_type == MSG_TYPE_REPLY:
        status, = struct.unpack('h',payload[0:2])
        message = payload[2:]
        return msg_reply(status,message)
    elif msg_type == MSG_TYPE_PULSE:
        header = msg_pulse_header(*struct.unpack('HHIIIHHfff',payload[0:32]))
        data = np.frombuffer(payload[32:],dtype=np.dtype('<u2'))
        return msg_pulse(header,data)
    else:
        # Unexpected Packet
        err = 'Unexpected packed type=%d.  Ignoring: "%s"' % (msg_type, str(payload),)
        raise ValueError(err)
    return None

def parse_common_header(header_bytes):
    try:
        header = msg_common_header(*struct.unpack('IHH',header_bytes))
    except Exception as e:
        raise ValueError('Cannot parse common header')
    if header.unique_word != MSG_UNIQUE_WORD:
        raise ValueError('Bad message unique_word')
    return header

def parse_message(msg):
    header = parse_common_header(msg[0:8])
    if header.msg_size != len(msg)-8:
        raise ValueError('Bad message size' + str(header))
    return parse_payload(header.msg_type, msg[8:])
