#include "global_vars.h"
//  Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY

//volatile bool global_vars::transmit_trigger = false;
volatile bool global_vars::transmit_trigger = true;
volatile uint32_t global_vars::pulse_number = 0;
volatile uint32_t global_vars::prev_pulse_number = 0;
volatile uint32_t global_vars::pulse_cycle_count = 0;

void global_vars::enable_cpu_cycle_counter(void)
{
	ARM_DEMCR |= ARM_DEMCR_TRCENA;
	ARM_DWT_CTRL |= ARM_DWT_CTRL_CYCCNTENA;
	ARM_DWT_CYCCNT = 0;
}

void global_vars::reset_cpu_cycle_counter(void)
{
	ARM_DWT_CYCCNT = 0;
}

volatile uint32_t global_vars::read_cpu_cycle_counter(void)
{
	return ARM_DWT_CYCCNT;
}