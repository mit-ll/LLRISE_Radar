/***************************************************
* Radar specific message packets
***************************************************/
#include <stdlib.h>
#include <string.h>
#include "msg_radar.h"

//  Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
/***************************************************
* Send functions
***************************************************/
int msg_send_heartbeat(uint32_t time_stamp)
{
    msg_heartbeat_t *msg = 
        (msg_heartbeat_t *)msg_get_payload_buffer(sizeof(msg_heartbeat_t));
    if (msg != NULL)
    {
        msg->time_stamp = time_stamp;
 
        msg_send(sizeof(msg_heartbeat_t), MSG_TYPE_HEARTBEAT, (uint8_t *)msg);
        msg_free_payload_buffer((uint8_t *)msg);
        return 0;
    }
    return -1;
}

int msg_send_log(uint8_t category, uint8_t level, const char *message)
{
    msg_log_t *msg = NULL;
    uint16_t slen = strlen(message);

    msg = (msg_log_t *)msg_get_payload_buffer(sizeof(msg_log_t) + slen);
    if (msg != NULL)
    {
        msg->category = category;
        msg->level = level;
        strncpy(msg->message, message, slen);

        msg_send(sizeof(msg_reply_t) + slen, MSG_TYPE_LOG, (uint8_t *)msg);
        msg_free_payload_buffer((uint8_t *)msg);
        return 0;
    }
    return -1;
}

int msg_send_reply(int16_t status, const char *message)
{
    msg_reply_t *msg = NULL;
    uint16_t slen = strlen(message);

    msg = (msg_reply_t *)msg_get_payload_buffer(sizeof(msg_reply_t) + slen);
    if (msg != NULL)
    {
        msg->status = status;
        strncpy(msg->message, message, slen);

        msg_send(sizeof(msg_reply_t) + slen, MSG_TYPE_REPLY, (uint8_t *)msg);
        msg_free_payload_buffer((uint8_t *)msg);
        return 0;
    }
    return -1;
}

int msg_send_pulse(
    const msg_pulse_header_t *pulse_header,
    const uint16_t *data, uint16_t data_count)
{
    msg_pulse_t *msg = NULL;
    uint16_t hsize = sizeof(msg_pulse_header_t);
    uint16_t dsize = sizeof(uint16_t) * data_count;

    msg = (msg_pulse_t *)msg_get_payload_buffer(hsize + dsize);
    if (msg != NULL)
    {
        memcpy(&msg->pulse_header, pulse_header, hsize);
        memcpy(msg->data, data, dsize);

        msg_send(hsize + dsize, MSG_TYPE_PULSE, (uint8_t *)msg);
        msg_free_payload_buffer((uint8_t *)msg);
        return 0;
    }
    return -1;
}
//     Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
