#include "Gain_Mux.h"
//  Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY

Gain_Mux::Gain_Mux() : _mux_channel{0}, _mux_idx{0},
                       _spi_settings{2000000, MSBFIRST, SPI_MODE0}
{
    SPI.setMOSI(GAIN_SPI_MOSI);
    SPI.setMISO(GAIN_SPI_MISO);
    SPI.setSCK(GAIN_SPI_SCK);
 
    // Set device to a known initial state
    digitalWriteFast(GAIN_SPI_CS, HIGH);
    configure(1);
}

int8_t Gain_Mux::configure(uint16_t gain)
{
    int status = -2;
    status = _configure_mux_settings(gain);
    status = _configure_pins();
    status = _configure_SPI();
    return status;
}

int8_t Gain_Mux::_configure_mux_settings(uint16_t gain)
{
    int8_t status = -1;
    for (uint8_t channel = 0; channel < _mux_channel_max; channel++)
    {
        for (uint8_t idx = 0; idx < _mux_idx_max; idx++)
        {
            if (_mux_params[channel][idx] == gain)
            {
                status = 0;
                _mux_channel = channel;
                _mux_idx = idx;
                break;
            }
        }
    }
    return status;
}

int8_t Gain_Mux::_configure_pins(void)
{
    // Setup SPI pins for gain control.
    pinMode(GAIN_SPI_CS, OUTPUT);
    return 0;
}

int8_t Gain_Mux::_configure_SPI(void)
{
    //_mux_channel = 4;

    // TBD: Why does this need to be here rather than in constructor?
    // Without this there is not clock activity on the pin
    SPI.begin();

    // Set the channel of the mux
    SPI.beginTransaction(_spi_settings);
    digitalWriteFast(GAIN_SPI_CS, LOW);
    // Address the channel register
    SPI.transfer(0b01000001);
    // Set channel to desired channel
    SPI.transfer(0b00000000 | _mux_channel);
    digitalWriteFast(GAIN_SPI_CS, HIGH);
    SPI.endTransaction();
    // Small delay between transactions. Not sure if needed
    //delay(1);
    delayMicroseconds(100);

    // Set the gain of the mux
    SPI.beginTransaction(_spi_settings);
    digitalWriteFast(GAIN_SPI_CS, LOW);
    // Address the gain register
    SPI.transfer(0b01000000);
    SPI.transfer(0b00000000 | _mux_idx);
    digitalWriteFast(GAIN_SPI_CS, HIGH);
    SPI.endTransaction();
    //delay(1);
    delayMicroseconds(100);

    return 0;
}
