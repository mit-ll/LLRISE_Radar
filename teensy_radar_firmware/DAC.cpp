#include "DAC.h"
//  Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY

DAC::DAC() : _dac_hold_time_us{0}, _dac_hold_counts{0},
			 _dma_channel{false}
{
	// Enable DAC clock
	SIM_SCGC2 |= SIM_SCGC2_DAC0;
	// Initializes the dma channel for the dac.
	// Initialization is forced since this is a necessary component of the radar.
	_dma_channel.begin(true);
}

int8_t DAC::configure(Buffer *dac_buffer)
{
	int8_t status = -3;

	status = _configure_pins();
	status = _configure_dma(dac_buffer);
	status = _configure_registers();

	return status;
}

void DAC::start(void)
{
	// Enable DMA requests on the configured channel
	_dma_channel.enable();
	// Enable the DAC module
	DAC0_C0 |= DAC_C0_DACEN;
}

void DAC::stop(void)
{
	// Disable the DMA engine to stop transfers.
	// Note that in theory this is all that is needed since this blocks output.
	// The downside is that doing so leaves the DAC outputing an unknown signal,
	// (i.e whatever was being output at the time the radar was stopped).
	_dma_channel.disable();
	// Disable the DAC module
	// We explicitely want to stop output as an additional safety so that the DAC output is left floating
	// and therefore a noise-like signal is being output at all times.
	DAC0_C0 &= ~DAC_C0_DACEN;
}

/*
 * Convert tuning voltage to DAC values
 * The -1 at the end follows from the definition of output voltage for the Teensy 3.2:
 * v_out = v_ref * (1 + dac_reg)/4096
 * 
 * see https://www.pjrc.com/teensy/K20P64M72SF1RM.pdf chapter 33
 *
*/
uint16_t DAC::voltage_to_dac_count(float_t voltage)
{
	uint16_t dac_count = roundf((voltage / _dac_ref_voltage) * _dac_max_count) - 1;
    return dac_count;
}

int8_t DAC::_configure_pins(void)
{
	// Setup output of DAC. Unnecessary/Does nothing. Only for illustrative purposes
	// pinMode() only configures digital pins (i.e pins# < CORE_NUM_DIGITAL == 34 == pin A10)
	pinMode(DAC_PIN, OUTPUT);
	return 0;
}

int8_t DAC::_configure_dma(Buffer *dac_buffer)
{
	// Configure the triggering source for the dma to be the dac hardware
	// This enables the DMA mux and routes it correctly between the channel and dac hardware
	_dma_channel.triggerAtHardwareEvent(DMAMUX_SOURCE_DAC0);

	// Source address from which the DMA reads from is the ramp_array
	_dma_channel.TCD->SADDR = dac_buffer->data; //ramp_array;
	// Destination address is that of the dac buffer
	_dma_channel.TCD->DADDR = &DAC0_DAT0L;
	// Each DMA request should fill half of the dac buffer, treating it as a ping-pong buffer
	// Half the dac buffer size == 8 x 2byte "words" == 16 bytes
	_dma_channel.TCD->NBYTES = 16;

	/*
    * Unfortunately a 16byte burst doesn't seem to work unless the source (maybe also destination) are aligned
    * to a 16byte boundary. See comment by dale.roberts at:
    * https://hackaday.io/project/12543-solid-state-flow-sensing-using-eis/log/41575-dac-with-dma-and-buffer-on-a-teensy-32)
    * To fix this we align dac_buffer->buffer in the struct it is defined in.
    * If a way exists that doesn't require alignment it would waste less memory.
    * As it stands though 16byte transfers tax the DMA resources the least since a single burst fills half the DAC buffer
    */
	// We configure a transfer of 16bytes == 128bits == 8 x 2byte dac_register == half the dac buffer size
	// This represents 8 waveform samples transfered at once
	_dma_channel.TCD->ATTR_SRC = DMA_TCD_ATTR_SIZE_16BYTE;
	// We wish to configure the DMA to treat the destination address as a circular buffer.
	// First we configure a transfer of 16bytes == 128bits == 8 x 2byte dac_register == half the dac buffer size
	// Then we configure the number of lower bits of the destination address we want to change before the address
	// circles back to zero.
	// The DAC buffer starts at address 0x400C_C000 and goes to 0x400C_C01E. We therefore want to only allow variation
	// to the bottom 0x1E + 2 bits (the 2 accounts for the low/high buffer registers at 0X1E and 0x1F).
	// By counting the leading zeros of 0x1E + 2 and subtracting them from 31 be get the number of modulo bits.
	// This number is 31 - __builtin_clz(0X1E + 2) == 31 - _builtin_clz(32) == 31 - 26 == 5 lower modulo bits.
	_dma_channel.TCD->ATTR_DST = DMA_TCD_ATTR_SIZE_16BYTE | DMA_TCD_ATTR_DMOD(31 - __builtin_clz(32));
	// Each DMA read will read 16bytes == 128bits == 8 waveform samples.
	// Therefore we want the source address to advance 16bytes after each read
	_dma_channel.TCD->SOFF = 16;
	// Each DMA write will place 16 bytes into the dac buffer.
	// Therefore we want the source address to advance 16bytes during each write
	_dma_channel.TCD->DOFF = 16;

	// Total number of DMA transfers we should make before we re-adjust addresses to the start
	// The number of transfers is equal to the size of our source array divided by the size of each transfer,
	// num_transfers == ramp_array_size(bytes)/16byte transfers
	_dma_channel.TCD->BITER_ELINKNO = dac_buffer->size / 16; // ramp_array_size / 16;
	_dma_channel.TCD->CITER_ELINKNO = dac_buffer->size / 16; // ramp_array_size / 16;

	// Adjustment to source and destination addresses when we complete the full number of transfers defined above
	// The source address is reset to the start of the waveform array.
	// The destination address is not changed since it is the DAC buffer whih we have defined to be circular and
	// auto adjusting.
	_dma_channel.TCD->SLAST = -(dac_buffer->size); // -ramp_array_size;
	_dma_channel.TCD->DLASTSGA = 0;

	return 0;
}

int8_t DAC::_configure_registers(void)
{
	DAC0_C0 = 0;
	DAC0_C1 = 0;
	DAC0_C2 = 0;

	// enable DAC0 timer
	// set DAC reference to 3.3V
	DAC0_C0 |= DAC_C0_DACRFS;
	// Set upper limit of the dac buffer to be 15, i.e all availalbe words
	DAC0_C2 |= DAC_C2_DACBFUP(15);
	// Set Buffer read pointer to upper limit.
	// We set the read pointer here so that the top flag interrupt/dma transfer doesn't get instantly triggered.
	DAC0_C2 |= DAC_C2_DACBFRP(15);
	// Enable buffer watermark and top flag interrupts
	DAC0_C0 |= DAC_C0_DACBWIEN | DAC_C0_DACBTIEN;
	// Enable DAC pointer read buffer. DAC will output data pointed to by read pointer
	DAC0_C1 |= DAC_C1_DACBFEN;
	// Set DAC buffer to work in Normal (circular) mode
	DAC0_C1 |= DAC_C1_DACBFMD(0);
	// Set Watermark Flag (3+1) == 4 words away from the DAC buffer upper limit (i.e position 11)
	DAC0_C1 |= DAC_C1_DACBFWM(3);
	// Enable DMA transfers on interrupts.
	DAC0_C1 |= DAC_C1_DMAEN;

	// Set buffer read pointer to top, triggering DMA transfer to fill the bottom half of the buffer
	//DAC0_C2 = DAC_C2_DACBFRP(0) | DAC_C2_DACBFUP(15);
	//delay(1);

	// Set buffer read pointer to watermark flag, triggering DMA transfer to fill top half of the buffer
	DAC0_C2 = DAC_C2_DACBFRP(11) | DAC_C2_DACBFUP(15);
	delay(1);
	// Set buffer read pointer to bottom.  So that it ticks over to top on first irq.
	DAC0_C2 = DAC_C2_DACBFRP(15) | DAC_C2_DACBFUP(15);

	return 0;
}
