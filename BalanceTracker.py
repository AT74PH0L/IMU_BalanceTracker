import tkinter as tk
from tkinter import ttk
from tkinter import messagebox, filedialog
import serial
import threading
import time
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import queue
import numpy as np
import os
import sys
import signal
from datetime import datetime

def signal_handler(sig, frame):
    print('Closing the program.')
    sys.exit(0)

# ตั้งค่า signal handler สำหรับ SIGINT
signal.signal(signal.SIGINT, signal_handler)

# การตั้งค่าพอร์ตอนุกรม
def connect_serial(port, baudrate=115200):
    try:
        ser = serial.Serial("COM"+port, baudrate, timeout=1)
        return ser
    except serial.SerialException:
        messagebox.showerror("Connection Error", f"Cannot open port {port}. Please check the port and try again.")
        return None

# ตัวแปรสำหรับเก็บค่าศูนย์
zero_x = 0.0
zero_y = 0.0
zero_z = 0.0

# ตัวแปรสำหรับตรวจสอบการเชื่อมต่อ
ser = None
ser_connected = False

# ตัวแปรสำหรับตรวจสอบการเลือกโฟลเดอร์
folder_selected = False

# ฟังก์ชันสำหรับอ่านข้อมูลจาก IMU
def read_gyro_data(data_queue):
    buffer_size = 10
    gyro_x_buffer = []
    gyro_y_buffer = []
    gyro_z_buffer = []
    while collecting:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8').strip()
            if line.startswith("Gyro: "):
                data = line[6:].split(', ')
                if len(data) == 3:
                    try:
                        raw_gyro_x = float(data[0]) - zero_x
                        raw_gyro_y = float(data[1]) - zero_y
                        raw_gyro_z = float(data[2].split(' ')[0]) - zero_z
                        
                        # แปลงหน่วยเป็นมิลลิเมตร (สมมติว่าเรามีการแปลงที่เหมาะสม)
                        raw_gyro_x_mm = raw_gyro_x # ตัวอย่างแปลงหน่วย (ควรปรับตามความเหมาะสม)
                        raw_gyro_y_mm = raw_gyro_y # ตัวอย่างแปลงหน่วย (ควรปรับตามความเหมาะสม)
                        raw_gyro_z_mm = raw_gyro_z # ตัวอย่างแปลงหน่วย (ควรปรับตามความเหมาะสม)
                        
                        # Add new data to buffers
                        gyro_x_buffer.append(raw_gyro_x_mm)
                        gyro_y_buffer.append(raw_gyro_y_mm)
                        gyro_z_buffer.append(raw_gyro_z_mm)
                        
                        # Keep only the last 'buffer_size' elements in the buffer
                        if len(gyro_x_buffer) > buffer_size:
                            gyro_x_buffer.pop(0)
                        if len(gyro_y_buffer) > buffer_size:
                            gyro_y_buffer.pop(0)
                        if len(gyro_z_buffer) > buffer_size:
                            gyro_z_buffer.pop(0)
                        
                        # Calculate the average of the buffer
                        gyro_x = np.mean(gyro_x_buffer)
                        gyro_y = np.mean(gyro_y_buffer)
                        gyro_z = np.mean(gyro_z_buffer)

                        data_queue.put((gyro_x, gyro_y, gyro_z))
                    except ValueError:
                        continue

# ฟังก์ชันสำหรับตั้งค่าศูนย์
def calibrate_gyro():
    global zero_x, zero_y, zero_z
    samples = 100
    sum_x = sum_y = sum_z = 0.0
    for _ in range(samples):
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8').strip()
            if line.startswith("Gyro: "):
                data = line[6:].split(', ')
                if len(data) == 3:
                    try:
                        sum_x += float(data[0])
                        sum_y += float(data[1])
                        sum_z += float(data[2].split(' ')[0])
                    except ValueError:
                        continue
    zero_x = sum_x / samples
    zero_y = sum_y / samples
    zero_z = sum_z / samples

# ฟังก์ชันสำหรับเริ่มการเก็บข้อมูล
def start_collection():
    global collection_thread, collecting, start_time, duration, canvas, folder_path, ser, ser_connected
    if not ser_connected:  # เชื่อมต่อกับพอร์ต COM เฉพาะครั้งแรก
        port = port_entry.get()  # รับพอร์ตจากช่องใส่ข้อมูล
        ser = connect_serial(port)
        if ser is None:
            return
        ser_connected = True
    
    if canvas:
        canvas.get_tk_widget().pack_forget()  # ลบกราฟเก่าออกจากกรอบ
    
    collecting = True
    calibrate_gyro()  # ตั้งค่าศูนย์ก่อนเริ่มเก็บข้อมูล
    start_time = time.time()
    duration = int(duration_entry.get())  # รับค่าจำนวนวินาทีจากช่องใส่ข้อมูล
    start_button.config(state=tk.DISABLED)
    stop_button.config(state=tk.NORMAL)
    collection_thread = threading.Thread(target=read_gyro_data, args=(data_queue,), daemon=True)
    collection_thread.start()
    update_timer()

    # ตรวจสอบว่าโฟลเดอร์ถูกเลือกแล้ว
    if not folder_selected:
        messagebox.showerror("Error", "No folder selected. Please select a folder to save the data.")
        stop_collection()
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # folder_path = os.path.join(folder_path, f"gyro_data_{timestamp}")
    global folder_path_data
    folder_path_data = folder_path+"/"+timestamp
    os.makedirs(folder_path_data, exist_ok=True)

# ฟังก์ชันสำหรับหยุดการเก็บข้อมูล
def stop_collection():
    global collecting
    collecting = False
    start_button.config(state=tk.NORMAL)
    stop_button.config(state=tk.DISABLED)
    plot_data()

# ฟังก์ชันสำหรับอัปเดตตัวจับเวลา
def update_timer():
    if collecting:
        elapsed_time = time.time() - start_time
        timer_label.config(text=f"Time elapsed: {elapsed_time:.1f} seconds")
        if elapsed_time < duration:
            root.after(100, update_timer)
        else:
            stop_collection()

# ฟังก์ชันสำหรับบันทึกภาพกราฟในแต่ละแกน
def save_axis_plots(x_data, y_data, z_data):
    # Plot for X-axis
    plt.figure(figsize=(7, 5))
    plt.plot(x_data, label='Gyro X')
    plt.xlabel('Sample Index')
    plt.ylabel('Gyro X (dps)')
    plt.title('Gyro X Data')
    plt.legend()
    plt.grid(True)
    plt.savefig(os.path.join(folder_path_data, 'gyro_x.png'))
    plt.close()
    
    # Plot for Y-axis
    plt.figure(figsize=(7, 5))
    plt.plot(y_data, label='Gyro Y')
    plt.xlabel('Sample Index')
    plt.ylabel('Gyro Y (dps)')
    plt.title('Gyro Y Data')
    plt.legend()
    plt.grid(True)
    plt.savefig(os.path.join(folder_path_data, 'gyro_y.png'))
    plt.close()
    
    # Plot for Z-axis
    plt.figure(figsize=(7, 5))
    plt.plot(z_data, label='Gyro Z')
    plt.xlabel('Sample Index')
    plt.ylabel('Gyro Z (dps)')
    plt.title('Gyro Z Data')
    plt.legend()
    plt.grid(True)
    plt.savefig(os.path.join(folder_path_data, 'gyro_z.png'))
    plt.close()

# ฟังก์ชันสำหรับแสดงข้อมูลในกราฟ 3D
def plot_data():
    global canvas, folder_path_data
    gyro_data = []
    while not data_queue.empty():
        gyro_data.append(data_queue.get())
    
    if not gyro_data:
        messagebox.showinfo("No Data", "No data to plot.")
        return

    x_data = [data[0] for data in gyro_data]
    y_data = [data[1] for data in gyro_data]
    z_data = [data[2] for data in gyro_data]

    # บันทึกกราฟแต่ละแกน
    save_axis_plots(x_data, y_data, z_data)

    fig = plt.figure(figsize=(5, 5))  # ขนาดของกราฟเป็นนิ้ว
    ax = fig.add_subplot(111, projection='3d')

    ax.plot(x_data, y_data, z_data, label='Gyro Data')
    
    # กำหนดขอบเขตของกราฟให้เป็น 5x5 ซม (50x50 มม)
    ax.set_xlim([-50, 50])
    ax.set_ylim([-50, 50])
    ax.set_zlim([-50, 50])

    # กำหนดอัตราส่วนของกล่องกราฟให้เป็น 1:1:1
    ax.set_box_aspect([1, 1, 1])
    
    ax.set_xlabel('Gyro X (dps)')
    ax.set_ylabel('Gyro Y (dps)')
    ax.set_zlabel('Gyro Z (dps)')
    ax.set_title('3D Gyro Data in dps')
    ax.legend()

    # ฝังกราฟใน tkinter
    canvas = FigureCanvasTkAgg(fig, master=graph_frame)
    canvas.draw()
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    # บันทึกภาพกราฟ 3D
    fig.savefig(os.path.join(folder_path_data, 'gyro_3d.png'))
    
    # คำนวณและบันทึกค่าเฉลี่ยและค่าสูงสุด
    avg_x, avg_y, avg_z = np.mean(x_data), np.mean(y_data), np.mean(z_data)
    max_x, max_y, max_z = np.max(x_data), np.max(y_data), np.max(z_data)

    with open(os.path.join(folder_path_data, 'summary.txt'), 'w') as f:
        f.write(f"Average X: {avg_x:.2f} dps\n")
        f.write(f"Max X: {max_x:.2f} dps\n")
        f.write(f"Average Y: {avg_y:.2f} dps\n")
        f.write(f"Max Y: {max_y:.2f} dps\n")
        f.write(f"Average Z: {avg_z:.2f} dps\n")
        f.write(f"Max Z: {max_z:.2f} dps\n")

# ฟังก์ชันสำหรับเลือกโฟลเดอร์
def select_folder():
    global folder_path, folder_selected
    folder_path = filedialog.askdirectory()
    if not folder_path:
        messagebox.showerror("Error", "No folder selected.")
        folder_button.config(state=tk.NORMAL)
    else:
        folder_selected = True
        folder_path_name_label.config(text=f"Path: {folder_path} ")

# ฟังก์ชันสำหรับการนับถอยหลังก่อนเริ่มการเก็บข้อมูล
def countdown(count):
    if count > 0:
        start_button.config(text=str(count))
        root.after(1000, countdown, count-1)
    else:
        start_button.config(text="Start")
        start_collection()

def Close():
    signal_handler(None, None)  
    root.destroy()

# การตั้งค่า GUI
root = tk.Tk()
root.title("Balance Tracker")

data_queue = queue.Queue()
collecting = False
start_time = 0
duration = 0
canvas = None
folder_path = ""
folder_path_data = ""

main_frame = ttk.Frame(root, padding="10")
main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

duration_label = ttk.Label(main_frame, text="Duration (seconds):")
duration_label.grid(row=0, column=0, padx=5, pady=5)

duration_entry = ttk.Entry(main_frame)
duration_entry.grid(row=0, column=1, padx=5, pady=5)

port_label = ttk.Label(main_frame, text="Serial Port:")
port_label.grid(row=1, column=0, padx=5, pady=5)

port_entry = ttk.Entry(main_frame)
port_entry.grid(row=1, column=1, padx=5, pady=5)

start_button = ttk.Button(main_frame, text="Start", command=lambda: countdown(3))
start_button.grid(row=2, column=0, padx=5, pady=5)

stop_button = ttk.Button(main_frame, text="Stop", command=stop_collection, state=tk.DISABLED)
stop_button.grid(row=2, column=1, padx=5, pady=5)

timer_label = ttk.Label(main_frame, text="Time elapsed: 0.0 seconds")
timer_label.grid(row=3, column=0, columnspan=2, padx=5, pady=5)

folder_button = ttk.Button(main_frame, text="Select Folder", command=select_folder)
folder_button.grid(row=4, column=0, columnspan=2, padx=5, pady=5)

folder_path_name_label = ttk.Label(main_frame, text="Path: Not selected")
folder_path_name_label.grid(row=5, column=0, columnspan=2, padx=5, pady=5)

# สร้างเลขเวอร์ชัน
version_label = tk.Label(root, text="Version 1.0.3", font=("Arial", 8))
version_label.place(relx=1.0, rely=0.0, anchor='ne', x=-10, y=10)

# การตั้งค่ากราฟ
graph_frame = ttk.Frame(root, padding="10")
graph_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

root.protocol("WM_DELETE_WINDOW", Close)
root.mainloop()
