import webview
import json
from pylibftdi import BitBangDevice
import os

relay_on_cmds = [0x42, 0x08, 0x20, 0xe2]
relay_off_cmds = [0xFE, 0xFD, 0xFB, 0xF7]

def relay_on(rel_num, bbobj):
    bbobj.port |= relay_on_cmds[rel_num - 1]
    print(f"Relay {rel_num} ON Command {relay_on_cmds[rel_num - 1]:#04x}: port = {bbobj.port:#04x}")

def relay_off(rel_num, bbobj):
    bbobj.port &= relay_off_cmds[rel_num - 1]
    print(f"Relay {rel_num} OFF Command {relay_off_cmds[rel_num - 1]:#04x}: port = {bbobj.port:#04x}")

def relay_off_all(bbobj):
    bbobj.port = 0x00
    print(f"All Relays OFF: port = {bbobj.port:#04x}")

class RelayApi:
    def __init__(self):
        try:
            self.bb = BitBangDevice('AQ02JEVF')
            self.bb.direction = 0xFF
            print("BitBang device initialized.")
        except Exception as e:
            print("Error initializing BitBang device: ", e)
            self.bb = None

        self.led_states = [False] * 4

    def control_relay(self, relay_num, action):
        if self.bb:
            if action == "on":
                relay_on(relay_num, self.bb)
                self.led_states[relay_num - 1] = True
            elif action == "off":
                relay_off(relay_num, self.bb)
                self.led_states[relay_num - 1] = False
            elif action == "off_all":
                relay_off_all(self.bb)
                self.led_states = [False] * 4
            return json.dumps(self.led_states)
        else:
            return json.dumps({"error": "BitBang device not initialized"})

    def get_led_states(self):
        return json.dumps(self.led_states)

api = RelayApi()

def start_app():
    base_dir = os.path.abspath(os.path.dirname(__file__))
    html_path = os.path.join(base_dir, "relay_control.html")
    window = webview.create_window("Relay Control", f"file://{html_path}", js_api=api)
    webview.start()

if __name__ == "__main__":
    start_app()