#include <math.h>
#include "gen_dac_ramp.h"

/*
 * This depends on the board design
 */
const double vco_tune_gain = 1.5;

/*
 * Convert tuning voltage to DAC values
 * The -1 at the end follow the definition of output voltage for the Teensy 3.2:
 * v_out = v_ref * (1 + dac_reg)/4096
 * 
 * see https://www.pjrc.com/teensy/K20P64M72SF1RM.pdf chapter 33
 *
*/
uint16_t vco_voltage_dac(double v) {
	const double dac_max_voltage = 3.3; // TBD: should it be 3.2V?
	const double dac_max_count = 4096;
	uint16_t dac_count = round(v/vco_tune_gain/dac_max_voltage*dac_max_count)-1;
	return dac_count;
}

/*
 * Generate a more linear frequecy ramp by using the vco fit to correct tune 
 * voltage.  Then, transform the voltage into teensy dac counts.
 * 
 * If fstart <= fstop, generate an up ramp
 * If fstop < fstart, generate a down ramp
 *
 * All frequencies must be in the closed interval
 * [vco_min_usable_freq , vco_max_usable_freq]
 *
 * returns 0 on success, other values on failure
*/
int gen_dac_ramp(double fstart, double fstop, int fcount, uint16_t *dac_ramp) {
  // Establish ramp direction
  int up_ramp = 1;
  if (fstart > fstop) {
    double fswap = fstart;
    fstart = fstop;
    fstop = fswap;
    up_ramp = 0;
  }	
  
  if (fstart < vco_min_usable_freq) return -1;
  if (fstop > vco_max_usable_freq) return -2;
  
  double fnext = fstart;
  double fstep = (fstop-fstart)/(fcount-1.0);
  int fidx = 0;
  for(int ii=0; ii<vco_poly_count; ii++) {
    while ((fnext >= vco_freq_break[ii]) && (fnext <= vco_freq_break[ii+1])) {
      double x = fnext - vco_freq_break[ii];
      double v = vco_voltage_c0[ii] + x*(vco_voltage_c1[ii] + x*(vco_voltage_c2[ii] + x*vco_voltage_c3[ii]));
      uint16_t dac_count = vco_voltage_dac(v);
      if (up_ramp)
	dac_ramp[fidx] = dac_count;
      else
	dac_ramp[fcount-fidx-1] = dac_count;
      fnext = fnext + fstep;
      fidx++;
      if (fidx >= fcount) goto done;
    }
  }
 done:
  if (fidx < fcount) return -3;
  return 0;
}

