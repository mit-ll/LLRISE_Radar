#include "PDB.h"
//  Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY

PDB::PDB() : _pdb_mod{0}, _channel_delay{0}, _dac_interval_trigger{0} 
{
	// enable PDB clock
	SIM_SCGC6 |= SIM_SCGC6_PDB;
}

int8_t PDB::configure(void)
{
	// Reset PDB0 Status register to clear state
	PDB0_SC = 0;
	// Enable the PDB
	PDB0_SC |= PDB_SC_PDBEN;
	// Determines how PDB registers are loaded.
	// 0d == 00b means registers are loaded immediately after PDB_SC_LDOK bit is set
	PDB0_SC |= PDB_SC_LDMOD(0);
	// Select Trigger source for PDB. 15d == 1111b is software trigger
	PDB0_SC |= PDB_SC_TRGSEL(15);
	// Set interrupt delay to 0
	PDB0_IDLY = 0;
	// Set PRESCALER and MULTIPLER of counter.
	// PDB0_MOD  modulus register, sets period.
	// counts == (F_BUS * period) / (2^prescaler * multiplier)
	// PDB_MOD ==(F_BUS * dac_hold_time) / (2^PRESCALER * MULT);
	// Note that counts == PDB_MOD can be at most 2^16 - 1 = 65535,
	// so PRESCALER and MULT need to be set appropriately.
	PDB0_SC |= PDB_SC_PRESCALER(0) | PDB_SC_MULT(0);
	// Set PDB to run in continuous mode
	PDB0_SC |= PDB_SC_CONT;

	// The PDB counter max value.
	// The counter will reset to 0 after reaching this value
	// The counter is sized so as to allow adequate time for the adc to perform a measurement
	PDB0_MOD = _pdb_mod; // (adc_period_counter - 1);

	// PDB Channel Control Register 1. Handles pre-triggering operations.
	// Enable the pre-trigger by writing: 0X01.
	// Set the pre-trigger output to be asserted when the counter reaches the channel delay value in PDB_CH0DLY1 by writing: 0x0100
	PDB0_CH0C1 = 0x0100 | 0x01;
	// Trigger adc at the end of the MOD counter.
	// We subtract the duration it takes the adc to sample the signal at its input, so that sampling doesn't stradle the ramp-out transition
	// We additionally subtract one cycle to account for delay when the channel trigger output changes in response to the pre-trigger asserting.
	PDB0_CH0DLY0 = _channel_delay; //((adc_period_counter - 1) - adc_sampling_duration_counter - 1);

	// Enable DAC interval Trigger
	PDB0_DACINTC0 |= PDB_DACINTC_TOE;
	// Set DAC interval trigger to occur whenever the counter reaches the desire DAC period value
	PDB0_DACINT0 = _dac_interval_trigger; // (dac_hold_counter - 1);

	// load registers from buffers
	PDB0_SC |= PDB_SC_LDOK;

	return 0;
}

void PDB::start(void)
{

	PDB0_SC |= PDB_SC_SWTRIG; // Reset and restart PDB. Will begin counting down immediately.
}

void PDB::stop(void)
{
	PDB0_SC &= ~PDB_SC_PDBEN;
}