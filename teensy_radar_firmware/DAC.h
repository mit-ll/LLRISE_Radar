/*   Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY */
#ifndef DAC_H_
#define DAC_H_

#include "Arduino.h"
#include "core_pins.h" // contains pin specific definitions and control functions
#include "DMAChannel.h"
#include "kinetis.h" // contains peripheral definitions

#include "Buffer.h"
#include "msg_radar.h"
#include "peripheral_pins.h"


class DAC
{
public:

    DAC();
    int8_t configure(Buffer *dac_buffer);
    void start(void);
    void stop(void);
    uint16_t voltage_to_dac_count(float_t voltage);
    
    float_t _dac_hold_time_us;
    uint16_t _dac_hold_counts;

    const float_t _dac_ref_voltage {3.3};
    const float_t _dac_max_count {4096};

private:
    DMAChannel _dma_channel;

    int8_t _configure_pins(void);
    int8_t _configure_dma(Buffer *adc_buffer);
    int8_t _configure_registers(void);
};

#endif // DAC_H_