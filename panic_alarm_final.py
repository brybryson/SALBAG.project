from gpiozero import Buzzer, Button
from time import sleep, strftime, localtime, time
import logging
import os
import firebase_admin
from firebase_admin import credentials, storage
from google.cloud.exceptions import GoogleCloudError

# Set the path for logs
logs_folder = "/home/bryant/Desktop/panic_alarm_logs"

# Create the logs directory if it doesn't exist
os.makedirs(logs_folder, exist_ok=True)

# Firebase configuration
cred = credentials.Certificate("/home/bryant/Desktop/salbag-project-4-firebase-adminsdk-xg89v-0845d4c58a.json")  # Path to your service account key file
firebase_admin.initialize_app(cred, {
    'storageBucket': 'salbag-project-4.appspot.com'  # Replace with your Firebase project ID
})

# Initialize the buzzer on GPIO 23 and button on GPIO 17
buzzer = Buzzer(23)
button = Button(17)

# State variables
buzzer_on = False
current_logger = None
pending_uploads = []

def configure_logging():
    global current_logger
    timestamp = strftime("%Y-%m-%d_%H-%M-%S", localtime())
    log_file_path = os.path.join(logs_folder, f"panic_alarm_{timestamp}.log")
    logger = logging.getLogger(timestamp)
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_file_path)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    logger.addHandler(handler)
    logger.info('Button pressed')
    print(f"Log file created: {log_file_path}")  # Verify log file creation
    current_logger = logger
    return log_file_path

def upload_log_to_firebase(log_file_path):
    # Ensure the file exists before attempting to upload
    if os.path.isfile(log_file_path):
        try:
            bucket = storage.bucket()
            blob = bucket.blob(f'alarm_logs/{os.path.basename(log_file_path)}')
            blob.upload_from_filename(log_file_path)
            print(f'Log file {log_file_path} uploaded to Firebase.')
            return True
        except (GoogleCloudError, Exception) as e:
            print(f'Failed to upload {log_file_path}: {e}')
            return False
    else:
        print(f'Log file {log_file_path} does not exist.')
        return False

def manage_old_logs():
    cutoff_time = time() - 10 * 24 * 60 * 60  # 10 days ago
    for log_file in os.listdir(logs_folder):
        log_file_path = os.path.join(logs_folder, log_file)
        if os.path.isfile(log_file_path):
            file_creation_time = os.path.getctime(log_file_path)
            if file_creation_time < cutoff_time:
                if is_uploaded_to_firebase(log_file):
                    os.remove(log_file_path)
                    print(f'Deleted old log file: {log_file_path}')

def is_uploaded_to_firebase(log_file):
    bucket = storage.bucket()
    blob = bucket.blob(f'alarm_logs/{log_file}')
    return blob.exists()

while True:
    if button.is_pressed:
        if not buzzer_on:
            log_file_path = configure_logging()
            buzzer_on = True
            buzzer.on()
            print(1)  # Print 1 when the buzzer is turned on
            current_logger.info('Buzzer turned on')
            sleep(0.5)  # Debounce delay to avoid multiple toggles from a single press
        else:
            buzzer.off()
            buzzer_on = False
            current_logger.info('Buzzer turned off')
            print(0)  # Print 0 when the buzzer is manually turned off
            sleep(0.5)  # Ensure the log file is written

            # Close the current logger to ensure the log file is saved properly
            handlers = current_logger.handlers[:]
            for handler in handlers:
                handler.close()
                current_logger.removeHandler(handler)

            # Attempt to upload log file
            if not upload_log_to_firebase(log_file_path):
                pending_uploads.append(log_file_path)

            sleep(0.5)  # Debounce delay to avoid multiple toggles from a single press

            current_logger = None  # Reset the current logger

    else:
        if buzzer_on:
            print(1)  # Print 1 when the buzzer is still on
        else:
            print(0)  # Print 0 when the button is not pressed and the buzzer is off

    # Retry uploading pending log files
    for log_file_path in pending_uploads[:]:
        if upload_log_to_firebase(log_file_path):
            pending_uploads.remove(log_file_path)

    # Manage old logs
    manage_old_logs()

    sleep(0.1)
