from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
from sqlalchemy.sql import func

app = Flask(__name__)
app.config['SECRET_KEY'] = 'replace-with-a-secure-random-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///expenses.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    expenses = db.relationship('Expense', backref='owner', lazy=True)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(120), nullable=False)
    date = db.Column(db.Date, nullable=False, default=func.current_date())
    note = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET','POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            flash('Fill all fields', 'danger')
            return redirect(url_for('signup'))
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('signup'))
        hashed = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(username=username, password=hashed)
        db.session.add(user)
        db.session.commit()
        flash('Account created. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard', methods=['GET','POST'])
@login_required
def dashboard():
    if request.method == 'POST':
        # add expense
        title = request.form['title'].strip()
        amount = request.form['amount']
        category = request.form['category'].strip()
        date_str = request.form['date']
        note = request.form.get('note', '').strip()
        if not title or not amount or not category:
            flash('Please fill required fields', 'danger')
            return redirect(url_for('dashboard'))
        try:
            amount_val = float(amount)
        except ValueError:
            flash('Invalid amount', 'danger')
            return redirect(url_for('dashboard'))
        try:
            date_val = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            date_val = datetime.utcnow().date()
        expense = Expense(title=title, amount=amount_val, category=category, date=date_val, note=note, owner=current_user)
        db.session.add(expense)
        db.session.commit()
        flash('Expense added', 'success')
        return redirect(url_for('dashboard'))

    # Read data
    expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).all()
    total = db.session.query(func.sum(Expense.amount)).filter(Expense.user_id==current_user.id).scalar() or 0.0
    # Send summary by category
    cat_summary = db.session.query(Expense.category, func.sum(Expense.amount)).filter(Expense.user_id==current_user.id).group_by(Expense.category).all()
    # monthly trend (YYYY-MM)
    monthly = db.session.query(func.strftime('%Y-%m', Expense.date), func.sum(Expense.amount)).filter(Expense.user_id==current_user.id).group_by(func.strftime('%Y-%m', Expense.date)).order_by(func.strftime('%Y-%m', Expense.date)).all()
    return render_template('dashboard.html', expenses=expenses, total=total, cat_summary=cat_summary, monthly=monthly)

@app.route('/delete/<int:expense_id>', methods=['POST'])
@login_required
def delete_expense(expense_id):
    e = Expense.query.get_or_404(expense_id)
    if e.user_id != current_user.id:
        flash('Not allowed', 'danger')
        return redirect(url_for('dashboard'))
    db.session.delete(e)
    db.session.commit()
    flash('Deleted', 'success')
    return redirect(url_for('dashboard'))

# Endpoint to serve chart data as JSON
@app.route('/chart-data')
@login_required
def chart_data():
    cat_summary = db.session.query(Expense.category, func.sum(Expense.amount)).filter(Expense.user_id==current_user.id).group_by(Expense.category).all()
    monthly = db.session.query(func.strftime('%Y-%m', Expense.date), func.sum(Expense.amount)).filter(Expense.user_id==current_user.id).group_by(func.strftime('%Y-%m', Expense.date)).order_by(func.strftime('%Y-%m', Expense.date)).all()
    return jsonify({
        'by_category': [{ 'category': c, 'amount': a } for c,a in cat_summary],
        'monthly': [{ 'month': m, 'amount': a } for m,a in monthly]
    })

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
