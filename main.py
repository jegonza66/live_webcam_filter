import cv2
import os
from datetime import datetime
import time
import functions
import tensorflow as tf
import json
import threading
from ui import run_ui
import sys
import pyvirtualcam
import numpy as np
import insightface

def visuai():
    # Read initial config
    with open('config.json', 'r') as f:
        config = json.load(f)[0]
    
    # Configure TensorFlow GPU usage based on gpu_ids
    if config.get('gpu_ids', []):  # If gpu_ids is not empty, use GPU
        tf.config.optimizer.set_jit(True)
        gpus = tf.config.list_physical_devices('GPU')
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)
    else:  # If gpu_ids is empty, force CPU
        tf.config.set_visible_devices([], 'GPU')
    
    # Define models with initial config
    models, params = functions.define_models_params(
        img_load_size=config.get('img_load_size', 256),
        output_width=config.get('output_width', 1500),
        output_height=config.get('output_height', 780),
        save_output_path=config.get('save_output_path', 'output/'),
        gpu_ids=config.get('gpu_ids', [])  # Default to empty list (CPU)
    )

    # initialize the camera (only one camera use port = 0)
    cam_port = 0
    cam = cv2.VideoCapture(cam_port)
    try:
        cam.getBackendName()
    except:
        raise ValueError('No camera detected')

    # Get cam parameters
    fps = int(cam.get(cv2.CAP_PROP_FPS)) or 30

    # Define the codec and create VideoWriter object
    if config.get('save_output_bool'):
        output_path = config['save_output_path']
        print(f'saving output to {output_path} folder')
        os.makedirs(output_path, exist_ok=True)
        start_time = datetime.today().strftime('%Y-%m-%d_%H-%M')
        # Use XVID codec instead of mp4v
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        out = cv2.VideoWriter(f'{output_path}/{start_time}.avi', fourcc, fps, 
                            (config['output_width'], config['output_height']))

    # Setup virtual cam only if flag is True
    v_cam = None
    if config.get('use_virtual_cam'):
        v_cam = pyvirtualcam.Camera(width=config['output_width'], height=config['output_height'], fps=30)
        print("Virtual camera started")

    # Run
    frame_count = 0
    # Get last update image time
    last_update_time = time.time()
    config_dict = {}

    # Start config reading thread
    config_thread = threading.Thread(target=functions.read_config,
                                     args=(config_dict, config['output_width'], config['output_height'], config['img_load_size'], config['save_output_path'], config['gpu_ids']),
                                     daemon=True)
    config_thread.start()

    try:
        while True:
            # Read frame
            ret, frame = cam.read()
            if not ret:
                raise ValueError('No camera detected')

            # Apply models in sequence
            model_name = config_dict.get('model_name', '')

            if 'faceswap' in model_name and (config_dict.get('face_image_path', '') != ''
                                                   or isinstance(params['prev_face'], insightface.app.common.Face)
                                                   or (config_dict.get('randomize_face', True) and config_dict.get('face_images_dir', '') != '')):
                try:
                    current_time = time.time()
                    if current_time - last_update_time >= config_dict.get('beats', 4) * 60 / config_dict.get('bpm', 60):
                        if config_dict.get('randomize_face', True) and config_dict.get('face_images_dir', '') != '':
                            try:
                                face_image_path = functions.randomize_face_image(
                                    face_images_dir=config_dict.get('face_images_dir', ''),
                                    current_image=os.path.basename(config_dict.get('face_image_path', '')))
                            except:
                                face_image_path = config_dict.get('face_image_path', '')
                        else:
                            face_image_path = config_dict.get('face_image_path', '')
                        last_update_time = current_time

                    frame, params['prev_face'], params['prev_face_image_path'] = (
                        functions.transform_frame_faceswap(models=models, frame=frame,
                                                           face_detector=params['face_detector'],
                                                           face_image_path=face_image_path,
                                                           prev_face_image_path= params['prev_face_image_path'],
                                                           prev_face=params['prev_face']))
                except:
                    pass

            if 'cyclegan' in model_name:
                try:
                    frame = functions.transform_frame_cyclegan(models=models, model_name=model_name, frame=frame,
                                                             img_load_size=config_dict.get('img_load_size', 256),
                                                             opt=params['opt'], transform=params['transform'])
                except:
                    pass

            if 'yolo' in model_name:
                try:
                    frame = functions.transform_frame_yolo(models=models, frame=frame, device=params['device'])
                except:
                    pass

            if 'style_transfer' in model_name and (config_dict.get('style_image_path', '') != ''
                                                   or isinstance(params['prev_style_image'], np.ndarray)
                                                   or (config_dict.get('randomize_style', True) and config_dict.get('style_images_dir', '') != '')):
                try:
                    current_time = time.time()
                    if current_time - last_update_time >= config_dict.get('beats', 4) * 60 / config_dict.get('bpm', 60):
                        if config_dict.get('randomize_style', True) and config_dict.get('style_images_dir', '') != '':
                            try:
                                style_image_path = functions.randomize_style_image(
                                    style_images_dir=config_dict.get('style_images_dir', ''),
                                    current_image=os.path.basename(config_dict.get('style_image_path', '')))
                            except:
                                style_image_path = config_dict.get('style_image_path', '')
                        else:
                            style_image_path = config_dict.get('style_image_path', '')
                        last_update_time = current_time

                    frame, params['prev_style_image'] = (
                    functions.transform_frame_style_transfer(models=models, frame=frame,
                                                             img_load_size=config_dict.get('img_load_size', 256),
                                                             style_image_path=style_image_path,
                                                             prev_style_image=params['prev_style_image']))
                except:
                    pass

            if 'psych' in model_name:
                try:
                    frame = functions.transform_frame_psych(frame=frame, frame_count=frame_count, amplitude=20, wavelength=150, frame_count_div=3)
                except:
                    pass

            # Resize output frame
            frame = cv2.resize(frame, (config_dict.get('output_width', 1500), config_dict.get('output_height', 780)))

            # Display the captured frame
            cv2.imshow('VisuAI', frame)

            # Optionally route to virtual camera
            if config.get('use_virtual_cam') and v_cam is not None:
                # Brighten up
                frame_vcam = functions.increase_brightness(img=frame, value=50)
                frame_rgb = cv2.cvtColor(frame_vcam, cv2.COLOR_BGR2RGB)  # Convert RGB to RGB for OBS
                frame_flipped = cv2.flip(frame_rgb, 1)
                # Send the frame to the virtual camera
                v_cam.send(frame_flipped)
                v_cam.sleep_until_next_frame()

            # Save frame if output path is set
            if config_dict.get('save_output_bool'):
                out.write(frame)

            # Press 'q' to exit the loop
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            # Update frame count
            frame_count += 1

    finally:
        # Clean up
        cam.release()
        if config_dict.get('save_output_bool'):
            out.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--run":
        visuai()
    else:
        run_ui()