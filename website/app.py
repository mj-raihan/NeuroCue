from flask import Flask, render_template, jsonify, request
import threading
import time
import json
from pylsl import StreamInlet, resolve_stream
import numpy as np
import multiprocessing
from multiprocessing import shared_memory, Manager
import matplotlib.pyplot as plt
import logging
import p1
import p2
import p4
import warnings
import logging

warnings.filterwarnings("ignore")
logging.getLogger('matplotlib').setLevel(logging.CRITICAL)
logging.getLogger('matplotlib.font_manager').setLevel(logging.WARNING)

app = Flask(__name__)

# Sample rates and parameters for Muse
SAMPLE_RATE = 256  # Hz for Muse EEG
ACC_SAMPLE_RATE = 52  # Hz for Muse accelerometer
GYRO_SAMPLE_RATE = 52  # Hz for Muse gyroscope
PPG_SAMPLE_RATE = 64  # Hz for Muse PPG
DISPLAY_TIME = 10  # seconds to display
BUFFER_SIZE = SAMPLE_RATE * DISPLAY_TIME  # Buffer size for EEG data
PPG_BUFFER_SIZE = PPG_SAMPLE_RATE * DISPLAY_TIME  # Buffer size for PPG data

# Global variables for recording
recording = False
recorded_data = {
    "eeg": [],
    "acc": [],
    "gyro": [],
    "ppg": []
}

# Initialize data buffers
eeg_data = np.zeros((4, BUFFER_SIZE))  # 4 EEG channels (TP9, AF7, AF8, TP10)
acc_data = np.zeros((3, BUFFER_SIZE))  # 3 accelerometer axes
gyro_data = np.zeros((3, BUFFER_SIZE))  # 3 gyroscope axes
ppg_data = np.zeros((3, PPG_BUFFER_SIZE))  # 3 PPG channels (PPG1, PPG2, PPG3)

# Initialize time buffers
time_buffer = np.linspace(-DISPLAY_TIME, 0, BUFFER_SIZE)
ppg_time_buffer = np.linspace(-DISPLAY_TIME, 0, PPG_BUFFER_SIZE)

# Create shared memory for inter-process communication
# Create shared memory blocks
eeg_shm = shared_memory.SharedMemory(create=True, size=eeg_data.nbytes)
acc_shm = shared_memory.SharedMemory(create=True, size=acc_data.nbytes)
gyro_shm = shared_memory.SharedMemory(create=True, size=gyro_data.nbytes)
ppg_shm = shared_memory.SharedMemory(create=True, size=ppg_data.nbytes)

# Create numpy arrays that use the shared memory
shared_eeg_data = np.ndarray(eeg_data.shape, dtype=eeg_data.dtype, buffer=eeg_shm.buf)
shared_acc_data = np.ndarray(acc_data.shape, dtype=acc_data.dtype, buffer=acc_shm.buf)
shared_gyro_data = np.ndarray(gyro_data.shape, dtype=gyro_data.dtype, buffer=gyro_shm.buf)
shared_ppg_data = np.ndarray(ppg_data.shape, dtype=ppg_data.dtype, buffer=ppg_shm.buf)

# Initialize the shared memory arrays with the initial data
shared_eeg_data[:] = eeg_data[:]
shared_acc_data[:] = acc_data[:]
shared_gyro_data[:] = gyro_data[:]
shared_ppg_data[:] = ppg_data[:]

# Store shared memory names for the visualization process
shared_memory_names = {
    'eeg': eeg_shm.name,
    'acc': acc_shm.name,
    'gyro': gyro_shm.name,
    'ppg': ppg_shm.name
}

# Connection status flags
eeg_connected = False
acc_connected = False
gyro_connected = False
ppg_connected = False

# Global variables for LSL inlets
eeg_inlet = None
acc_inlet = None
gyro_inlet = None
ppg_inlet = None

# Threading lock for thread safety
data_lock = threading.Lock()

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

# Connect to Muse streams
def connect_to_muse():
    global eeg_connected, acc_connected, gyro_connected, ppg_connected
    global eeg_inlet, acc_inlet, gyro_inlet, ppg_inlet  # Make inlets global

    print("Looking for an EEG stream...")
    eeg_streams = resolve_stream('type', 'EEG')
    if eeg_streams:
        print("Creating inlet for EEG stream...")
        eeg_inlet = StreamInlet(eeg_streams[0])  # Assign to global variable
        eeg_connected = True
    
    # Look for accelerometer stream
    acc_streams = resolve_stream('type', 'Accelerometer')
    if acc_streams:
        print("Creating inlet for Accelerometer stream...")
        acc_inlet = StreamInlet(acc_streams[0])  # Assign to global variable
        acc_connected = True
    
    # Look for gyroscope stream
    gyro_streams = resolve_stream('type', 'Gyroscope')
    if gyro_streams:
        print("Creating inlet for Gyroscope stream...")
        gyro_inlet = StreamInlet(gyro_streams[0])  # Assign to global variable
        gyro_connected = True
    
    # Look for PPG stream
    ppg_streams = resolve_stream('type', 'PPG')
    if ppg_streams:
        print("Creating inlet for PPG stream...")
        ppg_inlet = StreamInlet(ppg_streams[0])  # Assign to global variable
        ppg_connected = True
    
    if eeg_connected or acc_connected or gyro_connected or ppg_connected:
        print("Successfully connected to Muse streams.")
    else:
        print("No streams found. Please ensure the Muse device is connected and streaming.")

# Process data in a separate thread
def process_data_thread():
    global recording, recorded_data
    global eeg_inlet, acc_inlet, gyro_inlet, ppg_inlet
    # Explicitly declare globals for data arrays
    global eeg_data, acc_data, gyro_data, ppg_data

    while True:
        try:
            if eeg_connected and eeg_inlet:
                chunk, timestamps = eeg_inlet.pull_chunk()
                if chunk:
                    with data_lock:  # Acquire lock before modifying shared data
                        for i, sample in enumerate(chunk):
                            # Update the global buffer
                            eeg_data = np.roll(eeg_data, -1, axis=1)
                            for ch in range(4):
                                if ch < len(sample):
                                    eeg_data[ch, -1] = sample[ch]
                            
                            # Update the shared memory buffer
                            shared_eeg_data[:] = eeg_data[:]
                            
                            if recording:
                                recorded_data["eeg"].append({
                                    "timestamp": timestamps[i],
                                    "values": sample[:4]
                                })
            
            if acc_connected and acc_inlet:
                chunk, timestamps = acc_inlet.pull_chunk()
                if chunk:
                    with data_lock:
                        for i, sample in enumerate(chunk):
                            # Update global buffer
                            acc_data = np.roll(acc_data, -1, axis=1)
                            for axis in range(3):
                                if axis < len(sample):
                                    acc_data[axis, -1] = sample[axis]
                            
                            # Update shared memory buffer
                            shared_acc_data[:] = acc_data[:]
                            
                            if recording:
                                recorded_data["acc"].append({
                                    "timestamp": timestamps[i],
                                    "values": sample[:3]
                                })
            
            if gyro_connected and gyro_inlet:
                chunk, timestamps = gyro_inlet.pull_chunk()
                if chunk:
                    with data_lock:
                        for i, sample in enumerate(chunk):
                            # Update global buffer
                            gyro_data = np.roll(gyro_data, -1, axis=1)
                            for axis in range(3):
                                if axis < len(sample):
                                    gyro_data[axis, -1] = sample[axis]
                            
                            # Update shared memory buffer
                            shared_gyro_data[:] = gyro_data[:]
                            
                            if recording:
                                recorded_data["gyro"].append({
                                    "timestamp": timestamps[i],
                                    "values": sample[:3]
                                })
            
            if ppg_connected and ppg_inlet:
                chunk, timestamps = ppg_inlet.pull_chunk()
                if chunk:
                    with data_lock:
                        for i, sample in enumerate(chunk):
                            # Update global buffer
                            ppg_data = np.roll(ppg_data, -1, axis=1)
                            for ch in range(3):
                                if ch < len(sample):
                                    ppg_data[ch, -1] = sample[ch]
                            
                            # Update shared memory buffer
                            shared_ppg_data[:] = ppg_data[:]
                            
                            if recording:
                                recorded_data["ppg"].append({
                                    "timestamp": timestamps[i],
                                    "values": sample[:3]
                                })
            
            time.sleep(0.001)
        except Exception as e:
            logging.error(f"Error in processing thread: {e}")
            time.sleep(0.1)

# Start the data processing thread
thread = threading.Thread(target=process_data_thread, daemon=True)
thread.start()

# Flask routes
@app.route("/")
def index():
    return render_template("index.html")

# subject description start
@app.route("/subject_information", methods=["POST"])
def subject_information():
    data = request.get_json()  # Get JSON data from request
    config = json.loads(data)
    with open("data/subject_information.json", "w") as file:
        json.dump(config, file)
    print("Received Data:", data)  # Debugging
    return jsonify({"status": "Subject Information Saved"})
# subject description end

# command for video feed control
def send_command(conn, command, json_data=None):
    """Send a command to Program 2 via a pipe connection"""
    try:
        # Send the command
        conn.send(command)
        print(f"Sent command: {command}")

        # If the command is 'save_config', send the JSON data, for program 2
        if command == "save_config" or command == "save_video_config" and json_data is not None:
            conn.send(json_data)
            print(f"Sent JSON data: {json_data}")
        
        # Wait for a response
        response = conn.recv()
        print(f"Received response: {response}")
        
        return True
    except Exception as e:
        print(f"Error sending command: {e}")
        return False
    
@app.route("/start_recording_video", methods=["POST"])
def start_recording_video():
    global parent_conn
    cmd = 'start_recording'
    if send_command(parent_conn, cmd):
        return jsonify({"status": f"Recording Camera Feed"})
    else:
        return jsonify({"status": f"Failed to send command: {cmd}. Make sure camera program is running."})

@app.route("/stop_recording_video", methods=["POST"])
def stop_recording_video():
    global parent_conn
    cmd = 'stop_recording'
    if send_command(parent_conn, cmd):
        return jsonify({"status": f"Camera Feed Recording Stopped and Saved"})
    else:
        return jsonify({"status": f"Failed to send command: {cmd}. Make sure camera program is running."})
    
@app.route("/open_visualization_video", methods=["POST"])
def open_visualization_video():
    global parent_conn
    cmd = 'show_feed'
    if send_command(parent_conn, cmd):
        return jsonify({"status": f"Showing Camera Feed"})
    else:
        return jsonify({"status": f"Failed to send command: {cmd}. Make sure camera program is running."})
    
@app.route("/close_visualization_video", methods=["POST"])
def close_visualization_video():
    global parent_conn
    cmd = 'close_feed'
    if send_command(parent_conn, cmd):
        return jsonify({"status": f"Closed Video Feed"})
    else:
        return jsonify({"status": f"Failed to send command: {cmd}. Make sure Program 2 is running."})

# command for muse control
@app.route("/start_recording", methods=["POST"])
def start_recording():
    global recording, recorded_data
    recording = True
    recorded_data = {
        "eeg": [],
        "acc": [],
        "gyro": [],
        "ppg": []
    }
    return jsonify({"status": "Recording started"})

@app.route("/stop_recording", methods=["POST"])
def stop_recording():
    global recording
    recording = False
    filename = f"data/recorded_data_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w") as f:
        json.dump(recorded_data, f, indent=4)
    return jsonify({"status": f"Recording stopped. Data saved to {filename}"})

@app.route("/open_visualization", methods=["POST"])
def open_visualization():
    logging.debug("Opening visualization window")
    # Pass the shared memory names to the visualization process
    process = multiprocessing.Process(
        target=start_visualization,
        args=(shared_memory_names, time_buffer.tolist(), ppg_time_buffer.tolist(), 
              BUFFER_SIZE, PPG_BUFFER_SIZE)
    )
    process.start()
    return jsonify({"status": "Visualization window opened"})


# command for image stimuli program start
@app.route("/load_stimuli_config", methods=["POST"])
def load_stimuli_config():
    global parent_conn2

    cmd = 'load_stimuli'
    if send_command(parent_conn2, cmd):
        return jsonify({"status": f"Loaded Stimuli Configuration"})
    else:
        return jsonify({"status": f"Failed to send command: {cmd}. Make sure Program 2 is running."})
    
@app.route("/save_stimuli_config", methods=["POST"])
def save_stimuli_config():
    global parent_conn2

    data = request.get_json()  # Get JSON data from request
    print("Received Data:", data)  # Debugging

    cmd = 'save_config'
    if send_command(parent_conn2, cmd, data):
        return jsonify({"status": f"Saved Stimuli Configuration"})
    else:
        return jsonify({"status": f"Failed to send command: {cmd}. Make sure Program 2 is running."})
    

@app.route("/start_stimuli", methods=["POST"])
def start_stimuli():
    global parent_conn2
    cmd = 'start_stimuli'
    if send_command(parent_conn2, cmd):
        return jsonify({"status": f"Started Stimuli"})
    else:
        return jsonify({"status": f"Failed to send command: {cmd}. Make sure Program 2 is running."})
# command for image stimuli program end

# command for video stimuli program start
@app.route("/load_video_stimuli_config", methods=["POST"])
def load_video_stimuli_config():
    global parent_conn4

    cmd = 'load_video_stimuli'
    if send_command(parent_conn4, cmd):
        return jsonify({"status": f"Loaded Stimuli Configuration"})
    else:
        return jsonify({"status": f"Failed to send command: {cmd}. Make sure Program 2 is running."})
    
@app.route("/save_video_stimuli_config", methods=["POST"])
def save_video_stimuli_config():
    global parent_conn4

    data = request.get_json()  # Get JSON data from request
    print("Received Data:", data)  # Debugging

    cmd = 'save_video_config'
    if send_command(parent_conn4, cmd, data):
        return jsonify({"status": f"Saved Stimuli Configuration"})
    else:
        return jsonify({"status": f"Failed to send command: {cmd}. Make sure Program 2 is running."})
    

@app.route("/start_video_stimuli", methods=["POST"])
def start_video_stimuli():
    global parent_conn4
    cmd = 'start_video_stimuli'
    if send_command(parent_conn4, cmd):
        return jsonify({"status": f"Started Stimuli"})
    else:
        return jsonify({"status": f"Failed to send command: {cmd}. Make sure Program 2 is running."})
# command for video stimuli program end

def start_visualization(shared_memory_names, time_buffer_list, ppg_time_buffer_list, 
                        buffer_size, ppg_buffer_size):
    import tkinter as tk
    import numpy as np
    from multiprocessing import shared_memory
    import logging
    import matplotlib
    matplotlib.use("TkAgg")  # Explicitly set backend
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.animation import FuncAnimation
    import matplotlib.pyplot as plt
    from scipy import signal
    
    # Convert lists back to numpy arrays
    time_buffer = np.array(time_buffer_list)
    ppg_time_buffer = np.array(ppg_time_buffer_list)
    
    # Attach to the shared memory created in the main process
    eeg_shm = shared_memory.SharedMemory(name=shared_memory_names['eeg'])
    acc_shm = shared_memory.SharedMemory(name=shared_memory_names['acc'])
    gyro_shm = shared_memory.SharedMemory(name=shared_memory_names['gyro'])
    ppg_shm = shared_memory.SharedMemory(name=shared_memory_names['ppg'])
    
    # Create numpy arrays that use the shared memory
    eeg_shape = (4, buffer_size)
    acc_shape = (3, buffer_size)
    gyro_shape = (3, buffer_size)
    ppg_shape = (3, ppg_buffer_size)
    
    eeg_data = np.ndarray(eeg_shape, dtype=np.float64, buffer=eeg_shm.buf)
    acc_data = np.ndarray(acc_shape, dtype=np.float64, buffer=acc_shm.buf)
    gyro_data = np.ndarray(gyro_shape, dtype=np.float64, buffer=gyro_shm.buf)
    ppg_data = np.ndarray(ppg_shape, dtype=np.float64, buffer=ppg_shm.buf)
    
    # Assume EEG sampling rate (adjust as needed)
    fs = 256  # Hz, typical for EEG
    
    # Calculate frequency bands for EEG
    def extract_frequency_bands(eeg_data, fs):
        # Define frequency bands
        bands = {
            'delta': (0.5, 4),    # 0.5-4 Hz
            'theta': (4, 8),      # 4-8 Hz
            'alpha': (8, 13),     # 8-13 Hz
            'beta': (13, 30),     # 13-30 Hz
            'gamma': (30, 45)     # 30-45 Hz (or higher)
        }
        
        results = {}
        
        # Design filters for each band
        for band_name, (low_freq, high_freq) in bands.items():
            # Normalize frequencies to Nyquist frequency
            low = low_freq / (fs/2)
            high = high_freq / (fs/2)
            
            # Create bandpass filter
            b, a = signal.butter(4, [low, high], btype='bandpass')
            
            # Apply filter to each EEG channel
            band_data = np.zeros_like(eeg_data)
            for i in range(eeg_data.shape[0]):
                # Apply filter and get filtered signal
                band_data[i, :] = signal.filtfilt(b, a, eeg_data[i, :])
            
            results[band_name] = band_data
        
        return results

    class VisualizationWindow:
        def __init__(self):
            # Use a more efficient matplotlib backend
            plt.style.use('fast')  # Use a faster style
            
            self.root = tk.Tk()
            self.root.title("Enhanced EEG Visualization")
            self.root.geometry("1600x1000")  # Larger window to accommodate all plots
            
            # Create figure for plotting
            self.fig = Figure(figsize=(16, 14), dpi=100)
            self.setup_plots()
            
            # Add figure to Tkinter window
            self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
            self.canvas_widget = self.canvas.get_tk_widget()
            self.canvas_widget.pack(fill=tk.BOTH, expand=True)
            
            # Reduce the number of points for faster rendering
            self.downsample_factor = 2  # Adjust this based on your needs
            
            # Pre-calculate fixed y-axis limits for better performance
            self._calculate_fixed_limits()
            
            # Start animation with reduced frequency
            self.ani = FuncAnimation(
                self.fig, 
                self.update_plot, 
                interval=200,  # Slower refresh rate for better performance
                blit=True,     # Use blitting for faster rendering
                cache_frame_data=False
            )
            
            # Handle window close
            self.root.protocol("WM_DELETE_WINDOW", self.on_close)
            
            # Add performance optimizations for Tkinter
            self.root.update_idletasks()
            self.last_update_time = 0
        
        def _calculate_fixed_limits(self):
            """Pre-calculate reasonable fixed y-axis limits for all plots"""
            # These are example values - adjust based on your actual data ranges
            self.eeg_ylim = (-500, 500)      # μV range for EEG
            self.band_ylim = (-150, 150)     # μV range for frequency bands
            self.acc_ylim = (-1.2, 1.2)      # m/s² range for accelerometer
            self.gyro_ylim = (-250, 250)     # deg/s range for gyroscope
            self.ppg_ylim = (-2500, 2500)    # Arbitrary units for PPG
            
            # Apply fixed limits
            for ax in self.eeg_axes:
                ax.set_ylim(self.eeg_ylim)
            
            for band_name, band_axes in self.band_axes.items():
                for ax in band_axes:
                    ax.set_ylim(self.band_ylim)
                    
            self.acc_ax.set_ylim(self.acc_ylim)
            self.gyro_ax.set_ylim(self.gyro_ylim)
            self.ppg_ax.set_ylim(self.ppg_ylim)
            
            # Set fixed x-axis limits
            t_max = max(time_buffer.max() if len(time_buffer) > 0 else 10, 
                        ppg_time_buffer.max() if len(ppg_time_buffer) > 0 else 10)
            t_min = min(time_buffer.min() if len(time_buffer) > 0 else 0,
                        ppg_time_buffer.min() if len(ppg_time_buffer) > 0 else 0)
            
            all_axes = self.eeg_axes[:]
            for band_axes_list in self.band_axes.values():
                all_axes.extend(band_axes_list)
            all_axes.extend([self.acc_ax, self.gyro_ax, self.ppg_ax])
            
            for ax in all_axes:
                ax.set_xlim(t_min, t_max)
        
        def setup_plots(self):
            # Clear any existing plots
            self.fig.clear()
            
            # Create a 6x5 grid layout
            gs = self.fig.add_gridspec(6, 5, hspace=0.5, wspace=0.4)
            
            channel_names = ['TP9', 'AF7', 'AF8', 'TP10']
            band_names = ['Raw', 'Delta', 'Theta', 'Alpha', 'Beta', 'Gamma']
            
            # Define colors for different data types
            band_colors = {
                'Delta': 'purple',
                'Theta': 'blue',
                'Alpha': 'green',
                'Beta': 'orange',
                'Gamma': 'red',
                'Raw': 'black'
            }
            
            # Initialize collections to store axes and lines
            self.eeg_axes = []
            self.eeg_lines = []
            
            self.band_axes = {
                'delta': [],
                'theta': [],
                'alpha': [],
                'beta': [],
                'gamma': []
            }
            
            self.band_lines = {
                'delta': [],
                'theta': [],
                'alpha': [],
                'beta': [],
                'gamma': []
            }
            
            # Create the main 4x6 grid for EEG channels
            for col, channel in enumerate(channel_names):
                for row, band in enumerate(band_names):
                    ax = self.fig.add_subplot(gs[row, col])
                    
                    # Set title only for the first row
                    if row == 0:
                        ax.set_title(f"{channel}")
                    
                    # Set band label only for the first column
                    if col == 0:
                        ax.set_ylabel(f"{band}")
                    
                    # Only show x-axis labels for the bottom row
                    if row < 5:
                        ax.set_xticklabels([])
                    else:
                        ax.set_xlabel("Time (s)")
                    
                    ax.grid(True, alpha=0.3)
                    
                    # Create line for this subplot with appropriate color
                    color = band_colors[band]
                    line, = ax.plot([], [], lw=1, color=color)
                    
                    # Store the axes and lines appropriately
                    if band == 'Raw':
                        self.eeg_axes.append(ax)
                        self.eeg_lines.append(line)
                    else:
                        # Convert band name to lowercase to match original code's structure
                        band_lower = band.lower()
                        self.band_axes[band_lower].append(ax)
                        self.band_lines[band_lower].append(line)
            
            # Create sensor plots in the 5th column
            # Accelerometer (first row, fifth column)
            self.acc_ax = self.fig.add_subplot(gs[0, 4])
            self.acc_ax.set_title("Accelerometer")
            self.acc_ax.set_ylabel("m/s²")
            # self.acc_ax.set_xlabel("Time (s)")
            self.acc_ax.grid(True, alpha=0.3)
            
            # Gyroscope (second row, fifth column)
            self.gyro_ax = self.fig.add_subplot(gs[1, 4])
            self.gyro_ax.set_title("Gyroscope")
            self.gyro_ax.set_ylabel("deg/s")
            # self.gyro_ax.set_xlabel("Time (s)")
            self.gyro_ax.grid(True, alpha=0.3)
            
            # PPG (third row, fifth column)
            self.ppg_ax = self.fig.add_subplot(gs[2, 4])
            self.ppg_ax.set_title("PPG Signals")
            self.ppg_ax.set_ylabel("A.U.")
            # self.ppg_ax.set_xlabel("Time (s)")
            self.ppg_ax.grid(True, alpha=0.3)
            
            # Create lines for motion sensors and PPG
            colors = ['r', 'g', 'b']
            
            self.acc_lines = []
            for i in range(3):
                line, = self.acc_ax.plot([], [], lw=1, color=colors[i], label=f"{'XYZ'[i]}")
                self.acc_lines.append(line)
            self.acc_ax.legend(loc="upper right", ncol=3, fontsize='small')
            
            self.gyro_lines = []
            for i in range(3):
                line, = self.gyro_ax.plot([], [], lw=1, color=colors[i], label=f"{'XYZ'[i]}")
                self.gyro_lines.append(line)
            self.gyro_ax.legend(loc="upper right", ncol=3, fontsize='small')
            
            self.ppg_lines = []
            for i in range(3):
                line, = self.ppg_ax.plot([], [], lw=1, color=colors[i], label=f"PPG{i + 1}")
                self.ppg_lines.append(line)
            self.ppg_ax.legend(loc="lower right", ncol=3, fontsize='small')
            
            # Add frequency band legend in the remaining space in the 5th column
            legend_ax = self.fig.add_subplot(gs[3:, 4])
            legend_ax.axis('off')
            
            # Create legend entries for each band with their frequency ranges
            band_ranges = {
                'Delta': "0.5-4 Hz",
                'Theta': "4-8 Hz",
                'Alpha': "8-13 Hz",
                'Beta': "13-30 Hz",
                'Gamma': "30-45 Hz"
            }
            
            legend_handles = []
            for band, color in band_colors.items():
                if band != 'Raw':
                    legend_handles.append(matplotlib.lines.Line2D([0], [0], color=color, lw=2, 
                                                            label=f"{band}: {band_ranges.get(band, '')}"))
            
            legend_ax.legend(handles=legend_handles, loc='center', fontsize='medium')
            
            # Add a main title
            self.fig.suptitle("EEG Brain Wave Analysis", fontsize=16, y=0.99)
            
            # Adjust the figure layout
            self.fig.tight_layout(rect=[0, 0, 1, 0.98])
            
            # Optimize figure rendering
            self.fig.set_facecolor('white')
            self.fig.set_dpi(90)  # Lower DPI for better performance
        
        def update_plot(self, frame):
            # Downsample data for faster plotting
            ds = self.downsample_factor
            time_ds = time_buffer[::ds]
            ppg_time_ds = ppg_time_buffer[::ds]
            
            # Update EEG lines with data from shared memory
            for i in range(4):
                self.eeg_lines[i].set_data(time_ds, eeg_data[i][::ds])
            
            # Calculate frequency bands
            if len(time_ds) > 0:  # Only process if we have data
                bands_data = extract_frequency_bands(eeg_data, fs)
                
                # Update band lines
                for band_name, band_data in bands_data.items():
                    for i in range(4):  # 4 EEG channels
                        self.band_lines[band_name][i].set_data(time_ds, band_data[i][::ds])
            
            # Update accelerometer lines
            for i in range(3):
                self.acc_lines[i].set_data(time_ds, acc_data[i][::ds])
            
            # Update gyroscope lines
            for i in range(3):
                self.gyro_lines[i].set_data(time_ds, gyro_data[i][::ds])
            
            # Update PPG lines
            for i in range(3):
                self.ppg_lines[i].set_data(ppg_time_ds, ppg_data[i][::ds])
            
            # Return all lines for blitting
            all_lines = self.eeg_lines[:]
            for band_lines in self.band_lines.values():
                all_lines.extend(band_lines)
            all_lines.extend(self.acc_lines + self.gyro_lines + self.ppg_lines)
            
            return all_lines
        
        def on_close(self):
            logging.debug("Closing visualization window")
            if hasattr(self, 'ani') and self.ani is not None:
                self.ani.event_source.stop()  # Stop the animation
            
            # Clean up shared memory (only unlink, not close)
            # We don't close/unlink the shared memory here because the main process is still using it
            
            self.root.quit()     # Stop the mainloop
            self.root.destroy()  # Close the window

    # Create and run the Tkinter visualization window
    visualization_window = VisualizationWindow()
    
    try:
        visualization_window.root.mainloop()
    except Exception as e:
        logging.error(f"Error in visualization: {str(e)}")
    finally:
        # Cleanup when done
        eeg_shm.close()
        acc_shm.close()
        gyro_shm.close()
        ppg_shm.close()
        
# Add a function to clean up shared memory resources
def cleanup_shared_memory():
    eeg_shm.close()
    acc_shm.close()
    gyro_shm.close()
    ppg_shm.close()
    
    eeg_shm.unlink()
    acc_shm.unlink()
    gyro_shm.unlink()
    ppg_shm.unlink()

    global parent_conn
    cmd = 'video_clean_up'
    if send_command(parent_conn, cmd):
        print('Video feed cleaned up')
    else:
        print('Failed to clean up video feed')

    print(f"Shared memory cleaned up")

if __name__ == "__main__":
    try:
        connect_to_muse()

        # Start Program 2 as a separate process
        print("Program 'flask - control' started - will send commands to 'Camera Program p1'")
        global parent_conn, child_conn  # Make pipes global
        parent_conn, child_conn = multiprocessing.Pipe()
        # Start Program 2 as a separate process
        p1_process = multiprocessing.Process(target=p1.main, args=(child_conn,))
        p1_process.start()
        # Wait for Program 2 to start (5 seconds)
        print("Waiting for 'Camera Program p1' to start (5 seconds)...")
        time.sleep(2)
        send_command(parent_conn, 'initialize_camera')
        time.sleep(3)


        # Start Program 2 as a separate process
        print("Program 'flask - control' started - will send commands to 'Image Stimuli Program p2'")
        global parent_conn2, child_conn2  # Make pipes global
        parent_conn2, child_conn2 = multiprocessing.Pipe()
        # Start Program 2 as a separate process
        p2_process = multiprocessing.Process(target=p2.main, args=(child_conn2,))
        p2_process.start()
        # Wait for Program 2 to start (5 seconds)
        time.sleep(2)

        # Start Program 4 as a separate process
        print("Program 'flask - control' started - will send commands to Program 'Video Stimuli Program p4'")
        global parent_conn4, child_conn4  # Make pipes global
        parent_conn4, child_conn4 = multiprocessing.Pipe()
        # Start Program 4 as a separate process
        p4_process = multiprocessing.Process(target=p4.main, args=(child_conn4,))
        p4_process.start()
        # Wait for Program 4 to start (5 seconds)
        time.sleep(2)

        # run flask app
        app.run(host='0.0.0.0', port=8082)
        # app.run(port=8082)
    finally:
        # Clean up shared memory when the application exits
        cleanup_shared_memory()