/***************************************************
* Transport layer for generic message packets
***************************************************/
#include <stdlib.h>

#include "msg_packet.h"

//  Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
// Current implementation, as a fixed buffer used to create message
//const uint16_t MSG_MAX_SIZE = sizeof(msg_common_header_t) + 100 + 2 * 1024;

// #TODO: Not sure how big this needs to be. For 50KHz the largest amount of data tha is sent is 2000 data points.
// Perhaps it should be dynamically sized based on requested waveform parameters like the dac_buffer and adc_buffer are?
const uint16_t MSG_MAX_SIZE = sizeof(msg_common_header_t) + 100 + 2 * 2048;
uint8_t msg_buf[MSG_MAX_SIZE];

// Pointer the the function that sends data
send_buffer_func_ptr send_buffer_func = NULL;

void msg_set_send_function(send_buffer_func_ptr f)
{
    send_buffer_func = f;
}

uint8_t *msg_get_payload_buffer(uint16_t size)
{
    const uint16_t hsize = sizeof(msg_common_header_t);
    if (hsize + size <= MSG_MAX_SIZE)
    {
        // Returns a buffer with enough space in front for the header
        return msg_buf + sizeof(msg_common_header_t);
    }
    return NULL;
}

int msg_free_payload_buffer(uint8_t *buffer)
{
    return 0;
}

int msg_send(uint16_t msg_size, uint16_t msg_type, uint8_t *msg)
{
    const uint16_t hsize = sizeof(msg_common_header_t);
    msg_common_packet_t *packet = (msg_common_packet_t *)(msg - hsize);

    if (hsize + msg_size <= MSG_MAX_SIZE)
    {
        // Set header
        packet->header.unique_word = msg_unique_word;
        packet->header.msg_size = msg_size;
        packet->header.msg_type = msg_type;

        // Send message
        (*send_buffer_func)((uint8_t *)packet, hsize + msg_size);

        // Return success
        return 0;
    }

    // Return failure
    return -1;
}
