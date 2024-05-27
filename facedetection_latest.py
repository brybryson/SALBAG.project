import cv2
import os
import numpy as np
import time
from datetime import datetime, timedelta
from firebase_admin import credentials, storage, initialize_app

# Initialize Firebase Admin SDK
cred = credentials.Certificate("/home/bryant/Desktop/salbag-project-4-firebase-adminsdk-xg89v-0845d4c58a.json")
initialize_app(cred, {
    'storageBucket': 'salbag-project-4.appspot.com'
})

# Get a reference to the storage service
storage_client = storage.bucket()
bucket = storage_client

# Load gender and age detection models
faceProto = "/home/bryant/Desktop/age_and_gender_detection/opencv_face_detector.pbtxt"
faceModel = "/home/bryant/Desktop/age_and_gender_detection/opencv_face_detector_uint8.pb"
ageProto = "/home/bryant/Desktop/age_and_gender_detection/age_deploy.prototxt"
ageModel = "/home/bryant/Desktop/age_and_gender_detection/age_net.caffemodel"
genderProto = "/home/bryant/Desktop/age_and_gender_detection/gender_deploy.prototxt"
genderModel = "/home/bryant/Desktop/age_and_gender_detection/gender_net.caffemodel"

MODEL_MEAN_VALUES = (78.4263377603, 87.7689143744, 114.895847746)
ageList = ['(0-2)', '(4-6)', '(8-12)', '(15-20)', '(25-32)', '(38-43)', '(48-53)', '(60-100)']
genderList = ['Male', 'Female']

# Load networks
ageNet = cv2.dnn.readNet(ageModel, ageProto)
genderNet = cv2.dnn.readNet(genderModel, genderProto)
faceNet = cv2.dnn.readNet(faceModel, faceProto)

# Function to detect face, gender, and age
def detect_face_gender_age(frame):
    frameDnn = frame.copy()
    frameHeight = frameDnn.shape[0]
    frameWidth = frameDnn.shape[1]
    blob = cv2.dnn.blobFromImage(frameDnn, 1.0, (300, 300), [104, 117, 123], True, False)

    faceNet.setInput(blob)
    detections = faceNet.forward()

    faces = []
    for i in range(detections.shape[2]):
        confidence = detections[0, 0, i, 2]
        if confidence > 0.7:  # Adjust confidence threshold as needed
            x1 = int(detections[0, 0, i, 3] * frameWidth)
            y1 = int(detections[0, 0, i, 4] * frameHeight)
            x2 = int(detections[0, 0, i, 5] * frameWidth)
            y2 = int(detections[0, 0, i, 6] * frameHeight)
            faces.append([x1, y1, x2, y2])

            # Crop face from frame
            face = frame[y1:y2, x1:x2]
            
            # Preprocess face for gender detection
            blob = cv2.dnn.blobFromImage(face, 1.0, (227, 227), MODEL_MEAN_VALUES, swapRB=False)
            genderNet.setInput(blob)
            genderPreds = genderNet.forward()
            gender = genderList[genderPreds[0].argmax()]

            # Preprocess face for age detection
            blob = cv2.dnn.blobFromImage(face, 1.0, (227, 227), MODEL_MEAN_VALUES, swapRB=False)
            ageNet.setInput(blob)
            agePreds = ageNet.forward()
            age = ageList[agePreds[0].argmax()]

            # Draw rectangle around face
            cv2.rectangle(frameDnn, (x1, y1), (x2, y2), (0, 255, 0), 1)

            # Annotate with gender and age
            label = "{},{}".format(gender, age)
            cv2.rectangle(frameDnn, (x1, y1-30), (x2, y1), (0, 255, 0), -1)
            cv2.putText(frameDnn, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)

    return frameDnn, faces

# Function to upload image to Firebase Storage
def upload_image_to_storage(image_path, bucket, destination_blob_name):
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(image_path)
    print(f"File uploaded to Firebase Storage: {destination_blob_name}")

# Function to check if an image exists in Firebase Storage
def image_exists_in_storage(destination_blob_name):
    blob = bucket.blob(destination_blob_name)
    return blob.exists()

# Function to upload pending images in a directory
def upload_pending_images(directory):
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".jpg"):
                local_path = os.path.join(root, file)
                # Generate the Firebase Storage path based on local path structure
                firebase_path = os.path.relpath(local_path, '/home/bryant/Desktop/face_detected')
                firebase_path = f"images_detected/{firebase_path}"
                if not image_exists_in_storage(firebase_path):
                    upload_image_to_storage(local_path, bucket, firebase_path)

# Function to delete folders older than 15 days
def delete_old_folders(base_dir, days=15):
    now = time.time()
    cutoff = now - (days * 86400)
    for folder in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder)
        if os.path.isdir(folder_path):
            folder_mtime = os.path.getmtime(folder_path)
            if folder_mtime < cutoff:
                # Before deleting, upload any pending images
                upload_pending_images(folder_path)
                # Check again if all images are uploaded before deletion
                if not any(not image_exists_in_storage(os.path.relpath(os.path.join(folder_path, f), '/home/bryant/Desktop/face_detected')) 
                           for f in os.listdir(folder_path) if f.endswith(".jpg")):
                    os.rmdir(folder_path)
                    print(f"Deleted folder: {folder_path}")

# Create a folder with the current date and time
current_datetime = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
output_dir = f'/home/bryant/Desktop/face_detected/{current_datetime}'

# Create the output directory
os.makedirs(output_dir, exist_ok=True)

# Initialize the webcam with retry mechanism
cap = None
while cap is None or not cap.isOpened():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("No webcam detected. Please connect a webcam. Retrying in 5 seconds...")
        time.sleep(5)

# Set the resolution to 640x480
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# Main loop to capture video from the webcam
index = 1
while True:
    # Read a frame from the webcam
    ret, frame = cap.read()
    if not ret:
        print("Failed to capture image. Please ensure the webcam is connected.")
        time.sleep(5)
        continue

    # Detect faces and annotate with gender and age
    frame_detections, faces = detect_face_gender_age(frame)

    # Only save the annotated frame if faces are detected
    if faces:
        img_name = os.path.join(output_dir, f'imagedetected{index}.jpg')
        cv2.imwrite(img_name, frame_detections)
        print(f"Image saved: {img_name}")
        
        # Upload the annotated image to Firebase Storage
        destination_blob_name = f"images_detected/{current_datetime}/imagedetected{index}.jpg"
        upload_image_to_storage(img_name, bucket, destination_blob_name)
        index += 1

    # Display the annotated frame
    cv2.imshow('Webcam', frame_detections)

    # Check for key press to exit the loop
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release the webcam and close all OpenCV windows
cap.release()
cv2.destroyAllWindows()

# Upload any pending images
upload_pending_images('/home/bryant/Desktop/face_detected')

# Delete old folders
delete_old_folders('/home/bryant/Desktop/face_detected', days=15)
