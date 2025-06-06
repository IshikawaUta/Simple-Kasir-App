# wsgi.py
# Pastikan 'app' diimpor dari file 'app.py' Anda
from app import app

# Vercel akan secara otomatis mencari variabel 'app' di file ini
# atau variabel 'handler' jika Anda menggunakan fungsi serverless.
# Untuk Flask, kita biasanya mendefinisikan instance Flask sebagai 'app'.