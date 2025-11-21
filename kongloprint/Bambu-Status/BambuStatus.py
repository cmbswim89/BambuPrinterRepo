import threading
import paho.mqtt.client as mqtt
import Bambu 
from flask import Flask, jsonify

app = Flask(__name__)
bb = Bambu.Bambu()  # make it global so Flask routes can read from it

@app.route("/temps", methods=["GET"])
def get_temps():
    """
    Returns current bed & nozzle temps.
    Example response:
    {
      "status": "ON",
      "bed_temp": 60,
      "nozzle_temp": 215,
      "last_update": 1732041234.123
    }
    """
    return jsonify({
        "status": bb.status,
        "bed_temp": bb.bed_temp,
        "nozzle_temp": bb.nozzle_temp,
        "last_update": bb.last_update,
    })


if __name__ == "__main__":
    updBambu = threading.Thread(target=bb.start, name="Bambu")
    updBambu.start()
    app.run(host="0.0.0.0", port=5000, debug=False)