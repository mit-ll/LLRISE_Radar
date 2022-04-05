/*   Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY */
#ifndef RX_GAIN_H_
#define RX_GAIN_H_

#include <Arduino.h>   // contains definition of Arduino requirements
#include <core_pins.h> // contains pin specific definitions and control functions
#include <kinetis.h>   // contains peripheral definitions
#include <SPI.h>

// #TODO: Consider storing these as class members to allow different mux/gain devices
#define GAIN_SPI_CS 10
#define GAIN_SPI_MOSI 11
#define GAIN_SPI_MISO 12
#define GAIN_SPI_SCK 13

class Gain_Mux
{
public:
    Gain_Mux();
    int8_t configure(uint16_t gain);

private:
    uint8_t _mux_channel;
    uint8_t _mux_idx;

#if DEBUG_MUX == 1
    static const uint8_t _mux_channel_max=6;
    static const uint8_t _mux_idx_max=8;
    const uint16_t _mux_params[_mux_channel_max][_mux_idx_max] 
            {{11, 12, 13, 14, 15,  16,  17,  18},
             {21, 22, 23, 24, 25,  26,  27,  28},
             {31, 32, 33, 34, 35,  36,  37,  38},
             {41, 42, 43, 44, 45,  46,  47,  48},
             {51, 52, 53, 54, 55,  56,  57,  58},
             {61, 62, 63, 64, 65,  66,  67,  68}};
#else
    // 2021 Radar
    // Note: Gains are scaled to be integers.  The 2021 radar includes a
    // resistor divider that reduces ch01 by a factor of 10.
    static const uint8_t _mux_channel_max=2;
    static const uint8_t _mux_idx_max=8;
    const uint16_t _mux_params[_mux_channel_max][_mux_idx_max] 
            {{10, 20, 40, 50, 80, 100, 160, 320},
             { 1,  2,  4,  5,  8,  10,  16,  32}};
#endif

    SPISettings _spi_settings;
    int8_t _configure_mux_settings(uint16_t gain);
    int8_t _configure_pins(void);
    int8_t _configure_SPI(void);
};

#endif // RX_GAIN_H_