import os
import sys
import time
import cv2
import numpy as np

# ---- Ensure ONNXRuntime DLLs load properly (Windows safety) ----
onnx_dll_path = os.path.join(sys.prefix, "Lib", "site-packages", "onnxruntime", "capi")
if os.path.exists(onnx_dll_path):
    try:
        os.add_dll_directory(onnx_dll_path)
    except Exception:
        pass

import onnxruntime as ort


class ShrimpDetector:
    def __init__(self, model_path="models/YOLOshrimp.onnx", conf_thresh=0.25, imgsz=416):
        """Initialize ONNX model session and tracking parameters."""
        self.model_path = model_path
        self.conf_thresh = conf_thresh
        self.imgsz = imgsz

        try:
            self.session = ort.InferenceSession(
                model_path, providers=["CPUExecutionProvider"]
            )
            self.input_name = self.session.get_inputs()[0].name
            self.output_names = [o.name for o in self.session.get_outputs()]
            print(f"Loaded ONNX model: {model_path}")
        except Exception as e:
            print("Failed to load ONNX model:", e)
            self.session = None

        # --- NEW: Parameters for Tracking and Counting ---
        self.total_count = 0
        self.count_log_file = "shrimp_count.txt"
        self.load_count() # Load previous count from file

        # Define the counting line (horizontal, in the middle)
        # We assume shrimp move from top-to-bottom
        self.counting_line_x = int(imgsz * 0.5) 
        
        # Tracking parameters
        self.active_tracks = {}  # {id: [cx, cy, frames_unseen]}
        self.next_track_id = 0
        self.counted_track_ids = set()
        
        # How far can a shrimp move (in pixels) between frames?
        self.max_distance = int(imgsz / 8) 
        # How many frames can we lose a shrimp before dropping the track?
        self.max_disappeared_frames = 10 

    def load_count(self):
        """Load the total count from a text file."""
        try:
            if os.path.exists(self.count_log_file):
                with open(self.count_log_file, 'r') as f:
                    self.total_count = int(f.read())
                    print(f"Loaded previous total count: {self.total_count}")
        except Exception as e:
            print(f"Could not load count file: {e}. Starting from 0.")
            self.total_count = 0

    def save_count(self):
        """Save the current total count to a text file."""
        try:
            with open(self.count_log_file, 'w') as f:
                f.write(str(self.total_count))
            print(f"Saved total count ({self.total_count}) to {self.count_log_file}")
        except Exception as e:
            print(f"Error saving count: {e}")

    # ---------------------------------------------------------------
    # Preprocess: resize + letterbox (maintain aspect ratio)
    # ---------------------------------------------------------------
    def preprocess(self, frame):
        h, w = frame.shape[:2]
        scale = min(self.imgsz / w, self.imgsz / h)
        nw, nh = int(w * scale), int(h * scale)

        resized = cv2.resize(frame, (nw, nh))
        top = (self.imgsz - nh) // 2
        bottom = self.imgsz - nh - top
        left = (self.imgsz - nw) // 2
        right = self.imgsz - nw - left

        padded = cv2.copyMakeBorder(
            resized, top, bottom, left, right,
            cv2.BORDER_CONSTANT, value=(114, 114, 114)
        )

        img = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
        img = img.transpose(2, 0, 1) / 255.0
        img = np.expand_dims(img, axis=0).astype(np.float32)
        return img, scale, left, top

    def save_count(self):
        """Save the current total count to a text file."""
        try:
            with open(self.count_log_file, 'w') as f:
                f.write(str(self.total_count))
            print(f"Saved total count ({self.total_count}) to {self.count_log_file}")
        except Exception as e:
            print(f"Error saving count: {e}")

    # --- ADD THIS NEW FUNCTION ---
    def reset_total_count(self):
        """Resets the internal total count to 0 and saves it."""
        print("Resetting total count to 0.")
        self.total_count = 0
        self.counted_track_ids.clear() # Clear the set of counted IDs
        self.active_tracks.clear()     # Clear all current tracks
        self.next_track_id = 0
        self.save_count() # Save the reset "0" to the file
    # --- END OF NEW FUNCTION ---

    # ---------------------------------------------------------------
    # Preprocess: resize + letterbox (maintain aspect ratio)
    # ---------------------------------------------------------------

    # ---------------------------------------------------------------
    # NEW: Tracking and Counting Logic
    # ---------------------------------------------------------------
    def _update_tracker(self, detections, scale, pad_x, pad_y):
        """
        Updates active tracks with new detections and counts line-crossings.
        
        This is a simple centroid tracker with a greedy matching algorithm.
        """
        current_centers = []
        for (x1, y1, x2, y2) in detections:
            # Map box back to padded image space for consistent tracking
            x1_pad = (x1 * scale) + pad_x
            y1_pad = (y1 * scale) + pad_y
            x2_pad = (x2 * scale) + pad_x
            y2_pad = (y2 * scale) + pad_y
            cx = int((x1_pad + x2_pad) / 2)
            cy = int((y1_pad + y2_pad) / 2)
            current_centers.append((cx, cy))

        if not current_centers:
            # No detections, increment unseen frames for all active tracks
            for tid in list(self.active_tracks.keys()):
                self.active_tracks[tid][2] += 1
            return

        if not self.active_tracks:
            # No active tracks, register all new detections
            for (cx, cy) in current_centers:
                self.active_tracks[self.next_track_id] = [cx, cy, 0]
                self.next_track_id += 1
            return

        # Match new detections to existing tracks
        matched_track_ids = set()
        unmatched_center_indices = set(range(len(current_centers)))
        
        # Get current track positions
        track_ids = list(self.active_tracks.keys())
        track_positions = np.array([self.active_tracks[tid][:2] for tid in track_ids])
        
        # Calculate distance matrix (Tracks x Detections)
        dist_matrix = np.linalg.norm(track_positions[:, np.newaxis] - current_centers, axis=2)
        
        # Greedy matching: find best match (closest) for each track
        for i, tid in enumerate(track_ids):
            if dist_matrix.shape[1] == 0:
                break # No more detections to match
                
            min_dist_idx = np.argmin(dist_matrix[i, :])
            min_dist = dist_matrix[i, min_dist_idx]
            
            if min_dist < self.max_distance:
                # This is a match
                new_cx, new_cy = current_centers[min_dist_idx]
                old_cx, old_cy, _ = self.active_tracks[tid]
                
                # --- CHECK FOR COUNTING LINE CROSS ---
                # Check if it crossed the line (moving downwards)
                if (old_cx < self.counting_line_x and 
                    new_cx >= self.counting_line_x):
                    
                    if tid not in self.counted_track_ids:
                        self.total_count += 1
                        self.counted_track_ids.add(tid)
                        print(f"Shrimp counted! Total: {self.total_count}")
                
                # Update track
                self.active_tracks[tid] = [new_cx, new_cy, 0]
                matched_track_ids.add(tid)
                
                # Mark this detection as used and remove from distance matrix
                if min_dist_idx in unmatched_center_indices:
                    unmatched_center_indices.remove(min_dist_idx)
                dist_matrix[:, min_dist_idx] = np.inf 

        # Handle unmatched tracks (disappeared)
        for tid in track_ids:
            if tid not in matched_track_ids:
                self.active_tracks[tid][2] += 1

        # Register new tracks from unmatched detections
        for idx in unmatched_center_indices:
            cx, cy = current_centers[idx]
            self.active_tracks[self.next_track_id] = [cx, cy, 0]
            self.next_track_id += 1

        # Clean up old, lost tracks
        for tid in list(self.active_tracks.keys()):
            if self.active_tracks[tid][2] > self.max_disappeared_frames:
                # print(f"Removing track {tid}")
                del self.active_tracks[tid]
                self.counted_track_ids.discard(tid)


    # ---------------------------------------------------------------
    # Detect and visualize
    # ---------------------------------------------------------------
    def detect(self, frame, draw=True):
        if self.session is None:
            return 0, frame

        h, w = frame.shape[:2]
        input_tensor, scale, pad_x, pad_y = self.preprocess(frame)

        # ---- Run inference ----
        start = time.time()
        outputs = self.session.run(self.output_names, {self.input_name: input_tensor})
        inference_time = (time.time() - start) * 1000

        detections = [] # List of (x1, y1, x2, y2) in original frame coords
        out = outputs[0]

        # Case 1: model already includes NMS
        if len(out.shape) == 3 and out.shape[-1] in [6, 7]:
            for det in out[0]:
                if det is None or len(det) < 6:
                    continue
                x1, y1, x2, y2, conf, cls = det[:6]
                if conf < self.conf_thresh:
                    continue

                # Reverse letterbox to map boxes back to original frame
                x1 = max((x1 - pad_x) / scale, 0)
                y1 = max((y1 - pad_y) / scale, 0)
                x2 = min((x2 - pad_x) / scale, w)
                y2 = min((y2 - pad_y) / scale, h)
                detections.append((x1, y1, x2, y2))

        # Case 2: raw output (no NMS)
        elif len(out.shape) == 3 and out.shape[-1] > 7:
            preds = out[0]
            # Note: This part needs proper NMS.
            # This is a simplified stand-in.
            # For a real application, you should add NMS here.
            for det in preds:
                obj_conf = det[4]
                cls_conf = det[5:].max()
                conf = obj_conf * cls_conf
                if conf < self.conf_thresh:
                    continue

                x, y, bw, bh = det[:4]

                # Reverse letterbox mapping
                x1 = (x - bw / 2 - pad_x) / scale
                y1 = (y - bh / 2 - pad_y) / scale
                x2 = (x + bw / 2 - pad_x) / scale
                y2 = (y + bh / 2 - pad_y) / scale

                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)
                detections.append((x1, y1, x2, y2))
        
        # --- NEW: Update tracker with current detections ---
        # We pass detections in *original* frame coordinates
        # The tracker will map them back to padded-space for tracking
        self._update_tracker(detections, scale, pad_x, pad_y)


        # ---- Draw bounding boxes ----
        frame_count = len(detections)
        if draw:
            overlay = frame.copy()
            for (x1, y1, x2, y2) in detections:
                cv2.rectangle(
                    overlay,
                    (int(x1), int(y1)),
                    (int(x2), int(y2)),
                    (0, 255, 0),
                    1
                )
            
            # Draw active track centers and IDs (in padded-space)
            # We must map them back to original frame for drawing
            for tid, (cx_pad, cy_pad, unseen) in self.active_tracks.items():
                # Map from padded space back to original frame
                cx_orig = int((cx_pad - pad_x) / scale)
                cy_orig = int((cy_pad - pad_y) / scale)
                
                # Check if point is inside the original frame
                if 0 <= cx_orig < w and 0 <= cy_orig < h:
                    color = (0, 0, 255) if tid in self.counted_track_ids else (255, 0, 0)
                    cv2.circle(overlay, (cx_orig, cy_orig), 4, color, -1)
                    cv2.putText(overlay, str(tid), (cx_orig + 5, cy_orig + 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

            # Draw the counting line (mapped back to original frame)
            # (x_line_pad - pad_x) / scale = x_line_orig
            line_x_orig = int((self.counting_line_x - pad_x) / scale)
            
            # Check if the line is inside the frame's WIDTH
            if 0 <= line_x_orig < w: 
                # Draw a VERTICAL line from top (y=0) to bottom (y=h)
                cv2.line(overlay, (line_x_orig, 0), (line_x_orig, h), (0, 255, 255), 2)

            # Semi-transparent overlay
            frame = cv2.addWeighted(overlay, 0.6, frame, 0.4, 0)

            fps = int(1000 / inference_time) if inference_time > 0 else 0
            
            # --- NEW: Updated display text ---
            display_text = f"{fps} FPS | Frame: {frame_count} | Total: {self.total_count}"
            cv2.putText(
                frame,
                display_text,
                (15, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2,
            )

        # Return frame as RGB for PyQt display
        return self.total_count, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


# ---------------------------------------------------------------
# Stand-alone camera test (optional)
# ---------------------------------------------------------------
if __name__ == "__main__":
    detector = ShrimpDetector("models/YOLOshrimp.onnx", conf_thresh=0.25, imgsz=416)
    cap = cv2.VideoCapture(0)
    
    # Set camera resolution (optional, but good for consistency)
    # cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    # cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Failed to grab frame")
                break

            count, vis = detector.detect(frame, draw=True)
            
            # Convert back to BGR for cv2.imshow
            cv2.imshow("Shrimp Detector", cv2.cvtColor(vis, cv2.COLOR_RGB2BGR))
            
            if cv2.waitKey(1) == 27: # Press 'ESC' to quit
                break
    
    finally:
        # --- NEW: Save the count on exit ---
        detector.save_count()
        cap.release()
        cv2.destroyAllWindows()