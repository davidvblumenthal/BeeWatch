import cv2 as cv
import numpy as np

cap = cv.VideoCapture("../dataset/video_data/bees_demo1.mp4")


_, frame = cap.read()
old_gray = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)

# Lucas-Kanade params
lk_params = dict(winSize=(15, 15),
                 maxLevel=8,
                 criteria=(cv.TERM_CRITERIA_EPS | cv.TERM_CRITERIA_COUNT, 10, 0.03))


# Mouse positioning
def select_point(event, x, y, flags, params):
    global point, point_selected, old_points
    if event == cv.EVENT_LBUTTONDOWN:
        point = (x, y)
        point_selected = True
        old_points = np.array([[x, y]], dtype=np.float32)


cv.namedWindow("Frame")
cv.setMouseCallback("Frame", select_point)

point_selected = False
point = ()
old_points = np.array([[]], dtype=np.float32)
while True:
    _, frame = cap.read()
    gray_frame = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)

    if point_selected is True:
        cv.circle(frame, point, 5, (0, 0, 255), 2)

        new_points, status, error = cv.calcOpticalFlowPyrLK(
            old_gray, gray_frame, old_points, None, **lk_params)
        old_gray = gray_frame.copy()
        old_points = new_points

        x, y = new_points.ravel()
        cv.circle(frame, (x, y), 5, (0, 255, 0), -1)

    cv.imshow("Frame", frame)

    key = cv.waitKey(1)
    if key == 27:
        break

cap.release()
cv.destroyAllWindows()
