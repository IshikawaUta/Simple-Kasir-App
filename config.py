# config.py
import os
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'super_secret_key_yang_sangat_sulit_ditebak' # Ganti dengan kunci rahasia yang kuat
    MONGO_URI = os.environ.get('MONGO_URI') # Connection string MongoDB Atlas Anda
    MONGO_DBNAME = os.environ.get('MONGO_DBNAME') or 'cashier_db' # Nama database Anda di MongoDB Atlas