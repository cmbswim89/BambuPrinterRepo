import ssl
import json
import time
import paho.mqtt.client as mqtt
import requests
import logging
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("bambu")
logger.setLevel(logging.INFO)

handler = RotatingFileHandler(
    "bambu.log", maxBytes=5_000_000, backupCount=3
)
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)

# Also print to console
console = logging.StreamHandler()
console.setFormatter(formatter)
logger.addHandler(console)

class Bambu:
    PRINTER_IP = "192.168.1.115"
    SERIAL     = "01P00C4C1200687"
    ACCESS     = "15315482"  # LAN access code from printer
    Door_Open_Temp = 45


    def __init__(self):
        self.client      = None
        self.status      = "UNKNOWN"
        self.remain      = None
        self.bed_temp    = None
        self.nozzle_temp = None
        self.last_update = None
        self.topic       = f"device/{self.SERIAL}/report"
        self.doorOpen = self.checkDoorState()
        self.ComletedPrint = False
        self.completedPercent = 100
        self.currentLayer = 0
        self.totalLayers = 0

    def start(self):
        self.client = mqtt.Client(
            client_id="test-p1s",
            protocol=mqtt.MQTTv311,
            clean_session=True,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )

        # username/password
        self.client.username_pw_set("bblp", self.ACCESS)

        # TLS 1.2
        self.client.tls_set(
            cert_reqs=ssl.CERT_NONE,
            tls_version=ssl.PROTOCOL_TLSv1_2,
        )
        self.client.tls_insecure_set(True)

        # Callbacks
        self.client.on_connect    = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message    = self.on_message

        while True:
            try:
                logger.info(f"[MQTT] Connecting to {self.PRINTER_IP}:8883 ...")
                self.client.connect(self.PRINTER_IP, 8883, keepalive=60)
                self.client.loop_start()
                break
            except Exception as ex:
                logger.error(f"[MQTT] Connect failed: {ex}")
                self.status = "OFF"
                time.sleep(10)

    def checkDoorState(self):
        try:
            # use http or https depending on what your service expects
            url = "http://bambudooropener.com/door-motor/state"
            payload = requests.get(url, timeout=5).content
            resp = json.loads(payload)
            logger.info(f"[DOOR] State Called {url}, status: {resp['open']}")
            self.doorOpen = resp["open"]
            # self.doorOpen = True
            return resp
        except requests.RequestException as e:
            logger.error("[DOOR] Error calling door opener: %s", e)
            return None
        
    def on_connect(self, client, userdata, flags, reason_code, properties):
        logger.info("[MQTT] on_connect reason: %s", reason_code)
        try:
            logger.info("[MQTT] reason code value: %s", int(reason_code))
        except Exception:
            pass

        if reason_code == 0:
            logger.info("[MQTT] Connected OK, subscribing to %s", self.topic)
            client.subscribe(self.topic)
            self.status = "ON"
        else:
            logger.info("[MQTT] Connect failed: %s", reason_code)
            self.status = "OFF"

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        logger.info("[MQTT] on_disconnect reason: %s", reason_code)
        if reason_code != 0:
            logger.info("[MQTT] Lost connection, attempting reconnect...")
            self.reconnect(client)

    def reconnect(self, client):
        reconnect_delay = 1
        while True:
            try:
                client.reconnect()
                logger.info("[MQTT] Bambu Labs reconnected successfully")
                break
            except Exception as e:
                logger.error(f"[MQTT] Reconnect failed: {e}")
                self.status = "OFF"
                time.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)

    def on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode("utf-8")
            resp = json.loads(payload)
            # logger.info(f"Payload: {resp}")
        except Exception as e:
            logger.error(f"[MQTT] Failed to parse message: {e}")
            logger.error(f"[MQTT] Raw payload: {msg.payload}")
            return

        #print("[MQTT] Message on", msg.topic, ":", resp)

        # Store whatever we care about from the print status
        if "print" in resp:
            p = resp["print"]

            # remaining time, percent, etc., if you still want them
            if "mc_remaining_time" in p:
                self.remainPercent = p["mc_remaining_time"]
            if "total_layer_num" in p:
                self.totalLayers = p["total_layer_num"]
            if "layer_num" in p:
                self.currentLayer = p["layer_num"]
                # logger.log(f"Layer {self.currentLayer}//{self.totalLayers}")
                # logger.log(f"Layer Completion {(self.currentLayer/self.totalLayers) * 100}%")
            if "mc_percent" in p:
                self.completedPercent = p["mc_percent"]
                # logger.info(f"Completed {self.completedPercent}%")
                if self.completedPercent == 100 and self.ComletedPrint == False:
                    self.completedPrint()
                elif self.completedPercent < 100:
                    self.ComletedPrint = False
            # NEW: track bed & nozzle temps
            if "nozzle_temper" in p:
                self.nozzle_temp = p["nozzle_temper"]
            if "bed_temper" in p:
                self.bed_temp = p["bed_temper"]
                if self.bed_temp < Bambu.Door_Open_Temp and self.doorOpen == False:
                    self.trigger_door_open()
                if self.bed_temp > Bambu.Door_Open_Temp and self.doorOpen:
                    self.trigger_door_close()

            self.last_update = time.time()

    def completedPrint(self):
        logger.info(f"Completed Print!")
        self.ComletedPrint = True
        # self.trigger_door_open()

    def trigger_door_open(self):
        try:
            # use http or https depending on what your service expects
            url = "http://bambudooropener.com/door-motor/open"
            resp = requests.get(url, timeout=5)
            logger.info(f"[DOOR] Open Called {url}, status: {resp.status_code}")
            self.doorOpen = True
            return resp
        except requests.RequestException as e:
            logger.error("[DOOR] Error calling door opener: %s", e)
            return None
    
    def trigger_door_close(self):
        try:
            # use http or https depending on what your service expects
            url = "http://bambudooropener.com/door-motor/close"
            resp = requests.get(url, timeout=5)
            logger.info(f"[DOOR] Close Called {url}, status: {resp.status_code}")
            self.doorOpen = False
            return resp
        except requests.RequestException as e:
            logger.error("[DOOR] Error calling door opener: %s", e)
            return None
