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


# --- NEW: Custom Dialog for Number Input (FIXED) ---
class NumberInputDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("Set Target Count")
        
        # We set *only* the frameless hint here, just like app.py
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
        
        # <--- FIX 1: Use the exact lambda from app.py ---
        # This calls the parent's open_keyboard and discards the event
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
    
    # <--- FIX 2: Add the showEvent, just like app.py ---
    def showEvent(self, event):
        """This runs when the dialog is shown, just like your Login screen."""
        super().showEvent(event)
        # This flag allows the keyboard to appear on top
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnBottomHint)
        self.show()

    def get_number(self):
        return int(self.lineEdit.text()) if self.lineEdit.text().isdigit() else 0

# --- Video Label (Unchanged) ---
class VideoLabel(QtWidgets.QLabel):
    # (This class is unchanged)
    def __init__(self):
        super().__init__()
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setStyleSheet("border: 2px solid #0077cc; border-radius: 8px; background-color: black;")
        self.setMinimumSize(640, 320)
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
        # (All this is the same as your last version)
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
        top_bar_layout.setAlignment(QtCore.Qt.AlignVCenter)
        top_bar_layout.addWidget(self.btnArrowBack, stretch=0, alignment=QtCore.Qt.AlignLeft)
        top_bar_layout.addWidget(self.lblTitle, stretch=1, alignment=QtCore.Qt.AlignCenter)
        spacer = QtWidgets.QWidget()
        spacer.setFixedSize(QtCore.QSize(50, 50))
        top_bar_layout.addWidget(spacer, stretch=0, alignment=QtCore.Qt.AlignRight)

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

        self.COLOR_SET_COUNT_INACTIVE = "#5bc0de" 
        self.COLOR_SET_COUNT_ACTIVE = "#0077cc"   
        self.COLOR_START = "#5cb85c"             
        self.COLOR_STOP = "#d9534f"              
        self.COLOR_SAVE = "#0077cc"              
        self.COLOR_RESET = "#999999"
        self.COLOR_DISPENSE = "#ffbb33"

        self.btnCount = self.make_button("Set Count", self.COLOR_SET_COUNT_INACTIVE)
        self.btnStart = self.make_button("Start", self.COLOR_START)
        self.btnStop = self.make_button("Stop", self.COLOR_STOP)
        self.btnSave = self.make_button("Save", self.COLOR_SAVE)
        self.btnReset = self.make_button("Reset", self.COLOR_RESET)
        self.btnDispense = self.make_button("Dispense Feed", self.COLOR_DISPENSE)
        self.btnDispense.setEnabled(False) 
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 12)
        layout.setSpacing(8)
        layout.setAlignment(QtCore.Qt.AlignTop)

        layout.addLayout(top_bar_layout)
        layout.addLayout(status_layout)
        layout.addWidget(self.video, alignment=QtCore.Qt.AlignCenter)
        layout.addWidget(self.lblCount)
        layout.addWidget(self.lblFeed)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.setAlignment(QtCore.Qt.AlignCenter)
        for b in [self.btnCount, self.btnStart, self.btnStop, self.btnSave, self.btnReset, self.btnDispense]:
            button_layout.addWidget(b)

        layout.addLayout(button_layout) 

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_frame)

        self.btnArrowBack.clicked.connect(self.go_back)
        self.btnStart.clicked.connect(self.start)
        self.btnStop.clicked.connect(self.stop)
        self.btnSave.clicked.connect(self.save)
        self.btnReset.clicked.connect(self.reset)
        self.btnCount.clicked.connect(self.set_count)
        self.btnDispense.clicked.connect(self.dispense_feed)

    def make_button(self, text, color):
        b = QtWidgets.QPushButton(text)
        b.setFixedWidth(150) 
        b.setFixedHeight(56)
        b.setStyleSheet(self.make_button_style(color))
        return b

    # --- On-Screen Keyboard Functions ---
    
    # <--- FIX 3: Remove 'event=None' to match app.py ---
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
            self.mqtt.publish("shrimp/pump/command", "PUMP ON")

    def stop(self):
        if self.running:
            self.running = False
            self.timer.stop()
            self.lblStatus.setText("Stopped")
            self.mqtt.publish("shrimp/pump/command", "PUMP OFF")
            self.btnDispense.setEnabled(True)

    def reset(self):
        self.running = False
        self.timer.stop()

        # This resets the detector's internal count to 0
        self.detector.reset_total_count() 
        
        # --- NEW LOGIC TO UPDATE VIDEO FRAME ---
        frame = self.camera.get_frame()
        if frame is not None:
            # Run detect one more time. The detector's total_count is now 0.
            # 'total_count_from_detector' will be 0, and 'frame_rgb' will have "Total: 0"
            total_count_from_detector, frame_rgb = self.detector.detect(frame, draw=True)
            
            # Set the UI's internal count to 0
            self.count = total_count_from_detector
            
            # Update the video feed with the new frame
            self.video.set_frame(cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR))
        else:
            # If camera fails, just set UI count to 0
            self.count = 0
        # --- END OF NEW LOGIC ---

        self.threshold_count = 0 
        self.threshold_reached = False 
        
        # Update UI labels
        self.lblCount.setText(f"Count: {self.count}") # This will now be "Count: 0"
        self.lblFeed.setText("Biomass: 0.00g | Feed: 0.00g | Protein: 0.00g | Filler: 0.00g")
        self.lblStatus.setText("Idle")
        self.lblThresholdStatus.setText("Target Count: Not Set")
        
        # Reset dispense button
        self.btnDispense.setEnabled(False)
        QtWidgets.QMessageBox.information(self, "Reset", "Process has been reset successfully.")

    def save(self):
        b, f, p, fl = compute_feed(self.count)
        save_biomass_record(self.user_id, self.count, b, f)
        QtWidgets.QMessageBox.information(self, "Saved", "Process saved locally.")
        self.lblStatus.setText("Saved")
        self.mqtt.publish("shrimp/pump/command", "PUMP OFF")
        self.btnDispense.setEnabled(True)

    def go_back(self):
        self.timer.stop()
        self.mqtt.publish("shrimp/pump/command", "PUMP OFF")
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
    def set_count(self):
        dialog = NumberInputDialog(self)
        
        # <--- FIX 4: Remove the .exec_() override ---
        # Now we let the user tap the text box to open the keyboard.
        if dialog.exec_():
            num = dialog.get_number()
            if num > 0:
                self.threshold_count = num
                self.threshold_reached = False 
                print(f"Target count set to: {self.threshold_count}")
                self.lblThresholdStatus.setText(f"Target Count: {num}")
        
        # We still close the keyboard when the dialog is accepted OR rejected.
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