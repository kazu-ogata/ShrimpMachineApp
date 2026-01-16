import os
import sys
from PyQt5 import QtWidgets, QtCore, QtGui
from ui_biomass import BiomassWindow
from theme import *

# Fix scaling for Touchscreens
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
os.environ["QT_SCALE_FACTOR"] = "1"
os.environ["QT_FONT_DPI"] = "96"
os.environ["QT_SCREEN_SCALE_FACTORS"] = "1"
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")

class MainMenu(QtWidgets.QWidget):
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
        self.logout_requested = False

        # Window Config
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint)
        self.setFixedSize(1024, 600)
        
        # 1. Background
        self.setStyleSheet("background-color: #FAF7F2;") 

        # Main Layout (Original margins and spacing)
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(60, 40, 60, 40)
        self.main_layout.setSpacing(0)

        # 1. Middle Section: (Your original layout logic)
        self.mid_layout = QtWidgets.QHBoxLayout()
        
        # Left Side: Your original Welcome Text style
        self.lblWelcome = QtWidgets.QLabel("WELCOME!")
        self.lblWelcome.setStyleSheet("font-size: 65px; font-weight: 900; color: #111; border: none;")
        self.lblWelcome.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.lblWelcome.setContentsMargins(0, 80, 0, 0)

        # Right Side: Your original Landing Image scaling
        self.lblImage = QtWidgets.QLabel()
        img_path = "/home/hiponpd/Documents/GitHub/ShrimpMachineApp/assets/images/landing.png"
        if os.path.exists(img_path):
            pixmap = QtGui.QPixmap(img_path).scaled(450, 450, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            self.lblImage.setPixmap(pixmap)
        self.lblImage.setAlignment(QtCore.Qt.AlignCenter)
        
        self.mid_layout.addWidget(self.lblWelcome, stretch=1)
        self.mid_layout.addWidget(self.lblImage, stretch=1)

        self.main_layout.addLayout(self.mid_layout)

        # 2. Bottom Section: Controls
        self.button_layout = QtWidgets.QHBoxLayout()
        
        # 2, 3, 4. START Button: Black background, White text, 10px corner radius
        self.btnStart = QtWidgets.QPushButton("START")
        self.btnStart.setFixedSize(280, 70)
        self.btnStart.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.btnStart.setStyleSheet("""
            QPushButton {
                background-color: #111111;
                color: white;
                border-radius: 10px;
                font-size: 24px;
                font-weight: bold;
                letter-spacing: 2px;
            }
            QPushButton:pressed { background-color: #333333; }
        """)

        # 5. logout: Minimalist black text in the same position
        self.btnLogout = QtWidgets.QPushButton("logout")
        self.btnLogout.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.btnLogout.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #111111;
                font-size: 18px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover { color: #444444; }
        """)

        self.button_layout.addWidget(self.btnStart)
        self.button_layout.addStretch()
        self.button_layout.addWidget(self.btnLogout)

        self.main_layout.addLayout(self.button_layout)

        # Connections
        self.btnStart.clicked.connect(self.open_biomass)
        self.btnLogout.clicked.connect(self.logout)

    def open_biomass(self):
        self.bw = BiomassWindow(self.user_id, self)
        self.bw.showFullScreen()
        self.hide()

    def logout(self):
        self.logout_requested = True
        self.close()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, False)
    app.setAttribute(QtCore.Qt.AA_DisableHighDpiScaling, True)
    app.setAttribute(QtCore.Qt.AA_Use96Dpi, True)

    window = MainMenu(user_id="test_user")
    window.showFullScreen()
    sys.exit(app.exec_())