"""Optional LOCAL-only static face-aware crop recommendation.

This does not track face motion frame-by-frame or run an AI video editor.
It samples bounded real frames using FFmpeg and (when installed) OpenCV's
bundled Haar cascade. Ambiguous, missing, unstable or cropped faces are
skipped. No photos or biometrics are persisted/transmitted.
"""
from __future__ import annotations

import statistics
import subprocess
from pathlib import Path
from typing import Any


class FaceAnalysisUnavailable(ValueError):
    pass


def _norm_anchor(
    face_boxes: list[tuple[float,float,float,float]],
    zoom_pct: int
) -> dict:
    """Each box is (center_x,center_y,width,height) in rendered 9:16 fraction."""
    if type(zoom_pct) is not int or not 105<=zoom_pct<=130:
        raise ValueError("Face framing requires zoom in [1.05x,1.30x]")
    if len(face_boxes)<3:
        return {"status":"skip","reason":"insufficient_unique_face_samples"}
    for box in face_boxes:
        if len(box)!=4 or any(not isinstance(v,(int,float)) or not 0<=v<=1
                              for v in box):
            raise ValueError("Bad normalized face box")
    xs=[b[0] for b in face_boxes];ys=[b[1] for b in face_boxes]
    if max(xs)-min(xs)>0.14 or max(ys)-min(ys)>0.14:
        return {"status":"skip","reason":"moving_face_requires_dynamic_tracking"}
    cx=statistics.median(xs);cy=statistics.median(ys)
    width=statistics.median([b[2] for b in face_boxes])
    height=statistics.median([b[3] for b in face_boxes])
    zoom=zoom_pct/100
    visible=1/zoom
    def anchor(center):
        return max(0,min(1,(center-0.5*visible)/(1-visible)))
    ax,ay=anchor(cx),anchor(cy)
    cropx,cropy=(1-visible)*ax,(1-visible)*ay
    margin=0.04*visible
    if (cx-width/2<cropx+margin or cx+width/2>cropx+visible-margin or
            cy-height/2<cropy+margin or cy+height/2>cropy+visible-margin):
        return {"status":"skip","reason":"face_not_safely_contained"}
    return {"status":"ready","anchor_x_pct":round(ax*100),
            "anchor_y_pct":round(ay*100),
            "samples":len(face_boxes),"method":"local-haar-stable-crop-v1",
            "median_face_x_pct":round(cx*100),
            "median_face_y_pct":round(cy*100)}


def _sample_image(source:Path,at_ms:int, *, ffmpeg_exe:str)->bytes:
    proc=subprocess.run([
        ffmpeg_exe,"-hide_banner","-nostdin","-v","error",
        "-ss",f"{at_ms/1000:.3f}","-i",str(source),
        "-frames:v","1","-vf","scale=w=360:h=640:force_original_aspect_ratio=decrease,"
            "pad=360:640:(ow-iw)/2:(oh-ih)/2",
        "-f","image2pipe","-vcodec","mjpeg","-"
    ],capture_output=True,timeout=10,check=False)
    if proc.returncode or not proc.stdout or len(proc.stdout)>2_000_000:
        raise FaceAnalysisUnavailable("No safe frame from local source")
    return proc.stdout


def propose_face_anchor(
    source:Path, *, start_ms:int,end_ms:int,zoom_pct:int
)->dict:
    """No network or model-weight download; no face identity recognition."""
    if (not source.is_file() or source.is_symlink() or
            type(start_ms) is not int or type(end_ms) is not int or
            not 0<=start_ms<end_ms<=172_800_000 or
            not 500<=end_ms-start_ms<=60_000):
        raise FaceAnalysisUnavailable("Invalid source or bounded time range")
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise FaceAnalysisUnavailable(
            "Face-aware framing requires opt-in local opencv-python-headless"
        ) from exc
    from pausio.media import require_binary
    cascade_path=Path(cv2.data.haarcascades)/"haarcascade_frontalface_default.xml"
    if not cascade_path.is_file():
        raise FaceAnalysisUnavailable("Local OpenCV face cascade missing")
    classifier=cv2.CascadeClassifier(str(cascade_path))
    if classifier.empty():
        raise FaceAnalysisUnavailable("Local OpenCV cascade unavailable")
    exe=require_binary("ffmpeg")
    anchors=[]
    num=5
    ambiguous=0
    for i in range(num):
        at=start_ms+round((end_ms-start_ms)*(i+1)/(num+1))
        encoded=_sample_image(source,at,ffmpeg_exe=exe)
        frame=cv2.imdecode(np.frombuffer(encoded,dtype=np.uint8),cv2.IMREAD_COLOR)
        if frame is None:
            continue
        height,width=frame.shape[:2]
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        boxes=classifier.detectMultiScale(
            gray,scaleFactor=1.12,minNeighbors=6,minSize=(35,35))
        if len(boxes)>1:
            ambiguous+=1
            continue
        if len(boxes)==1:
            x,y,w,h=map(float,boxes[0])
            anchors.append(((x+w/2)/width,(y+h/2)/height,w/width,h/height))
    if ambiguous:
        return {"status":"skip","reason":"multiple_faces_detected"}
    if len(anchors)<3:
        return {"status":"skip","reason":"no_stable_unique_face"}
    return _norm_anchor(anchors,zoom_pct)
