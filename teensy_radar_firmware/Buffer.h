/*   Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY */
#ifndef BUFFER_T_H_
#define BUFFER_T_H_

#include "WProgram.h"
struct Buffer
{
    uint16_t length;
    uint16_t size;
    volatile uint16_t *data;
    
    Buffer() : length{0}, size{0}, data{nullptr} {}
};

#endif // BUFFER_T_H_