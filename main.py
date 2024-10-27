import time
import machine
import rp2
import network
import secrets
import urequests as requests
print('boot')
## Pin Setup / LED
shower_led = machine.Pin(14, mode=machine.Pin.OUT, pull=None, value=0)
wled = machine.Pin("LED", machine.Pin.OUT) #Pico W LED
heater = machine.Pin(18, mode=machine.Pin.OPEN_DRAIN, pull=None, value=1)
fill = machine.Pin(19, mode=machine.Pin.OPEN_DRAIN, pull=None, value=1)
drain = machine.Pin(20, mode=machine.Pin.OPEN_DRAIN, pull=None, value=1)
extra =  machine.Pin(21, mode=machine.Pin.OPEN_DRAIN, pull=None, value=1)
# Turn off internal pull up on jmp pin
sense = machine.Pin(12, mode=machine.Pin.IN, pull=None)
adc = machine.ADC(machine.Pin(26))     # create ADC object on ADC pin
# Let us know were booting
wled.value(1)
shower_led.value(1)
# WLAN Setup
wlan = network.WLAN(network.STA_IF)
# Timers
statetimer = machine.Timer()
currentLogTimer = machine.Timer()
# Globals
state = 'off' # off / filling / heat / cool / flush / quickdrain
flush_count = 4 #Zero means flush done
baseline = 350_000 # Inital state for baseline IIR Value for touch detection (350_000, connected, 4_000 bare PCB)
touch_threshold = 4_000_000 #Threshold above baseline for a touch (4_000_000, connected, 4_000 bare PCB)
time_between_touches_ms = 1000 #Debounce time for a touch
current_raw = 0 #Inital State for current IIR
DATA_IIR_CONST = 1000  # Filtering constant for the IIR filters
time_between_status_ms = 1000 * 60 * 240 # How often to log status
max = 0
# Logging Function
def logWifi(logmessage):
    print('Log: ' + logmessage)
    if not wlan.isconnected():
        print(f"Reconnecting to WiFi Network Name: {secrets.ssid}")
        try:
            wlan.active(True)
            wlan.connect(secrets.ssid, secrets.password)
        except OSError as error:
            print(f'Connect error is {error}')
        except Exception as e:
            print(f"An unkown connect error occurred: {e}")
            return
        print('Waiting for connection...')
        counter = 0
        while not wlan.isconnected():
            wdt.feed()
            time.sleep(1)
            print(counter, '.', sep='', end='')
            counter += 1
            if counter > 20:
                print('Failed to Connect')
                return
        print('\nIP Address: ', wlan.ifconfig()[0])
    try:
        res = requests.post(secrets.url, data = logmessage)
    except OSError: #Need to catch this or we stop
        print("Log Failed, Post Error")
    except Exception as e:
        print(f"An unkown post error occurred: {e}")
    else:
        if res.text != 'OK':
            print('Unexpected Post Response:', res.text)
    
# Helper functions to make code readable, and to add logging
def logCurrent(callingtimer):
    logWifi(f"C: {round(current_raw)}")

def ledOn():
    wled.value(1) #Turn on board LED
    shower_led.value(1) #Turn on Shower LED

def ledOff():
    wled.value(0) #Turn off LED
    shower_led.value(0) #Turn off Shower LED

def heat_on():
    heater.value(0) #Turn on Heat, Active Low
    currentLogTimer.init(mode=machine.Timer.PERIODIC,period=30_000,callback=logCurrent) 

def heat_off():
    heater.value(1) #Turn off Heat, Active Low
    currentLogTimer.deinit() #No need to log anymore

def fill_open():
    fill.value(0) #Start Filling

def is_fill_off():
    return fill.value()

def fill_closed():
    fill.value(1) #Stop Filling

def drain_open():
    drain.value(0) #Start Draining

def drain_closed():
    drain.value(1) #Stop Draining

def is_drain_open():
    return drain.value()

# State Functions
def goFlush(callingtimer):
    global flush_count, state
    state = 'flush'
    fill_open() #Start Filling
    if is_drain_open(): #We are not draining
         drain_open() #Start Draining
         logWifi(f"Flush Drain Cycle: {flush_count}")
    else:
        drain_closed() #Stop Draining
        flush_count -= 1 # Done with this flush round
        logWifi(f"Flush Fill Cycle: {flush_count}")
    if flush_count > 0: #More flushes to go, recursive
        statetimer.init(mode=machine.Timer.ONE_SHOT,period=300_000,callback=goFlush) # Cycle the Flush 5 mins (300_000)
    else:
        logWifi("Final Long Drain Cycle")
        drain_open() #Start Draining
        fill_closed()   # Stop Filling
        statetimer.init(mode=machine.Timer.ONE_SHOT,period=3_600_000,callback=goOff) # Final Drain Cycle 60 mins (3_600_000)
             
def goHeat(callingtimer):
    global state
    state = 'heat'
    ledOn() #Turn on LED
    fill_open() #Keep Filling
    heat_on() # Start Heat
    drain_closed() # Stop Drain
    statetimer.init(mode=machine.Timer.ONE_SHOT,period=900_000,callback=goCool) # Auto Off Timer 15 mins (900_000)
    logWifi('Heat State')

def goCool(callingtimer):
    global flush_count, state
    state = 'cool'
    ledOff()
    fill_closed()   # Stop Filling
    heat_off() # Stop Heat
    drain_closed() # Stop Drain
    flush_count = 4 #Queue up some flushing
    statetimer.init(mode=machine.Timer.ONE_SHOT,period=1_800_000,callback=goFlush) # Cooling Timer 30 mins (1_800_000)
    logWifi('Cool State')
    
def goFill(callingtimer):
    global state
    state = 'filling'
    ledOn() #Turn on LED
    fill_open() #Start Filling
    heat_off() # Stop Heat
    drain_closed() # Stop Drain
    statetimer.init(mode=machine.Timer.ONE_SHOT,period=20_000,callback=goHeat) # Fill Timer, 20s (20_000)
    logWifi('Fill State')
   
def goOff(callingtimer):
    global state
    state = 'off'
    ledOff() #Turn off LED
    fill_closed()   # Stop Filling
    heat_off() # Stop Heat
    drain_closed() # Stop Drain
    statetimer.deinit()
    logWifi('Off State')

def goQuickDrain(callingtimer):
    global state
    state = 'quickdrain'
    ledOff() #Turn off LED
    fill_closed()   # Stop Filling
    heat_off() # Stop Heat
    drain_open() #Start Draining
    statetimer.init(mode=machine.Timer.ONE_SHOT,period=600_000,callback=goOff) # Final Drain Cycle 10 mins (600_000)
    logWifi('Quick Drain')
    
def printTouchStatus():
    global max, baseline, last_status
    logWifi(f"Base: {round(baseline)} Max:  {round(max - baseline)}")
    max = 0
    last_status = time.ticks_ms()

# Touch Sensor PIO State Machine
@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW, autopull=False, pull_thresh=32, autopush=False, push_thresh=32)
def detectTouch():                                         # type: ignore
    pull(block)                 # Get charge delay val     # type: ignore
    mov(x,osr)                  # Load charge delay val    # type: ignore
    wrap_target()               # Only do the above once   # type: ignore
    mov(y, invert(null))        # Set Y to Large (All Ones)# type: ignore
    set(pins, 1)                # Start Charging           # type: ignore
    label("innerloop")                                     # type: ignore
    jmp(pin, "loopescape")      # If Pin is High, Escape   # type: ignore
    jmp(y_dec, "innerloop")     # Loop and decrement Y     # type: ignore
    label("loopescape")                                    # type: ignore
    mov(isr,y)                  # Move Y to CPU SR         # type: ignore
    set(pins, 0)                # Discharge                # type: ignore
    push(noblock)               # Push Y                   # type: ignore
    mov(y,x)                    # Load charge delay val    # type: ignore
    label("chargeloop")                                    # type: ignore
    jmp(y_dec, "chargeloop")     # If !Zero, X-- and loop  # type: ignore
    wrap()                                                 # type: ignore
# Setup Code
# Create the State Machine, a 1 MegaOhm resistor from set_base to jmp_pin is needed
sm = rp2.StateMachine(0, detectTouch, freq=125_000_000, set_base=machine.Pin(9), jmp_pin=machine.Pin(12))
# Start the State Machine.
sm.active(1)
sm.put(1_250_000, 0)  #This sets Charging Delay and detection rate in SM clock cycles (10 ms)
# Let us know were done booting
# Start the Watchdog
wdt = machine.WDT(timeout=5000)
logWifi("Rebooted: v6 Long Delay, Watchdog")
wled.value(0)
shower_led.value(0)
last_touch = time.ticks_ms() # Limit immediate and back-to-back touch detections (debounce)
last_status = last_touch
while True: #Main loop
    curval = 4_294_967_295 - sm.get() #State Machine counts down from 2^32
    if time.ticks_diff(time.ticks_ms(), last_touch) > time_between_touches_ms: #Not a multi-touch event 
        if curval > baseline + touch_threshold: #We have a touch event
            last_touch = time.ticks_ms() #States are: off / filling / heat / cool / flush
            if state == 'off' or state == 'flush' or state == 'quickdrain':
                goFill(0)
            elif state == 'heat':
                goCool(0)
            elif state == 'filling':
                goQuickDrain(0) # Someone shut us off before full
            elif state == 'cool':
                goHeat(0)
            else:
                goCool(0)
                logWifi("Uh Oh, we fell though the state if")
            printTouchStatus()
            logWifi(f"Press at: {round(curval - baseline)}")
        else: #Only start taking button stats after the touch event has passed
            baseline = curval / DATA_IIR_CONST + baseline * (DATA_IIR_CONST - 1) / DATA_IIR_CONST #Take Baseline Stats
            if curval > max: # Take some stats for logging
                max = curval
    # Do these things always
    current_raw  = adc.read_u16() / DATA_IIR_CONST + current_raw * (DATA_IIR_CONST - 1) / DATA_IIR_CONST
    #print status on an interval
    if time.ticks_diff(time.ticks_ms(), last_status) > time_between_status_ms:
        printTouchStatus()       
    wdt.feed()
