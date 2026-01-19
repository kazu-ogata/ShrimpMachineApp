import cv2, os

class Camera:
    def __init__(self):
        # Prefer the virtual camera created by rpicam-vid

        if os.path.exists("/dev/video10"):
            self.cap = cv2.VideoCapture("/dev/video10", cv2.CAP_V4L2)
        else:
            self.cap = cv2.VideoCapture(0)

        # Configure resolution (optional, some bridges ignore this)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    def get_frame(self):
        ret, frame = self.cap.read()
        return frame if ret else None

    def release(self):
        if self.cap.isOpened():
            self.cap.release()