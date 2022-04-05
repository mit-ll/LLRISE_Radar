#include "ADC.h"
//  Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
DMAChannel ADC::_dma_channel {false};

const uint8_t ADC::_channel2sc1a[] = {
	//0x1F=31 deactivates the ADC.
	5, 14, 8, 9, 13, 12, 6, 7, 15, 4, 0, 19, 3, 31,												  // 0-13, we treat them as A0-A13
	5, 14, 8, 9, 13, 12, 6, 7, 15, 4,															  // 14-23 (A0-A9)
	31, 31, 31, 31, 31, 31, 31, 31, 31, 31,														  // 24-33
	0 + ADC_SC1A_PIN_DIFF, 19 + ADC_SC1A_PIN_DIFF, 3 + ADC_SC1A_PIN_DIFF, 31 + ADC_SC1A_PIN_DIFF, // 34-37 (A10-A13)
	26, 22, 23, 27, 29, 30																		  // 38-43: temp. sensor, VREF_OUT, A14, bandgap, VREFH, VREFL.
																								  // A14 isn't connected to anything in Teensy 3.0.
};

FASTRUN void ADC::_dma_isr(void)
{
	// Since we have accumulated a full pulse,send out a trigger signal.
  //digitalWriteFast(TRIGGER_PIN, HIGH);

	if (global_vars::transmit_trigger && (global_vars::pulse_number&0x1))
        digitalWriteFast(TRIGGER_PIN, HIGH);
    else
        digitalWriteFast(TRIGGER_PIN, LOW);

	// get time interrupt occured in CPU cycles
	global_vars::pulse_cycle_count = global_vars::read_cpu_cycle_counter();
	// increment pulse number counter
	global_vars::pulse_number++;
	//digitalWriteFast(TRIGGER_PIN, LOW);
	// clear interrupt on the ADC DMA channel
	ADC::_dma_channel.clearInterrupt();
}

ADC::ADC() : _adc_timing_scale_factor{0}, _adc_period_counts{0}, _adc_sample_rate{0}
			 
{
	// Set ADC0 and ADC1 to trigger of default sources (pdb)
    SIM_SOPT7 = 0;
	ADC::_dma_channel.begin(true);
}

int8_t ADC::configure(Buffer *adc_buffer)
{
	int8_t status;
	status = _configure_pins();
	status = _configure_dma(adc_buffer);
	status = _calibrate_adc();
	status = _configure_registers();
	return status;
}

void ADC::start(void)
{
	// Enable DMA requests on the configured channel
	ADC::_dma_channel.enable();
}

void ADC::stop(void)
{
	ADC::_dma_channel.disable();
}

int8_t ADC::_configure_pins(void)
{
	// Setup positive Input to ADC. Unnecessary/Does nothing. Only for illustrative purposes
	// pinMode() only configures digital pins (i.e pins# < CORE_NUM_DIGITAL == 34 == pin A10)
	//pinMode(ADC_PIN, INPUT);

	// Setup the Trigger pins
	pinMode(TRIGGER_PIN, OUTPUT);
	// Change the pin configuration to allow fast slew rate.
	volatile uint32_t *config;
	config = portConfigRegister(TRIGGER_PIN);
	// SRE bit = 0 for fast slew rate
	*config = PORT_PCR_DSE | PORT_PCR_MUX(1);
	// Consider patch to core_pins.h and pins_teensy.c to allow
	// pinModeFast() function.
	// See here for approach: https://forum.pjrc.com/threads/28735-Interrupts-not-always-served-on-Teensy-3-1?p=75044&viewfull=1#post75044
	return 0;
}

int8_t ADC::_configure_dma(Buffer *adc_buffer)
{
	// Trigger DMA when ADC completes a conversion
	ADC::_dma_channel.triggerAtHardwareEvent(DMAMUX_SOURCE_ADC0);

	// What exactly does this mean? Would this be better with some reinterpret_cast to make it explicit?
	// Source takes a reference and sets source address dma parameter to address of passed reference (see source code).
	// The reason for this conversion to uint16_t is that the transfer size is also set by the type of this value (again see source code).
	// Does this weird cast become redundant if we use the transfer size and transfer count stuff?
	// It looks ugly and I don't like it.
	// ADC::_dma_channel.source((volatile uint16_t &)(ADC0_RA));
	// ADC::_dma_channel.destinationBuffer(adc_buffer->data, adc_buffer->size);
	// ADC::_dma_channel.transferSize(sizeof(uint16_t));
	// ADC::_dma_channel.transferCount(adc_buffer->length);

	ADC::_dma_channel.TCD->SADDR = &ADC0_RA;
	ADC::_dma_channel.TCD->DADDR = adc_buffer->data; // data_buffer;

	ADC::_dma_channel.TCD->NBYTES = sizeof(uint16_t);

	ADC::_dma_channel.TCD->ATTR_SRC = DMA_TCD_ATTR_SIZE_16BIT;
	ADC::_dma_channel.TCD->ATTR_DST = DMA_TCD_ATTR_SIZE_16BIT;

	ADC::_dma_channel.TCD->SOFF = 0;
	ADC::_dma_channel.TCD->DOFF = sizeof(uint16_t);

	ADC::_dma_channel.TCD->BITER_ELINKNO = adc_buffer->length; // data_buffer_length;
	ADC::_dma_channel.TCD->CITER_ELINKNO = adc_buffer->length; //data_buffer_length;

	ADC::_dma_channel.TCD->SLAST = 0;
	ADC::_dma_channel.TCD->DLASTSGA = -(adc_buffer->size); //-data_buffer_size;

	ADC::_dma_channel.interruptAtCompletion();
	ADC::_dma_channel.interruptAtHalf();

	ADC::_dma_channel.attachInterrupt(ADC::_dma_isr);
	return 0;
}

int8_t ADC::_calibrate_adc(void)
{
	/*
		Perform Initial ADC calibration
		For best configuration results the following conditions are set:
			- 16 bit accuracy.
			- Hardware averaging to maximum == 32 averages
			- Slow clock frequency, f_ADCK <= 4MHz
			- V_REFH == VDDA, i.e 3.3V internal reference

	*/
	// Select b channels. Shouldn't matter for differential mode but just in case
	// ADC0_CFG2 |= ADC_CFG2_MUXSEL;
	// Select the 3.3V reference. ADC_SC2_REFSEL[1] can also select an external reference that remains unconnected
	ADC0_SC2 |= ADC_SC2_REFSEL(0);

	// Set conversion resolution to 16 bits. ADC_CFG1_MODE[3] == 0b11 configures ADC for 16 bits
	ADC0_CFG1 |= ADC_CFG1_MODE(3);
	// Enable hardware averaging
	ADC0_SC3 |= ADC_SC3_AVGE;
	// Set hardware averages to 32 samples. ADC_SC3_AVGS[3] == 0b11 configures ADC for 32 sample hardware averaging.
	ADC0_SC3 |= ADC_SC3_AVGS(3);

	// Set clock to low speed <= 4MHz
	// Disable internal asynchronous clock.
	// Complement bit and AND it with existing configuration. All other bits should remain the same except this
	ADC0_CFG2 &= ~ADC_CFG2_ADACKEN;
	// Input clock is bus/2
	ADC0_CFG1 |= ADC_CFG1_ADICLK(1);
	// Divisor to input clock is 2^ADC_CFG1_ADIV == 2^3 = 8;
	// We therefore get ADC_Clock = (F_BUS/2)/2^ADC_CFG1_ADIV == (48e6/2)/8 == 3MHz <= 4MHz
	ADC0_CFG1 |= ADC_CFG1_ADIV(3);

	// First set conversion speed
	// Disable high speed configuration
	ADC0_CFG2 &= ~ADC_CFG2_ADHSC;
	// Enable low power mode.
	ADC0_CFG1 |= ADC_CFG1_ADLPC;

	// Subsequently set slow sampling speed
	// Enable long sampling time
	ADC0_CFG1 |= ADC_CFG1_ADLSMP;
	// Set total sample time to 16 ADCK cycles.
	// ADC_CFG2_ADLSTS[1] == 0b01 configures ADC to add 12 extra ADCK cycles to sample time
	ADC0_CFG2 |= ADC_CFG2_ADLSTS(1);

	// Perform calibration
	// Disable interrupts during this process
	__disable_irq();

	// Clear calibration bit to stop any previous spurious calibration.
	ADC0_SC3 &= ~ADC_SC3_CAL;
	// Write to calibration failed bit field clears it. Any calibration errors are recorded here.
	ADC0_SC3 |= ADC_SC3_CALF;
	// Write to calibration bit to begin callibration.
	ADC0_SC3 |= ADC_SC3_CAL;

	// Wait while calibration completes. The CAL bit is cleared when calibration is complete
	while(ADC0_SC3 & ADC_SC3_CAL);

	if (ADC0_SC3 & ADC_SC3_CALF)
	{
		__enable_irq();
		// This should never print.
		// If set high before radar start check here
		digitalWriteFast(13, HIGH);
		return -99;
	}
	uint16_t gainSum;
	// Set plus side gain based on calibration results
	gainSum = ADC0_CLPS + ADC0_CLP4 + ADC0_CLP3 + ADC0_CLP2 + ADC0_CLP1 + ADC0_CLP0;
	gainSum = (gainSum / 2) | 0x8000;
	ADC0_PG = gainSum;
	// Set minus side gain based on calibration results
	gainSum = ADC0_CLMS + ADC0_CLM4 + ADC0_CLM3 + ADC0_CLM2 + ADC0_CLM1 + ADC0_CLM0;
	gainSum = (gainSum / 2) | 0x8000;
	ADC0_MG = gainSum;

	// enable interrupts at end of callibration
	__enable_irq();
	return 0;
}

int8_t ADC::_configure_registers(void)
{
	// Reset values for clean configuration. They all reset to zero.
	ADC0_CFG1 = 0;
	ADC0_CFG2 = 0;
	ADC0_SC2 = 0;
	ADC0_SC3 = 0;
	// Reset ADC Status and Control register
	ADC0_SC1A = 0;

	// Select b channels. Shouldn't matter for differential mode but just in case
	// ADC0_CFG2 |= ADC_CFG2_MUXSEL;
	// Select the 3.3V reference. ADC_SC2_REFSEL[1] can also select an external reference that remains unconnected
	ADC0_SC2 |= ADC_SC2_REFSEL(0);

	// Once calibration is complete configure ADC as desired
	// Set conversion resolution to 16 bits. ADC_CFG1_MODE[3] == 0b11 configures ADC for 16 bits
	ADC0_CFG1 |= ADC_CFG1_MODE(3);
	// Disable continuous conversion
	ADC0_SC3 &= ~ADC_SC3_ADCO;
	// Hardware trigger for ADC. Will be triggered by PDB
	ADC0_SC2 |= ADC_SC2_ADTRG;
	// Enable DMA transfers on conversion complete
	ADC0_SC2 |= ADC_SC2_DMAEN;
	// Disable hardware averages
	ADC0_SC3 &= ~ADC_SC3_AVGE;

	// Configure ADC Clock to be as close to as fast as possible == 12MHz (limit for 16 bits)
	// Disable internal asynchronous clock.
	ADC0_CFG2 &= ~ADC_CFG2_ADACKEN;
	// Input clock is bus/2
	ADC0_CFG1 |= ADC_CFG1_ADICLK(1);
	// Divisor to input clock is 2^ADC_CFG1_ADIV == 2^1 = 2;
	// We therefore get ADC_Clock = (ADC_CFG1_ADICLK)/(2^ADC_CFG1_ADIV) == (48e6/2)/2 == 12MHz
	ADC0_CFG1 |= ADC_CFG1_ADIV(1);

	// Set conversion speed to fastest possible
	// Enable high speed configuration
	ADC0_CFG2 |= ADC_CFG2_ADHSC;
	// Disable low power mode
	ADC0_CFG1 &= ~ADC_CFG1_ADLPC;

	// Set sampling speed to LST + 2.
	// Due to not using "continuous mode", this is just as fast as the shortest possible sampling time but with better sample quality
	// Enable long sampling time
	ADC0_CFG1 |= ADC_CFG1_ADLSMP;
	// Set total sample time to additional 2 ADCK cycles over base of 4
	ADC0_CFG2 |= ADC_CFG2_ADLSTS(3);
	// ADC0_CFG2 |= ADC_CFG2_ADLSTS(2);

	// Configures ADC to select correct internal input channel based on desired external pin
	ADC0_SC1A |= ADC_SC1_ADCH(_channel2sc1a[ADC_PIN]); //(SC1A_PIN & ADC_SC1A_CHANNEL_MASK);
	// C0nfigure ADC to not be in differential mode
	ADC0_SC1A &= ~ADC_SC1_DIFF;
	// Configure ADC to enable interrupts on conversion complete.
	// ADC0_SC1A |= ADC_SC1_AIEN;
	// NVIC_SET_PRIORITY(IRQ_ADC0, 0);
    // NVIC_ENABLE_IRQ(IRQ_ADC0);

	return 0;
}

#ifdef DEFINE_ADC0_ISR
void adc0_isr(void)
{
	global_pulse_vars::pulse_number++;
	// if((global_pulse_vars::pulse_number % 100) == 0)
	// {
	// 	msg_send_log(LOG_INFO, 1, "adc coco");
	// 	digitalWriteFast(13, !digitalReadFast(13));
	// }
	volatile uint32_t tmp = ADC0_RA;
}
#endif
