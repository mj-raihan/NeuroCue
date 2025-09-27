import json
import os
import time
import tkinter as tk
from tkinter import messagebox
import multiprocessing
import threading
import queue
import json
from datetime import datetime

# Global variables
config = {}
config_lock = threading.Lock()
tkinter_queue = queue.Queue()  # Queue for sending tasks to the Tkinter thread
tkinter_thread = None  # Thread for running Tkinter
root = None  # Tkinter root window
label = None  # Tkinter label for displaying images
stop_event = threading.Event()  # Event to signal threads to stop
window_destroyed = False  # Flag to track if the Tkinter window is destroyed

def load_stimuli():
    """
    Load and read a JSON file containing image stimuli configuration.

    Loads `data/image_stimuli_data_sequence.json` and updates the global
    ``config`` dictionary.
    """
    global config
    try:
        with open("data/image_stimuli_data_sequence.json", "r") as file:
            with config_lock:
                config = json.load(file)
            print("Image Stimuli Program p2: Stimuli configuration loaded successfully.")
    except Exception as e:
        print(f"Image Stimuli Program p2: ERROR loading stimuli configuration: {e}")

def save_config(json_data):
    """
    Save JSON configuration received from parent program.

    Args:
        json_data (str): A JSON-encoded string representing the configuration.

    Side effects:
        - Updates the global ``config`` dictionary.
        - Saves the configuration into
          ``data/image_stimuli_data_sequence.json``.
    """
    global config
    try:
        with config_lock:
            config = json.loads(json_data)
        with open("data/image_stimuli_data_sequence.json", "w") as file:
            json.dump(config, file)
        print("Image Stimuli Program p2: Configuration saved successfully.")
    except Exception as e:
        print(f"Image Stimuli Program p2: ERROR saving configuration: {e}")

def initialize_tkinter():
    """
    Initialize a fullscreen Tkinter window in a separate thread.

    Returns:
        tuple:
            - root (tk.Tk): The Tkinter root window.
            - label (tk.Label): The label widget for displaying content.
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
    
    print("Image Stimuli Program p2: Tkinter window initialized.")
    return root, label

def update_ui(task_type, data=None):
    """
    Update the Tkinter UI depending on the given task type.

    Args:
        task_type (str): One of ``update_label``, ``display_image``,
            or ``close_window``.
        data (Any, optional): Data associated with the task:
            - For ``update_label``: a string to display.
            - For ``display_image``: path to an image file.
            - For ``close_window``: list [timestamps, filenames, json_filename].
    """
    global root, label, window_destroyed
    
    if window_destroyed or root is None:
        return
        
    try:
        if task_type == "update_label":
            label.config(text=data, fg='white', font=("Arial", 100))

        elif task_type == "display_image":
            image = tk.PhotoImage(file=data)
            label.config(image=image, text="")
            label.image = image  # Keep a reference to avoid garbage collection

        elif task_type == "close_window":
            if not window_destroyed:
                print("Image Stimuli Program p2: Closing Tkinter window...")
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
        print(f"Image Stimuli Program p2: ERROR updating UI: {e}")

def cleanup():
    """
    Clean up resources, stop threads, and reset global variables.

    Side effects:
        - Stops all active threads by setting ``stop_event``.
        - Closes Tkinter window if open.
        - Clears timestamps and filenames for stimuli.
    """
    global stop_event, tkinter_thread, window_destroyed, root, label, stimuli_timestamps, stimuli_file
    
    # Signal all threads to stop
    stop_event.set()
    
    # Close Tkinter window if it exists
    if root is not None:
        try:
            print("Image Stimuli Program p2: Closing Tkinter window from cleanup...")
            window_destroyed = True
            root.destroy()
        except Exception as e:
            print(f"Image Stimuli Program p2: Error closing Tkinter window: {e}")
    
    # Reset all Tkinter-related variables
    root = None
    label = None
    window_destroyed = True
    
    # Reset event for future use
    stop_event.clear()

    stimuli_timestamps = []
    stimuli_file = []
    
    print("Image Stimuli Program p2: Cleanup completed.")

def start_stimuli():
    """
    Start displaying images according to the loaded configuration.

    Uses ``config`` values for:
        - fileSequence: Comma-separated image names.
        - fileDuration: Comma-separated durations for each image.
        - initialDelay: Countdown time before starting.

    Displays each image sequentially in a fullscreen Tkinter window,
    logs timestamps, and saves output to JSON.
    """
    global config, root, label, stop_event, window_destroyed, stimuli_timestamps, stimuli_file

    # Initialize frame timestamps list
    stimuli_timestamps = []
    stimuli_file = []
    
    # Reset stop event
    stop_event.clear()
    
    with config_lock:
        if not config:
            print("Image Stimuli Program p2: No configuration loaded. Please load or save a configuration first.")
            return

        # Extract values from the configuration
        file_sequence = config.get("fileSequence", "").split(",")
        file_duration = list(map(int, config.get("fileDuration", "").split(",")))
        initial_delay = int(config.get("initialDelay", 0))

        # Remove any leading/trailing spaces from filenames
        file_sequence = [file.strip() for file in file_sequence]

        # Check if the number of files and durations match
        if len(file_sequence) != len(file_duration):
            print("Image Stimuli Program p2: ERROR: The number of files and durations do not match.")
            return
    
    # Initialize Tkinter window
    try:
        # Create new Tkinter window
        global root, label
        root, label = initialize_tkinter()
        window_destroyed = False

        timestamp = time.strftime('%Y%m%d_%H%M%S')
        output_filename = f"data/image_stimuli_start_time_{timestamp}.json"

        # Initial delay countdown
        for i in range(initial_delay, 0, -1):
            if stop_event.is_set():
                break  # Exit if stop event is set
            stimuli_timestamps.append(datetime.now().timestamp())
            stimuli_file.append(f"initial_delay_{i}")
            update_ui("update_label", str(i))
            time.sleep(1)

        # Display each image for the specified duration
        for file, duration in zip(file_sequence, file_duration):
            if stop_event.is_set():
                break  # Exit if stop event is set

            try:
                image_path = f"image_stimuli/{file}.png"
                if not os.path.exists(image_path):
                    print(f"Image Stimuli Program p2: ERROR: File {image_path} not found.")
                    continue

                # Display the image
                stimuli_timestamps.append(datetime.now().timestamp())
                stimuli_file.append(image_path)
                update_ui("display_image", image_path)

                # Wait for the specified duration
                time.sleep(duration)
            except Exception as e:
                print(f"Image Stimuli Program p2: ERROR displaying image: {e}")
        
        # Close the window after displaying all images
        update_ui("close_window", [stimuli_timestamps, stimuli_file, output_filename])
    except Exception as e:
        print(f"Image Stimuli Program p2: ERROR in start_stimuli: {e}")
    finally:
        cleanup()

def handle_command(command, conn):
    """
    Handle commands received from parent program.

    Args:
        command (str): Command string such as ``load_stimuli``, ``save_config``,
            ``start_stimuli``, or ``stop_stimuli``.

    Sends back responses over the connection.
    """
    command = command.strip().lower()
    print(f"Image Stimuli Program p2: Received command: {command}")

    if command == "load_stimuli":
        load_stimuli()
        conn.send("Stimuli configuration loaded")
    elif command == "save_config":
        json_data = conn.recv()
        save_config(json_data)
        conn.send("Configuration saved")
    elif command == "start_stimuli":
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
    Main entry point for the Image Stimuli Program (p2).

    Args:
        conn (multiprocessing.Connection): IPC connection for commands.

    Starts the command listener thread and keeps the program running until
    interrupted or explicitly exited.
    """
    try:
        print("Image Stimuli Program p2: Command listener started. Waiting for commands...")
        while True:
            if conn.poll():
                command = conn.recv()
                if command == "exit":
                    print("Image Stimuli Program p2: Received exit command. Shutting down...")
                    stop_event.set()
                    cleanup()
                    break
                if command:
                    handle_command(command, conn)
            time.sleep(0.1)  # Small delay to prevent high CPU usage
    except Exception as e:
        print(f"Image Stimuli Program p2: Command listener error: {e}")
    finally:
        conn.close()
        print("Image Stimuli Program p2: Command listener stopped")

def main(conn):
    """Main function to start the program."""
    print("Image Stimuli Program p2: Program starting...")
    try:
        # Start command listener in a separate thread
        listener_thread = threading.Thread(target=command_listener, args=(conn,))
        listener_thread.daemon = True
        listener_thread.start()

        print("Image Stimuli Program p2: Program ready. Run another program to send commands.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Image Stimuli Program p2: Program interrupted by user")
    finally:
        stop_event.set()
        cleanup()
        print("Image Stimuli Program p2: Program exited")

if __name__ == "__main__":
    # Create a pipe for communication
    parent_conn, child_conn = multiprocessing.Pipe()

    # Start the program
    main(child_conn)