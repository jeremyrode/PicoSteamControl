﻿# PicoSteamControl
Pico control for a Leisure Steam One Touch LS series.

The factory control PCB was misbehaving, so I thought it would be a good challenge to replace it with a Raspberry Pi Pico.

This is my first MicroPython project.  I was originally implementing this system in C, but when I started down the path to connect to WiFi, I decided to try out MicroPython and I was blown away by the power and rapid development/test cycles.

I mostly think this project might be interesting to people because of a few new ideas that I have not seen documented well in the wild:

# New ideas:

This project served as a testbed for 3 new ideas that I wanted to try:
- Status Logging and Timestamping though WiFi
- Capacitive Touch Sensing via PIO State Machine
- New Ideal Diode Peak Detector CT Interface

## Status Logging and Timestamping though WiFi

A major reason I was implementing much of my IoT work with boards that run full Linux (usually a Raspberry Pi Zero W) is logging and timestamping functionality.  Many of these IoT systems are very difficult to debug without a persistent log that is timestamped.  Both storing and retrieving persistent logs (to some sort of nonvolatile memory) and getting real time (UTC) on a microcontroller are difficult.

Here, this is solved by sending my log messages out to Raspberry Pi with NTP running via the network and urequests libraries:

```python
def logWifi(logmessage):
    print('Log: ' + logmessage)
    res = requests.post(secrets.url, data = logmessage)
```

Remarkably simple and effective, this server could easily serve many Pico W boards. See main.py for the full code with WiFi reconnection, and error handling.  [The secrets.url uses a config file to not checkin WiFi passwords or local IPs to a public Git.]( https://www.coderdojotc.org/micropython/wireless/02-connecting-to-wifi/ "MicroPython WiFi Info")

The logWifi() function in main.py takes the log request and sends it to a http server (SteamLogger.js) running in Node.js that timestamps it and writes it to a file.

```node
const server = http.createServer((req, res) => {
  if (req.method === 'POST') {
    let data = '';
    req.on('data', chunk => {
      data += chunk.toString();
    });
    req.on('end', () => {
      let curDate = new Date();
      let dateStr = curDate.toString();
      message = dateStr.slice(0,dateStr.length-33) + ' ' + data; //Prepend Time to message
      console.log(message);
      logfile.write(message + '\n')
      res.end('OK');
    });
  }
});
```

## Capacitive Touch Sensing via PIO State Machine

After discovering that the control button on the LS1 one touch is a capacitive membrane switch, I investigated specific ICs that do capacitive touch sensing, but then this is a perfect task for a PIO state machine. It is very reliable and has very good dynamic range: Around 250K cycles for the untouched state, and with a strong push increasing this to 6-8M cycles.  A logging function serves to measure this. 

Here is a very unoptimized PIO state machine that charges a capacitive touch sensor via an output pin and a resistor, then cycle counts the time to discharge.
[I’ve broke this out into its own repository]( https://github.com/jeremyrode/RaspPiPicoTouchSensor "RaspPiPicoTouchSensor Repo"), and I might try to optimize it eventually.

```
pull(block)                 # Get charge delay val     
mov(x,osr)                  # Load charge delay val    
wrap_target()               # Only do the above once   
mov(y, invert(null))        # Set Y to Large (All Ones)
set(pins, 1)                # Start Charging           
label("innerloop")                                     
jmp(pin, "loopescape")      # If Pin is High, Escape   
jmp(y_dec, "innerloop")     # Loop and decrement Y     
label("loopescape")                                    
mov(isr,y)                  # Move Y to CPU SR         
set(pins, 0)                # Discharge                
push(noblock)               # Push Y                   
mov(y,x)                    # Load charge delay val    
label("chargeloop")                                    
jmp(y_dec, "chargeloop")     # If !Zero, X-- and loop  
wrap()                                                 
```

### How it Works

This code uses a PIO state machine to repeatedly charge and discharge the touch sensor detecting a change in capacitance via the time-to-charge.  The touch sensor is charged via an output pin connected through 1-megaohm resistor (R1 on schematic) giving a RC time delay that can be measured by an input pin connected directly to the touch sensor.

The PIO state machine starts by getting the discharge time via an initial value written to the PIO state machine, that is moved to scratch register X.  This is necessary, as the PIO SET instruction is limited to 31, which is nowhere near the necessary value* (1,250,000).  The state machine then sets Y to all ones, sets the charge pin to "1", and counts down (via the "innterloop") until the jump pin goes low via RC discharge.  The jump escapes the loop (via jumping to "loopescape").  The Y value is outputted by moving Y to the input shift register (ISR) and pushing to the FIFO.  The push is nonblocking, to keep the detections going, but the FIFO will go stale if it's not read periodically.  To prepare for the next detection the charge pin is set to discharge "0", and then the discharge delay is performed, but copying the charge delay value stored in scratch register X, to Y, then looping via “chargeloop”.  At this point, we return to wrap_target(), which repeats everything (except loading the charge delay to scratch register X).

The user space code calibrates the baseline charge time with an IIR filter, and if a difference (here 500 cycles or 4 us) in the charge time is detected a touch even is registered.  The touch detection is debounced via a time delay gate, as a single human touch event can trigger multiple detections.

*Yes, I’m aware that large values in scratch registers can be set via the bit-reverse function of the MOV instruction, but these are a bit too large, as the smallest value is a SET of 16 (0b10000), bit reversed is 2^27, which is a delay of 1 second (2^27 / 125 MHz).

```python
baseline = 350_000 # Inital state for baseline IIR Value for touch detection (350_000, connected, 4_000 bare PCB)
touch_threshold = 4_000_000 #Threshold above baseline for a touch (4_000_000, connected, 4_000 bare PCB)
time_between_touches_ms = 1000 #Debounce time for a touch
DATA_IIR_CONST = 1000  # Filtering constant for the IIR filter
sm.put(1_250_000, 0)  #This sets Charging Delay and detection rate in SM clock cycles (10 ms)
while True:
    curval = 4_294_967_295 - sm.get() #State Machine counts down from 2^32
    if time.ticks_diff(time.ticks_ms(), last_touch) > time_between_touches_ms: #Not a multi-touch event
        if curval > baseline + touch_threshold: #We have a touch event
            last_touch = time.ticks_ms()
            print('Touch')
        else: #Only start taking button stats after the touch event has passed
            baseline = curval / DATA_IIR_CONST + baseline * (DATA_IIR_CONST - 1) / DATA_IIR_CONST #Take Baseline Stats
```

Here the python sets the discharge delay via sm.put().  An infinite loop pulls the discharge value and changes it into delay counts by subtracting from 2^32.  Here the detection is debounced via a timestamp and compared to a threshold value above a baseline non-touched value.  This code adapts the baseline capacitance via an infinite first-order impulse response (IIR) filter that adapts to any slow varying baseline capacitance.

## New Ideal Diode Peak Detector CT Interface

Interfacing to Current Transformers (CT) is a real pain; either one needs to bias the signal in the middle of the ADC range, and sample fast enough to capture the 60 Hz sine wave, or a diode peak detector can be used, but that makes the circuit non-linear when the signal from the CT is below the diode threshold voltage.

Here, I’ve tried to make an ideal diode based peak detector (with gain) out of a non-inverting op amp driving though a diode.  Ideally this should both make the ADC readout much simpler and more accurate, as the output is DC, and the time constant can be set via a capacitor, and make the CT more accurate as the burden resistor can be sized optimally for the CT, with the op-amp gain used to optimally fill the ADC range from the typically lower voltage from a CT in the linear regime.

# Schematic:

The factory control board was replaced with a quad relay board from amazon, wired directly to a RJ45 (J2) breakout board from Spark Fun.  This relay board replaces the factory control board, and is wired into the 220V fill solenoid, drain valve, and the 50A heater contactor.  The factory touchpad with LED is wired to J1.

Note that this is the schematic that I built on a proto board with parts on hand.  I would recommend a proper ground and changing J1 to a RJ12 if I build a PCB (which I have done in the PCB directory).

![Schematic](./PCB/protoschematic.png)

# Future Ideas
- Higher touch threshold for on than off
- Low/High via separate contactors for each heating element

