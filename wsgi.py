# wsgi.py
from app import app as application # Mengimpor instance 'app' dari app.py Anda

# Penting: Pastikan app.py Anda memiliki 'app = Flask(__name__)'
# dan tidak ada 'if __name__ == '__main__': app.run(debug=True)' yang akan dieksekusi di sini.
# Vercel akan menangani server WSGI sendiri.