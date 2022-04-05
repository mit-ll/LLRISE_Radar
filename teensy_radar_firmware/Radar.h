/*   Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY */
#ifndef RADAR_H_
#define RADAR_H_

#include <WProgram.h>

#include "ADC.h"
#include "Buffer.h"
#include "DAC.h"
#include "Gain_Mux.h"
#include "PDB.h"

class Radar
{
public:
    ADC m_adc;
    DAC m_dac;
    PDB m_pdb;
    Gain_Mux m_rx_gain_mux;

    uint16_t pulse_length_ms;
    uint16_t rx_gain;
    float_t freq_start;
    float_t freq_stop;
    float_t freq_return;

    Buffer adc_buffer;
    Buffer dac_buffer;

    Radar();
    int8_t configure(uint16_t pulse_length_ms, uint16_t rx_gain, float_t freq_start, float_t freq_stop, float_t freq_return);
    void start(void);
    void stop(void);

private:
    // Timing parameters correct for 50 KHz sampling rate. Ideally this could be dynamically computed
    // pulse_length | dac_params.buffer_length | adc_params._adc_timing_scale_factor |
    static const uint16_t _timing_params[8][3];

    const float _vco_tune_gain {1.5};

    int8_t _gen_dac_ramp(float_t freq_start, float_t freq_stop, uint16_t buffer_length, volatile uint16_t *buffer);
    int8_t _set_peripheral_params();
    int8_t _configure_sawtooth();
    int8_t _configure_triangle();
};
#endif // RADAR_H_
