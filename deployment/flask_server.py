"""
Flask server
This server makes it very easy to run, view results and configure our model. 
Warning: this server starts in Debug mode and is visible in your local network
Provide a data folder under yolov5/ with images or video. Also a evaluation folder eval_data under tracking.
"""

import os, sys
currentdir = os.path.dirname(os.path.realpath(__file__))
parentdir = os.path.dirname(currentdir)
sys.path.append(parentdir)
print("Parent dir", parentdir)
import random
import argparse
from os import listdir
from os.path import isfile, join
import natsort
import cv2
from flask import Flask, render_template, Response, redirect, url_for, request
from flask_bootstrap import Bootstrap
from tracking.tracker_centriod import run_centroid_tracker
from tracking.blob_det_correct_tracker_centroid import run_blob_det_correct_centroid_tracker
from tracking.tracker_no_blob import run_no_blob_tracker
from tracking.tracker_no_objdet import run_no_tracker
from tracking.blob_det_add_tracker_centroid import run_blob_det_add_centroid_tracker
from datetime import datetime
import numpy as np
import json

def arguments_parse():
    parser = argparse.ArgumentParser()
    parser.add_argument('--weights', nargs='+', type=str, default=parentdir+'/yolov5_trainingArtefacts/adjusted_data_augmentation/weights_adjusted_data_augmentation/best.pt', help='model.pt path(s)')
    parser.add_argument('--source', type=str, default=parentdir+'/yolov5/data/bees_demo1.mp4', help='file, camera for webcam')
    parser.add_argument('--imgsz', '--img', '--img-size', type=int, default=640, help='inference size (pixels)')
    parser.add_argument('--conf-thres', type=float, default=0.25, help='confidence threshold')
    parser.add_argument('--iou-thres', type=float, default=0.45, help='NMS IoU threshold')
    parser.add_argument('--max-det', type=int, default=1000, help='maximum detections per image')
    parser.add_argument('--device', default='', help='cuda device, i.e. 0 or 0,1,2,3 or cpu')
    parser.add_argument('--view-img', default=False, action='store_true', help='show results')
    parser.add_argument('--save-txt', default=False, action='store_true', help='save results to *.txt')
    parser.add_argument('--save-conf', default=False, action='store_true', help='save confidences in --save-txt labels')
    parser.add_argument('--save-crop', action='store_true', help='save cropped prediction boxes')
    parser.add_argument('--nosave', default=True, action='store_true', help='do not save images/videos')
    parser.add_argument('--classes', nargs='+', type=int, help='filter by class: --class 0, or --class 0 2 3')
    parser.add_argument('--agnostic-nms', action='store_true', help='class-agnostic NMS')
    parser.add_argument('--augment', action='store_true', help='augmented inference')
    parser.add_argument('--update', action='store_true', help='update all models')
    parser.add_argument('--project', default=parentdir+'/yolov5/runs/detect', help='save results to project/name')
    parser.add_argument('--name', default='exp', help='save results to project/name')
    parser.add_argument('--exist-ok', action='store_true', help='existing project/name ok, do not increment')
    parser.add_argument('--line-thickness', default=3, type=int, help='bounding box thickness (pixels)')
    parser.add_argument('--hide-labels', default=False, action='store_true', help='hide labels')
    parser.add_argument('--hide-conf', default=False, action='store_true', help='hide confidences')
    parser.add_argument('--half', action='store_true', help='use FP16 half-precision inference')
    opt = parser.parse_args()

    ### TRACKER AND TYPE OF DETECTION
    parser.add_argument('--maxDisappeared', default=5,
                        help='maximum consecutive frames a given object is allowed to be marked as "disappeared"')
    parser.add_argument('--save_tracking_img', default=False,
                        help='if tracking image results and images should be safed')
    parser.add_argument('--save_tracking_text', default=False,
                        help='if tracking text results and images should be safed')
    parser.add_argument('--show_tracking', default=False, help='view tracking')
    parser.add_argument('--show_trajectories', default=True, help='view tracking trajectories')
    parser.add_argument('--show_info', default=True, help='yield back img and info for flask')
    parser.add_argument('--yield_back', default=True, help='yield back img and info for flask')
    parser.add_argument('--det_and_blob', default=True,
                        help='when using blob detection add object det as a checker')
    parser.add_argument('--matching_threshold', default=100,
                        help='threshold between detections from blob detection and object detection')
    parser.add_argument('--tracker_threshold', default=150,
                        help='threshold between detections tracked and detected')
    parser.add_argument('--show_blob_update', default=True,
                        help='show when a blob is detected')
    args = parser.parse_args()

    return opt, args

global args
global opt
opt, args = arguments_parse()
path_data = parentdir + "/yolov5/data/"
path_eval = parentdir + "/tracking/eval_data/"
global file_path, tracker_sel, det_sel
tracker_sel = "NO tracker"
global tracker_info
track_info = {
    "time": [],
    "frame": [],
    "no_det_cur": [],
    "no_tr_cur": [],
    "ids_cur": [],
    "sum_tr": []
} # time, frame, no detec, no tracks, track ids

app = Flask(__name__)
bootstrap = Bootstrap(app)

# Start page
@app.route('/')
def index():
    return render_template('index.html')

# Source: choose source (image, video, camera) and method of detection
@app.route('/source', methods=['GET'])
def source():
    # get files in ./data/ to select and infere on
    file_list = [f for f in listdir(path_data) if isfile(join(path_data, f)) and (f[-3:] in ["mp4", "avi", "png", "jpg"])]
    print(file_list)
    file_list = (natsort.natsorted(file_list))
    print(file_list)
    file_list.append("Camera")
    print(file_list)
    detection_list = ["Object Detection", "Blob Detection", "Blob corrected by Object Det", "Blob and Object Det"]
    return render_template('source.html', file_list=file_list, detection_list=detection_list)

# Post choices from source
@app.route('/source_selected', methods=['POST'])
def source_selected():
    global opt, file_path, det_sel
    if request.form.get('file_select') != "Camera":
        file_path = path_data + request.form.get('file_select')
    else:
        file_path = request.form.get('file_select')
    opt.source = file_path
    print(file_path) # only file names

    det_sel = file_path = request.form.get('detection_select')

    if det_sel in ["Object Detection", "Blob corrected by Object Det", "Blob and Object Det"]:
        return redirect(url_for('object_detection_settings'))
    else:
        return redirect(url_for('tracker'))

# Configure the object detection
@app.route('/object_detection_settings', methods=['GET'])
def object_detection_settings():
    return render_template('object_detection_settings.html')

# Post choices of object detection
@app.route('/objdet_set', methods=['POST'])
def objdet_set():
    global opt, det_sel
    if request.form.get('save_img') == "on":
        opt.nosave = False
    else:
        opt.nosave = True
    print(opt.nosave)
    if request.form.get('save_txt') == "on":
        opt.save_txt = True
    else:
        opt.save_txt = False
    print(opt.save_txt)
    if request.form.get('save_conf') == "on":
        opt.save_conf = True
    else:
        opt.save_conf = False
    print(opt.save_conf)
    opt.conf_thres = float(request.form.get('conf_thres'))/100
    print(opt.conf_thres)

    return redirect(url_for('tracker'))

# Choose tracker
@app.route('/tracker', methods=['GET'])
def tracker():
    global det_sel
    if det_sel in ["Blob corrected by Object Det", "Blob and Object Det"]:
        # tracker needed
        tracker_list = ["Centriod"]
    else:
        tracker_list = ["Centriod", "NO tracker"]
    return render_template('tracker.html', tracker_list=tracker_list)

# Post choices of the tracker
@app.route('/tracker_selected', methods=['POST'])
def tracker_selected():
    global tracker_sel
    tracker_sel = request.form.get('tracker_select')
    #print(tracker_sel)
    if tracker_sel == "Centriod":
        return redirect(url_for('centriod_tracker'))
    elif tracker_sel == "NO tracker":
        return redirect(url_for('inference'))
    return redirect(url_for('tracker'))

# Configure the object detection
@app.route('/centriod_tracker', methods=['GET'])
def centriod_tracker():
    return render_template('centriod_tracker.html')

# Run inference, stream video
@app.route('/inference', methods=['GET', 'POST'])
def inference():
    global tracker_sel
    global args
    global track_info
    track_info = {
        "time": [],
        "frame": [],
        "no_det_cur": [],
        "no_tr_cur": [],
        "ids_cur": [],
        "sum_tr": []
    }
    if tracker_sel == "Centriod":
        maxDis = request.form["maxDisappeared"]
        args.maxDisappeared = int(maxDis)
        print(args.maxDisappeared)
        tracker_threshold = request.form["tracker_threshold"]
        args.tracker_threshold = int(tracker_threshold)
        print(args.tracker_threshold)
        matching_threshold = request.form["matching_threshold"]
        args.matching_threshold = int(matching_threshold)
        print(args.matching_threshold)

        if request.form.get('show_trajectories') == "on":
            args.show_trajectories = True
        else:
            args.show_trajectories = False
        print(args.show_trajectories)
        if request.form.get('show_info') == "on":
            args.show_info = True
        else:
            args.show_info = False
        print(args.show_info)
        if request.form.get('save_tracking_img') == "on":
            args.save_tracking_img = True
        else:
            args.save_tracking_img = False
        print(args.save_tracking_img)
        if request.form.get('save_tracking_text') == "on":
            args.save_tracking_text = True
        else:
            args.save_tracking_text = False
        print(args.save_tracking_text)

    return render_template('inference.html')

# documentation page
@app.route('/documentation', methods=['GET', 'POST'])
def documentation():
    return render_template('documentation.html')

# save information from tracker
def save_info_tracker(frame_no, no_det, no_tr, ids, sum_tr):
    """
    Save information
    :param frame_no:
    :param no_det:
    :param no_tr:
    :param ids:
    :param sum_tr:
    :return:
    """
    global track_info
    track_info["time"].append(datetime.now().strftime("%H:%M:%S"))
    track_info["frame"].append(frame_no)
    track_info["no_det_cur"].append(no_det)
    if no_tr is not None:
        track_info["no_tr_cur"].append(no_tr)
    if ids is not None:
        track_info["ids_cur"].append(ids)
    if ids is not None:
        track_info["sum_tr"].append(sum_tr)
    #print(track_info)

# Run generator tracker and yield itself the image to inference
def info_tracker():
    global tracker_sel, args, opt, det_sel

    if tracker_sel == "Centriod" and det_sel == "Object Detection":
        for frame, no_det, no_tr, sum_tr, _, frame_no, ids in run_centroid_tracker(opt, args):
            save_info_tracker(frame_no, no_det, no_tr, ids, sum_tr)
            ret, buffer = cv2.imencode('.png', frame)
            img = buffer.tobytes()
            yield (b'--frame\r\n'
                    b'Content-Type: image/png\r\n\r\n' + img + b'\r\n')
    elif tracker_sel == "NO tracker" and det_sel == "Object Detection":
        for frame, no_det, _, frame_no in run_no_tracker(opt, args):
            save_info_tracker(frame_no, no_det, None, None, None)
            ret, buffer = cv2.imencode('.png', frame)
            img = buffer.tobytes()
            yield (b'--frame\r\n'
                    b'Content-Type: image/png\r\n\r\n' + img + b'\r\n')
    elif tracker_sel == "NO tracker" and det_sel == "Blob Detection":
        for frame, no_det, _, frame_no in run_no_blob_tracker(opt, args):
            save_info_tracker(frame_no, no_det, None, None, None)
            ret, buffer = cv2.imencode('.png', frame)
            img = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/png\r\n\r\n' + img + b'\r\n')
    elif tracker_sel == "Centriod" and det_sel == "Blob Detection":
        args.det_and_blob = False
        for frame, no_det, no_tr, sum_tr, _, frame_no, ids in run_blob_det_correct_centroid_tracker(opt, args):
            save_info_tracker(frame_no, no_det, no_tr, ids, sum_tr)
            ret, buffer = cv2.imencode('.png', frame)
            img = buffer.tobytes()
            yield (b'--frame\r\n'
                    b'Content-Type: image/png\r\n\r\n' + img + b'\r\n')
    elif tracker_sel == "Centriod" and det_sel == "Blob corrected by Object Det":
        args.det_and_blob = True
        for frame, no_det, no_tr, sum_tr, _, frame_no, ids in run_blob_det_correct_centroid_tracker(opt, args):
            save_info_tracker(frame_no, no_det, no_tr, ids, sum_tr)
            ret, buffer = cv2.imencode('.png', frame)
            img = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/png\r\n\r\n' + img + b'\r\n')
    elif tracker_sel == "Centriod" and det_sel == "Blob and Object Det":
        args.det_and_blob = True
        for frame, no_det, no_tr, sum_tr, _, frame_no, ids in run_blob_det_add_centroid_tracker(opt, args):
            save_info_tracker(frame_no, no_det, no_tr, ids, sum_tr)
            ret, buffer = cv2.imencode('.png', frame)
            img = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/png\r\n\r\n' + img + b'\r\n')

# Respone object - streams images to inference page
@app.route('/video_feed')
def video_feed():
    #Video streaming route. Put this in the src attribute of an img tag
    return Response(info_tracker(), mimetype='multipart/x-mixed-replace; boundary=frame')

# Display results of the tracking / detection
@app.route('/results', methods=['GET', 'POST'])
def results():
    global tracker_sel, track_info, args, ids_frame_list, time_cur_g, eval_data_list

    if tracker_sel == "Centriod":
        # get evaluation files
        eval_data_list = [f for f in listdir(path_eval) if
                     isfile(join(path_eval, f)) and (f[-4:] in ["json"])]
        det_cur_g = np.array(track_info["no_det_cur"])
        frame_g = np.array(track_info["frame"]) # time if webcam
        tr_cur_g = np.array(track_info["no_tr_cur"])
        tr_sum_g = np.array(track_info["sum_tr"])
        # no frame, no det, no tracked, sum tracked
        time_cur_g = np.stack((frame_g, det_cur_g, tr_cur_g, tr_sum_g), axis=1)

        # For Candlestick graph
        ids_frame_list = []
        for id in range(0, track_info["sum_tr"][-1]):
            # create list to infer length of bee in the video
            ids_frame_list.append([id])
        for i, ids_frame in enumerate(track_info["ids_cur"]):
            # find all frames in which id is
            for id in ids_frame:
                ids_frame_list[id].append(i)
        for id in range(0, len(ids_frame_list)):
            # get first and last frame no.
            #print(id)
            if ids_frame_list[id][-1] != len(track_info["frame"]) - 1:
                # candle stick: # Bee Id, first frame, first frame, last frame no. - (if maxDis), last frame no.
                # so line will show the frames where it is still tracked
                ids_frame_list[id] = [ids_frame_list[id][0], ids_frame_list[id][1], ids_frame_list[id][1], (ids_frame_list[id][-1] - int(args.maxDisappeared)), ids_frame_list[id][-1]]
                # - max disaperance if not in last frame
            else:
                ids_frame_list[id] = [ids_frame_list[id][0], ids_frame_list[id][1], ids_frame_list[id][1],
                                      ids_frame_list[id][-1], ids_frame_list[id][-1]]
        print(ids_frame_list)
        print(time_cur_g.tolist())
        return render_template('results_track.html', time_det_cur=time_cur_g.tolist(), id_line=ids_frame_list, eval_data_list=eval_data_list)
    elif tracker_sel == "NO tracker":
        det_cur_g = np.array(track_info["no_det_cur"])
        frame_g = np.array(track_info["frame"])  # time if webcam
        time_cur_g = np.stack((frame_g, det_cur_g), axis=1)
        return render_template('results_notrack.html', time_det_cur=time_cur_g.tolist())

    return render_template('results_notrack.html')

# show evaluation graphs
@app.route('/eval_selected', methods=['POST'])
def eval_selected():
    global path_eval, track_info, args, ids_frame_list, time_cur_g, eval_data_list
    eval_sel = path_eval + request.form.get('eval_select')

    with open(eval_sel) as json_file:
        data_eval = json.load(json_file)

    # get a list of ids per frame and a list of all unique ids
    bee_id_list, ids, no_tracked = [], [], []
    for no_frame, frame in enumerate(data_eval['tracking-annotations']):
        bee_id_list_frame = []
        if no_frame == 0:
            # first frame
            no_tracked.append(0)
        else:
            # take last no of tracked
            no_tracked.append(no_tracked[-1])

        for bee in frame["annotations"]:
            id = int((bee["object-name"])[4:])
            bee_id_list_frame.append(id)
            if id not in ids:
                # unseen id
                ids.append(id)
                # add
                no_tracked[-1] = no_tracked[-1] + 1
        bee_id_list.append(bee_id_list_frame)
    print(bee_id_list)
    print(ids)
    print(no_tracked)  # add to graph per frame
    # create list with len of ids
    no_bees, bees_frames = [], []
    for id in ids:
        bees_frames.append([])

    # retrieve how many ids in the frame and the length a id is continuous
    for no_f, bees_frame in enumerate(bee_id_list):
        no_bees.append(len(bees_frame))
        for id in bees_frame:
            bees_frames[id - 1].append(no_f)
    print(no_bees)  # add to graph per frame
    print(bees_frames)

    ids_frame_list_eval = []
    # for candle stick
    for i, id in enumerate(bees_frames):
        ids_frame_list_eval.append([ids[i], id[0], id[0], id[-1], id[-1]])
    print(ids_frame_list_eval)
    print(ids_frame_list)

    # add to graph data
    time_cur_g = time_cur_g.tolist()
    # assert len(time_cur_g) == len(no_bees) == len(no_tracked)
    for no_frame, frame_data in enumerate(time_cur_g):
        frame_data.append(no_bees[no_frame])
        frame_data.append(no_tracked[no_frame])
    print(time_cur_g)

    return render_template('results_track_eval.html', time_det_cur=time_cur_g, id_line=ids_frame_list,
                           eval_data_list=eval_data_list, id_line_eval=ids_frame_list_eval)

if __name__ == '__main__':
    #app.run(debug=True, ssl_context='adhoc') # ssl_context='adhoc' for https https://blog.miguelgrinberg.com/post/running-your-flask-application-over-https

    app.run(host='0.0.0.0', debug=True, port=5000)



















