/*   Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY */
#ifndef GLOBAL_PULSE_H_
#define GLOBAL_PULSE_H_

/* #TODO: This is a file to hold the volatile stuff incremented by the ADC code every pulse.
 * A better way exists to do this but it eludes me.
 * Some combination of smarter ADC instance management to allow for both ADCs to co-exist with static methods
 * Or something along those lines. See here: http://www.gammon.com.au/forum/?id=12983 and figure it out when you can think better
*/

#include "WProgram.h" // contains definition of FASTRUN
#include "kinetis.h"

// #TODO: Would this be better as some sort of class? Perhaps combined with some of the messagin stuff

// Indicator variable asserted when a buffer is filled with ADC data.
// Reset when all data has been written by USB
namespace global_vars
{
	extern volatile bool transmit_trigger;
	extern volatile uint32_t pulse_number;
	extern volatile uint32_t prev_pulse_number;
	extern volatile uint32_t pulse_cycle_count;

	void enable_cpu_cycle_counter(void);

	void reset_cpu_cycle_counter(void);

	volatile uint32_t read_cpu_cycle_counter(void);
}


#endif // GLOBAL_PULSE_H_