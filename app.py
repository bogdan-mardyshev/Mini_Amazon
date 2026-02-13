import os
from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Product, Order, OrderItem

# Настройки
app = Flask(__name__)
app.config['SECRET_KEY'] = 'simple-secret-key-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация
db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- СОЗДАНИЕ НАЧАЛЬНЫХ ДАННЫХ ---
def create_initial_data():
    db.create_all()

    # Создаем админа, если нет
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', is_admin=True)
        admin.set_password('admin123')
        db.session.add(admin)
        print("Admin user created (pass: admin123)")

    # Создаем тестовые товары
    if Product.query.count() == 0:
        products = [
            Product(name='iPhone 15', price=999.00, stock=10),
            Product(name='MacBook Air', price=1200.50, stock=5),
            Product(name='Sony Headphones', price=199.99, stock=20),
            Product(name='Gaming Mouse', price=59.90, stock=50),
            Product(name='Mechanical Keyboard', price=149.00, stock=15)
        ]
        db.session.add_all(products)
        print("Test products added")

    db.session.commit()


#  ROUTES

@app.route('/')
def index():
    query = request.args.get('search')
    if query:
        products = Product.query.filter(Product.name.ilike(f'%{query}%')).all()
    else:
        products = Product.query.all()
    return render_template('index.html', products=products)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('register'))

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        return redirect(url_for('index'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid login', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)

    if product.stock <= 0:
        flash('Out of stock', 'warning')
        return redirect(url_for('index'))

    if 'cart' not in session:
        session['cart'] = {}

    cart = session['cart']
    pid = str(product_id)

    current_qty = cart.get(pid, 0)

    if current_qty + 1 > product.stock:
        flash('Cannot add more than stock', 'warning')
    else:
        cart[pid] = current_qty + 1
        session.modified = True

    return redirect(url_for('index'))


@app.route('/cart')
def cart():
    cart_data = session.get('cart', {})
    items = []
    grand_total = 0

    for pid, qty in cart_data.items():
        product = Product.query.get(int(pid))
        if product:
            total = product.price * qty
            grand_total += total
            items.append({'product': product, 'qty': qty, 'total': total})

    return render_template('cart.html', items=items, grand_total=grand_total)



@app.route('/remove_item/<int:product_id>')
def remove_item(product_id):
    if 'cart' in session:
        cart = session['cart']
        pid = str(product_id)
        if pid in cart:
            cart.pop(pid) # Удаляем конкретный ключ (товар)
            session.modified = True
            flash('Item removed', 'info')
    return redirect(url_for('cart'))



@app.route('/clear_cart')
def clear_cart():
    session.pop('cart', None)
    return redirect(url_for('cart'))


@app.route('/checkout', methods=['POST'])
@login_required
def checkout():
    cart_data = session.get('cart', {})
    if not cart_data:
        return redirect(url_for('index'))

    total_price = 0
    final_items = []

    # Validation loop
    for pid, qty in cart_data.items():
        product = Product.query.get(int(pid))
        if not product or product.stock < qty:
            flash(f'Stock issue with {product.name}', 'danger')
            return redirect(url_for('cart'))
        total_price += product.price * qty
        final_items.append((product, qty))

    # Create Order
    order = Order(user_id=current_user.id, total_price=total_price)
    db.session.add(order)
    db.session.flush()

    for product, qty in final_items:
        product.stock -= qty
        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            product_name=product.name,
            quantity=qty,
            price_at_purchase=product.price
        )
        db.session.add(order_item)

    db.session.commit()
    session.pop('cart', None)
    flash('Order placed successfully!', 'success')
    return redirect(url_for('orders'))


@app.route('/orders')
@login_required
def orders():
    my_orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.date_posted.desc()).all()
    return render_template('orders.html', orders=my_orders)


#  ADMIN ROUTES (NEW: ADD & EDIT)

@app.route('/admin/add', methods=['GET', 'POST'])
@login_required
def add_product():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name')
        price = float(request.form.get('price'))
        stock = int(request.form.get('stock'))

        db.session.add(Product(name=name, price=price, stock=stock))
        db.session.commit()
        return redirect(url_for('index'))

    # Передаем product=None, чтобы шаблон знал, что это создание
    return render_template('admin.html', product=None)


@app.route('/admin/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))

    product = Product.query.get_or_404(product_id)

    if request.method == 'POST':
        product.name = request.form.get('name')
        product.price = float(request.form.get('price'))
        product.stock = int(request.form.get('stock'))

        db.session.commit()
        flash('Product updated!', 'success')
        return redirect(url_for('index'))

    # Передаем существующий product для заполнения полей
    return render_template('admin.html', product=product)


if __name__ == '__main__':
    with app.app_context():
        create_initial_data()
    app.run(debug=True)