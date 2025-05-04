from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["doctor_appointments"]

doctor_availability = db["DoctorAvailability"]
appointments = db["Appointments"]
patients = db["Patients"]

# Optional test function to verify connection
def test_connection():
    try:
        db.command("ping")
        print("✅ MongoDB connection successful!")
    except Exception as e:
        print("❌ MongoDB connection failed:", e)
