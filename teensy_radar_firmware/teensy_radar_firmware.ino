// Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
#include "Radar.h"
#include "global_vars.h"

#include "PacketSerial.h"
#include "msg_radar.h"

// #TODO: can this be a compile variable? or perhaps pulled from git?
#define VERSION "1.1.0"

PacketSerial myPacketSerial {};
Radar LLRISE_Radar {};

/***************************************************
* Radar states
***************************************************/
enum radar_state_enum
{
	RSTATE_UNKNOWN = 0,
	RSTATE_COMMAND,
	RSTATE_STREAMING
};

int radar_state = RSTATE_COMMAND;

void on_packet_received(const uint8_t *buffer, size_t size)
{
	int s;

    if (size <= 0) return;

	s = msg_send_log(LOG_DEBUG, 1, "RECEIVED A COMMAND");
	if(s)
	{
		// #TODO: do some error checking here maybe? not sure.
	}

	// Received a request
	switch (radar_state)
	{
	case RSTATE_COMMAND:
		switch (buffer[0])
		{
		case 'V':
			s = msg_send_reply(0, "LLRISE RADAR VERSION " VERSION);
			radar_state = RSTATE_COMMAND;
			break;
		case 'S':
			// Parse the rest of the message, and set values
			uint16_t pulse_length_ms;
			uint16_t rx_gain;
			float_t freq_start;
			float_t freq_stop;
			float_t freq_return;
			s = sscanf((const char *)buffer, "S %hu %hu %f %f %f",
					   &(pulse_length_ms), &(rx_gain),
					   &(freq_start), &(freq_stop), &(freq_return));
			// #TODO check return values of these and do something if something goes wrong
			// #TODO is it better to pass these values explicitely to configure?
			// #TODO Maybe create more general setters/getters?
			// #TODO just, keep an eye out...

			s = LLRISE_Radar.configure(pulse_length_ms, rx_gain, freq_start, freq_stop, freq_return);
			// #TODO: actually check status code and do something

			LLRISE_Radar.start();
			s = msg_send_reply(0, "STREAMING");
			// #TODO: actually check status code and do something
			radar_state = RSTATE_STREAMING;
			break;
		case 'X':
			LLRISE_Radar.stop();
			s = msg_send_reply(0, "STOPPED");
			radar_state = RSTATE_COMMAND;
			break;
		case 'A':
			global_vars::transmit_trigger = true;
			s = msg_send_reply(0, "TRIGGER ON");
			break;
		case 'L':
			global_vars::transmit_trigger = false;
			s = msg_send_reply(0, "TRIGGER OFF");
			break;
		default:
			s = msg_send_reply(-1, "COMMAND NOT VALID");
			radar_state = RSTATE_COMMAND;
		}
		break;
	case RSTATE_STREAMING:
		switch (buffer[0])
		{
		case 'X':
			LLRISE_Radar.stop();
			s = msg_send_reply(0, "STOPPING");
			radar_state = RSTATE_COMMAND;
			break;
		case 'A':
			global_vars::transmit_trigger = true;
			s = msg_send_reply(0, "TRIGGER ON");
			break;
		case 'L':
			global_vars::transmit_trigger = false;
			s = msg_send_reply(0, "TRIGGER OFF");
			break;
		// Could add other cases
		default:
			s = msg_send_reply(-1, "COMMAND NOT VALID");
			radar_state = RSTATE_STREAMING;
		}
		break;
	default:
		s = msg_send_log(LOG_ERROR, 1, "UNEXPECTED STATE, STOPPING");
		radar_state = RSTATE_COMMAND;
	}
}
/************************************************************************************/

const uint16_t MAX_DATA = 1024;
msg_pulse_header_t pulse_header;

// Send function with the msg handler
void send_function(const uint8_t *buffer, uint16_t size)
{
	myPacketSerial.send(buffer, size);
    Serial.flush();
}

void setup()
{
	// #TODO: Setup LED pins.
	// #TODO: Consider having a pin driver class of some kind
	pinMode(LED_PIN_RED, OUTPUT);
	pinMode(LED_PIN_GRN, OUTPUT);
	pinMode(LED_PIN_BLU, OUTPUT);
	// #TODO: default LED pin. Used for other stuff. Remove
	pinMode(13, OUTPUT); 

	pinMode(ENABLE_PIN_5V, OUTPUT);


	//==================== Disable Watchdog ====================
	// May be unnecessary but watchdog is not used so disabling it may help with jitter issues.
	WDOG_UNLOCK = WDOG_UNLOCK_SEQ1; // Watchdog Unlock Sequence
	WDOG_UNLOCK = WDOG_UNLOCK_SEQ2;
	WDOG_TOVALH = 0xFFFF;
	WDOG_TOVALL = 0xFFFF;
	WDOG_STCTRLH = 0x01D2; //0x4102;

	//==================== Lower Systick Priority ====================
	// Lower Systick Priority should help with any jitter. We are not concerned with accuracy of delay function
	SCB_SHPR3 = 0x20200000; // Systick = priority 32 (defaults to zero which is highest priority)
	
	//==================== Establish Serial Connection ====================
	Serial.begin(2000000);
	while (!Serial)
	{
	};
	delay(250);

	//==================== Setup radar ====================
	// Explicitely stop radar to put it in known state.
	LLRISE_Radar.stop();

    // Start CPU Cycle Counter
	global_vars::enable_cpu_cycle_counter();

	//==================== Setup radar ====================
	myPacketSerial.setStream(&Serial);
	myPacketSerial.setPacketHandler(&on_packet_received);
	// Register the send function with the msg handler
	msg_set_send_function(&send_function);


}

void loop()
{
	char msg[100] = {0};
	int s;
	elapsedMillis time_stamp;
	elapsedMillis heartbeat;

    // Set the LED colors to indicate the radar has never communicated
    digitalWrite(LED_PIN_RED, LOW);
    digitalWrite(LED_PIN_GRN, HIGH);
    digitalWrite(LED_PIN_BLU, HIGH);

	while (true)
	{
		// Should this be a message type?
		switch (radar_state)
		{
		case RSTATE_COMMAND:
			// Send alive messages when in command state
			if (heartbeat >= 2000)
			{
				heartbeat = heartbeat - 2000;
                s = msg_send_heartbeat(time_stamp);
				// s = msg_send_log(LOG_INFO, 1, "ALIVE");
				// #TODO: actually check status code and do something
			}
			break;
		case RSTATE_STREAMING:
			if (global_vars::pulse_number > global_vars::prev_pulse_number)
			{
                if (global_vars::pulse_number - global_vars::prev_pulse_number > 1)
                {
                    sprintf(msg,"Teensy pulse sequence error. Dropped %lu pulses before %lu",
                        global_vars::pulse_number - global_vars::prev_pulse_number,
                        global_vars::pulse_number);
                    msg_send_log(LOG_ERROR, 1, msg);
                }

				global_vars::prev_pulse_number = global_vars::pulse_number;
				// Fill in header
				pulse_header.hdr_size = sizeof(msg_pulse_header_t);
				pulse_header.data_size = LLRISE_Radar.adc_buffer.length/2; // #TODO: TBD: Or is it adc_buffer.size/2? The /2 is to allow for the ping/pong behavior
				pulse_header.pulse_number = global_vars::prev_pulse_number;
				pulse_header.pulse_cycle_count = global_vars::pulse_cycle_count;
				pulse_header.status.transmit_trigger = global_vars::transmit_trigger;
				pulse_header.gain = LLRISE_Radar.rx_gain;
				pulse_header.pulse_length_ms = LLRISE_Radar.pulse_length_ms;
				pulse_header.freq_start = LLRISE_Radar.freq_start;
				pulse_header.freq_stop = LLRISE_Radar.freq_stop;
				pulse_header.freq_return = LLRISE_Radar.freq_return;

				// This is operation is so that we point to the correct half of the data buffer.
				// #TODO: Ensure I am pointing to correct half each time
				uint16_t adc_buffer_pulse_offset = (1 - (global_vars::prev_pulse_number % 2)) * (LLRISE_Radar.adc_buffer.length / 2);
                //delayMicroseconds(25000);
				s = msg_send_pulse(&pulse_header, const_cast<const uint16_t *>(LLRISE_Radar.adc_buffer.data + adc_buffer_pulse_offset), LLRISE_Radar.adc_buffer.length / 2);
                //s=0;
				// #TODO: actually check status code and do something
				if (s)
				{
					msg_send_log(LOG_ERROR, 1, "PROBLEM SENDING PULSE, MSG_MAX_BUFFER too small?");
				}
			}
			// Keep sending hearbeats
			if (heartbeat >= 2000)
			{
				heartbeat = heartbeat - 2000;
                s = msg_send_heartbeat(time_stamp);
				// s = msg_send_log(LOG_INFO, 1, "ALIVE");
				// #TODO: actually check status code and do something
			}

			break;

		default:
			s = msg_send_log(LOG_ERROR, 1, "UNEXPECTED STATE, STOPPING");
			radar_state = RSTATE_COMMAND;
		}

		// Look for incomming messages and dispatch
		myPacketSerial.update();

		// Check for a receive buffer overflow (optional).
		if (myPacketSerial.overflow())
		{
			s = msg_send_log(LOG_ERROR, 1, "OVERFLOW");
			// Send an alert via a pin (e.g. make an overflow LED) or return a
			// user-defined packet to the sender.
			//
			// Ultimately you may need to just increase your recieve buffer via the
			// template parameters (see the README.md).
		}
	}
}
