/* Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY */
#ifndef VCO_DAC_RAMP_H
#define VCO_DAC_RAMP_H

#include <stdint.h>
#include "vco_fit_coefs.h"

int gen_dac_ramp(double fstart, double fstop, int fcount, uint16_t *dac_ramp);

#endif //VCO_DAC_RAMP_H
