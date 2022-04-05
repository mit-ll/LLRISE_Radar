#include <malloc.h>
#include <math.h>
#include "Radar.h"

#include "global_vars.h"
#include "msg_radar.h"

//#include "vco_linear_coefs.h"
#include "vco_fit_coefs.h"

//  Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY

Radar::Radar() : m_adc{}, m_dac{}, m_pdb{}, m_rx_gain_mux{},
                 pulse_length_ms{0}, rx_gain{0},
                 freq_start{0}, freq_stop{0}, freq_return{0},
                 adc_buffer{}, dac_buffer{} {}

int8_t Radar::configure(uint16_t pulse_length_ms, uint16_t rx_gain, float_t freq_start, float_t freq_stop, float_t freq_return)
{
    int8_t status = -2;
    
    stop();

    // #TODO: Maybe check ranges here? Should validation happen elsewhere?
    // #TODO: Perhaps have explicit setters for variables with localized validation
    this->pulse_length_ms = pulse_length_ms;
    this->rx_gain = rx_gain;
    this->freq_start = freq_start;
    this->freq_stop = freq_stop;
    this->freq_return = freq_return;

    if (fabsf(this->freq_return - 0) < 1e-6f)
    {
        status = _configure_sawtooth();

        // #TODO: actually check status code and do something
    }
    else
    {
        status = _configure_triangle();

        // #TODO: actually check status code and do something
    }

    status = m_adc.configure(&adc_buffer);
    status = m_dac.configure(&dac_buffer);
    status = m_pdb.configure();
    status = m_rx_gain_mux.configure(this->rx_gain);

    // #TODO: actually check status code and do something

    return status;
}

void Radar::start(void)
{
     __disable_irq();
    // Reset CPU cycle counter to 0.
    global_vars::reset_cpu_cycle_counter();
    // Start each peripheral in order
    m_pdb.start();
    m_dac.start();
    m_adc.start();
    __enable_irq();

    digitalWrite(LED_PIN_RED, HIGH);
    digitalWrite(LED_PIN_GRN, HIGH);
    digitalWrite(LED_PIN_BLU, LOW);
    digitalWrite(ENABLE_PIN_5V, HIGH);
}

void Radar::stop(void)
{
    digitalWrite(LED_PIN_RED, HIGH);
    digitalWrite(LED_PIN_GRN, LOW);
    digitalWrite(LED_PIN_BLU, HIGH);
    digitalWrite(ENABLE_PIN_5V, LOW);

    __disable_irq();
    m_pdb.stop();
    m_dac.stop();
    m_adc.stop();
    __enable_irq();
}

int8_t Radar::_gen_dac_ramp(float_t freq_start, float_t freq_stop, uint16_t buffer_length, volatile uint16_t *buffer)
{
    // Establish ramp direction
    uint8_t up_ramp = 1;
    if (freq_start > freq_stop)
    {
        float_t freq_swap = freq_start;
        freq_start = freq_stop;
        freq_stop = freq_swap;
        up_ramp = 0;
    }

    if (freq_start < vco_min_usable_freq || freq_start > vco_max_usable_freq)
        return -1;
    if (freq_stop > vco_max_usable_freq || freq_stop < vco_min_usable_freq)
        return -2;

    float_t freq_next = freq_start;
    float_t freq_step = (freq_stop - freq_start) / (buffer_length - 1.0f);
    uint16_t freq_idx = 0;
    for (uint32_t ii = 0; ii < vco_poly_count; ii++)
    {
        while ((freq_next >= vco_freq_break[ii]) && (freq_next <= vco_freq_break[ii + 1]))
        {
            float_t x = freq_next - vco_freq_break[ii];
            float_t v = vco_voltage_c0[ii] + x * (vco_voltage_c1[ii] + x * (vco_voltage_c2[ii] + x * vco_voltage_c3[ii]));
            uint16_t dac_count = m_dac.voltage_to_dac_count(v/_vco_tune_gain);
            if (up_ramp)
            {
                buffer[freq_idx] = dac_count;
            }
            else
            {
                buffer[buffer_length - freq_idx - 1] = dac_count;
            }
            freq_next = freq_next + freq_step;
            freq_idx++;

            if (freq_idx >= buffer_length)
            {
                goto done;
            }
        }
    }
done:
    if (freq_idx < buffer_length)
        return -3;
    return 0;
}

int8_t Radar::_set_peripheral_params(void)
{
    int8_t status = -3;
    for (uint8_t ii = 0; ii < 8; ii++)
    {
        if (_timing_params[ii][0] == pulse_length_ms)
        {
            status = 0;
            dac_buffer.length = _timing_params[ii][1];
            dac_buffer.size = dac_buffer.length * sizeof(uint16_t);

            // #TODO: Concern for memory fragmentation?
            // Fortunately most memory requested is of the same size.
            // Alternatively give Buffer.data a fixed size that accomodates everything
            free(static_cast<void *>(const_cast<uint16_t *>(dac_buffer.data)));
            dac_buffer.data = const_cast<volatile uint16_t *>(static_cast<uint16_t *>(memalign(16, dac_buffer.size)));
            if(dac_buffer.data == NULL)
            {
                status = -1;
                break;
            }

            m_dac._dac_hold_time_us = (static_cast<float_t>(pulse_length_ms) * 1e3f / dac_buffer.length);
            m_dac._dac_hold_counts = static_cast<uint16_t>(roundf(F_BUS * m_dac._dac_hold_time_us * 1e-6f));

            m_adc._adc_timing_scale_factor = _timing_params[ii][2];
            m_adc._adc_period_counts = m_adc._adc_timing_scale_factor * m_dac._dac_hold_counts;

            // adc_buffer is sized to be twice as large as one pulse to allow for ping-pong operation
            adc_buffer.length = 2 * (dac_buffer.length / m_adc._adc_timing_scale_factor);
            adc_buffer.size = adc_buffer.length * sizeof(uint16_t);
           
            // #TODO: Concern for memory fragmentation?
            // Fortunately most memory requested is of the same size.
            // Alternatively give Buffer.data a fixed size that accomodates everything
            free(static_cast<void *>(const_cast<uint16_t *>(adc_buffer.data)));
            adc_buffer.data = const_cast<volatile uint16_t *>(static_cast<uint16_t *>(memalign(16, adc_buffer.size)));
            if(dac_buffer.data == NULL)
            {
                status = -2;
                break;
            }
            memset(static_cast<void *>(const_cast<uint16_t *>(adc_buffer.data)), 0, adc_buffer.size);

            m_pdb._pdb_mod = (m_adc._adc_period_counts - 1);
            m_pdb._channel_delay = m_pdb._pdb_mod - (m_adc._adc_sampling_duration_counts - 1);
            m_pdb._dac_interval_trigger = (m_dac._dac_hold_counts - 1);

            break;
        }
    }
    return status;
}

int8_t Radar::_configure_sawtooth()
{
    int8_t status = 0;
    status = _set_peripheral_params();
    status = _gen_dac_ramp(freq_start, freq_stop, dac_buffer.length, dac_buffer.data);

    // #TODO: actually check status code and do something

    return status;
}

int8_t Radar::_configure_triangle()
{
    int8_t status = 0;
    status = _set_peripheral_params();
    uint16_t up_ramp_length = dac_buffer.length / 2;
    uint16_t down_ramp_length = dac_buffer.length - up_ramp_length;
    status = _gen_dac_ramp(freq_start, freq_stop, up_ramp_length, dac_buffer.data);
    status = _gen_dac_ramp(freq_stop, freq_return, down_ramp_length, (dac_buffer.data + up_ramp_length));

    // #TODO: actually check status code and do something
    
    return status;
}

// Timing parameters correct for 50 KHz sampling rate. Idially this could be dynamically computed
// pulse_length | dac_params.buffer_length | adc_params._adc_timing_scale_factor |
const uint16_t Radar::_timing_params[8][3] = {{ 5, 3000, 12},
                                              {10, 3000,  6},
                                              {15, 3000,  4},
                                              {20, 3000,  3},
                                              {25, 5000,  4},
                                              {30, 3000,  2},
                                              {35,    0,  0}, // apparently no values work for this pulse_length. Alternative DAC DMA transfer sizes should fix this
                                              {40, 4000,  2}};
