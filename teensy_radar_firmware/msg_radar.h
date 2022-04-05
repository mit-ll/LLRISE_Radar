/*   Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY */
#ifndef MSG_RADAR_H
#define MSG_RADAR_H
/****************************************************
* Radar specific message packets
***************************************************/
#include <stdint.h>
#include <math.h>
#include "msg_packet.h"

enum msg_type
{
    MSG_TYPE_HEARTBEAT = 0,
    MSG_TYPE_LOG = 1,
    MSG_TYPE_REPLY = 2,
    MSG_TYPE_PULSE = 3
};

/***************************************************
* Heartbeat message
***************************************************/
struct __attribute__((packed)) msg_heartbeat_s
{
    uint32_t time_stamp;
};
typedef struct msg_heartbeat_s msg_heartbeat_t;


/***************************************************
* Log message
***************************************************/
enum log_category
{
    LOG_DEBUG = 0,
    LOG_INFO = 1,
    LOG_WARN = 2,
    LOG_ERROR = 3
};

struct msg_log_s
{
    uint8_t category;
    uint8_t level;
    char message[];
};
typedef struct msg_log_s msg_log_t;

/***************************************************
* Reply message
***************************************************/
struct msg_reply_s
{
    int16_t status;
    char message[];
};
typedef struct msg_reply_s msg_reply_t;

/***************************************************
* Pulse message
***************************************************/
struct msg_pulse_header_status_s {
    unsigned int transmit_trigger:1;
    unsigned int _reserved:31;
};
typedef struct msg_pulse_header_status_s msg_pulse_header_status_t;

struct __attribute__((packed)) msg_pulse_header_s
{
    uint16_t hdr_size;
    uint16_t data_size;
    uint32_t pulse_number;
    uint32_t pulse_cycle_count;
    msg_pulse_header_status_t status;
    uint16_t gain;
    uint16_t pulse_length_ms;
    float_t freq_start;
    float_t freq_stop;
    float_t freq_return;
};
typedef struct msg_pulse_header_s msg_pulse_header_t;

struct __attribute__((packed)) msg_pulse_s
{
    msg_pulse_header_t pulse_header;
    uint16_t data[];
};
typedef struct msg_pulse_s msg_pulse_t;

/***************************************************
* Send functions
***************************************************/
extern int
msg_send_heartbeat(uint32_t time_stamp);

extern int
msg_send_log(uint8_t category, uint8_t level, const char *message);

extern int
msg_send_reply(int16_t status, const char *message);

extern int
msg_send_pulse(
    const msg_pulse_header_t *pulse_header,
    const uint16_t *data, uint16_t data_count);

#endif // MSG_PACKET_H
