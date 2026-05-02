import logging
import cv2
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import vision

client = None
try:
    client = vision.ImageAnnotatorClient()
except DefaultCredentialsError:
    logging.warning('Google Vision credentials were not found. Falling back to empty vision labels.')


def analyze_frame(frame):
    if client is None:
        return []

    _, buffer = cv2.imencode('.jpg', frame)
    image = vision.Image(content=buffer.tobytes())

    response = client.label_detection(image=image)
    labels = [label.description.lower() for label in response.label_annotations]

    return labels