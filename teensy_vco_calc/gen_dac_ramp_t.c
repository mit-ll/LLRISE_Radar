#include <stdio.h>
#include "gen_dac_ramp.h"

int main(int argc, char *argv[]) {
  double fstart = 2258.0;
  double fstop = 2588.0;
  //double fstart = 2260.0;
  //double fstop = 2560.0;
  int fcount = 360;
  uint16_t up_ramp[360];
  uint16_t dn_ramp[360];
  
  int s1 = gen_dac_ramp(fstart,fstop,fcount,up_ramp);
  int s2 = gen_dac_ramp(fstop,fstart,fcount,dn_ramp);

  if (s1 != 0 || s1 != 0) {
    printf("Failed: s1 = %d, s2 = %d\n",s1,s2);
    return -1;
  }
  
  for(int ii=0; ii<fcount; ii++) {
    int up = up_ramp[ii];
    int dn = dn_ramp[ii];
    printf("%4d %4d %4d\n", ii, up, dn);
  }	
  
  return 0;
}
