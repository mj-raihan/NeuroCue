import cv2
import threading
import time
import os
import multiprocessing
import json
from datetime import datetime

class VideoRecorder:
    def __init__(self):
        self.recording = False
        self.show_feed = False
        self.video_writer = None
        self.capture = None
        self.output_filename = None
        self.frame_timestamps = []
        self.lock = threading.Lock()
        self.capture_thread = None
        self.display_thread = None

    def setup_camera(self):
        """Initialize the camera and set to highest available frame rate"""
        try:
            self.capture = cv2.VideoCapture(0)
            if not self.capture.isOpened():
                print("Camera Program p1: ERROR: Could not open camera!")
                return False
                
            max_fps = self.capture.get(cv2.CAP_PROP_FPS)
            print(f"Camera Program p1: Maximum FPS supported by camera: {max_fps}")
            self.capture.set(cv2.CAP_PROP_FPS, max_fps)
            
            ret, _ = self.capture.read()
            if not ret:
                print("Camera Program p1: ERROR: Could not read frame from camera!")
                self.capture.release()
                return False
                
            print("Camera Program p1: Camera initialized successfully")
            return True
        except Exception as e:
            print(f"Camera Program p1: ERROR: Camera setup failed: {e}")
            if self.capture is not None:
                self.capture.release()
            return False

    def _capture_frames(self):
        """Internal method to capture frames for both recording and display"""
        try:
            while self.recording or self.show_feed:
                ret, frame = self.capture.read()
                if not ret:
                    print("Camera Program p1: ERROR: Failed to read frame from camera")
                    break
                    
                with self.lock:
                    if self.recording and self.video_writer is not None:
                        self.frame_timestamps.append(datetime.now().timestamp())
                        self.video_writer.write(frame)
                        
                    if self.show_feed:
                        cv2.imshow("Camera Feed", frame)
                        key = cv2.waitKey(1) & 0xFF
                        if key == ord('q') or cv2.getWindowProperty("Camera Feed", cv2.WND_PROP_VISIBLE) < 1:
                            self.show_feed = False
                            cv2.destroyAllWindows()
                            
        except Exception as e:
            print(f"Camera Program p1: ERROR in frame capture: {e}")
        finally:
            print("Camera Program p1: Frame capture stopped")

    def start_recording(self):
        """Start recording video at the highest available frame rate"""
        with self.lock:
            if self.recording:
                print("Camera Program p1: Already recording")
                return
                
            try:
                ret, frame = self.capture.read()
                if not ret:
                    print("Camera Program p1: ERROR: Couldn't read frame to start recording")
                    return
                    
                timestamp = time.strftime('%Y%m%d_%H%M%S')
                self.output_filename = f"data/recording_start_time_{timestamp}.avi"
                self.frame_timestamps = [datetime.now().timestamp()]
                
                fourcc = cv2.VideoWriter_fourcc(*'XVID')
                h, w = frame.shape[:2]
                max_fps = self.capture.get(cv2.CAP_PROP_FPS)
                self.video_writer = cv2.VideoWriter(self.output_filename, fourcc, max_fps, (w, h))
                
                if not self.video_writer.isOpened():
                    print(f"Camera Program p1: ERROR: Failed to open video writer for file: {self.output_filename}")
                    return
                    
                self.video_writer.write(frame)
                self.recording = True
                
                # Start capture thread if not already running
                if not self.show_feed and (self.capture_thread is None or not self.capture_thread.is_alive()):
                    self.capture_thread = threading.Thread(target=self._capture_frames)
                    self.capture_thread.start()
                    
                print(f"Camera Program p1: Recording started - saving to {self.output_filename} at {max_fps} FPS")
                
            except Exception as e:
                print(f"Camera Program p1: ERROR starting recording: {e}")
                if self.video_writer is not None:
                    self.video_writer.release()
                    self.video_writer = None

    def stop_recording(self):
        """Stop video recording"""
        with self.lock:
            if not self.recording:
                print("Camera Program p1: Not recording")
                return
                
            try:
                if self.video_writer is not None:
                    self.video_writer.release()
                    self.video_writer = None

                    json_filename = self.output_filename.replace('.avi', '_timestamps.json')
                    with open(json_filename, 'w') as jsonfile:
                        json_data = [{
                            'frame_number': i,
                            'timestamp': ts,
                            'datetime': datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S.%f')
                        } for i, ts in enumerate(self.frame_timestamps)]
                        json.dump(json_data, jsonfile, indent=4)
                                    
                    print(f"Camera Program p1: Recording stopped and saved to {self.output_filename}")
                    print(f"Camera Program p1: Timestamps saved to {json_filename}")

                    if os.path.exists(self.output_filename):
                        size = os.path.getsize(self.output_filename)
                        print(f"Camera Program p1: File size: {size / 1024:.2f} KB")
                    else:
                        print("Camera Program p1: WARNING: Output file not found!")
                        
            except Exception as e:
                print(f"Camera Program p1: ERROR stopping recording: {e}")
            finally:
                self.recording = False

    def display_feed(self):
        """Function to display camera feed"""
        with self.lock:
            if self.show_feed:
                return
                
            self.show_feed = True
            
            # Start capture thread if not already running
            if self.capture_thread is None or not self.capture_thread.is_alive():
                self.capture_thread = threading.Thread(target=self._capture_frames)
                self.capture_thread.start()
                
            print("Camera Program p1: Camera feed started")

    def close_feed(self):
        """Close camera feed display"""
        with self.lock:
            self.show_feed = False
            time.sleep(0.1)  # Allow time for display loop to exit
            cv2.destroyAllWindows()
            
            # Stop capture thread if not recording
            if not self.recording and self.capture_thread is not None:
                self.capture_thread.join(timeout=1)
                
            print("Camera Program p1: Camera feed closed")

    def video_clean_up(self):
        """Clean up all resources"""
        with self.lock:
            self.show_feed = False
            if self.recording:
                self.stop_recording()
                
            if self.capture is not None:
                self.capture.release()
                self.capture = None
                
            cv2.destroyAllWindows()
            self.frame_timestamps = []
            
            if self.capture_thread is not None:
                self.capture_thread.join(timeout=1)
                
            print("Camera Program p1: All resources cleaned up")

def handle_command(recorder, command, conn):
    """Handle commands received from Program 1"""
    command = command.strip().lower()
    print(f"Camera Program p1: Received command: {command}")
    
    if command == "show_feed":
        recorder.display_feed()
        conn.send("Camera Feed started")
    elif command == "close_feed":
        recorder.close_feed()
        conn.send("Camera Feed closed")
    elif command == "start_recording":
        recorder.start_recording()
        conn.send("Recording started")
    elif command == "stop_recording":
        recorder.stop_recording()
        conn.send("Recording stopped")
    elif command == "video_clean_up":
        recorder.video_clean_up()
        conn.send("Cleaned up video data")
    elif command == "initialize_camera":
        recorder.setup_camera()
        conn.send("Initialized camera")
    else:
        conn.send(f"Unknown command: {command}")

def command_listener(recorder, conn):
    """Listen for commands from Program 1"""
    try:
        print("Camera Program p1: Command listener started. Waiting for commands...")
        
        while True:
            if conn.poll():
                command = conn.recv()
                if command == "exit":
                    print("Camera Program p1: Received exit command. Shutting down...")
                    recorder.video_clean_up()
                    print("Camera Program p1: Program exited")
                    break
                if command:
                    handle_command(recorder, command, conn)
                    
    except Exception as e:
        print(f"Camera Program p1: Command listener error: {e}")
    finally:
        conn.close()
        print("Camera Program p1: Command listener stopped")

def main(conn):
    print("Camera Program p1: Video Program starting...")
    recorder = VideoRecorder()
    
    try:
        listener_thread = threading.Thread(target=command_listener, args=(recorder, conn))
        listener_thread.daemon = True
        listener_thread.start()
        
        print("Camera Program p1: Video Program ready. Run Parent Program to send commands.")
        
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("Camera Program p1: Program interrupted by user")
    finally:
        recorder.video_clean_up()
        print("Camera Program p1: Program exited")

if __name__ == "__main__":
    parent_conn, child_conn = multiprocessing.Pipe()
    main(child_conn)