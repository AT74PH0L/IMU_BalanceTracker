import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import time
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import queue
import os
import threading
import signal
from datetime import datetime
import asyncio
from bleak import BleakClient
import sys

def signal_handler(sig, frame):
    print('Closing the program.')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

folder_selected = False
bluetooth_connected = False

data_queue = queue.Queue()
collecting = False
start_time = 0
duration = 0
canvas = None
folder_path = ""
folder_path_data = ""
address = "C0:8A:EF:C8:ED:07"

client = None

async def read_sensor_data():
    global collecting
    while collecting:
        if bluetooth_connected and client and client.is_connected:
            try:
                raw_gyro_x = await client.read_gatt_char("1e182bb7-f3fd-4240-bc91-aabb9436c0b7")
                raw_gyro_y = await client.read_gatt_char("3198a4f7-e0da-4ec0-aafe-d978201bdcaa")
                raw_gyro_z = await client.read_gatt_char("4a3c7e31-deae-43ed-90a3-01a71c7ad28b")
                gyro_x_str = raw_gyro_x.decode('utf-8').strip().replace(',', '')
                gyro_y_str = raw_gyro_y.decode('utf-8').strip().replace(',', '')
                gyro_z_str = raw_gyro_z.decode('utf-8').strip().replace(',', '')
                update_timer()
                gyro_x = float(gyro_x_str)
                gyro_y = float(gyro_y_str)
                gyro_z = float(gyro_z_str)
                data_queue.put((gyro_x, gyro_y, gyro_z))
            except Exception as e:
                print(f"Error reading sensor data: {e}")
        await asyncio.sleep(0.1)

async def init_bluetooth_connection():
    global bluetooth_connected, client
    try:
        client = BleakClient(address)
        await client.connect()
        if client.is_connected:
            bluetooth_connected = True
            if folder_selected and bluetooth_connected:
                start_button.config(state=tk.NORMAL)
            connection_status.set("Bluetooth connected.")
            
        else:
            connection_status.set("Bluetooth not connected.")
    except Exception as e:
        connection_status.set(f"Connection error: {e}")

def start_collection():
    global collecting, start_time, duration, canvas, folder_path
    if canvas:
        canvas.get_tk_widget().pack_forget()  # Remove old graph from frame
    
    collecting = True
    start_time = time.time()
    duration = int(duration_entry.get())  # Get duration from entry field
    start_button.config(state=tk.DISABLED)
    
    # Ensure folder path is selected
    if not folder_selected:
        messagebox.showerror("Error", "No folder selected. Please select a folder to save the data.")
        stop_collection()
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    global folder_path_data
    folder_path_data = folder_path + "/" + timestamp
    os.makedirs(folder_path_data, exist_ok=True)

    # Start the data collection thread
    threading.Thread(target=lambda: asyncio.run(read_sensor_data())).start()

def stop_collection():
    global collecting
    collecting = False
    start_button.config(state=tk.NORMAL)
    plot_and_save_data()

def update_timer():
    if collecting:
        elapsed_time = time.time() - start_time
        timer_label.config(text=f"Time elapsed: {elapsed_time:.1f} seconds")
        if elapsed_time < duration:
            root.after(100, update_timer)
        else:
            stop_collection()

def save_raw_data(gyro_data):
    raw_data_file = os.path.join(folder_path_data, 'raw_gyro_data.csv')
    with open(raw_data_file, 'w') as f:
        f.write("Gyro_X,Gyro_Y,Gyro_Z\n")
        for data in gyro_data:
            f.write(f"{data[0]},{data[1]},{data[2]}\n")

def save_axis_plots(x_data, y_data, z_data):

    plt.figure(figsize=(7, 5))
    plt.plot(x_data, label='Gyro X')
    plt.xlabel('Sample Index')
    plt.ylabel('Gyro X (dps)')
    plt.title('Gyro X Data')
    plt.legend()
    plt.grid(True)
    plt.savefig(os.path.join(folder_path_data, 'gyro_x.png'))
    plt.close()

    plt.figure(figsize=(7, 5))
    plt.plot(y_data, label='Gyro Y')
    plt.xlabel('Sample Index')
    plt.ylabel('Gyro Y (dps)')
    plt.title('Gyro Y Data')
    plt.legend()
    plt.grid(True)
    plt.savefig(os.path.join(folder_path_data, 'gyro_y.png'))
    plt.close()

    plt.figure(figsize=(7, 5))
    plt.plot(z_data, label='Gyro Z')
    plt.xlabel('Sample Index')
    plt.ylabel('Gyro Z (dps)')
    plt.title('Gyro Z Data')
    plt.legend()
    plt.grid(True)
    plt.savefig(os.path.join(folder_path_data, 'gyro_z.png'))
    plt.close()

def plot_and_save_data():
    gyro_data = []
    while not data_queue.empty():
        gyro_data.append(data_queue.get())

    if not gyro_data:
        messagebox.showinfo("No Data", "No data to plot.")
        return

    x_data = [data[0] for data in gyro_data]
    y_data = [data[1] for data in gyro_data]
    z_data = [data[2] for data in gyro_data]

    # Save raw data
    save_raw_data(gyro_data)

    # Save axis plots
    save_axis_plots(x_data, y_data, z_data)

    # Plot in main thread using after
    root.after(0, lambda: plot_3d_data(x_data, y_data, z_data))\
    
def plot_3d_data(x_data, y_data, z_data):
    fig = plt.figure(figsize=(5, 5))
    ax = fig.add_subplot(111, projection='3d')

    ax.plot(x_data, y_data, z_data, label='Gyro Data')

    ax.set_xlim([-100, 100])
    ax.set_ylim([-100, 100])
    ax.set_zlim([-100, 100])

    ax.set_box_aspect([1, 1, 1])

    ax.set_xlabel('Gyro X (dps)')
    ax.set_ylabel('Gyro Y (dps)')
    ax.set_zlabel('Gyro Z (dps)')
    ax.set_title('3D Gyro Data in dps')
    ax.legend()

    global canvas
    canvas = FigureCanvasTkAgg(fig, master=graph_frame)
    canvas.draw()
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    # Save 3D plot
    fig.savefig(os.path.join(folder_path_data, 'gyro_3d.png'))

def select_folder():
    global folder_path, folder_selected, new_folder_path
    new_folder_path = filedialog.askdirectory()
    
    if not new_folder_path and not folder_selected:
        messagebox.showerror("Error", "No folder selected.")
    elif new_folder_path == folder_path:
        messagebox.showinfo("Info", "The selected folder is the same as the current folder.")
    else:
        if new_folder_path != "":
            folder_path = new_folder_path
            folder_selected = True
            folder_path_name_label.config(text=f"Path: {folder_path}")
            if folder_selected and bluetooth_connected:
                start_button.config(state=tk.NORMAL)


def countdown(count):
    if count > 0:
        timer_label.config(text=f"Starting in {count}...")
        root.after(1000, countdown, count - 1)
    else:
        start_collection()

def Close():
    signal_handler(None, None)
    root.destroy()

root = tk.Tk()
root.title("Balance Tracker")

main_frame = ttk.Frame(root, padding="10")
main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

duration_label = ttk.Label(main_frame, text="Duration (seconds):")
duration_label.grid(row=0, column=0, padx=5, pady=5)

duration_entry = ttk.Entry(main_frame)
duration_entry.grid(row=0, column=1, padx=5, pady=5)

start_button = ttk.Button(main_frame, text="Start", command=lambda: countdown(3), state=tk.DISABLED)
start_button.grid(row=2, column=0, padx=5, pady=5)

timer_label = ttk.Label(main_frame, text="Time elapsed: 0.0 seconds")
timer_label.grid(row=2, column=1, columnspan=2, padx=5, pady=5)

folder_button = ttk.Button(main_frame, text="Select Folder", command=select_folder)
folder_button.grid(row=3, column=0,padx=5, pady=5)

folder_path_name_label = ttk.Label(main_frame, text="Path: Not selected")
folder_path_name_label.grid(row=3, column=1)

connection_status = tk.StringVar()
connection_status.set("Bluetooth Connecting...")
connection_status_label = ttk.Label(main_frame, textvariable=connection_status)
connection_status_label.grid(row=6, column=0, columnspan=2, padx=5, pady=5)

version_label = tk.Label(root, text="Version 1.1.0", font=("Arial", 8))
version_label.place(relx=1.0, rely=0.0, anchor='ne', x=-10, y=10)

graph_frame = ttk.Frame(root, padding="10")
graph_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

def init_bluetooth():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_bluetooth_connection())

bt_thread = threading.Thread(target=init_bluetooth)
bt_thread.start()

root.protocol("WM_DELETE_WINDOW", Close)
root.mainloop()
