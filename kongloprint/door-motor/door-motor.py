# door-motor.py
import os, time, pigpio
from flask import Flask, jsonify

app = Flask(__name__)

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------
HOST = os.getenv("PIGPIO_ADDR")   # "pigpio" when sidecar
PORT = int(os.getenv("PIGPIO_PORT", "8888"))

SERVO_PIN      = 18              # Servo control pin (BCM)
OPEN_POSITION  = 500             # µs pulse for OPEN
CLOSE_POSITION = 2000            # µs pulse for CLOSE

BUTTON_PIN     = 23              # RobotGeek button (BCM 23)
LIMIT_PIN      = 25              # Limit switch (BCM 25) - confirm wiring!

BUTTON_GLITCH_US = 10000         # 10 ms glitch filter for button
LIMIT_GLITCH_US  = 10000         # 10 ms glitch filter for limit switch

DEBOUNCE_MS    = 300             # software debounce window
MOVE_TIME_MS   = 900             # how long a move takes (guard window)

door_is_open   = False
_last_press_ms = 0
_busy_until_ms = 0

_pi = None

# -------------------------------------------------------------------
# pigpio helpers
# -------------------------------------------------------------------
def get_pi(retries=10, delay=0.3):
    global _pi
    if _pi and _pi.connected:
        return _pi
    for _ in range(retries):
        _pi = pigpio.pi(host=HOST, port=PORT)
        if _pi.connected:
            return _pi
        time.sleep(delay)
    return None

def _now_ms():
    return int(time.time() * 1000)

def move_servo(position):
    """Move the servo to the given pulse width position (µs)."""
    pi = get_pi()
    if not pi:
        return "pigpio daemon not running!"
    pi.set_servo_pulsewidth(SERVO_PIN, position)
    time.sleep(0.8)
    pi.set_servo_pulsewidth(SERVO_PIN, 0)  # Stop signal
    print("Door Action:", position)
    return f"Servo moved to {position} µs"

def _toggle_handler(gpio, level, tick):
    """
    Shared callback for both the RobotGeek button and the limit switch.
    """
    global door_is_open, _last_press_ms, _busy_until_ms

    now = _now_ms()

    # Ignore while moving
    if now < _busy_until_ms:
        return

    # Software debounce
    if now - _last_press_ms < DEBOUNCE_MS:
        return
    _last_press_ms = now

    print(f"Toggle handler fired from GPIO {gpio}, level {level}")

    try:
        if door_is_open:
            _ = move_servo(CLOSE_POSITION)
            door_is_open = False
        else:
            _ = move_servo(OPEN_POSITION)
            door_is_open = True
    finally:
        _busy_until_ms = _now_ms() + MOVE_TIME_MS

def setup_button():
    """
    RobotGeek button:
      - Red  -> 3.3V
      - Black -> GND
      - White -> GPIO23 (BUTTON_PIN)
    It drives the signal HIGH when pressed.
    """
    pi = get_pi()
    if not pi:
        print("WARN: pigpio not connected; button disabled")
        return None

    pi.set_mode(BUTTON_PIN, pigpio.INPUT)
    pi.set_pull_up_down(BUTTON_PIN, pigpio.PUD_DOWN)  # idle 0, press 1
    pi.set_glitch_filter(BUTTON_PIN, BUTTON_GLITCH_US)

    cb = pi.callback(BUTTON_PIN, pigpio.RISING_EDGE, _toggle_handler)
    print("Button callback registered on GPIO", BUTTON_PIN)
    return cb

def setup_limit_switch():
    """
    Limit switch wired:
      - COM -> GND
      - NO  -> GPIO25 (LIMIT_PIN)
    With PUD_UP: idle HIGH (1), hit pulls to LOW (0) -> FALLING_EDGE.
    """
    pi = get_pi()
    if not pi:
        print("WARN: pigpio not connected; limit switch disabled")
        return None

    pi.set_mode(LIMIT_PIN, pigpio.INPUT)
    pi.set_pull_up_down(LIMIT_PIN, pigpio.PUD_UP)
    pi.set_glitch_filter(LIMIT_PIN, LIMIT_GLITCH_US)

    cb = pi.callback(LIMIT_PIN, pigpio.FALLING_EDGE, _toggle_handler)
    print("Limit switch callback registered on GPIO", LIMIT_PIN)
    return cb

# -------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------
@app.route("/diag", methods=["GET"])
def diag():
    pi = get_pi(retries=1)
    return jsonify(daemon_connected=bool(pi and pi.connected))

@app.route("/move/<int:pos>", methods=["GET"])
def move_custom(pos):
    pi = get_pi()
    if not pi:
        return ("pigpio not connected", 500)
    # Clamp to safe servo range (500–2500 microseconds)
    pos = max(500, min(2500, pos))
    pi.set_servo_pulsewidth(SERVO_PIN, pos)
    time.sleep(0.8)
    pi.set_servo_pulsewidth(SERVO_PIN, 0)
    return f"Servo moved to {pos} µs"

@app.route("/state")
def state():
    global door_is_open
    return {"open": door_is_open}

@app.route("/pins")
def pins():
    pi = get_pi()
    if not pi:
        return {"error": "no pigpio"}
    return {
        "button": int(pi.read(BUTTON_PIN)),
        "limit": int(pi.read(LIMIT_PIN)),
        "open": door_is_open,
    }

@app.route("/scan")
def scan():
    """
    Helper to see which pins change when you press things.
    """
    pi = get_pi()
    if not pi:
        return {"error": "no pigpio"}
    pins = [17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]
    return {str(p): int(pi.read(p)) for p in pins}

@app.route("/open")
def open_door():
    global door_is_open
    pi = get_pi()
    if not pi:
        return ("pigpio not connected", 500)
    move_servo(OPEN_POSITION)
    door_is_open = True
    # pi.set_servo_pulsewidth(SERVO_PIN, OPEN_POSITION)
    # time.sleep(0.8)
    # pi.set_servo_pulsewidth(SERVO_PIN, 0)
    return "ok"

@app.route("/close")
def close_door():
    global door_is_open
    pi = get_pi()
    if not pi:
        return ("pigpio not connected", 500)
    move_servo(CLOSE_POSITION)
    # pi.set_servo_pulsewidth(SERVO_PIN, CLOSE_POSITION)
    # time.sleep(0.8)
    # pi.set_servo_pulsewidth(SERVO_PIN, 0)
    door_is_open = False
    return "ok"

@app.route("/setState/<string:state>")
def setDoorState(state):
    global door_is_open
    door_is_open = state == "Open"
    return "ok"

@app.route("/", methods=["GET"])
def index():
    htmlFile = open("doorMotor.html",'r',encoding='utf-8')
    sc = htmlFile.read()
    return sc

# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------
if __name__ == "__main__":
    print("Starting door motor API...")
    _button_cb = setup_button()
    _limit_cb  = setup_limit_switch()
    app.run(host="0.0.0.0", port=3000)   # must bind to 0.0.0.0
