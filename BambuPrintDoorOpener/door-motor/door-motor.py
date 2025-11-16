# door-motor.py
import os, time, pigpio
from flask import Flask, jsonify
app = Flask(__name__)

HOST = os.getenv("PIGPIO_ADDR")   # "pigpio" when sidecar
PORT = int(os.getenv("PIGPIO_PORT", "8888"))

SERVO_PIN = 18
OPEN_POSITION = 500 #500
CLOSE_POSITION = 2000 #2100
BUTTON_PIN   = 23            # BCM 23 (physical pin 16)
DEBOUNCE_MS  = 300           # software debounce window
GLITCH_US    = 50000         # 50 ms hardware (pigpio) glitch filter
MOVE_TIME_MS = 900           # how long a move takes (guard window)

door_is_open   = False
_last_press_ms = 0
_busy_until_ms = 0

_pi = None
def get_pi(retries=10, delay=0.3):
    global _pi
    if _pi and _pi.connected: return _pi
    for _ in range(retries):
        _pi = pigpio.pi(host=HOST, port=PORT)
        if _pi.connected: return _pi
        time.sleep(delay)
    return None

def _now_ms():
    import time
    return int(time.time() * 1000)

def _button_handler(gpio, level, tick):
    """
    Called on configured edge. We:
    - ignore if a move is in progress (_busy_until_ms)
    - apply software debounce on top of pigpio's glitch filter
    - toggle exactly once per valid press
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

    # Perform the move and set the busy window
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
    Configure BUTTON_PIN as input with pull and filters, then register a single-edge callback.
    Use RISING edge if you're powering the RobotGeek module (red→3.3V) and using PUD_DOWN.
    Use FALLING edge if you rewire as bare NO-to-GND with PUD_UP.
    """
    pi = get_pi()
    if not pi:
        print("WARN: pigpio not connected; button disabled")
        return None

    # RobotGeek module powered via 3.3V: signal goes HIGH when pressed.
    pi.set_mode(BUTTON_PIN, pigpio.INPUT)
    pi.set_pull_up_down(BUTTON_PIN, pigpio.PUD_DOWN)

    # Hardware glitch filter (debounces at the daemon level)
    pi.set_glitch_filter(BUTTON_PIN, GLITCH_US)
    # Optional: additional noise filter; uncomment if you still see chatter
    # pi.set_noise_filter(BUTTON_PIN, steady=5000, active=5000)

    # Trigger on press (HIGH transition)
    cb = pi.callback(BUTTON_PIN, pigpio.RISING_EDGE, _button_handler)
    return cb

def move_servo(position):
    """Move the servo to the given pulse width position (µs)."""
    pi = get_pi()
    if not pi:
        return "pigpio daemon not running!"
    pi.set_servo_pulsewidth(SERVO_PIN, position)
    time.sleep(0.8)
    pi.set_servo_pulsewidth(SERVO_PIN, 0)  # Stop signal
    print("Door Action:",position)
    return f"Servo moved to {position} µs"

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
    return {"open": door_is_open}

@app.route("/open")
def open_door():
    pi = get_pi()
    if not pi: return ("pigpio not connected", 500)
    pi.set_servo_pulsewidth(SERVO_PIN, OPEN_POSITION); 
    time.sleep(0.8); 
    pi.set_servo_pulsewidth(SERVO_PIN, 0)
    return "ok"

@app.route("/close")
def close_door():
    pi = get_pi()
    if not pi: return ("pigpio not connected", 500)
    pi.set_servo_pulsewidth(SERVO_PIN, CLOSE_POSITION); time.sleep(0.8); pi.set_servo_pulsewidth(SERVO_PIN, 0)
    return "ok"
# <iframe src="/webcam/?action=stream" width="640" height="480px"></iframe>
@app.route("/", methods=["GET"])
def index():
    return """
    <html>
      <head>
        <title>Door Opener</title>
        <style>
          body { text-align:center; font-family:sans-serif; margin-top:30px; }
          button { font-size:18px; margin:10px; padding:10px 20px; }
          input[type="number"] { font-size:18px; width:220px; text-align:center; }
          #status { margin-top:20px; font-weight:bold; color:#006600; }
        </style>
        <script>
          async function sendCommand(endpoint) {
            const statusEl = document.getElementById('status');
            statusEl.textContent = 'Working...';
            try {
              const res = await fetch(endpoint);
              if (!res.ok) throw new Error('HTTP ' + res.status);
              const text = await res.text();
              statusEl.style.color = '#006600';
              statusEl.textContent = text || 'Done';
            } catch (err) {
              statusEl.style.color = '#cc0000';
              statusEl.textContent = 'Error: ' + err.message;
            }
          }

          function sendCustomMove() {
            const val = document.getElementById('pos').value;
            if (!val) return alert('Enter a number between 500–2500');
            sendCommand('/door-motor/move/' + val);
          }
        </script>
      </head>
      <body>
        <h1>Door Opener</h1>

        <iframe src="/webcam/?action=stream" width="640" height="480" style="border:1px solid #ccc; border-radius:8px;"></iframe>

        <div>
          <button onclick="sendCommand('/door-motor/open')">Open</button>
          <button onclick="sendCommand('/door-motor/close')">Close</button>
          <button onclick="sendCommand('/door-motor/diag')">Diag</button>
        </div>

        <div style="margin-top:15px;">
          <input id="pos" type="number" min="500" max="2500" placeholder="Close(2000)-Open(500)">
          <button onclick="sendCustomMove()">Move</button>
        </div>

        <div id="status"></div>
      </body>
    </html>
    """

if __name__ == "__main__":
    _button_cb = setup_button()
    app.run(host="0.0.0.0", port=3000)   # must bind to 0.0.0.0
