from flask import Flask, jsonify, request
from flask_cors import CORS
import threading
import cv2
import face_recognition
import mysql.connector
import numpy as np
import os
from datetime import datetime

app = Flask(__name__)
CORS(app) # Allow web portal to talk to Flask

# --- CONFIG ---
DB_CONFIG = { "host": "localhost", "user": "root", "password": "", "database": "unibot" }
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

# --- BIOMETRIC LOGIC ---
is_running = False

def run_biometric_scan():
    global is_running
    is_running = True
    
    # Load known faces logic (similar to attendance_system.py)
    known_encodings = []
    known_ids = []
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT s.id, s.face_front FROM students s WHERE s.face_front IS NOT NULL AND s.face_front != ''")
    records = cursor.fetchall()
    
    for r in records:
        path = os.path.join(os.path.dirname(PROJECT_ROOT), r['face_front'].replace('/', os.sep))
        if os.path.exists(path):
            img = face_recognition.load_image_file(path)
            enc = face_recognition.face_encodings(img)[0]
            known_encodings.append(enc)
            known_ids.append(r['id'])
    
    cap = cv2.VideoCapture(0)
    today = datetime.now().strftime('%Y-%m-%d')
    
    while is_running:
        ret, frame = cap.read()
        if not ret: break
        
        small = cv2.resize(frame, (0,0), fx=0.25, fy=0.25)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        
        locs = face_recognition.face_locations(rgb)
        encs = face_recognition.face_encodings(rgb, locs)
        
        for enc in encs:
            matches = face_recognition.compare_faces(known_encodings, enc, 0.5)
            if True in matches:
                idx = matches.index(True)
                sid = known_ids[idx]
                
                # Mark in DB
                cursor.execute("SELECT id FROM attendance WHERE student_id=%s AND date=%s", (sid, today))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO attendance (student_id, date, status) VALUES (%s, %s, 'present')", (sid, today))
                    conn.commit()
        
        # Stop if Admin triggers shutdown (or just keep running)
        if cv2.waitKey(1) & 0xFF == ord('q'): break
        
    cap.release()
    conn.close()
    is_running = False

# --- API ENDPOINTS ---
@app.route('/api/start_attendance', methods=['POST'])
def start_attendance():
    if is_running: return jsonify({"status": "error", "message": "Attendance already running"}), 400
    threading.Thread(target=run_biometric_scan).start()
    return jsonify({"status": "success", "message": "Biometric CCTV Initialized"})

@app.route('/api/get_attendance/<int:user_id>', methods=['GET'])
def get_attendance(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Get student_id from user_id
    cursor.execute("SELECT id FROM students WHERE user_id=%s", (user_id,))
    student = cursor.fetchone()
    if not student: return jsonify({"status": "absent"})
    
    cursor.execute("SELECT status FROM attendance WHERE student_id=%s AND date=%s", (student['id'], today))
    record = cursor.fetchone()
    conn.close()
    
    return jsonify({"status": record['status'] if record else "absent"})

if __name__ == '__main__':
    app.run(port=5000, debug=True)
