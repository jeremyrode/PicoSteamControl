# PicoSteamControl
Pico control for a Leisure Steam One Touch LS series.  

The factory control board was replaced with a quad relay board from amazon, wired directly to a RJ45 (J2) breakout board from Spark Fun.  This relay board replaces the factory control board, and is wired into the 220V fill solenoid, drain valve, and the 50A heater contactor.

Factory touchpad with LED is wired to J1.  Yes, I used another RJ45, when the actual plug is a 6P6C RJ12/18/25 style plug.  It works, but not well.

I have a round “One-touch” installed in my shower.  I reverse engineered it without removing it, so these are my best guesses that work.  A quick reverse engineering has the pilot LED with no ballast resistor on Pins 1 (anode) and 2 (cathode).  The capacitive touch front is on pin 4, and the ground is pin 3.  No idea on pins 5 and 6, these might be used for the digital control panel option, which I do not have.
# New ideas:
## Capacitive Touch Sensing via PIO State Machine
A very unoptimized PIO state machine that charges a capacitive touch sensor via an output pin and a resistor, then cycle counts
[I’ve broke this out into its own repository]( https://github.com/jeremyrode/RaspPiPicoTouchSensor "RaspPiPicoTouchSensor Repo"), and I might try to optimize it eventually.
### How it Works
This code uses a PIO state machine to repeatedly charge via an output pin and 1 Mega Ohm resistor and detect a change in capacitance on the input pin.  The charge time is set by an initial value written in scratch register X, as the PIO SET instruction is limited to 31.  The state machine then sets Y to all ones, sets the charge pin to "1", and counts down until the input (jump pin) goes low.  The value is outputted, the charge pin is set to discharge "0", and then the discharge delay is performed.

The user space code calibrates the baseline charge time with an IIR filter, and if a difference (here 500 cycles or 4 us) in the charge time is detected a touch even is registered.  The touch detection is debounced via a time delay gate, as a single human touch event can trigger multiple detections.
## New Ideal Diode Peak Detector CT Interface
Interfacing to Current Transformers (CT) is a real pain; either one needs to bias the signal in the middle of the ADC range, and sample fast enough to capture the 60 Hz sine wave, or a diode peak detector can be used, but that makes the circuit non-linear when the signal from the CT is below the diode threshold voltage.

Here, I’ve tried to make an ideal diode based peak detector (with gain) out of a non-inverting op amp driving though a diode.  Ideally this should make the ADC readout much simpler and more accurate, as the output is DC, and the time constant can be set via a capacitor. 
# Schematic:
Note that this is the schematic that I built on a proto board with parts on hand.  I would recommend a proper ground and changing J1 to a RJ12 if I actually build a PCB (which I might do).
![Schematic](./PCB/protoschematic.png)

# Future Ideas
- Higher touch threshold for on than off
- Low/High via separate contactors for each heating element



