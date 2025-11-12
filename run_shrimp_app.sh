#!/bin/bash
# --- Load environment variables ---
export MONGO_URI="mongodb+srv://qajgvalencia:BUxIhYb4nDlfH4DV@cluster0.h07iggq.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
export MONGO_DB="test"
export QT_QPA_PLATFORM="Wayland"
export QT_AUTO_SCREEN_SCALE_FACTOR=0
export QT_SCALE_FACTOR=1
export QT_FONT_DPI=96

# --- Move to project folder ---
cd /home/hiponpd/Documents/GitHub/ShrimpMachineApp

# --- Run the app using your virtual environment ---
/home/hiponpd/Documents/GitHub/ShrimpMachineApp/hipon-venv/bin/python3 app.py
