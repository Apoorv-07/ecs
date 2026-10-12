import serial
import csv
from datetime import datetime
import time

SERIAL_PORT = 'COM10'
BAUD_RATE = 115200
OUTPUT_FILE = f"Dormant_CSI_Stable_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting Robust Dormant CSI Logger...")
print(f"Saving data to: {OUTPUT_FILE}")

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
    print("Connected successfully! Listening for CSI stream...")
    
    with open(OUTPUT_FILE, 'w', newline='') as file:
        writer = csv.writer(file)
        
        # Header
        header = ['Timestamp', 'RSSI']
        for i in range(1, 129):
            header.append(f'Subcarrier_{i}')
        writer.writerow(header)
        
        packet_count = 0
        start_time = time.time()
        
        while True:
            # Buffer me jitna bhi data pada hai use ek sath read karo
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                
                if line.startswith("CSI_DATA"):
                    parts = line.split(',')
                    if len(parts) >= 130:
                        rssi = parts[1]
                        csi_values = parts[2:]
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        
                        row = [timestamp, rssi] + csi_values[:128]
                        writer.writerow(row)
                        packet_count += 1
                        
                        # Har 50 packets par console me print karo taaki pata chale zinda hai
                        if packet_count % 50 == 0:
                            elapsed = time.time() - start_time
                            rate = packet_count / elapsed if elapsed > 0 else 0
                            print(f"[{timestamp}] Saved: {packet_count} packets | Rate: {rate:.2f} pkts/sec | RSSI: {rssi}")
                            file.flush()
            else:
                time.sleep(0.001) # CPU overload bachane ke liye chota sleep

except KeyboardInterrupt:
    print(f"\nStopped by user. Total packets saved: {packet_count}")
except Exception as e:
    print(f"\nError occurred: {e}")
finally:
    if 'ser' in locals() and ser.is_open:
        ser.close()