/*   Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY */
#ifndef MSG_PACKET_H
#define MSG_PACKET_H
/***************************************************
* Transport layer for generic message packets
***************************************************/
#include <PacketSerial.h>
#include <stdint.h>

const uint32_t msg_unique_word = 0xF1F2F3F4;

/***************************************************
* Each message is (common_header, payload)
***************************************************/
struct __attribute__((packed)) msg_common_header_s
{
    uint32_t unique_word;
    uint16_t msg_size;
    uint16_t msg_type;
};
typedef struct msg_common_header_s msg_common_header_t;

struct __attribute__((packed)) msg_common_packet_s
{
    msg_common_header_t header;
    uint8_t payload[];
};
typedef struct msg_common_packet_s msg_common_packet_t;

typedef void (*send_buffer_func_ptr)(const uint8_t *buffer, uint16_t size);

/***************************************************
* Send a generic message
***************************************************/
extern void msg_set_send_function(send_buffer_func_ptr f);

extern uint8_t *msg_get_payload_buffer(uint16_t size);
extern int msg_free_payload_buffer(uint8_t *buffer);
extern int msg_send(uint16_t msg_size, uint16_t msg_type, uint8_t *msg);

#endif // MSG_PACKET_H
