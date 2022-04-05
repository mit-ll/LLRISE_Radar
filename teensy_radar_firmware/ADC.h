/*   Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY */
#ifndef ADC_H_
#define ADC_H_

#include "Arduino.h"   // contains definition of Arduino requirements
#include "core_pins.h" // contains pin specific definitions and control functions
#include "DMAChannel.h"
#include "kinetis.h" // contains peripheral definitions

#include "Buffer.h"
#include "global_vars.h"
#include "msg_radar.h"
#include "peripheral_pins.h"

// Mask to select correct bits for channel mapping
#define ADC_SC1A_CHANNEL_MASK (0x1F)
// Mask to indicate pin is a differential capable pin on the ADC.
// This should maybe be 0x20 instead of 0x40 
// because then the ADCx_SC1A[DIFF] bit is automatically set for
// the relevant pins.
#define ADC_SC1A_PIN_DIFF (0x20) //(0x40) 

class ADC
{
public:
    uint16_t _adc_timing_scale_factor;
    uint16_t _adc_period_counts;
    uint16_t _adc_sample_rate;
    const float_t _adc_sampling_duration {0.666667f};
    const uint16_t _adc_sampling_duration_counts {static_cast<uint16_t>(roundf(F_BUS * 0.666667f * 1e-6f))};

    ADC(void);
    int8_t configure(Buffer *adc_buffer);
    void start(void);
    void stop(void);
    static void _dma_isr(void);

private:
    static DMAChannel _dma_channel;
    static const uint8_t _channel2sc1a[];

    int8_t _configure_pins(void);
    int8_t _configure_dma(Buffer *adc_buffer);
    int8_t _calibrate_adc(void);
    int8_t _configure_registers(void);

    void _enable_cpu_cycle_counter();
    void _reset_cpu_cycle_counter();
    void _read_cpu_cycle_counter();

};

#endif // ADC_H_
