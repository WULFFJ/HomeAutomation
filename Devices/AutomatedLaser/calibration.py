#Sets calibration for a lens for camera
#!/usr/bin/env python3

import cv2
import numpy as np
from picamera2 import Picamera2
import time

picam2 = Picamera2()
picam2.configure(picam2.create_video_configuration(main={"size": (1920, 1080)}))
picam2.start()

criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
objp = np.zeros((6*9, 3), np.float32)
objp[:, :2] = np.mgrid[0:9, 0:6].T.reshape(-1, 2)
objpoints = []
imgpoints = []

for i in range(20):
    frame = picam2.capture_array()
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    
    # Countdown 3, 2, 1
    for count in [3, 2, 1]:
        display_frame = frame.copy()
        cv2.putText(display_frame, str(count), (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 3)
        cv2.imshow("Calibrating", display_frame)
        cv2.waitKey(1000)  # 1 second per number
    
    # After countdown, check for checkerboard
    ret, corners = cv2.findChessboardCorners(gray, (9, 6), None)
    if ret:
        objpoints.append(objp)
        corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        imgpoints.append(corners2)
        cv2.drawChessboardCorners(frame, (9, 6), corners2, ret)
        print(f"Shot {i+1}/20: Checkerboard found")
    else:
        print(f"Shot {i+1}/20: No checkerboard")
    
    cv2.imshow("Calibrating", frame)
    cv2.waitKey(100)  # Short pause to show result

ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, gray.shape[::-1], None, None)
np.savez("new_calib.npz", mtx=mtx, dist=dist)
picam2.stop()
cv2.destroyAllWindows()
print("Saved new_calib.npz")
