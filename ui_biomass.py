import sys, cv2, datetime, os, subprocess 
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
os.environ["QT_SCALE_FACTOR"] = "1"
os.environ["QT_FONT_DPI"] = "96"
os.environ["QT_SCREEN_SCALE_FACTORS"] = "1"
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")

from PyQt5 import QtWidgets, QtGui, QtCore
from compute import compute_feed
from detector import ShrimpDetector
from camera import Camera
from database import save_biomass_record
from theme import *
from mqtt_client import MqttClient

# --- Catch all unhandled exceptions in Qt ---
def qt_exception_hook(exctype, value, traceback):
    print("Unhandled Exception:", value)
sys.excepthook = qt_exception_hook


# --- Custom Dialog for Number Input ---
class NumberInputDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("Set Target Count")
        
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint)
        self.setStyleSheet(f"background-color:{BG_COLOR}; color:{TEXT_COLOR}; font-size: 20px;")
        self.setModal(True) 

        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)

        self.label = QtWidgets.QLabel("Enter target shrimp count:")
        self.label.setStyleSheet("font-size: 22px; margin-bottom: 10px;")

        self.lineEdit = QtWidgets.QLineEdit()
        self.lineEdit.setStyleSheet("font-size:28px; padding:10px; border-radius:10px; background-color: white; color: black;")
        self.lineEdit.setValidator(QtGui.QIntValidator(0, 99999)) 
        
        self.lineEdit.focusInEvent = lambda event: self.parent.open_keyboard()

        self.btnBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.btnBox.accepted.connect(self.accept)
        self.btnBox.rejected.connect(self.reject)
        
        ok_btn = self.btnBox.button(QtWidgets.QDialogButtonBox.Ok)
        cancel_btn = self.btnBox.button(QtWidgets.QDialogButtonBox.Cancel)
        ok_btn.setStyleSheet(f"background-color:{BTN_SYNC}; color:white; font-size:18px; padding:10px 25px; border-radius:8px;")
        cancel_btn.setStyleSheet(f"background-color:{BTN_DANGER}; color:white; font-size:18px; padding:10px 25px; border-radius:8px;")

        self.layout.addWidget(self.label)
        self.layout.addWidget(self.lineEdit)
        self.layout.addWidget(self.btnBox)

    def showEvent(self, event):
        super().showEvent(event)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnBottomHint)
        self.show()

    def get_number(self):
        return int(self.lineEdit.text()) if self.lineEdit.text().isdigit() else 0

# --- NEW: Custom Dialog for Pump Control ---
class PumpControlDialog(QtWidgets.QDialog):
    """
    A simple pop-up dialog with Start and Stop buttons for the pump.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mqtt = parent.mqtt # Get the MQTT client from the parent
        
        self.setWindowTitle("Pump Control")
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint)
        self.setStyleSheet(f"background-color:{BG_COLOR}; color:{TEXT_COLOR}; font-size: 20px;")
        self.setModal(True)
        self.setMinimumWidth(400) # Set a fixed width

        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        self.label = QtWidgets.QLabel("Water Pump Control")
        self.label.setStyleSheet("font-size: 22px; font-weight: bold; margin-bottom: 10px;")
        self.label.setAlignment(QtCore.Qt.AlignCenter)

        # Start Pump Button
        self.btnStartPump = QtWidgets.QPushButton("START PUMP")
        self.btnStartPump.setFixedHeight(80)
        self.btnStartPump.setStyleSheet(f"background-color:{BTN_SYNC}; color:white; font-size:24px; font-weight:bold; border-radius:10px;")
        
        # Stop Pump Button
        self.btnStopPump = QtWidgets.QPushButton("STOP PUMP")
        self.btnStopPump.setFixedHeight(80)
        self.btnStopPump.setStyleSheet(f"background-color:{BTN_DANGER}; color:white; font-size:24px; font-weight:bold; border-radius:10px;")
        
        # Close Button
        self.btnClose = QtWidgets.QPushButton("Done")
        self.btnClose.setFixedHeight(50)
        self.btnClose.setStyleSheet(f"background-color:#999999; color:white; font-size:18px; border-radius:8px;")

        # Connect signals
        self.btnStartPump.clicked.connect(self.start_pump)
        self.btnStopPump.clicked.connect(self.stop_pump)
        self.btnClose.clicked.connect(self.accept) # 'accept' just closes the dialog

        # Add widgets to layout
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.btnStartPump)
        self.layout.addWidget(self.btnStopPump)
        self.layout.addWidget(self.btnClose, alignment=QtCore.Qt.AlignCenter)

    def start_pump(self):
        print("MQTT: Sending PUMP ON")
        self.mqtt.publish("shrimp/pump/command", "PUMP ON")

    def stop_pump(self):
        print("MQTT: Sending PUMP OFF")
        self.mqtt.publish("shrimp/pump/command", "PUMP OFF")

# --- Video Label (Unchanged) ---
class VideoLabel(QtWidgets.QLabel):
    # (This class is unchanged)
    def __init__(self):
        super().__init__()
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setStyleSheet("border: 2px solid #0077cc; border-radius: 8px; background-color: black;")
        self.setMinimumSize(640, 240)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
    def set_frame(self, frame):
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qimg = QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format_RGB888)
            pix = QtGui.QPixmap.fromImage(qimg)
            pix = pix.scaled(self.width(), self.height(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            self.setPixmap(pix)
        except Exception as e:
            print("Error displaying frame:", e)


class BiomassWindow(QtWidgets.QWidget):
    def __init__(self, user_id, parent=None):
        super().__init__()
        self.parent = parent
        self.user_id = user_id
        self.detector = ShrimpDetector()
        self.camera = Camera()
        self.mqtt = MqttClient()
        self.mqtt.connect()
        self.running = False
        self.count = 0
        self.threshold_count = 0
        self.threshold_reached = False

        self.setWindowFlag(QtCore.Qt.FramelessWindowHint)
        self.setStyleSheet(f"background-color:{BG_COLOR}; color:{TEXT_COLOR}; font-family:{FONT_FAMILY};")
        QtCore.QTimer.singleShot(0, lambda: self.showFullScreen())

        # Top Bar
        self.btnArrowBack = QtWidgets.QPushButton()
        icon = self.style().standardIcon(QtWidgets.QStyle.SP_ArrowLeft)
        self.btnArrowBack.setIcon(icon)
        self.btnArrowBack.setIconSize(QtCore.QSize(40, 40))
        self.btnArrowBack.setFixedSize(QtCore.QSize(50, 50))
        self.btnArrowBack.setFlat(True)
        self.btnArrowBack.setStyleSheet("border: none; padding: 5px;")
        self.btnArrowBack.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))

        self.lblTitle = QtWidgets.QLabel("Biomass Calculation")
        self.lblTitle.setAlignment(QtCore.Qt.AlignCenter)
        self.lblTitle.setStyleSheet("font-size:20px; font-weight:bold; margin-bottom:6px;")
        
        top_bar_layout = QtWidgets.QHBoxLayout()
        top_bar_layout.addWidget(self.btnArrowBack, stretch=0, alignment=QtCore.Qt.AlignLeft)
        top_bar_layout.addWidget(self.lblTitle, stretch=1, alignment=QtCore.Qt.AlignCenter)
        spacer = QtWidgets.QWidget()
        spacer.setFixedSize(QtCore.QSize(50, 50))
        top_bar_layout.addWidget(spacer, stretch=0, alignment=QtCore.Qt.AlignRight)

        # Status Labels
        self.lblStatus = QtWidgets.QLabel("Idle")
        self.lblStatus.setAlignment(QtCore.Qt.AlignRight)
        self.lblStatus.setStyleSheet("font-size:16px; margin-bottom:6px; color:#555;")
        
        self.lblThresholdStatus = QtWidgets.QLabel("Target Count: Not Set")
        self.lblThresholdStatus.setAlignment(QtCore.Qt.AlignLeft)
        self.lblThresholdStatus.setStyleSheet("font-size:16px; margin-bottom:6px; color:#005fa3; font-weight:bold;")

        status_layout = QtWidgets.QHBoxLayout()
        status_layout.addWidget(self.lblStatus, 1)
        status_layout.addWidget(self.lblThresholdStatus, 1)

        self.video = VideoLabel()

        self.lblCount = QtWidgets.QLabel("Count: 0")
        self.lblFeed = QtWidgets.QLabel("Biomass: 0.00g | Feed: 0.00g | Protein: 0.00g | Filler: 0.00g")
        for lbl in [self.lblCount, self.lblFeed]:
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            lbl.setStyleSheet("font-size:16px; margin:4px;")

        # --- Button Colors (7 Buttons) ---
        self.COLOR_SET_COUNT = "#5bc0de"          # Light Blue
        self.COLOR_START = "#5cb85c"             # Green
        self.COLOR_STOP = "#d9534f"              # Red
        self.COLOR_PUMP = "#f0ad4e"              # Orange
        self.COLOR_SAVE = "#0077cc"              # Blue
        self.COLOR_RESET = "#999999"             # Gray
        self.COLOR_RESET_DOOR = "#00AEEF"
        self.COLOR_DISPENSE_INACTIVE = "#999999" # Gray
        self.COLOR_DISPENSE_ACTIVE = "#8a63d2"   # Purple

        # --- Create the 7 buttons ---
        self.btnCount = self.make_button("Set Count", self.COLOR_SET_COUNT)
        self.btnStart = self.make_button("Start", self.COLOR_START)
        self.btnStop = self.make_button("Stop", self.COLOR_STOP)
        self.btnPump = self.make_button("Pump", self.COLOR_PUMP) # <-- NEW
        self.btnSave = self.make_button("Save", self.COLOR_SAVE)
        self.btnReset = self.make_button("Reset", self.COLOR_RESET)
        self.btnResetDoor = self.make_button("Reset Door", self.COLOR_RESET_DOOR)
        self.btnDispense = self.make_button("Dispense Feed", self.COLOR_DISPENSE_INACTIVE)
        self.btnDispense.setEnabled(False) 
        
        # --- Main Layout setup ---
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 12)
        layout.setSpacing(8)

        layout.addLayout(top_bar_layout)
        layout.addLayout(status_layout)
        layout.addWidget(self.video, alignment=QtCore.Qt.AlignCenter)

        layout.setStretch(2, 1)
        
        layout.addWidget(self.lblCount)
        layout.addWidget(self.lblFeed)

        # --- NEW 2x4 Button Layout ---
        button_row_1 = QtWidgets.QHBoxLayout()
        button_row_1.setSpacing(10)
        button_row_1.setAlignment(QtCore.Qt.AlignCenter)
        for b in [self.btnCount, self.btnStart, self.btnStop, self.btnPump]:
            button_row_1.addWidget(b)

        button_row_2 = QtWidgets.QHBoxLayout()
        button_row_2.setSpacing(10)
        button_row_2.setAlignment(QtCore.Qt.AlignCenter)
        for b in [self.btnSave, self.btnReset, self.btnResetDoor, self.btnDispense]:
            button_row_2.addWidget(b)

        layout.addLayout(button_row_1)
        layout.addLayout(button_row_2)

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_frame)

        # --- Button connections ---
        self.btnArrowBack.clicked.connect(self.go_back)
        self.btnStart.clicked.connect(self.start)
        self.btnStop.clicked.connect(self.stop)
        self.btnPump.clicked.connect(self.open_pump_control) # <-- NEW
        self.btnSave.clicked.connect(self.save)
        self.btnReset.clicked.connect(self.reset)
        self.btnCount.clicked.connect(self.set_count)
        self.btnResetDoor.clicked.connect(self.reset_door)
        self.btnDispense.clicked.connect(self.dispense_feed)

    # --- Helper ---
    def make_button(self, text, color):
        b = QtWidgets.QPushButton(text)
        # --- CHANGED: 130px for 7 buttons ---
        b.setFixedWidth(220) 
        b.setFixedHeight(56)
        b.setStyleSheet(self.make_button_style(color))
        return b

    # --- On-Screen Keyboard Functions ---
    def open_keyboard(self): 
        try:
            subprocess.Popen(["pkill", "-f", "matchbox-keyboard"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        try:
            subprocess.Popen(
                ["matchbox-keyboard"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
        except Exception as e:
            print("Keyboard launch failed:", e)

    def close_keyboard(self):
        try:
            subprocess.Popen(["pkill", "-f", "matchbox-keyboard"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    # ---------------- Logic ----------------
    def start(self):
        if not self.running:
            self.running = True
            self.timer.start(100)
            self.lblStatus.setText("Running...")
            # Pump command removed

    def stop(self):
        if self.running:
            self.running = False
            self.timer.stop()
            self.lblStatus.setText("Stopped")
            # Pump command removed
            self.btnDispense.setEnabled(True)
            self.btnDispense.setStyleSheet(self.make_button_style(self.COLOR_DISPENSE_ACTIVE))

    def reset(self):
        self.running = False
        self.timer.stop()
        
        # Tell door to re-open
        self.mqtt.publish("shrimp/servo1/command", "SERVO1_OPEN")
        
        self.detector.reset_total_count() 
        
        # Redraw the frame to show "Total: 0"
        frame = self.camera.get_frame()
        if frame is not None:
            total_count_from_detector, frame_rgb = self.detector.detect(frame, draw=True)
            self.count = total_count_from_detector
            self.video.set_frame(cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR))
        else:
            self.count = 0

        self.threshold_count = 0 
        self.threshold_reached = False 
        
        # Update UI labels
        self.lblCount.setText(f"Count: {self.count}")
        self.lblFeed.setText("Biomass: 0.00g | Feed: 0.00g | Protein: 0.00g | Filler: 0.00g")
        self.lblStatus.setText("Idle")
        self.lblThresholdStatus.setText("Target Count: Not Set")
        
        self.btnDispense.setEnabled(False)
        self.btnDispense.setStyleSheet(self.make_button_style(self.COLOR_DISPENSE_INACTIVE))
        QtWidgets.QMessageBox.information(self, "Reset", "Process has been reset successfully.")

    def save(self):
        b, f, p, fl = compute_feed(self.count)
        save_biomass_record(self.user_id, self.count, b, f)
        QtWidgets.QMessageBox.information(self, "Saved", "Process saved locally.")
        self.lblStatus.setText("Saved")
        # Pump command removed
        self.btnDispense.setEnabled(True)
        self.btnDispense.setStyleSheet(self.make_button_style(self.COLOR_DISPENSE_ACTIVE))

    def go_back(self):
        self.timer.stop()
        # Pump command removed
        self.mqtt.disconnect()
        self.close_keyboard() 
        try:
            self.camera.release()
        except Exception:
            pass
        if self.parent:
            self.parent.update_recent()
            self.parent.show()
        self.close()

    # --- Hardware Functions ---
    
    # --- NEW FUNCTION for the pump pop-up ---
    def open_pump_control(self):
        dialog = PumpControlDialog(self)
        dialog.exec_()

    # --- ADD THIS NEW FUNCTION ---
    def reset_door(self):
        """Manually opens the servo door and resets the count logic."""
        print("MQTT: Sending SERVO1_OPEN (manual reset)")
        self.mqtt.publish("shrimp/servo1/command", "SERVO1_OPEN")
        
        # Also reset the threshold logic
        self.threshold_count = 0 
        self.threshold_reached = False 
        self.lblThresholdStatus.setText("Target Count: Not Set")
    # --- END OF NEW FUNCTION ---
    
    def set_count(self):
        dialog = NumberInputDialog(self)
        
        if dialog.exec_():
            num = dialog.get_number()
            if num > 0:
                self.threshold_count = num
                self.threshold_reached = False 
                print(f"Target count set to: {self.threshold_count}")
                self.lblThresholdStatus.setText(f"Target Count: {num}")
        
        self.close_keyboard()
    
    def dispense_feed(self):
        print("MQTT: Sending DISPENSE command")
        self.mqtt.publish("shrimp/servo3/command", "SERVO3_DISPENSE")

    def update_frame(self):
        frame = self.camera.get_frame()

        if frame is None:
            print("Failed to get frame from camera.")
            return

        count, frame_rgb = self.detector.detect(frame)
        self.count = count

        if self.threshold_count > 0 and not self.threshold_reached:
            if self.count >= self.threshold_count:
                print(f"Target count reached ({self.count})! Sending CLOSE command.")
                self.mqtt.publish("shrimp/servo1/command", "SERVO1_CLOSE")
                self.threshold_reached = True

        b, f, p, fl = compute_feed(count)
        self.lblCount.setText(f"Count: {count}")
        self.lblFeed.setText(f"Biomass: {b:.2f}g | Feed: {f:.2f}g | Protein: {p:.2f}g | Filler: {fl:.2f}g")
        self.video.set_frame(cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR))

    # Helper function to get stylesheet string
    def make_button_style(self, color):
        return f"""
            QPushButton {{
                background-color:{color};
                color:white;
                border-radius:12px;
                font-size:16px;
                font-weight:bold;
            }}
            QPushButton:pressed, QPushButton:checked {{
                background-color:#005fa3;
            }}
        """

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, False)
    app.setAttribute(QtCore.Qt.AA_DisableHighDpiScaling, True)
    app.setAttribute(QtCore.Qt.AA_Use96Dpi, True)
    win = BiomassWindow(user_id=1)
    win.show()
    sys.exit(app.exec_())