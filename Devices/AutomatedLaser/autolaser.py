#Automated lasers powered by a servo on Raspberry Pi 5

#!/usr/bin/env python3

import numpy as np
import cv2
from picamera2 import Picamera2
import hailo_platform.pyhailort.pyhailort as hailort
import RPi.GPIO as GPIO
import time
import os

# Paths and constants
HEF_PATH = "/home/laser/models/yolov11n_nms.hef"
calib_data = np.load("/home/laser/new_calib.npz")
mtx = calib_data["mtx"]
dist = calib_data["dist"]

# Pan servo constants
PAN_PIN = 18
PWM_FREQ = 50
PAN_FOV = 141.0
PAN_CENTER = 70.5

# Tilt servo constants
TILT_PIN = 24
TILT_FOV = 81.67
TILT_CENTER = 40.835

running = True

# Pan servo setup
GPIO.setmode(GPIO.BCM)
GPIO.setup(PAN_PIN, GPIO.OUT)
pan_pwm = GPIO.PWM(PAN_PIN, PWM_FREQ)
pan_pwm.start(0)
print("Pan servo initialized, off")

# Tilt servo setup
GPIO.setup(TILT_PIN, GPIO.OUT)
tilt_pwm = GPIO.PWM(TILT_PIN, PWM_FREQ)
tilt_pwm.start(0)
print("Tilt servo initialized, off")

print("Starting up")
if not os.path.isfile(HEF_PATH):
    print(f"ERROR: HEF file {HEF_PATH} not found!")
    exit(1)

# Camera setup
picam2 = Picamera2()
config = picam2.create_video_configuration(
    main={"size": (1920, 1080), "format": "XRGB8888"},
    lores={"size": (640, 640), "format": "RGB888"}
)
picam2.configure(config)
picam2.start()
print("Camera started")

# HailoRT setup
with hailort.VDevice() as vdevice:
    hef = hailort.HEF(HEF_PATH)
    network_group = vdevice.configure(hef)[0]
    input_params = hailort.InputVStreamParams.make(network_group, format_type=hailort.FormatType.UINT8)
    output_params = hailort.OutputVStreamParams.make(network_group, format_type=hailort.FormatType.FLOAT32)
    print("HailoRT configured")

    with network_group.activate():
        print("Network activated")
        while running:
            frame_full = picam2.capture_array("main")
            frame = picam2.capture_array("lores")
            print("Frames captured")
            if frame is None or frame_full is None:
                print("Camera capture failed!")
                break

            if frame.shape != (640, 640, 3):
                frame = cv2.resize(frame, (640, 640))
            frame = frame.astype(np.uint8)
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            input_data = np.expand_dims(frame, axis=0)
            print("Frame prepped")

            with hailort.InferVStreams(network_group, input_params, output_params) as infer_pipeline:
                infer_results = infer_pipeline.infer(input_data)
                print("Inference ran")
                detections = infer_results['yolov11n/yolov8_nms_postprocess']

                person_detected = False
                if isinstance(detections, list) and len(detections) > 0:
                    dets_list = detections[0]
                    if isinstance(dets_list, list) and len(dets_list) > 0:
                        dets = dets_list[0]
                        if isinstance(dets, np.ndarray) and len(dets) > 0:
                            for det in dets:
                                if len(det) >= 5 and float(det[4]) >= 0.5:
                                    person_detected = True
                                    ymin = int(det[0] * 1080)
                                    xmin = int(det[1] * 1920)
                                    ymax = int(det[2] * 1080)
                                    xmax = int(det[3] * 1920)
                                    cv2.rectangle(frame_full, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)
                                    # Pan servo action
                                    xmin = det[1] * 640
                                    xmax = det[3] * 640
                                    x_pixel = (xmin + xmax) / 2
                                    points = np.array([[x_pixel, 320]], dtype=np.float32)
                                    points = points.reshape(-1, 1, 2)
                                    undistorted = cv2.undistortPoints(points, mtx, dist, None, mtx)
                                    pan_pixels_per_degree = 640 / PAN_FOV
                                    pan_angle = max(0, min(PAN_CENTER - ((undistorted[0, 0, 0] - 320) / pan_pixels_per_degree), PAN_FOV))
                                    print(f"PERSON DETECTED: x={x_pixel:.2f}, pan={pan_angle:.2f}")
                                    pan_duty = pan_angle / 18 + 2
                                    GPIO.output(PAN_PIN, True)
                                    pan_pwm.ChangeDutyCycle(pan_duty)
                                    time.sleep(0.5)
                                    GPIO.output(PAN_PIN, False)
                                    pan_pwm.ChangeDutyCycle(0)
                                    # Tilt servo action
                                    ymin = det[0] * 640
                                    ymax = det[2] * 640
                                    y_pixel = (ymin + ymax) / 2
                                    points = np.array([[320, y_pixel]], dtype=np.float32)  # Use 320 for x (center)
                                    points = points.reshape(-1, 1, 2)
                                    undistorted = cv2.undistortPoints(points, mtx, dist, None, mtx)
                                    tilt_pixels_per_degree = 640 / TILT_FOV
                                    tilt_angle = max(0, min(TILT_CENTER - ((undistorted[0, 0, 1] - 320) / tilt_pixels_per_degree), TILT_FOV))
                                    print(f"PERSON DETECTED: y={y_pixel:.2f}, tilt={tilt_angle:.2f}")
                                    tilt_duty = tilt_angle / 18 + 2  # Same duty calc as pan
                                    GPIO.output(TILT_PIN, True)
                                    tilt_pwm.ChangeDutyCycle(tilt_duty)
                                    time.sleep(0.5)
                                    GPIO.output(TILT_PIN, False)
                                    tilt_pwm.ChangeDutyCycle(0)
                                else:
                                    print("No person—servos stay put")
                                    pan_pwm.ChangeDutyCycle(0)
                                    tilt_pwm.ChangeDutyCycle(0)

            print("Loop ran")
            cv2.imshow("Tracking", frame_full)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    print("Starting cleanup")
    picam2.stop()
    running = False
    pan_pwm.ChangeDutyCycle(0)
    tilt_pwm.ChangeDutyCycle(0)
    time.sleep(0.1)
    pan_pwm.stop()
    tilt_pwm.stop()
    GPIO.output(PAN_PIN, GPIO.LOW)
    GPIO.output(TILT_PIN, GPIO.LOW)
    GPIO.cleanup()
    cv2.destroyAllWindows()
    print("Cleanup done")
