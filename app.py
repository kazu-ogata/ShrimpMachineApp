import sys
import os
import qrcode
from PyQt5 import QtWidgets, QtCore, QtGui
from database import init_db, create_qr_session, poll_for_login
from ui_main import MainMenu

# --- Environment setup for Wayland/RPi5 ---
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
os.environ["QT_SCALE_FACTOR"] = "1"
os.environ["QT_FONT_DPI"] = "96"

class Login(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ShrimpSense Login")
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint)
        
        # UI Styling
        self.setStyleSheet("background-color: #FAF7F2;") 

        # Handshake Data
        self.session_id = create_qr_session()
        self.user_id = None

        # --- Main Layout (Using your original 250px side margins) ---
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(100, 80, 100, 80) # Adjusted for wide WhatsApp look
        main_layout.setSpacing(20)

        # 1. Logo Section (Top Left)
        logo_layout = QtWidgets.QHBoxLayout()
        self.logo = QtWidgets.QLabel()
        logo_path = "/home/hiponpd/Documents/GitHub/ShrimpMachineApp/assets/images/ShrimpSenseLogo.png"
        if os.path.exists(logo_path):
            logo_pix = QtGui.QPixmap(logo_path).scaled(120, 120, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            self.logo.setPixmap(logo_pix)
        logo_layout.addWidget(self.logo)
        logo_layout.addStretch()
        main_layout.addLayout(logo_layout)

        # 2. The Card Container (The WhatsApp Look)
        card = QtWidgets.QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #D1D1D1;
                border-radius: 20px;
            }
        """)
        card_layout = QtWidgets.QHBoxLayout(card)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(40)

        # Left Side: Instructions (The part you want!)
        text_container = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("Steps to log in")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #111; border: none;")

        steps = QtWidgets.QLabel(
            "1. Open <b>ShrimpSense</b> app on your phone.<br><br>"
            "2. Go to <b>Scan → Start Scanner.</b><br><br>"
            "3. Scan the QR code displayed on this screen."
        )
        steps.setStyleSheet("font-size: 16px; color: #333; border: none; line-height: 140%;")
        
        text_container.addWidget(title)
        text_container.addSpacing(10)
        text_container.addWidget(steps)
        text_container.addStretch()

        # Right Side: QR Code
        self.qr_label = QtWidgets.QLabel()
        self.qr_label.setStyleSheet("border: none;")
        if self.session_id:
            # Small box_size ensures it doesn't push the window too wide
            qr = qrcode.QRCode(version=1, box_size=6, border=2)
            qr.add_data(self.session_id)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img.save("session_qr.png")
            
            pixmap = QtGui.QPixmap("session_qr.png").scaled(240, 240, QtCore.Qt.KeepAspectRatio)
            self.qr_label.setPixmap(pixmap)
        else:
            self.qr_label.setText("Check Internet Connection")

        card_layout.addLayout(text_container, stretch=2)
        card_layout.addWidget(self.qr_label, stretch=1)

        main_layout.addStretch()
        main_layout.addWidget(card)
        main_layout.addStretch()

        # Polling Timer
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.check_login_status)
        self.timer.start(2000)

    # --- Your Original Fullscreen Logic ---
    def showEvent(self, event):
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self.showFullScreen)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnBottomHint)
        self.show()

    def check_login_status(self):
        uid = poll_for_login(self.session_id)
        if uid:
            self.user_id = uid
            self.timer.stop()
            self.accept()

def main():
    init_db()
    app = QtWidgets.QApplication(sys.argv)

    while True:
        login = Login()
        login.showFullScreen()
        
        # Wait for the QR scan to complete
        if not login.exec_():
            break

        # Open the Main Menu with the user's ID
        main_window = MainMenu(login.user_id)
        main_window.showFullScreen()
        app.exec_()

        # If user logs out, the loop restarts and shows the QR code again
        if not getattr(main_window, "logout_requested", False):
            break

    sys.exit()

if __name__ == "__main__":
    main()