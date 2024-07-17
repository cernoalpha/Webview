import os
import json
import asyncio
import websockets
import webview
from threading import Thread, Lock
import base64
import webbrowser
import PySpin
import numpy as np
from PIL import Image

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as ReportLabImage
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import io

from Deviation import process_captured_images

# imported Code 
import threading
from pylibftdi import BitBangDevice
import time
import sqlite3
from datetime import datetime
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

def create_table():
    conn = sqlite3.connect('test_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS test_data (
        serial_number TEXT PRIMARY KEY,
        project_name TEXT,
        part_number TEXT,
        part_name TEXT,
        issue_number TEXT,
        work_order_number INTEGER,
        date_of_testing TEXT,
        captured_images TEXT,
        pdf_url TEXT
    )''')
    conn.commit()
    conn.close()

create_table()

# Finish


class Api:
    def __init__(self):
        self.live_feed_on = False
        self.websocket_clients = set()
        self.lock = Lock()
        self.form_data = {}
        self.captured_images = []
        
        try:
            self.system = PySpin.System.GetInstance()
            self.cam_list = self.system.GetCameras()
            self.cam = None
            if self.cam_list.GetSize() > 0:
                self.cam = self.cam_list.GetByIndex(0)
                self.cam.Init()
            else:
                print("Error: No camera detected.")
        except PySpin.SpinnakerException as e:
            print(f"Error initializing camera: {e}")
            self.cam = None

                 #Extra Code
        self.start_monitoring()
        self.camera_connected = False
        self.relay_connected = False

        try:
            self.bb = BitBangDevice('AQ02JEVF')
            self.bb.direction = 0xFF
            print("BitBang device initialized.")
        except Exception as e:
            print("Error initializing BitBang device: ", e)
            self.bb = None

        self.led_states = [False] * 4

         ## In Between

     #Extra Code

    def start_monitoring(self):
        threading.Thread(target=self.monitor_camera, daemon=True).start()
        threading.Thread(target=self.monitor_relay, daemon=True).start()

    def monitor_camera(self):
        while True:
            try:
                self.system = PySpin.System.GetInstance()
                self.cam_list = self.system.GetCameras()
                self.cam = None
                if self.cam_list.GetSize() > 0:
                    self.cam = self.cam_list.GetByIndex(0)
                    self.cam.Init()
                    self.camera_connected = True
                else:
                    print("Error: No camera detected.")
                    self.camera_connected = False
            except PySpin.SpinnakerException as e:
                print(f"Error initializing camera: {e}")
                self.cam = None
                self.camera_connected = False
            time.sleep(10)


    def monitor_relay(self):
        while True:
            try:
                self.bb = BitBangDevice('AQ02JEVF')
                self.bb.direction = 0xFF
                self.relay_connected = True
            except Exception:
                self.bb = None
                self.relay_connected = False
            time.sleep(5)

    def open_Test_Menu(self):
        window2 = webview.create_window("Testing Menu", url=f'file://{get_html_path("TestPage.html")}',js_api=self)
    def show_result(self):
        window3 = webview.create_window("Results Page", url=f'file://{get_html_path("result.html")}',js_api=self)
    def open_Relay_Menu(self):
        window4 = webview.create_window("Relay Menu", url=f'file://{get_html_path("relay.html")}',js_api=self)

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
    
    def get_status(self):
        status = {
            "camera_connected": self.camera_connected,
            "relay_connected": self.relay_connected
        }
        return json.dumps(status)
    
    def fetch_data(self, serial_number=None, date_of_testing=None):
        conn = sqlite3.connect('test_data.db')
        c = conn.cursor()
        if serial_number and date_of_testing:
            c.execute("SELECT serial_number, project_name, part_number, part_name, issue_number, work_order_number, date_of_testing, pdf_url FROM test_data WHERE serial_number = ? AND date_of_testing = ?", (serial_number, date_of_testing))
        elif serial_number:
            c.execute("SELECT serial_number, project_name, part_number, part_name, issue_number, work_order_number, date_of_testing, pdf_url FROM test_data WHERE serial_number = ?", (serial_number,))
        elif date_of_testing:
            c.execute("SELECT serial_number, project_name, part_number, part_name, issue_number, work_order_number, date_of_testing, pdf_url FROM test_data WHERE date_of_testing = ?", (date_of_testing,))
        else:
            c.execute("SELECT serial_number, project_name, part_number, part_name, issue_number, work_order_number, date_of_testing, pdf_url FROM test_data")
        rows = c.fetchall()
        conn.close()
        return rows
    
    def update_record(self, record):
        conn = sqlite3.connect('test_data.db')
        c = conn.cursor()
        
        update_query = 'UPDATE test_data SET '
        update_values = []
        
        for key, value in record.items():
            if value is not None and key in ['project_name', 'part_number', 'part_name', 'issue_number', 'work_order_number', 'captured_images', 'pdf_url']:
                update_query += f'{key} = ?, '
                update_values.append(value)
        
        update_query = update_query.rstrip(', ')
        
        update_query += ' WHERE serial_number = ?'
        update_values.append(record['serial_number'])
        
        c.execute(update_query, tuple(update_values))
        
        conn.commit()
        conn.close()


    def add_record_from_json(self, json_record):
        record = json.loads(json_record)
        self.add_record({
            'serial_number': record['serialNumber'],
            'project_name': record['projectName'],
            'part_number': record['partNumber'],
            'part_name': record['partName'],
            'issue_number': record['issueNumber'],
            'work_order_number': record['workOrderNumber'],
            'date_of_testing': datetime.now().strftime("%Y-%m-%d"),
            'captured_images': record['captured_images'],
            'pdf_url': record['pdf_url']
        })

    def add_record(self, record):
        conn = sqlite3.connect('test_data.db')
        c = conn.cursor()
        c.execute('''
            INSERT INTO test_data (serial_number, project_name, part_number, part_name, issue_number, work_order_number, date_of_testing, captured_images, pdf_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            record['serial_number'],
            record['project_name'],
            record['part_number'],
            record['part_name'],
            record['issue_number'],
            record['work_order_number'],
            record['date_of_testing'],
            json.dumps(record['captured_images']), 
            record['pdf_url']
        ))
        conn.commit()
        conn.close()

    def delete_record(self, serial_number):
        conn = sqlite3.connect('test_data.db')
        c = conn.cursor()
        c.execute("DELETE FROM test_data WHERE serial_number = ?", (serial_number,))
        conn.commit()
        conn.close()

    def fetch_pdf(self, pdf_path):
        try:
            webbrowser.open_new(pdf_path)
            return True
        except Exception as e:
            return str(e)

    ## In Between

    def toggle_live_feed(self):
        with self.lock:
            self.live_feed_on = not self.live_feed_on
            if self.live_feed_on:
                Thread(target=self.show_frame).start()
            return self.live_feed_on

    def show_frame(self):
        if self.cam is None:
            print("Error: Camera not initialized.")
            return

        self.cam.BeginAcquisition()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while self.live_feed_on:
            image_result = self.cam.GetNextImage()
            if image_result.IsIncomplete():
                print(f"Image incomplete with image status {image_result.GetImageStatus()}")
                continue

            image_data = image_result.GetNDArray()
            image = Image.fromarray(image_data)
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG')
            frame_data = buffer.getvalue()

            loop.run_until_complete(self.broadcast(frame_data))
            image_result.Release()
        self.cam.EndAcquisition()

    async def broadcast(self, frame_data):
        if self.websocket_clients:
            websockets_to_remove = set()
            for ws in self.websocket_clients:
                try:
                    await ws.send(frame_data)
                except websockets.exceptions.ConnectionClosed:
                    websockets_to_remove.add(ws)
            self.websocket_clients -= websockets_to_remove

    def capture_image(self):
        if self.cam is None:
            print("Error: Camera not initialized.")
            return None

        self.cam.BeginAcquisition()
        image_result = self.cam.GetNextImage()
        
        if image_result.IsIncomplete():
            print(f"Image incomplete with image status {image_result.GetImageStatus()}")
            return None

        image_data = image_result.GetNDArray()
        image = Image.fromarray(image_data)
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG')
        img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        self.captured_images.append(img_str)
        image_result.Release()
        self.cam.EndAcquisition()
        return img_str

    def append_captured_images(self):
        with open('form_data.json', 'r+') as f:
            data = json.load(f)
            data['captured_images'] = self.captured_images
            f.seek(0)
            json.dump(data, f)
            f.truncate()
            result = process_captured_images()

            pdf_path = self.generate_pdf(result)

        save_dir = os.path.abspath('Results')
        os.makedirs(save_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = os.path.join(save_dir, f"Result_{timestamp}.pdf")
        os.rename(pdf_path, pdf_filename)
        

        pdf_url = f'file:///{pdf_filename}'.replace("\\", "/")
        with open('form_data.json', 'r+') as f:
            data = json.load(f)
            data['pdf_url'] = pdf_url
            f.seek(0)
            json.dump(data, f)
            f.truncate()

        form_data = data
        form_data['captured_images'] = json.dumps(self.captured_images)  
        form_data['pdf_url'] = pdf_url
        self.add_record_from_json(json.dumps(form_data))


        webbrowser.open_new(pdf_url)
        return {"status": "success"}
    
    def generate_pdf(self, result):
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph("Test Results", styles['Title']))
        elements.append(Spacer(1, 12))

        elements.append(Paragraph("Project Data:", styles['Heading2']))
        for key, value in result.items():
            if key != "results":
                elements.append(Paragraph(f"{key}: {value}", styles['Normal']))
        elements.append(Spacer(1, 12))

        elements.append(Paragraph("Capture Results:", styles['Heading2']))
        for capture in result['results']:
            for key, value in capture.items():
                elements.append(Paragraph(f"{key}:", styles['Heading3']))
                elements.append(Paragraph(f"Deviation: {value['deviation']} arcminutes", styles['Normal']))

                img_data = io.BytesIO(base64.b64decode(value['combined_image']))
                img = Image(img_data, width=400, height=200)
                elements.append(img)
                elements.append(Spacer(1, 12))

        # Adding Remarks section
        elements.append(Spacer(1, 24))
        elements.append(Paragraph("Remarks:", styles['Heading2']))
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(result.get('remarks', '__________________________'), styles['Normal']))
        elements.append(Spacer(1, 24))

        # Adding Signature section
        elements.append(Paragraph("Signature of Inspector: __________________", styles['Normal']))
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(f"Date: {datetime.now().strftime('%Y-%m-%d')}", styles['Normal']))
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Stamp: __________________", styles['Normal']))
        elements.append(Spacer(1, 24))

        doc.build(elements)
        
        pdf_path = "results.pdf"
        with open(pdf_path, "wb") as f:
            f.write(buffer.getvalue())
        
        return pdf_path
    
    def reset_captured_images(self):
        self.captured_images = []
        return True

    def submit_form(self, form_data):
        self.form_data = form_data
        self.form_data['captured_images'] = self.captured_images
        with open('form_data.json', 'w') as f:
            json.dump(self.form_data, f)
        self.captured_images = []

    async def websocket_handler(self, websocket, path):
        self.websocket_clients.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
            self.websocket_clients.remove(websocket)

    def __del__(self):
        if self.cam:
            self.cam.DeInit()
        del self.cam
        self.cam_list.Clear()
        self.system.ReleaseInstance()

api = Api()

async def start_websocket_server():
    server = await websockets.serve(api.websocket_handler, "localhost", 8765)
    await server.wait_closed()

def run_websocket_server():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_websocket_server())

Thread(target=run_websocket_server).start()

base_dir = os.path.abspath(os.path.dirname(__file__))

def get_html_path(filename):
    return os.path.join(base_dir, filename)

window = webview.create_window("HAl", url=f'file://{get_html_path("index.html")}', js_api=api)
webview.start(debug=True)