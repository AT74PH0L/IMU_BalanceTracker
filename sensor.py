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
from create_report import create_report, save_axis_plots
import numpy as np
import math

def signal_handler(sig, frame):
    print('########### Close program ###########')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

folder_selected = False
bluetooth_connected = False
data_gyro = queue.Queue()
data_quat = queue.Queue()
collecting = False
start_time = 0
duration = 0
canvas = None
folder_path = ""
folder_path_data = ""
address = "C0:8A:EF:C8:ED:07"
client = None
gyro_offsets = np.zeros(3) 
quat_offsets = np.zeros(3) 

user_info = {
    "name": "",
    "age": "",
    "gender": ""
}

async def read_sensor_data():
    global collecting, gyro_offsets
    print("==> Start ")
    while collecting:
        if bluetooth_connected and client and client.is_connected:
            try:
                raw_gyro_x = await client.read_gatt_char("21680407-7051-434a-8fb5-362ea1c01916")
                raw_gyro_y = await client.read_gatt_char("53acd7ae-09f2-4015-9bfc-092342c68b1d")
                raw_gyro_z = await client.read_gatt_char("7838e6fa-b9da-4221-985b-12116226cacf")
                
                gyro_x_str = raw_gyro_x.decode('utf-8').strip().replace(',', '')
                gyro_y_str = raw_gyro_y.decode('utf-8').strip().replace(',', '')
                gyro_z_str = raw_gyro_z.decode('utf-8').strip().replace(',', '')

                raw_quat_x = await client.read_gatt_char("1e182bb7-f3fd-4240-bc91-aabb9436c0b7")
                raw_quat_y = await client.read_gatt_char("3198a4f7-e0da-4ec0-aafe-d978201bdcaa")
                raw_quat_z = await client.read_gatt_char("4a3c7e31-deae-43ed-90a3-01a71c7ad28b")
                
                quat_x_str = raw_quat_x.decode('utf-8').strip().replace(',', '')
                quat_y_str = raw_quat_y.decode('utf-8').strip().replace(',', '')
                quat_z_str = raw_quat_z.decode('utf-8').strip().replace(',', '')

                update_timer()
                quat_x = float(quat_x_str) 
                quat_y = float(quat_y_str)
                quat_z = float(quat_z_str)
                # roll, pitch, yaw = quaternion_to_euler(quat_x, quat_y, quat_z, 1.0)
                # pitch, roll, yaw = calculate_angles_from_quaternion(1.0, quat_x, quat_y, quat_z)
                # print(f"{pitch:<10.2f} {roll:<10.2f} {yaw:<10.2f}")
                
                gyro_x = float(gyro_x_str) - gyro_offsets[0]
                gyro_y = float(gyro_y_str) - gyro_offsets[1]
                gyro_z = float(gyro_z_str) - gyro_offsets[2]

                # print(f"{gyro_x:<10.2f} {gyro_y:<10.2f} {gyro_z:<10.2f}")

                filtered_gyro = low_pass_filter([gyro_x, gyro_y, gyro_z])
                # print(filtered_gyro)  # แสดงค่าที่ถูกกรอง
                # print(f"{filtered_gyro[0]:<10.2f} {filtered_gyro[1]:<10.2f} {filtered_gyro[2]:<10.2f}")
                # print('-------------------')
                data_gyro.put(filtered_gyro)  # เก็บข้อมูลที่กรองแล้ว
                # data_quat.put(quat_x, quat_y, quat_z)
            except Exception as e:
                print(f"Error reading sensor data: {e}")
        await asyncio.sleep(0.1)

def calculate_angles_from_quaternion(w, x, y, z):
    # w, x, y, z = quat
    global quat_offsets
    x -= quat_offsets[0]
    y -= quat_offsets[1]
    z -= quat_offsets[2]
    pitch = math.atan2(2 * (y * z + w * x), w * w + x * x - y * y - z * z) * (
        180 / math.pi
    )
    roll = math.atan2(2 * (x * y + w * z), w * w - x * x - y * y + z * z) * (
        180 / math.pi
    )

    sin_yaw = -2 * (x * z - w * y)
    sin_yaw = max(-1.0, min(1.0, sin_yaw))
    yaw = math.asin(sin_yaw) * (180 / math.pi)

    return pitch, roll, yaw

def quaternion_to_euler(x, y, z, w):
    global quat_offsets
    x -= quat_offsets[0]
    y -= quat_offsets[1]
    z -= quat_offsets[2]

    sinr_cosp = 2 * (w * x + y * z)
    cosr_cosp = 1 - 2 * (x * x + y * y)
    roll = np.arctan2(sinr_cosp, cosr_cosp)

    # คำนวณ Pitch (y-axis rotation)
    sinp = 2 * (w * y - z * x)
    if abs(sinp) >= 1:
        pitch = np.pi / 2 * np.sign(sinp)  # กรณีค่าที่อยู่นอกขอบเขต
    else:
        pitch = np.arcsin(sinp)

    # คำนวณ Yaw (z-axis rotation)
    siny_cosp = 2 * (w * z + x * y)
    cosy_cosp = 1 - 2 * (y * y + z * z)
    yaw = np.arctan2(siny_cosp, cosy_cosp)

    # แปลงผลลัพธ์เป็นองศา
    roll = np.degrees(roll)
    pitch = np.degrees(pitch)
    yaw = np.degrees(yaw)

    return roll, pitch, yaw


def low_pass_filter(data, alpha=0.1):
    filtered_data = [data[0]]
    for i in range(1, len(data)):
        filtered_value = alpha * data[i] + (1 - alpha) * filtered_data[i - 1]
        filtered_data.append(filtered_value)
    return filtered_data

async def calibrate_gyro(num_samples=50):
    global gyro_offsets, quat_offsets
    print('==> Calibrate...')
    calibrate_status.set("Calibrating...")
    gyro_offsets = np.zeros(3)
    samples_collected = 0
    while samples_collected < num_samples:
        if bluetooth_connected and client and client.is_connected:
            try:
                raw_gyro_x = await client.read_gatt_char("21680407-7051-434a-8fb5-362ea1c01916")
                raw_gyro_y = await client.read_gatt_char("53acd7ae-09f2-4015-9bfc-092342c68b1d")
                raw_gyro_z = await client.read_gatt_char("7838e6fa-b9da-4221-985b-12116226cacf")

                gyro_x_str = raw_gyro_x.decode('utf-8').strip().replace(',', '')
                gyro_y_str = raw_gyro_y.decode('utf-8').strip().replace(',', '')
                gyro_z_str = raw_gyro_z.decode('utf-8').strip().replace(',', '')

                raw_quat_x = await client.read_gatt_char("1e182bb7-f3fd-4240-bc91-aabb9436c0b7")
                raw_quat_y = await client.read_gatt_char("3198a4f7-e0da-4ec0-aafe-d978201bdcaa")
                raw_quat_z = await client.read_gatt_char("4a3c7e31-deae-43ed-90a3-01a71c7ad28b")
                
                quat_x_str = raw_quat_x.decode('utf-8').strip().replace(',', '')
                quat_y_str = raw_quat_y.decode('utf-8').strip().replace(',', '')
                quat_z_str = raw_quat_z.decode('utf-8').strip().replace(',', '')

                gyro_offsets += np.array([float(gyro_x_str), float(gyro_y_str), float(gyro_z_str)])
                quat_offsets += np.array([float(quat_x_str), float(quat_y_str), float(quat_z_str)])
                samples_collected += 1
                await asyncio.sleep(0.01)
            except Exception as e:
                print(f"Error during calibration: {e}")
    gyro_offsets /= samples_collected if samples_collected > 0 else 1
    quat_offsets /= samples_collected if samples_collected > 0 else 1
    print(f"Calibrated offsets: {gyro_offsets}")
    calibrate_status.set("Calibration complete")

async def init_bluetooth_connection():
    global bluetooth_connected, client
    try:
        client = BleakClient(address)
        await client.connect()
        if client.is_connected:
            bluetooth_connected = True
            if folder_selected and bluetooth_connected:
                start_button.config(state=tk.NORMAL)
            print("==> Bluetooth connected.")
            connection_status.set("Bluetooth connected.")
            reconnect_button.config(state=tk.DISABLED)
            calibrate_button.config(state=tk.NORMAL)
        else:
            connection_status.set("Bluetooth not connected.")
    except Exception as e:
        print("==> Connection error.")
        connection_status.set(f"Connection error")

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

    # Start the data collection thread
    threading.Thread(target=lambda: asyncio.run(read_sensor_data())).start()

def stop_collection():
    global collecting
    collecting = False
    start_button.config(state=tk.NORMAL)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    global folder_path_data
    folder_path_data = folder_path + "/" + timestamp
    os.makedirs(folder_path_data, exist_ok=True)
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
    
def plot_3d_data(x_data, y_data, z_data):
    global user_info
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

    # Call the function to create the report
    create_report(user_info, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), folder_path_data,x_data, y_data, z_data)

def select_folder():
    global folder_path, folder_selected, new_folder_path
    new_folder_path = filedialog.askdirectory()
    
    if not new_folder_path and not folder_selected:
        messagebox.showerror("Error", "No folder selected.")
    elif new_folder_path == folder_path:
        messagebox.showinfo("Info", "The selected folder is the same as the current folder.")
    else:
        if new_folder_path != "":
            print('==> Folder selected.')
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

def show_info_popup():
    # Create a new popup window
    info_popup = tk.Toplevel(root)
    info_popup.title("Enter Personal Information")

    # Name entry
    name_label = ttk.Label(info_popup, text="Name:")
    name_label.grid(row=0, column=0, padx=5, pady=5)
    name_entry = ttk.Entry(info_popup)
    name_entry.grid(row=0, column=1, padx=5, pady=5)

    # Age entry
    age_label = ttk.Label(info_popup, text="Age:")
    age_label.grid(row=1, column=0, padx=5, pady=5)
    age_entry = ttk.Entry(info_popup)
    age_entry.grid(row=1, column=1, padx=5, pady=5)

    # Gender entry
    gender_label = ttk.Label(info_popup, text="Gender:")
    gender_label.grid(row=2, column=0, padx=5, pady=5)
    gender_var = tk.StringVar()
    male_radio = ttk.Radiobutton(info_popup, text="Male", variable=gender_var, value="Male")
    female_radio = ttk.Radiobutton(info_popup, text="Female", variable=gender_var, value="Female")
    other_radio = ttk.Radiobutton(info_popup, text="Other", variable=gender_var, value="Other")
    male_radio.grid(row=2, column=1, padx=5, pady=5)
    female_radio.grid(row=2, column=2, padx=5, pady=5)
    other_radio.grid(row=2, column=3, padx=5, pady=5)

    # Submit button
    def submit_info():
        # Store the input in the global variable
        user_info["name"] = name_entry.get()
        user_info["age"] = age_entry.get()
        user_info["gender"] = gender_var.get()
        messagebox.showinfo("Information", f"Name: {user_info['name']}\nAge: {user_info['age']}\nGender: {user_info['gender']}")
        info_popup.destroy()

    submit_button = ttk.Button(info_popup, text="Submit", command=submit_info)
    submit_button.grid(row=3, column=0, columnspan=2, pady=10)

def plot_and_save_data():
    gyro_data = []
    while not data_gyro.empty():
        gyro_data.append(data_gyro.get())

    if not gyro_data:
        messagebox.showinfo("No Data", "No data to plot.")
        return

    x_gyro = [data[0] for data in gyro_data]
    y_gyro = [data[1] for data in gyro_data]
    z_gyro = [data[2] for data in gyro_data]

    # Save raw data
    save_raw_data(gyro_data)

    # Save axis plots
    save_axis_plots(folder_path_data, x_gyro, y_gyro, z_gyro)

    # Plot in main thread using after
    root.after(0, lambda: plot_3d_data(x_gyro, y_gyro, z_gyro))


async def reconnect_bluetooth():
    global bluetooth_connected
    bluetooth_connected = False  
    connection_status.set("Reconnecting...")
    await init_bluetooth_connection()  

def on_reconnect_button_click():
    print("==> Reconnect...")
    threading.Thread(target=lambda: asyncio.run(reconnect_bluetooth())).start()

def on_calibrate_button_click():
     threading.Thread(target=lambda: asyncio.run(calibrate_gyro())).start()

root = tk.Tk()
root.title("Balance Tracker")

main_frame = ttk.Frame(root, padding="10")
main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

dduration_label = ttk.Label(main_frame, text="Duration (seconds):")
dduration_label.grid(row=0, column=0, padx=5, pady=5, sticky='w')

duration_entry = ttk.Entry(main_frame)
duration_entry.grid(row=0, column=1, padx=5, pady=5, sticky='w')

start_button = ttk.Button(main_frame, text="Start", command=lambda: countdown(3), state=tk.DISABLED)
start_button.grid(row=2, column=0, padx=5, pady=5, sticky='w')

timer_label = ttk.Label(main_frame, text="Time elapsed: 0.0 seconds")
timer_label.grid(row=2, column=1, padx=5, pady=5, sticky='w')

folder_button = ttk.Button(main_frame, text="Select Folder", command=select_folder)
folder_button.grid(row=3, column=0, padx=5, pady=5, sticky='w')

folder_path_name_label = ttk.Label(main_frame, text="Path: Not selected")
folder_path_name_label.grid(row=3, column=1, padx=5, pady=5, sticky='w')

info_button = ttk.Button(main_frame, text="Add information", command=show_info_popup)
info_button.grid(row=4, column=0, padx=5, pady=5, sticky='w')

reconnect_button = ttk.Button(main_frame, text="Reconnect", command=on_reconnect_button_click)
reconnect_button.grid(row=6, column=0, padx=5, pady=5, sticky='w')

connection_status = tk.StringVar()
connection_status.set("Bluetooth Connecting...")
connection_status_label = ttk.Label(main_frame, textvariable=connection_status)
connection_status_label.grid(row=6, column=1, columnspan=2, padx=5, pady=5, sticky='w')

calibrate_button = ttk.Button(main_frame, text="Calibrate", command=on_calibrate_button_click, state=tk.DISABLED)
calibrate_button.grid(row=7, column=0, padx=5, pady=5,sticky='w')
calibrate_status = tk.StringVar()
calibrate_status.set("Not calibrated yet")
calibrate_status_label = ttk.Label(main_frame, textvariable=calibrate_status)
calibrate_status_label.grid(row=7, column=1, columnspan=2, padx=5, pady=5, sticky='w')

version_label = tk.Label(root, text="Version 0.0.1", font=("Arial", 8))
version_label.place(relx=1.0, rely=0.0, anchor='ne', x=-10, y=10)

graph_frame = ttk.Frame(root, padding="10")
graph_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

def init_bluetooth():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_bluetooth_connection())

bt_thread = threading.Thread(target=init_bluetooth)
bt_thread.start()
print("########### Start program ###########")

root.protocol("WM_DELETE_WINDOW", Close)
root.mainloop()