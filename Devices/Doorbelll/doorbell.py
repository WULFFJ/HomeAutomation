
#!/usr/bin/env python3
import logging
import threading
import time
import datetime
import os
#os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "dummy"   # forces dummy backend
#os.environ["OPENCV_VIDEOIO_BACKEND"] = "V4L2"           # forces V4L2 (no Qt)
#os.environ["OPENCV_LOG_LEVEL"] = "FATAL"                # kills all spam
import sys
import signal
import numpy as np
import cv2
import requests
import random
import ssl
import paho.mqtt.client as mqtt
from queue import Queue, Empty
import gpiod
# ========================== HARD-CODED CONFIG (ONLY SOURCE OF TRUTH) ==========================
MODEL_PATH       = '/home/homeaccount/models/zeus.rknn'
TARGET_PLATFORM  = 'rk3566'
DEVICE_ID        = None
CAMERA_ID        = 0

MQTT_BROKER      = 'xxx.xxx.x.xxx'
MQTT_PORT        = 8883
MQTT_USERNAME    = 'doorbell'
MQTT_PASSWORD    = 'mqttpassword'
MQTT_CA_CERT     = '/home/homeaccount/cert/ca.pem'
MQTT_CLIENT_CERT = '/home/homeaccount/cert/client.crt'
MQTT_CLIENT_KEY  = '/home/homeaccount/cert/client-key.pem'

TELEGRAM_TOKEN   = 'telegram token here'
TELEGRAM_CHAT_ID = 'telegram chat id'

SOUNDS_DIR       = '/home/homeaccount/sounds/'
IMAGES_DIR       = '/home/homeaccount/images/'
GONG_SOUND       = SOUNDS_DIR + 'Gong.mp3'
DOORBELL_GREETING = SOUNDS_DIR + 'buttonpush/buttongreeting.mp3'
GREETINGS        = [SOUNDS_DIR + f'Greet{i}.mp3' for i in range(1, 11)]
# ====================================================================================
OBJ_THRESH = 0.25
NMS_THRESH = 0.45
IMG_SIZE   = (640, 640)
CLASSES    = ("person",)

cap_lock = threading.Lock()

# Path setup for py_utils (only once)
_current_dir = os.path.dirname(os.path.abspath(__file__))
_myapp_dir = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(os.path.join(_myapp_dir, 'py_utils'))
from py_utils.coco_utils import COCO_test_helper

# Queues & globals
detection_queue = Queue()
capture_queue   = Queue()
last_gong_time = 0
last_doorbell_time = 0
motion_counter = 0
doorbell_line = None

# MQTT setup
client = mqtt.Client("FrontDoor")
client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
client.tls_set(ca_certs=MQTT_CA_CERT,
               certfile=MQTT_CLIENT_CERT,
               keyfile=MQTT_CLIENT_KEY,
               cert_reqs=ssl.CERT_REQUIRED,
               tls_version=ssl.PROTOCOL_TLS)
client.tls_insecure_set(True)
client.connect(MQTT_BROKER, MQTT_PORT)
client.loop_start()

# ==================================== UNTOUCHED WORKING FUNCTIONS ====================================

def filter_boxes(boxes, box_confidences, box_class_probs):
    box_confidences = box_confidences.reshape(-1)
    candidate, class_num = box_class_probs.shape
    class_max_score = np.max(box_class_probs, axis=-1)
    classes = np.argmax(box_class_probs, axis=-1)

    # Add this diagnostic line:
    raw_scores = class_max_score * box_confidences
    # print(f"Raw confidences - max: {raw_scores.max():.3f}, mean: {raw_scores.mean():.3f}, >0.01: {(raw_scores > 0.01).sum()}")
    _class_pos = np.where(class_max_score * box_confidences >= OBJ_THRESH)
    scores = (class_max_score * box_confidences)[_class_pos]
    boxes = boxes[_class_pos]
    classes = classes[_class_pos]
    return boxes, classes, scores

def nms_boxes(boxes, scores):
    x = boxes[:, 0]
    y = boxes[:, 1]
    w = boxes[:, 2] - boxes[:, 0]
    h = boxes[:, 3] - boxes[:, 1]
    areas = w * h
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x[i], x[order[1:]])
        yy1 = np.maximum(y[i], y[order[1:]])
        xx2 = np.minimum(x[i] + w[i], x[order[1:]] + w[order[1:]])
        yy2 = np.minimum(y[i] + h[i], y[order[1:]] + h[order[1:]])
        w1 = np.maximum(0.0, xx2 - xx1 + 0.00001)
        h1 = np.maximum(0.0, yy2 - yy1 + 0.00001)
        inter = w1 * h1
        ovr = inter / (areas[i] + areas[order[1:]] - inter)
        inds = np.where(ovr <= NMS_THRESH)[0]
        order = order[inds + 1]
    keep = np.array(keep)
    return keep

def dfl(position):
    """Distribution Focal Loss – pure NumPy version (no torch needed)"""
    import numpy as np
    x = position.astype(np.float32)
    n, c, h, w = x.shape
    p_num = 4
    mc = c // p_num
    y = x.reshape(n, p_num, mc, h, w)
    # Softmax over the 4 bins
    y = np.exp(y - np.max(y, axis=2, keepdims=True))
    y = y / np.sum(y, axis=2, keepdims=True)
    # Weighted sum of bin indices
    acc_metrix = np.arange(mc, dtype=np.float32).reshape(1, 1, mc, 1, 1)
    return (y * acc_metrix).sum(axis=2)

def box_process(position):
    grid_h, grid_w = position.shape[2:4]
    col, row = np.meshgrid(np.arange(0, grid_w), np.arange(0, grid_h))
    col = col.reshape(1, 1, grid_h, grid_w)
    row = row.reshape(1, 1, grid_h, grid_w)
    grid = np.concatenate((col, row), axis=1)
    stride = np.array([IMG_SIZE[1] // grid_h, IMG_SIZE[0] // grid_w]).reshape(1, 2, 1, 1)
    position = dfl(position)
    box_xy = grid + 0.5 - position[:, 0:2, :, :]
    box_xy2 = grid + 0.5 + position[:, 2:4, :, :]
    xyxy = np.concatenate((box_xy * stride, box_xy2 * stride), axis=1)
    return xyxy

def post_process(input_data):
    boxes, scores, classes_conf = [], [], []
    defualt_branch = 3
    pair_per_branch = len(input_data) // defualt_branch
    for i in range(defualt_branch):
        boxes.append(box_process(input_data[pair_per_branch * i]))
        classes_conf.append(input_data[pair_per_branch * i + 1])
        scores.append(np.ones_like(input_data[pair_per_branch * i + 1][:, :1, :, :], dtype=np.float32))
    def sp_flatten(_in):
        ch = _in.shape[1]
        _in = _in.transpose(0, 2, 3, 1)
        return _in.reshape(-1, ch)
    boxes = [sp_flatten(_v) for _v in boxes]
    classes_conf = [sp_flatten(_v) for _v in classes_conf]
    scores = [sp_flatten(_v) for _v in scores]
    boxes = np.concatenate(boxes)
    classes_conf = np.concatenate(classes_conf)
    scores = np.concatenate(scores)
    boxes, classes, scores = filter_boxes(boxes, scores, classes_conf)
    nboxes, nclasses, nscores = [], [], []
    for c in set(classes):
        inds = np.where(classes == c)
        b = boxes[inds]
        c = classes[inds]
        s = scores[inds]
        keep = nms_boxes(b, s)
        if len(keep) != 0:
            nboxes.append(b[keep])
            nclasses.append(c[keep])
            nscores.append(s[keep])
    if not nclasses and not nscores:
        return None, None, None
    boxes = np.concatenate(nboxes)
    classes = np.concatenate(nclasses)
    scores = np.concatenate(nscores)
    return boxes, classes, scores

def setup_model(_):
    from py_utils.rknn_executor import RKNN_model_container
    model = RKNN_model_container(MODEL_PATH, TARGET_PLATFORM, DEVICE_ID)
    print('Model-{} is rknn model, starting val'.format(MODEL_PATH))
    return model, 'rknn'

def setup_gpio():
    global doorbell_line
    try:
        chip = gpiod.Chip("gpiochip3")
        doorbell_line = chip.get_line(7)  # Pin 36 = line 7
        doorbell_line.request(
            consumer="doorbell",
            type=gpiod.LINE_REQ_DIR_IN,
            # NO pull-up flag — your 10kΩ external resistor does the job
        )
        print("GPIO initialized successfully — button ready")
        return True
    except Exception as e:
        print(f"GPIO failed: {e}")
        doorbell_line = None
        return False

def motion_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {'chat_id': TELEGRAM_CHAT_ID, 'text': text}
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"Telegram message error: {e}")

def send_photo(image_path, caption="Front Door Motion Detected"):
    if not os.path.exists(image_path):
        return


    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        with open(image_path, 'rb') as photo:
            files = {'photo': photo}
            data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}
            requests.post(url, files=files, data=data, timeout=30)
    except Exception as e:
        print(f"Telegram photo error: {e}")

def play_audio(audio_file):
    if os.path.exists(audio_file):
       os.system(f'mpg123 -o alsa -q "{audio_file}" >/dev/null 2>&1')

def detection_processor():
    """Process detection events - runs in separate thread"""
    global last_gong_time, motion_counter
    print("Detection processor started")
    while True:
        try:
            detection_event = detection_queue.get(timeout=1)
            if detection_event == "person_detected":
                current_time = time.time()

                if current_time - last_gong_time > 120:
                    # First detection after 2+ minutes
                    last_gong_time = current_time
                    motion_counter = 1
                    client.publish("doorbell/motion_detected", "ON")
                    threading.Thread(target=play_audio, args=(GONG_SOUND,), daemon=True).start()
                    motion_message("Front Door Motion Detected")
                    capture_queue.put("motion_first")

                elif motion_counter == 1 and (current_time - last_gong_time > 10):
                    # Second detection after 10+ seconds
                    motion_counter = 2
                    greeting_file = random.choice(GREETINGS)
                    threading.Thread(target=play_audio, args=(greeting_file,), daemon=True).start()
                    capture_queue.put("motion_second")

            detection_queue.task_done()

        except Empty:
            continue
        except Exception as e:
            print(f"Error in detection_processor: {e}")
            time.sleep(0.1)

def image_capture_thread(cap):
    """Handle image capture requests - runs in separate thread"""
    print("Image capture thread started")
    os.makedirs(IMAGES_DIR, exist_ok=True)
    while True:
        try:
            request = capture_queue.get(timeout=1)
            print(f"Processing capture request: {request}")
            xdate = datetime.datetime.now().strftime("%m%d%Y-%H%M%S")
            output_image = os.path.join(IMAGES_DIR, 'snap' + xdate + '.jpg')

            with cap_lock:
                ret, frame = cap.read()

            if ret and frame is not None:
                cv2.imwrite(output_image, frame)
                print(f"Image saved: {output_image}")

                # Send photos in background threads to avoid blocking
                if request == "doorbell_press":
                    threading.Thread(target=send_photo, args=(output_image, "Bell Ringer"), daemon=True).start()
                elif request == "motion_first":
                    threading.Thread(target=send_photo, args=(output_image, "Motion Detected"), daemon=True).start()
                elif request == "motion_second":
                    threading.Thread(target=send_photo, args=(output_image, "Person Still at Door"), daemon=True).start()

            capture_queue.task_done()
        except Empty:
            continue
        except Exception as e:
            print(f"Error in image capture thread: {e}")
            time.sleep(0.1)

def doorbell_monitor():
    global last_doorbell_time
    if doorbell_line is None:
        return

    print("Doorbell monitor ready — press the button")
    last_press = 0

    while True:
        try:
            if doorbell_line.get_value() == 0:  # PRESSED = LOW
                now = time.time()
                if now - last_press > 0.5:  # 500ms debounce
                    print("🔔🔔🔔 DOORBELL PRESSED!!! 🔔🔔🬬")
                    last_doorbell_time = now
                    client.publish("doorbell/button_pressed", "ON")
                    play_audio(DOORBELL_GREETING)
                    time.sleep(3)
                    capture_queue.put("doorbell_press")
                    last_press = now

                # Wait for release before allowing next press
                while doorbell_line.get_value() == 0:
                    time.sleep(0.01)

            time.sleep(0.01)
        except Exception as e:
            print(f"Button error: {e}")
            time.sleep(0.1)

def delete_old_files():
    """Delete image files older than 7 days"""
    directory = IMAGES_DIR          # ← changed from AUDIO_CONFIG['images_dir']
    now = datetime.datetime.now()
    for filename in os.listdir(directory):
        if filename.startswith("snap") and filename.endswith(".jpg"):
            try:
                date_str = filename[4:12]
                file_date = datetime.datetime.strptime(date_str, "%m%d%Y")
                if (now - file_date).days > 7:
                    os.remove(os.path.join(directory, filename))
                    print(f"Deleted old file: {filename}")
            except Exception as e:
                print(f"Error deleting old file {filename}: {e}")

def delete_old_files_thread():
    while True:
        delete_old_files()
        time.sleep(86400)

# ──────────────────────────────────────────────────────────────
# CLEAN EXIT ON CTRL+C — FINAL VERSION (ONLY ONE!)
# ──────────────────────────────────────────────────────────────
import signal

shutdown_requested = False

def signal_handler(sig, frame):
    global shutdown_requested
    print("\nCtrl+C pressed — shutting down cleanly...")
    shutdown_requested = True

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
# ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    setup_gpio()   # ← Initialize GPIO (pin 36 / line 7)

    # Load RKNN model
    model, platform = setup_model(type('obj', (), {
        'model_path': MODEL_PATH,
        'target': TARGET_PLATFORM,
        'device_id': DEVICE_ID,
        'camera_id': CAMERA_ID
    }))

    co_helper = COCO_test_helper(enable_letter_box=True)
    print(f"--> Using camera /dev/video{CAMERA_ID} – starting inference")

    # Open camera
    cap = cv2.VideoCapture(CAMERA_ID, cv2.CAP_V4L2)
    if not cap.isOpened():
        print("Cannot open camera – exiting")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    cap.set(cv2.CAP_PROP_FPS, 30)

    # Start background threads
    threading.Thread(target=detection_processor, daemon=True).start()
    threading.Thread(target=lambda: image_capture_thread(cap), daemon=True).start()
    threading.Thread(target=doorbell_monitor, daemon=True).start()
    threading.Thread(target=delete_old_files_thread, daemon=True).start()

    print("All systems go – running 24/7")

    # FPS counter
    frame_count = 0
    fps_start = time.time()

    try:
        while not shutdown_requested:
            with cap_lock:
                ret, frame = cap.read()
            if not ret:
                continue

            #img_src = frame.copy()
            img = co_helper.letter_box(im=frame, new_shape=(640, 640))
            #img = co_helper.letter_box(im=img_src, new_shape=(640, 640))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            input_data = img if platform == 'rknn' else img.transpose(2, 0, 1).reshape(1, 3, 640, 640).astype(np.float32) / 255.0
            input_data = np.expand_dims(input_data, axis=0)

            outputs = model.run([input_data])
            boxes, classes, scores = post_process(outputs)

            # FPS counter - print every 30 frames
            frame_count += 1
            if frame_count % 30 == 0:
                elapsed = time.time() - fps_start
                fps = 30 / elapsed
                print(f"FPS: {fps:.1f}")
                fps_start = time.time()

            # LIVE POPUP WINDOW WITH BOXES (safe for headless)
            #if boxes is not None and len(boxes) > 0:
                #display = img_src.copy()
                #real_boxes = co_helper.get_real_box(boxes)
                #for (box, score, cl) in zip(real_boxes, scores, classes):
                    #if cl == 0:  # person only
                        #x1, y1, x2, y2 = map(int, box)
                        #cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 3)
                        #cv2.putText(display, f"Person {score:.2f}", (x1, y1-10),
                                   # cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

               # try:
                   # cv2.imshow("Doorbell Live View", display)
                   # if cv2.waitKey(1) == ord('q'):
                       # shutdown_requested = True
               # except:
                   # pass  # silently ignore if no display (headless)

            # Person detection queue
            if boxes is not None:
                real_boxes = co_helper.get_real_box(boxes)
                for box, score, cl in zip(real_boxes, scores, classes):
                    if cl == 0:  # person
                        detection_queue.put("person_detected", block=False)
                        break

    except KeyboardInterrupt:
        print("\nCtrl+C detected — shutting down...")

    finally:
        # Clean shutdown — everything released safely
        print("Cleaning up...")
        if 'cap' in locals():
            cap.release()
            print("→ Camera released")
        if 'model' in globals():
            model.release()
            print("→ RKNN model released")
        client.loop_stop()
        client.disconnect()
        print("→ MQTT stopped")
        if doorbell_line is not None:
            try:
                doorbell_line.release()
                print("→ GPIO released")
            except:
                pass
        print("Goodbye!")
