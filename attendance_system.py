import cv2
import face_recognition
import mysql.connector
import pandas as pd
import numpy as np
import os
from datetime import datetime
import time

# --- UNIBOT BIOMETRIC CONFIG ---
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "unibot"
}

# Dynamic Path Resolution
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
EXCEL_OUTPUT = os.path.join(PROJECT_ROOT, "UniBot_Attendance_Report.xlsx")

def get_db_connection():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Exception as e:
        print(f"❌ [DB] Connection Failed: {e}")
        return None

def load_student_database():
    """Loads facial encodings from the project image repository."""
    known_encodings = []
    student_data = [] 
    
    conn = get_db_connection()
    if not conn: return [], []
    
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT s.id, u.name, s.face_front, s.guardian_phone 
        FROM students s 
        JOIN users u ON s.user_id = u.id 
        WHERE s.face_front IS NOT NULL AND s.face_front != ''
    """
    cursor.execute(query)
    records = cursor.fetchall()
    conn.close()

    print(f"🔄 [SYSTEM] Initializing Neural Library... Found {len(records)} students.")
    
    for record in records:
        # Standardize path for OS
        path = record['face_front'].replace('/', os.sep).replace('\\', os.sep)
        full_path = os.path.join(PROJECT_ROOT, path)
        
        if os.path.exists(full_path):
            try:
                img = face_recognition.load_image_file(full_path)
                encoding = face_recognition.face_encodings(img)[0]
                known_encodings.append(encoding)
                student_data.append({
                    'id': record['id'],
                    'name': record['name'],
                    'guardian': record['guardian_phone'] or "9000000000"
                })
                print(f"✅ Loaded: {record['name']}")
            except Exception as e:
                print(f"⚠️ Skip {record['name']}: {e}")
        else:
            print(f"❓ Missing Image: {full_path}")
            
    return known_encodings, student_data

def mark_attendance(student_id, name):
    conn = get_db_connection()
    if not conn: return False
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    
    try:
        cursor.execute("SELECT id FROM attendance WHERE student_id=%s AND date=%s", (student_id, today))
        if cursor.fetchone():
            conn.close()
            return False 
            
        cursor.execute("INSERT INTO attendance (student_id, date, status) VALUES (%s, %s, 'present')", (student_id, today))
        conn.commit()
        conn.close()
        print(f"📝 [ATTENDANCE] Marked PRESENT: {name}")
        return True
    except Exception as e:
        print(f"❌ [SQL] {e}")
        return False

def run_attendance_cctv():
    known_encs, known_stus = load_student_database()
    if not known_encs:
        print("❌ No facial data found. Please register faces first.")
        return

    cap = cv2.VideoCapture(0)
    print("\n🛡️ UniBot CCTV Mode Active. Press 'Q' to generate report.")
    
    present_ids = set()

    while True:
        ret, frame = cap.read()
        if not ret: break

        # Optimize for speed
        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        locs = face_recognition.face_locations(rgb_frame)
        encs = face_recognition.face_encodings(rgb_frame, locs)

        for enc, loc in zip(encs, locs):
            matches = face_recognition.compare_faces(known_encs, enc, tolerance=0.5)
            name = "UNKNOWN"
            color = (0, 0, 255) # Crimson for unknown
            
            dists = face_recognition.face_distance(known_encs, enc)
            if matches and len(dists) > 0:
                idx = np.argmin(dists)
                if matches[idx]:
                    student = known_stus[idx]
                    name = student['name'].upper()
                    color = (241, 102, 99) # Royal Indigo (BGR: 99,102,241)
                    
                    if student['id'] not in present_ids:
                        if mark_attendance(student['id'], student['name']):
                            present_ids.add(student['id'])

            # Draw UI
            t, r, b, l = [v * 4 for v in loc]
            cv2.rectangle(frame, (l, t), (r, b), color, 2)
            cv2.putText(frame, name, (l, t - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        cv2.imshow('UniBot Biometric Monitor', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break

    cap.release()
    cv2.destroyAllWindows()
    generate_final_assets(known_stus, present_ids)

def generate_final_assets(all_stus, present_ids):
    print("\n📊 Generating End-of-Day Analytics...")
    report_list = []
    
    for stu in all_stus:
        is_present = stu['id'] in present_ids
        report_list.append({
            "Student Name": stu['name'],
            "Guardian Contact": stu['guardian'],
            "Status": "Present" if is_present else "Absent",
            "Timestamp": datetime.now().strftime('%H:%M:%S') if is_present else "N/A"
        })
        
        if not is_present:
            print(f"📱 [SMS SIMULATION] TO: {stu['guardian']} | MSG: Your ward {stu['name']} is ABSENT today.")

    pd.DataFrame(report_list).to_excel(EXCEL_OUTPUT, index=False)
    print(f"📈 Report Saved: {EXCEL_OUTPUT}")

if __name__ == "__main__":
    run_attendance_cctv()
