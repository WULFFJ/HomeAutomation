import logging
import threading
import time
import datetime
import os
import sys
import argparse
import numpy as np
import cv2
import requests
import random
import json
import ssl
import paho.mqtt.client as mqtt
from queue import Queue, Empty
import gpiod

# Keep original logging setup from working script
old_check_level = logging._checkLevel

def new_check_level(level):
    if isinstance(level, str):
        level = level.upper()
        return getattr(logging, level, None)
    return old_check_level(level)

logging._checkLevel = new_check_level
logging.basicConfig()

# EXACT SAME PATH SETUP FROM WORKING SCRIPT
_current_dir = os.path.dirname(os.path.abspath(__file__))
_myapp_dir = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(os.path.join(_myapp_dir, 'py_utils'))

from py_utils.coco_utils import COCO_test_helper

# EXACT SAME CONSTANTS FROM WORKING SCRIPT
OBJ_THRESH = 0.25
NMS_THRESH = 0.45
IMG_SIZE = (640, 640)
CLASSES = ("person",)

coco_id_list = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 27, 28, 31, 32, 33, 34,
                35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63,
                64, 65, 67, 70, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 84, 85, 86, 87, 88, 89, 90]

# Doorbell configuration
MQTT_CONFIG = {
    'broker': 'yourlocaldomain.local',
    'port': 8883,
    'username': 'yourusername',
    'password': 'yourpassword',
    'ca_certs': '/home/yourdirectory/cert/ca.pem',
    'certfile': '/home/yourdirectory/cert/client.crt',
    'keyfile': '/home/yourdirectory/cert/client-key.pem'
}

TELEGRAM_CONFIG = {
    'bot_token': 'yourtelegrambottoken',
    'chat_id': '-yourtelegramchatid'
}

AUDIO_CONFIG = {
    'sounds_dir': '/home/homeaccount/sounds/',
    'images_dir': '/home/homeaccount/images/',
    'gong_sound': '/home/homeaccount/sounds/Gong.mp3',
    'doorbell_greeting': '/home/homeaccount/sounds/buttonpush/buttongreeting.mp3',
    'greetings': ['Greet1.mp3', 'Greet2.mp3', 'Greet3.mp3', 'Greet4.mp3', 'Greet5.mp3',
                  'Greet6.mp3', 'Greet7.mp3', 'Greet8.mp3', 'Greet9.mp3', 'Greet10.mp3']
}

# ONLY THESE ARE NEW - QUEUES FOR THREAD COMMUNICATION
detection_queue = Queue()
capture_queue = Queue()
last_gong_time = 0
last_doorbell_time = 0
motion_counter = 0
doorbell_line = None

# MQTT Setup
client = mqtt.Client("FrontDoor")
client.username_pw_set(MQTT_CONFIG['username'], MQTT_CONFIG['password'])

client.tls_set(
    ca_certs=MQTT_CONFIG['ca_certs'],
    certfile=MQTT_CONFIG['certfile'],
    keyfile=MQTT_CONFIG['keyfile'],
    cert_reqs=ssl.CERT_REQUIRED,
    tls_version=ssl.PROTOCOL_TLS,
    ciphers=None
)
client.tls_insecure_set(True)
client.connect(MQTT_CONFIG['broker'], MQTT_CONFIG['port'])
client.loop_start()

# EXACT SAME AI PROCESSING FUNCTIONS FROM WORKING SCRIPT - NO CHANGES
def filter_boxes(boxes, box_confidences, box_class_probs):
    """Filter boxes with object threshold."""
    box_confidences = box_confidences.reshape(-1)
    candidate, class_num = box_class_probs.shape

    class_max_score = np.max(box_class_probs, axis=-1)
    classes = np.argmax(box_class_probs, axis=-1)

    _class_pos = np.where(class_max_score * box_confidences >= OBJ_THRESH)
    scores = (class_max_score * box_confidences)[_class_pos]

    boxes = boxes[_class_pos]
    classes = classes[_class_pos]

    return boxes, classes, scores

def nms_boxes(boxes, scores):
    """Suppress non-maximal boxes."""
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
    import torch
    x = torch.tensor(position)
    n, c, h, w = x.shape
    p_num = 4
    mc = c // p_num
    y = x.reshape(n, p_num, mc, h, w)
    y = y.softmax(2)
    acc_metrix = torch.tensor(range(mc)).float().reshape(1, 1, mc, 1, 1)
    y = (y * acc_metrix).sum(2)
    return y.numpy()

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

def setup_model(args):
    model_path = args.model_path
    if model_path.endswith('.pt') or model_path.endswith('.torchscript'):
        platform = 'pytorch'
        from py_utils.pytorch_executor import Torch_model_container
        model = Torch_model_container(args.model_path)
    elif model_path.endswith('.rknn'):
        platform = 'rknn'
        from py_utils.rknn_executor import RKNN_model_container
        model = RKNN_model_container(args.model_path, args.target, args.device_id)
    elif model_path.endswith('onnx'):
        platform = 'onnx'
        from py_utils.onnx_executor import ONNX_model_container
        model = ONNX_model_container(args.model_path)
    else:
        assert False, "{} is not rknn/pytorch/onnx model".format(model_path)
    print('Model-{} is {} model, starting val'.format(model_path, platform))
    return model, platform

# GPIO Setup using gpiod
def setup_gpio():
    global doorbell_line
    try:
        chip = gpiod.Chip("gpiochip3")
        doorbell_line = chip.get_line(5)  # header-40 = bank3 pin5
        doorbell_line.request(
            consumer="doorbell",
            type=gpiod.LINE_REQ_DIR_IN,
            flags=gpiod.LINE_REQ_FLAG_BIAS_PULL_UP
        )
        print("GPIO initialized successfully")
        return True
    except Exception as e:
        print(f"GPIO initialization failed: {e}")
        doorbell_line = None
        return False

# NEW THREAD FUNCTIONS - THESE RUN IN BACKGROUND
def motion_message(chat_id, text, bot_token):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {'chat_id': chat_id, 'text': text}
    try:
        response = requests.post(url, data=data, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error sending message: {e}")
        return None

def send_photo(chat_id, output_image, bot_token, caption="Front Door Motion Detected"):
    if output_image is None or not os.path.exists(output_image):
        print(f"Image file not found: {output_image}")
        return None

    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    try:
        with open(output_image, 'rb') as photo:
            files = {'photo': photo}
            data = {'chat_id': chat_id, 'caption': caption}
            response = requests.post(url, files=files, data=data, timeout=30)
        return response.json()
    except Exception as e:
        print(f"Error sending photo: {e}")
        return None

def play_audio(audio_file):
    """Play audio file"""
    try:
        if os.path.exists(audio_file):
            print(f"Playing audio: {audio_file}")
            os.system(f'mpg123 -q {audio_file}')
        else:
            print(f"Audio file not found: {audio_file}")
    except Exception as e:
        print(f"Error playing audio: {e}")

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
                    # First detection in over 2 minutes
                    last_gong_time = current_time
                    motion_counter = 1
                    client.publish("doorbell/motion_detected", "Motion detected")

                    # Play gong in background thread
                    threading.Thread(target=play_audio, args=(AUDIO_CONFIG['gong_sound'],), daemon=True).start()

                    # Send message
                    motion_message(
                        TELEGRAM_CONFIG['chat_id'],
                        "Front Door Motion Detected",
                        TELEGRAM_CONFIG['bot_token']
                    )
                    capture_queue.put("motion_first")

                elif motion_counter == 1 and (current_time - last_gong_time > 10):
                    # Second detection after at least 10 seconds
                    motion_counter = 2

                    sound = random.choice(AUDIO_CONFIG['greetings'])
                    greeting = os.path.join(AUDIO_CONFIG['sounds_dir'], sound)

                    # Play greeting in background thread
                    threading.Thread(target=play_audio, args=(greeting,), daemon=True).start()

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
    os.makedirs(AUDIO_CONFIG['images_dir'], exist_ok=True)

    while True:
        try:
            request = capture_queue.get(timeout=1)
            print(f"Processing capture request: {request}")

            xdate = datetime.datetime.now().strftime("%m%d%Y"+"-"+"%H%M%S")
            output_image = os.path.join(AUDIO_CONFIG['images_dir'], 'snap' + xdate + '.jpg')

            # Capture frame
            ret, frame = cap.read()
            if ret and frame is not None:
                success = cv2.imwrite(output_image, frame)
                if success:
                    print(f"Image saved: {output_image}")

                    if request == "doorbell_press":
                        send_photo(TELEGRAM_CONFIG['chat_id'], output_image,
                                 TELEGRAM_CONFIG['bot_token'], "Bell Ringer")
                    elif request == "motion_first":
                        send_photo(TELEGRAM_CONFIG['chat_id'], output_image,
                                 TELEGRAM_CONFIG['bot_token'], "Motion Detected")
                    elif request == "motion_second":
                        send_photo(TELEGRAM_CONFIG['chat_id'], output_image,
                                 TELEGRAM_CONFIG['bot_token'], "Person Still at Door")

            capture_queue.task_done()

        except Empty:
            continue
        except Exception as e:
            print(f"Error in image capture thread: {e}")
            time.sleep(0.1)

def doorbell_monitor():
    """Monitor doorbell button using gpiod"""
    global last_doorbell_time, doorbell_line

    if doorbell_line is None:
        print("GPIO not initialized, doorbell monitoring disabled")
        return

    time.sleep(1)
    last_state = doorbell_line.get_value()
    print(f"Doorbell monitor started with state: {last_state}")

    while True:
        try:
            current_state = doorbell_line.get_value()

            if last_state == 1 and current_state == 0:
                time.sleep(0.05)
                confirm_state = doorbell_line.get_value()
                if confirm_state != 0:
                    last_state = current_state
                    continue

                current_time = time.time()
                if current_time - last_doorbell_time < 30:
                    print("Doorbell press ignored - too soon")
                    last_state = current_state
                    time.sleep(0.5)
                    continue

                last_doorbell_time = current_time
                print("DOORBELL BUTTON PRESSED!")
                client.publish("doorbell/button_pressed", "doorbell")
                play_audio(AUDIO_CONFIG['doorbell_greeting'])
                time.sleep(3)

                capture_queue.put("doorbell_press")
                time.sleep(2)

            last_state = current_state
            time.sleep(0.2)

        except Exception as e:
            print(f"Error in doorbell monitor: {e}")
            time.sleep(1)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Smart Doorbell with AI Detection')
    parser.add_argument('--model_path', type=str, required=True, help='model path, could be .pt or .rknn file')
    parser.add_argument('--target', type=str, default='rk3566', help='target RKNPU platform')
    parser.add_argument('--device_id', type=str, default=None, help='device id')
    parser.add_argument('--camera_id', type=int, default=0, help='Camera device ID, e.g., 0 for /dev/video0')
    args = parser.parse_args()

    # Setup model and camera EXACTLY LIKE WORKING SCRIPT
    model, platform = setup_model(args)
    co_helper = COCO_test_helper(enable_letter_box=True)

    print(f"--> Using camera /dev/video{args.camera_id} for live inference.")
    cap = cv2.VideoCapture(args.camera_id, cv2.CAP_V4L2)
    if not cap.isOpened():
        print(f"Error: Could not open camera /dev/video{args.camera_id}.")
        model.release()
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    cap.set(cv2.CAP_PROP_FPS, 30)

    # EXACT SAME FRAME VALIDATION FROM WORKING SCRIPT
    max_retries = 10
    retry_count = 0
    while retry_count < max_retries:
        ret, frame = cap.read()
        if ret and frame is not None:
            break
        print(f"Retrying frame capture ({retry_count + 1}/{max_retries})...")
        retry_count += 1
        cv2.waitKey(100)
    if not ret or frame is None:
        print(f"Error: Failed to grab frame after {max_retries} retries.")
        cap.release()
        model.release()
        sys.exit(1)

    # Initialize GPIO and ensure directories exist
    setup_gpio()
    os.makedirs(AUDIO_CONFIG['images_dir'], exist_ok=True)
    os.makedirs(AUDIO_CONFIG['sounds_dir'], exist_ok=True)

    print("Starting background threads...")

    # Start action threads
    threading.Thread(target=detection_processor, daemon=True).start()
    threading.Thread(target=lambda: image_capture_thread(cap), daemon=True).start()
    threading.Thread(target=doorbell_monitor, daemon=True).start()

    print("All threads started. Running AI detection...")

    try:
        # MAIN LOOP EXACTLY FROM WORKING SCRIPT - NO CHANGES TO PREPROCESSING
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            # EXACT SAME PREPROCESSING FROM WORKING SCRIPT
            img_src = frame.copy()
            pad_color = (0, 0, 0)
            img = co_helper.letter_box(im=img_src, new_shape=(IMG_SIZE[1], IMG_SIZE[0]), pad_color=pad_color)
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            if platform in ['pytorch', 'onnx']:
                input_data = img.transpose((2, 0, 1))
                input_data = input_data.reshape(1, *input_data.shape).astype(np.float32)
                input_data = input_data / 255.
            else:
                input_data = img

            input_data = np.expand_dims(input_data, axis=0)
            outputs = model.run([input_data])
            boxes, classes, scores = post_process(outputs)

            # EXACT SAME DETECTION CHECK FROM WORKING SCRIPT
            if boxes is not None and classes is not None:
                real_boxes = co_helper.get_real_box(boxes)
                for box, score, cl in zip(real_boxes, scores, classes):
                    if cl == 0:  # person class
                        top, left, right, bottom = [int(val) for val in box]
                        print("Person detected @ (%d, %d, %d, %d) with confidence: %.3f"
                              % (top, left, right, bottom, score), flush=True)

                        # ONLY NEW PART - SEND TO ACTION QUEUE
                        try:
                            detection_queue.put("person_detected", block=False)
                        except:
                            pass  # Queue full, skip
                        break

    except KeyboardInterrupt:
        print("\nInterrupted by user.", flush=True)

    finally:
        cap.release()
        model.release()
        print("Camera released and inference stopped.", flush=True)
