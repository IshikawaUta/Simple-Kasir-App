# app.py
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import sys
import json
from functools import wraps

# Import konfigurasi dari config.py
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Inisialisasi Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Halaman yang akan dialihkan jika pengguna belum login

# --- Debugging Koneksi MongoDB ---
print(f"DEBUG: MONGO_URI from config: {app.config.get('MONGO_URI')}")
print(f"DEBUG: MONGO_DBNAME from config: {app.config.get('MONGO_DBNAME')}")

mongo = None # Inisialisasi mongo sebagai None
try:
    mongo = PyMongo(app)
    # Coba akses database dengan perintah 'ping' untuk memicu koneksi awal.
    mongo.db.command('ping') # Menggunakan command('ping') pada objek database
    print("DEBUG: Koneksi MongoDB berhasil!")
except Exception as e:
    print(f"ERROR: Gagal terhubung ke MongoDB saat inisialisasi: {e}", file=sys.stderr)
    print("Pastikan MONGO_URI di file .env benar dan IP address Anda sudah diizinkan (whitelisted) di pengaturan Network Access MongoDB Atlas.", file=sys.stderr)
    sys.exit(1) # Keluar dari aplikasi jika koneksi gagal secara fatal

# Pastikan objek mongo.db terinisialisasi dengan benar sebelum mengakses koleksi
if mongo.db is None:
    print("FATAL ERROR: mongo.db is None after PyMongo initialization. This typically means the database name is missing in MONGO_URI or there's an issue with the URI format.", file=sys.stderr)
    sys.exit(1)

# Dapatkan referensi ke koleksi (collections) setelah koneksi berhasil dan terverifikasi
products_collection = mongo.db.products
sales_collection = mongo.db.sales
users_collection = mongo.db.users # Koleksi baru untuk pengguna
customers_collection = mongo.db.customers # Koleksi baru untuk pelanggan

# --- Model Pengguna untuk Flask-Login ---
class User(UserMixin):
    def __init__(self, user_data):
        self.user_data = user_data
        self.id = str(user_data['_id']) # Flask-Login membutuhkan atribut id
        self.username = user_data['username']
        self.role = user_data.get('role', 'cashier') # Default role: cashier

    def get_id(self):
        return self.id

# User loader untuk Flask-Login
@login_manager.user_loader
def load_user(user_id):
    user_data = users_collection.find_one({'_id': ObjectId(user_id)})
    if user_data:
        return User(user_data)
    return None

# --- Decorator Kustom untuk Peran Pengguna ---
def admin_required(f):
    @wraps(f)
    @login_required # Memastikan pengguna login terlebih dahulu
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Akses ditolak. Anda harus menjadi admin untuk melihat halaman ini.', 'danger')
            return redirect(url_for('index')) # Atau halaman error 403
        return f(*args, **kwargs)
    return decorated_function

# --- Rute Autentikasi ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_data = users_collection.find_one({'username': username})

        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(user_data)
            login_user(user)
            flash(f'Selamat datang, {user.username}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Username atau password salah.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Anda telah berhasil logout.', 'info')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
@admin_required # Hanya admin yang bisa mendaftar pengguna baru
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form.get('role', 'cashier') # Default role: cashier

        if users_collection.find_one({'username': username}):
            flash('Username ini sudah terdaftar. Silakan pilih yang lain.', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        users_collection.insert_one({
            'username': username,
            'password_hash': hashed_password,
            'role': role,
            'created_at': datetime.now()
        })
        flash(f'Pengguna {username} ({role}) berhasil ditambahkan!', 'success')
        return redirect(url_for('manage_users'))
    return render_template('register.html')

@app.route('/manage_users')
@admin_required # Hanya admin yang bisa melihat daftar pengguna
def manage_users():
    all_users = list(users_collection.find())
    return render_template('manage_users.html', users=all_users)

@app.route('/manage_users/delete/<id>', methods=['POST'])
@admin_required
def delete_user(id):
    if str(current_user.id) == id: # Pastikan admin tidak menghapus dirinya sendiri
        flash('Anda tidak bisa menghapus akun Anda sendiri!', 'danger')
    else:
        users_collection.delete_one({'_id': ObjectId(id)})
        flash('Pengguna berhasil dihapus!', 'success')
    return redirect(url_for('manage_users'))

# --- Rute Produk ---
@app.route('/')
@login_required # Semua pengguna yang login bisa melihat dashboard
def index():
    """Halaman Beranda Aplikasi Kasir."""
    latest_sales = list(sales_collection.find().sort('sale_date', -1).limit(5))
    return render_template('index.html', latest_sales=latest_sales)

@app.route('/products')
@login_required # Semua pengguna yang login bisa melihat produk
def products():
    """Menampilkan daftar semua produk."""
    all_products = list(products_collection.find())
    return render_template('products.html', products=all_products)

@app.route('/products/add', methods=['GET', 'POST'])
@admin_required # Hanya admin yang bisa menambah produk
def add_product():
    """Menambahkan produk baru."""
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        stock = int(request.form['stock'])
        unit = request.form.get('unit', 'pcs') # NEW: Tambahkan unit

        if products_collection.find_one({'name': name}):
            flash('Produk dengan nama ini sudah ada!', 'danger')
            return redirect(url_for('add_product'))

        products_collection.insert_one({
            'name': name,
            'price': price,
            'stock': stock,
            'unit': unit, # NEW: Simpan unit
            'created_at': datetime.now()
        })
        flash('Produk berhasil ditambahkan!', 'success')
        return redirect(url_for('products'))
    return render_template('add_product.html', product=None)

@app.route('/products/edit/<id>', methods=['GET', 'POST'])
@admin_required # Hanya admin yang bisa mengedit produk
def edit_product(id):
    """Mengedit detail produk."""
    product = products_collection.find_one({'_id': ObjectId(id)})
    if not product:
        flash('Produk tidak ditemukan!', 'danger')
        return redirect(url_for('products'))

    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        stock = int(request.form['stock'])
        unit = request.form.get('unit', 'pcs') # NEW: Tambahkan unit

        products_collection.update_one(
            {'_id': ObjectId(id)},
            {'$set': {'name': name, 'price': price, 'stock': stock, 'unit': unit}} # NEW: Update unit
        )
        flash('Produk berhasil diperbarui!', 'success')
        return redirect(url_for('products'))
    return render_template('add_product.html', product=product)

@app.route('/products/delete/<id>', methods=['POST'])
@admin_required
def delete_product(id):
    """Menghapus produk."""
    products_collection.delete_one({'_id': ObjectId(id)})
    flash('Produk berhasil dihapus!', 'success')
    return redirect(url_for('products'))

@app.route('/products/add_stock/<id>', methods=['GET', 'POST'])
@admin_required
def add_stock(id):
    """Menambah stok produk yang sudah ada."""
    product = products_collection.find_one({'_id': ObjectId(id)})
    if not product:
        flash('Produk tidak ditemukan!', 'danger')
        return redirect(url_for('products'))

    if request.method == 'POST':
        try:
            quantity = int(request.form['quantity'])
            if quantity <= 0:
                flash('Kuantitas harus lebih dari 0.', 'danger')
                return redirect(url_for('add_stock', id=id))
            
            products_collection.update_one(
                {'_id': ObjectId(id)},
                {'$inc': {'stock': quantity}}
            )
            flash(f'Stok {product["name"]} berhasil ditambahkan {quantity} unit!', 'success')
            return redirect(url_for('products'))
        except ValueError:
            flash('Kuantitas harus berupa angka valid.', 'danger')
            return redirect(url_for('add_stock', id=id))
    return render_template('add_stock.html', product=product)

# --- Rute Penjualan (diperbarui dengan Diskon) ---
@app.route('/sell', methods=['GET', 'POST'])
@login_required
def sell():
    """Melakukan proses penjualan."""
    all_products = list(products_collection.find())
    all_customers = list(customers_collection.find())
    
    if request.method == 'POST':
        cart_items_json = request.form.get('cart_items')
        customer_id = request.form.get('customer_id')
        amount_paid_str = request.form.get('amount_paid')
        discount_percentage_str = request.form.get('discount_percentage', '0') # NEW: Ambil persentase diskon, default 0

        print(f"DEBUG: Menerima request POST di /sell. cart_items_json: {cart_items_json}, amount_paid_str (raw from form): '{amount_paid_str}', discount_percentage_str: '{discount_percentage_str}'")

        if not cart_items_json:
            flash('Keranjang kosong!', 'danger')
            print("DEBUG: Keranjang kosong di sisi server.")
            return redirect(url_for('sell'))

        try:
            cart_items = json.loads(cart_items_json)
        except json.JSONDecodeError as e:
            flash('Data keranjang tidak valid.', 'danger')
            print(f"ERROR: JSONDecodeError pada cart_items: {e}", file=sys.stderr)
            return redirect(url_for('sell'))
        
        if not cart_items:
            flash('Keranjang kosong!', 'danger')
            print("DEBUG: Keranjang kosong setelah JSON parse.")
            return redirect(url_for('sell'))

        subtotal_before_discount = 0
        sale_products = []
        
        for item in cart_items:
            product_id_str = item['id']
            quantity = int(item['quantity'])
            
            product_info = products_collection.find_one({'_id': ObjectId(product_id_str)})
            
            if not product_info or product_info['stock'] < quantity:
                flash(f'Stok {product_info["name"] if product_info else "produk"} tidak mencukupi atau produk tidak ditemukan! Penjualan dibatalkan.', 'danger')
                print(f"DEBUG: Stok tidak mencukupi atau produk tidak ditemukan untuk {product_id_str}.")
                return redirect(url_for('sell'))
            
            item_subtotal = product_info['price'] * quantity
            subtotal_before_discount += item_subtotal
            
            sale_products.append({
                'product_id': ObjectId(product_id_str),
                'name': product_info['name'],
                'price': product_info['price'],
                'quantity': quantity,
                'subtotal': item_subtotal, # Ini adalah subtotal item, bukan total penjualan
                'unit': product_info.get('unit', 'pcs')
            })
            
            products_collection.update_one(
                {'_id': ObjectId(product_id_str)},
                {'$inc': {'stock': -quantity}}
            )
            print(f"DEBUG: Stok produk {product_info['name']} dikurangi.")
        
        # NEW: Hitung Diskon dan Total Akhir
        discount_percentage = 0.0
        try:
            # Clean discount percentage string
            cleaned_discount_str = discount_percentage_str.replace(',', '.')
            discount_percentage = float(cleaned_discount_str)
            
            if not (0 <= discount_percentage <= 100):
                flash('Persentase diskon harus antara 0 dan 100.', 'danger')
                print(f"DEBUG: Persentase diskon tidak valid: {discount_percentage}")
                return redirect(url_for('sell'))

            discount_amount = (subtotal_before_discount * discount_percentage) / 100
            total_amount = subtotal_before_discount - discount_amount
            print(f"DEBUG: Subtotal before discount: {subtotal_before_discount}, Discount Percentage: {discount_percentage}%, Discount Amount: {discount_amount}, Final Total: {total_amount}")
        except (ValueError, TypeError) as e:
            flash('Persentase diskon harus berupa angka valid.', 'danger')
            print(f"ERROR: ValueError/TypeError pada discount_percentage: {e}, Input string: '{discount_percentage_str}'", file=sys.stderr)
            return redirect(url_for('sell'))

        # Validasi dan hitung uang dibayar/kembalian
        amount_paid = 0.0
        try:
            if amount_paid_str is None:
                cleaned_amount_paid_str = ''
            else:
                cleaned_amount_paid_str = amount_paid_str.replace('.', '').replace(',', '.')
            
            print(f"DEBUG: Cleaned amount_paid_str (Python): '{cleaned_amount_paid_str}'")

            if not cleaned_amount_paid_str:
                amount_paid = 0.0
            else:
                amount_paid = float(cleaned_amount_paid_str)
            
            print(f"DEBUG: Parsed amount_paid (Python float): {amount_paid}")
            
            if amount_paid < total_amount:
                flash(f'Uang yang dibayarkan (Rp{amount_paid:,.2f}) kurang dari total belanja (Rp{total_amount:,.2f}). Penjualan dibatalkan.', 'danger')
                print("DEBUG: Uang dibayar kurang dari total.")
                return redirect(url_for('sell'))
            if amount_paid <= 0 and total_amount > 0:
                 flash('Uang yang dibayarkan harus lebih dari nol untuk total belanja positif.', 'danger')
                 print("DEBUG: Uang dibayar nol atau negatif untuk total positif.")
                 return redirect(url_for('sell'))
            
            change = amount_paid - total_amount
        except (ValueError, TypeError) as e:
            flash('Uang yang dibayarkan harus berupa angka valid.', 'danger')
            print(f"ERROR: ValueError/TypeError pada amount_paid: {e}, Input string: '{amount_paid_str}'", file=sys.stderr)
            return redirect(url_for('sell'))

        # Simpan transaksi penjualan
        sale_data = {
            'sale_date': datetime.now(),
            'products': sale_products,
            'subtotal_before_discount': subtotal_before_discount, 
            'discount_percentage': discount_percentage,           
            'discount_amount': discount_amount,                   
            'total_amount': total_amount,                         
            'amount_paid': amount_paid,
            'change': change,
            'cashier_id': current_user.id,
            'cashier_username': current_user.username
        }

        if customer_id and customer_id != 'none':
            sale_data['customer_id'] = ObjectId(customer_id)
            customer_info = customers_collection.find_one({'_id': sale_data['customer_id']})
            if customer_info:
                sale_data['customer_name'] = customer_info['name']
        
        print(f"DEBUG: Mencoba menyimpan sale_data: {sale_data}")
        try:
            result = sales_collection.insert_one(sale_data)
            new_sale_id = str(result.inserted_id)
            print(f"DEBUG: Penjualan berhasil disimpan. ID: {new_sale_id}")

            flash_message = f'Penjualan berhasil dilakukan! Kembalian: <strong>Rp{change:,.2f}</strong>. <a href="{url_for("view_receipt", sale_id=new_sale_id)}" target="_blank" class="alert-link">Lihat Struk</a>'
            flash(flash_message, 'success')
            return redirect(url_for('sell'))
        except Exception as e:
            flash('Gagal menyimpan transaksi. Mohon coba lagi atau hubungi administrator.', 'danger')
            print(f"CRITICAL ERROR: Gagal menyimpan transaksi ke MongoDB: {e}", file=sys.stderr)
            return redirect(url_for('sell'))

    return render_template('sell.html', products=all_products, customers=all_customers)

# --- Rute Struk Pembelian (diperbarui) ---
@app.route('/receipt/<sale_id>')
@login_required
def view_receipt(sale_id):
    sale = sales_collection.find_one({'_id': ObjectId(sale_id)})
    if not sale:
        flash('Struk tidak ditemukan.', 'danger')
        return redirect(url_for('index'))

    if 'customer_id' in sale:
        customer_info = customers_collection.find_one({'_id': sale['customer_id']})
        sale['customer_name'] = customer_info['name'] if customer_info else 'Pelanggan Tidak Dikenal'
    else:
        sale['customer_name'] = 'Umum'
    
    if isinstance(sale['sale_date'], dict) and '$date' in sale['sale_date']:
        if '$numberLong' in sale['sale_date']['$date']:
            sale['sale_date'] = datetime.fromtimestamp(int(sale['sale_date']['$date']['$numberLong']) / 1000)
        elif isinstance(sale['sale_date']['$date'], str):
            sale['sale_date'] = datetime.fromisoformat(sale['sale_date']['$date'].replace('Z', '+00:00'))

    # Jika subtotal_before_discount belum ada (untuk data lama), set ke total_amount
    sale['subtotal_before_discount'] = sale.get('subtotal_before_discount', sale.get('total_amount', 0))
    sale['discount_percentage'] = sale.get('discount_percentage', 0)
    sale['discount_amount'] = sale.get('discount_amount', 0)

    return render_template('receipt.html', sale=sale)


# --- Rute Laporan Penjualan (diperbarui) ---
@app.route('/sales_report')
@admin_required
def sales_report():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    query_filter = {}
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        query_filter['sale_date'] = {'$gte': start_date}
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1) - timedelta(microseconds=1)
        if 'sale_date' in query_filter:
            query_filter['sale_date']['$lte'] = end_date
        else:
            query_filter['sale_date'] = {'$lte': end_date}

    all_sales = list(sales_collection.find(query_filter).sort('sale_date', -1))

    for sale in all_sales:
        if 'customer_id' in sale:
            customer_info = customers_collection.find_one({'_id': sale['customer_id']})
            sale['customer_name'] = customer_info['name'] if customer_info else 'Pelanggan Tidak Dikenal'
        else:
            sale['customer_name'] = 'Umum'
        
        if not sale.get('cashier_username'):
            if sale.get('cashier_id'):
                cashier_info = users_collection.find_one({'_id': ObjectId(sale['cashier_id'])})
                sale['cashier_username'] = cashier_info['username'] if cashier_info else 'Kasir Tidak Dikenal'
            else:
                sale['cashier_username'] = 'Tidak Diketahui'
        
        # Tambahkan default untuk diskon jika data lama tidak punya field ini
        sale['subtotal_before_discount'] = sale.get('subtotal_before_discount', sale.get('total_amount', 0))
        sale['discount_percentage'] = sale.get('discount_percentage', 0)
        sale['discount_amount'] = sale.get('discount_amount', 0)


    return render_template('sales_report.html', 
                           sales=all_sales,
                           start_date=start_date_str,
                           end_date=end_date_str)

# --- Rute Manajemen Pelanggan ---
@app.route('/customers')
@admin_required
def customers():
    all_customers = list(customers_collection.find())
    return render_template('customers.html', customers=all_customers)

@app.route('/customers/add', methods=['GET', 'POST'])
@admin_required
def add_customer():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form.get('phone', '')
        email = request.form.get('email', '')

        if customers_collection.find_one({'name': name}):
            flash('Pelanggan dengan nama ini sudah ada!', 'danger')
            return redirect(url_for('add_customer'))

        customers_collection.insert_one({
            'name': name,
            'phone': phone,
            'email': email,
            'created_at': datetime.now()
        })
        flash('Pelanggan berhasil ditambahkan!', 'success')
        return redirect(url_for('customers'))
    return render_template('add_customer.html', customer=None)

@app.route('/customers/edit/<id>', methods=['GET', 'POST'])
@admin_required
def edit_customer(id):
    customer = customers_collection.find_one({'_id': ObjectId(id)})
    if not customer:
        flash('Pelanggan tidak ditemukan!', 'danger')
        return redirect(url_for('customers'))

    if request.method == 'POST':
        name = request.form['name']
        phone = request.form.get('phone', '')
        email = request.form.get('email', '')
        
        customers_collection.update_one(
            {'_id': ObjectId(id)},
            {'$set': {'name': name, 'phone': phone, 'email': email}}
        )
        flash('Data pelanggan berhasil diperbarui!', 'success')
        return redirect(url_for('customers'))
    return render_template('add_customer.html', customer=customer)

@app.route('/customers/delete/<id>', methods=['POST'])
@admin_required
def delete_customer(id):
    customers_collection.delete_one({'_id': ObjectId(id)})
    flash('Pelanggan berhasil dihapus!', 'success')
    return redirect(url_for('customers'))

# --- Rute untuk menampilkan 404 (optional) ---
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


if __name__ == '__main__':
    app.run(debug=True)
