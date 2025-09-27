import json
import os
import time
import tkinter as tk
from tkinter import messagebox
import multiprocessing
import threading
import queue
from datetime import datetime
import cv2
from PIL import Image, ImageTk
import vlc
import platform

# Global variables
config = {}
config_lock = threading.Lock()
tkinter_queue = queue.Queue()  # Queue for sending tasks to the Tkinter thread
tkinter_thread = None  # Thread for running Tkinter
root = None  # Tkinter root window
label = None  # Tkinter label for displaying videos
stop_event = threading.Event()  # Event to signal threads to stop
window_destroyed = False  # Flag to track if the Tkinter window is destroyed

def load_stimuli():
    """
    Load and read a JSON file containing stimuli configuration.

    Loads the configuration from:
        data/video_stimuli_data_sequence.json

    Updates the global `config` dictionary with:
    - fileSequence: comma-separated filenames
    - fileDuration: comma-separated durations
    - initialDelay: delay before the first stimulus
    """
    global config
    try:
        with open("data/video_stimuli_data_sequence.json", "r") as file:
            with config_lock:
                config = json.load(file)
            print("Video Stimuli Program p4: Stimuli configuration loaded successfully.")
    except Exception as e:
        print(f"Video Stimuli Program p4: ERROR loading stimuli configuration: {e}")

def save_config(json_data):
    """
    Save JSON configuration received from parent program.

    Args:
        json_data (str): JSON string containing configuration.

    Writes the data to:
        data/video_stimuli_data_sequence.json
    """
    global config
    try:
        with config_lock:
            config = json.loads(json_data)
        with open("data/video_stimuli_data_sequence.json", "w") as file:
            json.dump(config, file)
        print("Video Stimuli Program p4: Configuration saved successfully.")
    except Exception as e:
        print(f"Video Stimuli Program p4: ERROR saving configuration: {e}")

def initialize_tkinter():
    """
    Initialize a fullscreen Tkinter window for video display.

    Returns:
        tuple: (root, label)
            root  -> Tkinter root window
            label -> Tkinter Label widget to display video frames
    """
    global root, label, window_destroyed, tkinter_thread

    # Reset flags
    window_destroyed = False
    
    # Create the Tkinter window in the main thread
    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.configure(background='black')
    label = tk.Label(root, bg='black')
    label.pack(expand=True, fill=tk.BOTH)
    
    # Protocol for window closing
    root.protocol("WM_DELETE_WINDOW", lambda: stop_event.set())
    
    print("Video Stimuli Program p4: Tkinter window initialized.")
    return root, label

def update_ui(task_type, data=None):
    """
    Update the Tkinter UI depending on the task type.

    Args:
        task_type (str): Type of update. Supported values:
            - "update_label" -> Display countdown numbers.
            - "black_screen" -> Replace content with a black screen.
            - "close_window" -> Destroy Tkinter window and save results.
        data (Any): Extra data required by task_type.
    """
    global root, label, window_destroyed
    
    if window_destroyed or root is None:
        return
        
    try:
        if task_type == "update_label":
            label.config(text=data, fg='white', font=("Arial", 100))

        elif task_type == "black_screen":
            label.config(image='', text="", bg='black')

        elif task_type == "close_window":
            if not window_destroyed:
                print("Video Stimuli Program p4: Closing Tkinter window...")
                window_destroyed = True
                root.destroy()
                root = None
                label = None

            # save stimuli timestamps to json
            with open(data[2], 'w') as jsonfile:
                json_data = []
                for i, (ts, fn) in enumerate(zip(data[0], data[1])):
                    dt = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S.%f')
                    json_data.append({
                        'file_shown': fn,
                        'timestamp': ts,
                        'datetime': dt
                    })
                json.dump(json_data, jsonfile, indent=4)

        root.update()
    except Exception as e:
        print(f"Video Stimuli Program p4: ERROR updating UI: {e}")

def play_video(video_path, stimuli_timestamps, stimuli_file):
    """
    Play a video file (with audio) inside the Tkinter window using VLC.

    Args:
        video_path (str): Path to the video file (.mp4 expected).
        stimuli_timestamps (list): List to append presentation timestamps.
        stimuli_file (list): List to append filenames of presented stimuli.

    Returns:
        bool: True if playback succeeded, False otherwise.
    """
    global stop_event, root, label

    player = None
    instance = None

    if not os.path.exists(video_path):
        print(f"Video Stimuli Program p4: ERROR: Video file {video_path} not found.")
        return False

    try:
        # Create VLC player
        instance = vlc.Instance('--quiet', '--no-video-title-show', '--no-osd', '--no-snapshot-preview')
        player = instance.media_player_new()
        

        # Set the video file
        media = instance.media_new(video_path)
        player.set_media(media)

        # sound control
        # player.audio_set_mute(True)
        # player.audio_set_mute(False)
        # player.audio_set_volume(100)

        # Set the output to Tkinter window
        hwnd = label.winfo_id()  # Get the window handle
        player.set_hwnd(hwnd)    # Windows
        # For Linux: player.set_xwindow(hwnd)
        # For Mac: player.set_nsobject(hwnd)

        # Record start time
        stimuli_timestamps.append(datetime.now().timestamp())
        stimuli_file.append(video_path)
        # Play the video
        player.play()
        print(f"Video Stimuli Program p4: Playing {video_path}...")

        # Wait until the video is finished or stop_event is set
        while not stop_event.is_set():
            state = player.get_state()
            if state in [vlc.State.Ended, vlc.State.Error]:
                break
            root.update()
            time.sleep(0.1)

        # Stop the player
        player.stop()

        return True

    except Exception as e:
        print(f"Video Stimuli Program p4: ERROR playing video {video_path}: {e}")
        return False
    finally:
        # Ensure proper cleanup of VLC resources
        if player is not None:
            player.stop()
            player.release()
        if instance is not None:
            instance.release()
    
def cleanup():
    """
    Clean up resources and stop all active threads.

    Actions:
    - Set stop_event.
    - Clear Tkinter queue.
    - Destroy Tkinter window if active.
    - Reset global variables and clear stimulus lists.
    """
    global stop_event, tkinter_thread, window_destroyed, root, label, stimuli_timestamps, stimuli_file, tkinter_queue
    
    # Signal all threads to stop
    stop_event.set()
    
    # Clear the queue
    while not tkinter_queue.empty():
        try:
            tkinter_queue.get_nowait()
        except queue.Empty:
            break
    
    # Close Tkinter window if it exists
    if root is not None:
        try:
            print("Video Stimuli Program p4: Closing Tkinter window from cleanup...")
            window_destroyed = True
            root.after(100, root.destroy)  # Give time for pending operations
        except Exception as e:
            print(f"Video Stimuli Program p4: Error closing Tkinter window: {e}")
    
    # Reset all variables
    root = None
    label = None
    window_destroyed = True
    
    # Clear stimuli lists
    stimuli_timestamps = []
    stimuli_file = []
    
    # Reset event for future use
    if stop_event.is_set():
        stop_event.clear()
    
    print("Video Stimuli Program p4: Cleanup completed.")

def start_stimuli():
    """
    Start presenting video stimuli according to the loaded configuration.
    """
    global config, root, label, stop_event, window_destroyed, stimuli_timestamps, stimuli_file

    # Initialize frame timestamps list
    stimuli_timestamps = []
    stimuli_file = []
    
    # Reset stop event
    stop_event.clear()
    
    with config_lock:
        if not config:
            print("Video Stimuli Program p4: No configuration loaded. Please load or save a configuration first.")
            return

        # Extract values from the configuration
        file_sequence = config.get("fileSequence", "").split(",")
        file_duration = list(map(int, config.get("fileDuration", "").split(",")))
        initial_delay = int(config.get("initialDelay", 0))

        # Remove any leading/trailing spaces from filenames
        file_sequence = [file.strip() for file in file_sequence]

        # Check if the number of files and durations match
        if len(file_sequence) != len(file_duration):
            print("Video Stimuli Program p4: ERROR: The number of files and durations do not match.")
            return
    
    # Initialize Tkinter window
    try:
        # Create new Tkinter window
        global root, label
        root, label = initialize_tkinter()
        window_destroyed = False

        timestamp = time.strftime('%Y%m%d_%H%M%S')
        output_filename = f"data/video_stimuli_start_time_{timestamp}.json"
        
        # Initial delay countdown
        for i in range(initial_delay, 0, -1):
            if stop_event.is_set():
                break  # Exit if stop event is set
            stimuli_timestamps.append(datetime.now().timestamp())
            stimuli_file.append(f"initial_delay_{i}")
            update_ui("update_label", str(i))
            time.sleep(1)

        # Display each video with black screen intervals
        for file, duration in zip(file_sequence, file_duration):
            if stop_event.is_set():
                break  # Exit if stop event is set

            try:
                video_path = f"video_stimuli/{file}.mp4"  # Assuming video files are in MP4 format
                
                # Play the video
                if not play_video(video_path, stimuli_timestamps, stimuli_file):
                    continue
                
                # Show black screen for the specified duration
                if not stop_event.is_set():
                    stimuli_timestamps.append(datetime.now().timestamp())
                    stimuli_file.append("black_screen")
                    update_ui("black_screen")
                    time.sleep(duration)
                    
            except Exception as e:
                print(f"Video Stimuli Program p4: ERROR displaying video: {e}")
        
        # Close the window after displaying all videos
        update_ui("close_window", [stimuli_timestamps, stimuli_file, output_filename])
    except Exception as e:
        print(f"Video Stimuli Program p4: ERROR in start_stimuli: {e}")
    finally:
        cleanup()

def handle_command(command, conn):
    """
    Handle commands received from parent program via Pipe.

    Supported commands:
        - "load_video_stimuli" : Load configuration.
        - "save_video_config"  : Save configuration received via Pipe.
        - "start_video_stimuli": Start presenting stimuli.
        - "stop_stimuli"       : Stop presentation and cleanup.
    """
    command = command.strip().lower()
    print(f"Video Stimuli Program p4: Received command: {command}")

    if command == "load_video_stimuli":
        load_stimuli()
        conn.send("Stimuli configuration loaded")
    elif command == "save_video_config":
        json_data = conn.recv()
        save_config(json_data)
        conn.send("Configuration saved")
    elif command == "start_video_stimuli":
        # Make sure any previous resources are cleaned up
        cleanup()
        # Start new stimuli session in a new thread
        start_thread = threading.Thread(target=start_stimuli)
        start_thread.daemon = True
        start_thread.start()
        conn.send("Stimuli started")
    elif command == "stop_stimuli":
        stop_event.set()  # Signal to stop
        cleanup()
        conn.send("Stimuli stopped")
    else:
        conn.send(f"Unknown command: {command}")

def command_listener(conn):
    """
    Listen for commands from parent program.

    Loops until "exit" command is received.
    Dispatches valid commands to `handle_command`.
    """
    try:
        print("Video Stimuli Program p4: Command listener started. Waiting for commands...")
        while True:
            if conn.poll():
                command = conn.recv()
                if command == "exit":
                    print("Video Stimuli Program p4: Received exit command. Shutting down...")
                    stop_event.set()
                    cleanup()
                    break
                if command:
                    handle_command(command, conn)
            time.sleep(0.1)  # Small delay to prevent high CPU usage
    except Exception as e:
        print(f"Video Stimuli Program p4: Command listener error: {e}")
    finally:
        conn.close()
        print("Video Stimuli Program p4: Command listener stopped")

def main(conn):
    """
    Main entry point for the program.

    Starts the command listener thread and waits for external commands.
    Exits gracefully on KeyboardInterrupt or "exit" command.
    """
    print("Video Stimuli Program p4: Program starting...")
    try:
        # Start command listener in a separate thread
        listener_thread = threading.Thread(target=command_listener, args=(conn,))
        listener_thread.daemon = True
        listener_thread.start()

        print("Video Stimuli Program p4: Program ready. Run another program to send commands.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Video Stimuli Program p4: Program interrupted by user")
    finally:
        stop_event.set()
        cleanup()
        print("Video Stimuli Program p4: Program exited")

if __name__ == "__main__":
    # Create a pipe for communication
    parent_conn, child_conn = multiprocessing.Pipe()

    # Start the program
    main(child_conn)