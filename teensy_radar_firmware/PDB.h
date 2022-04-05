/*   Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY */
#ifndef PDB_H_
#define PDB_H_

#include "Arduino.h" // contains definition of Arduino requirements
#include "core_pins.h" // contains pin specific definitions and control functions
#include "kinetis.h" // contains peripheral definitions

#include "msg_radar.h"

class PDB
{
public:
    PDB();
    int8_t configure(void);
    void start(void);
    void stop(void);

    uint16_t _pdb_mod;
    uint16_t _channel_delay;
    uint16_t _dac_interval_trigger;
};

#endif // PDB_H_