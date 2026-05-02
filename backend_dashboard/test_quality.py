import cv2
import os

VIDEO_PATH = "data/Footage-1.mp4"

cap = cv2.VideoCapture(VIDEO_PATH)
ret, frame = cap.read()
cap.release()

if not ret:
    print("❌ Could not read video")
    exit()

# quality 80 original size (old)
cv2.imwrite("test_q80.jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])

# quality 50 small size (new)
small = cv2.resize(frame, (320, 240))
cv2.imwrite("test_q50.jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 50])

print(f"Quality 80 original: {os.path.getsize('test_q80.jpg')/1024:.1f} KB")
print(f"Quality 50 small:    {os.path.getsize('test_q50.jpg')/1024:.1f} KB")
print(f"\nOpen both files to compare visually.")
print(f"Saved: test_q80.jpg and test_q50.jpg")