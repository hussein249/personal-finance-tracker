import os
from datetime import datetime, date
from calendar import month_abbr

from flask import Flask, render_template, request, url_for, flash, redirect, Response
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from flask_wtf import CSRFProtect
from sqlalchemy import func, extract

from models import db, User, Transaction, Budget, EXPENSE_CATEGORIES, INCOME_CATEGORIES

app = Flask(__name__)

# --- Configuration -----------------------------------------------------
# DATABASE_URL is read from the environment so the same code runs on
# SQLite locally and PostgreSQL in production/deployment, as required
# by the thesis proposal. Falls back to SQLite for local dev only.
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'sqlite:///finance_tracker.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# SECRET_KEY must come from the environment in real deployment. A random
# fallback is generated so the app never silently ships a known dev key.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or os.urandom(24).hex()

db.init_app(app)
csrf = CSRFProtect(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Please log in to access your dashboard."
login_manager.login_message_category = "error"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


with app.app_context():
    db.create_all()


# --- Helpers -------------------------------------------------------------

def parse_date_or_none(s: str):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def categories_for(tx_type: str):
    return INCOME_CATEGORIES if tx_type == 'income' else EXPENSE_CATEGORIES


# --- Auth routes -----------------------------------------------------------

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        confirm = request.form.get('confirm_password') or ''

        if not username or not email or not password:
            flash('Please fill in all fields.', 'error')
            return redirect(url_for('register'))

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return redirect(url_for('register'))

        if password != confirm:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('That username is already taken.', 'error')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('That email is already registered.', 'error')
            return redirect(url_for('register'))

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Account created. Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''

        user = User.query.filter_by(username=username).first()

        if user is None or not user.check_password(password):
            flash('Invalid username or password.', 'error')
            return redirect(url_for('login'))

        login_user(user)
        flash(f'Welcome back, {user.username}!', 'success')
        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


# --- Dashboard -------------------------------------------------------------

@app.route('/')
@login_required
def index():
    start_str = (request.args.get('start') or '').strip()
    end_str = (request.args.get('end') or '').strip()
    selected_category = (request.args.get('category') or '').strip()
    selected_type = (request.args.get('type') or '').strip()

    start_date = parse_date_or_none(start_str)
    end_date = parse_date_or_none(end_str)

    if start_date and end_date and end_date < start_date:
        flash('End date cannot be before start date.', 'error')
        start_date = end_date = None
        start_str = end_str = ''

    base_q = Transaction.query.filter_by(user_id=current_user.id)

    def apply_filters(q):
        if start_date:
            q = q.filter(Transaction.date >= start_date)
        if end_date:
            q = q.filter(Transaction.date <= end_date)
        if selected_category:
            q = q.filter(Transaction.category == selected_category)
        if selected_type in ('income', 'expense'):
            q = q.filter(Transaction.type == selected_type)
        return q

    transactions = apply_filters(base_q).order_by(
        Transaction.date.desc(), Transaction.id.desc()
    ).all()

    total_income = sum(t.amount for t in transactions if t.type == 'income')
    total_expense = sum(t.amount for t in transactions if t.type == 'expense')
    balance = round(total_income - total_expense, 2)
    total_income = round(total_income, 2)
    total_expense = round(total_expense, 2)

    # Pie chart: expense breakdown by category (within current filters)
    cat_rows = (
        apply_filters(
            db.session.query(Transaction.category, func.sum(Transaction.amount))
            .filter_by(user_id=current_user.id, type='expense')
        )
        .group_by(Transaction.category)
        .all()
    )
    cat_labels = [c for c, _ in cat_rows]
    cat_values = [round(float(s or 0), 2) for _, s in cat_rows]

    # Monthly trend: income vs expense for the last 6 months
    trend_labels = []
    trend_income = []
    trend_expense = []
    today = date.today()
    year, month = today.year, today.month
    months_back = []
    for i in range(5, -1, -1):
        m = month - i
        y = year
        while m <= 0:
            m += 12
            y -= 1
        months_back.append((y, m))

    for y, m in months_back:
        income_sum = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.user_id == current_user.id,
            Transaction.type == 'income',
            extract('year', Transaction.date) == y,
            extract('month', Transaction.date) == m,
        ).scalar() or 0
        expense_sum = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.user_id == current_user.id,
            Transaction.type == 'expense',
            extract('year', Transaction.date) == y,
            extract('month', Transaction.date) == m,
        ).scalar() or 0
        trend_labels.append(f"{month_abbr[m]} {y}")
        trend_income.append(round(float(income_sum), 2))
        trend_expense.append(round(float(expense_sum), 2))

    # Budget alerts: current month spending vs. limit, per category
    cur_year, cur_month = today.year, today.month
    budgets = Budget.query.filter_by(user_id=current_user.id).all()
    budget_status = []
    for b in budgets:
        spent = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.user_id == current_user.id,
            Transaction.type == 'expense',
            Transaction.category == b.category,
            extract('year', Transaction.date) == cur_year,
            extract('month', Transaction.date) == cur_month,
        ).scalar() or 0
        spent = round(float(spent), 2)
        budget_status.append({
            'category': b.category,
            'limit': b.monthly_limit,
            'spent': spent,
            'over': spent > b.monthly_limit,
            'pct': min(100, round((spent / b.monthly_limit) * 100)) if b.monthly_limit > 0 else 0,
        })

    return render_template(
        'index.html',
        expense_categories=EXPENSE_CATEGORIES,
        income_categories=INCOME_CATEGORIES,
        today=date.today().isoformat(),
        transactions=transactions,
        total_income=total_income,
        total_expense=total_expense,
        balance=balance,
        start_str=start_str,
        end_str=end_str,
        selected_category=selected_category,
        selected_type=selected_type,
        cat_labels=cat_labels,
        cat_values=cat_values,
        trend_labels=trend_labels,
        trend_income=trend_income,
        trend_expense=trend_expense,
        budget_status=budget_status,
    )


# --- Transaction CRUD --------------------------------------------------

@app.route('/add', methods=['POST'])
@login_required
def add():
    description = (request.form.get('description') or '').strip()
    amount_str = (request.form.get('amount') or '').strip()
    category = (request.form.get('category') or '').strip()
    date_str = (request.form.get('date') or '').strip()
    tx_type = (request.form.get('type') or 'expense').strip()

    if tx_type not in ('income', 'expense'):
        tx_type = 'expense'

    if not description or not amount_str or not category:
        flash('Please fill description, amount, and category.', 'error')
        return redirect(url_for('index'))

    if category not in categories_for(tx_type):
        flash('Invalid category for the selected type.', 'error')
        return redirect(url_for('index'))

    try:
        amount = float(amount_str)
        if amount <= 0:
            raise ValueError
    except ValueError:
        flash('Amount must be a positive number.', 'error')
        return redirect(url_for('index'))

    d = parse_date_or_none(date_str) or date.today()

    t = Transaction(
        user_id=current_user.id,
        description=description[:120],
        amount=amount,
        category=category,
        type=tx_type,
        date=d,
    )
    db.session.add(t)
    db.session.commit()

    flash('Transaction added.', 'success')
    return redirect(url_for('index'))


@app.route('/delete/<int:tx_id>', methods=['POST'])
@login_required
def delete(tx_id):
    t = Transaction.query.filter_by(id=tx_id, user_id=current_user.id).first_or_404()
    db.session.delete(t)
    db.session.commit()
    flash('Transaction deleted.', 'success')
    return redirect(url_for('index'))


@app.route('/edit/<int:tx_id>', methods=['GET'])
@login_required
def edit(tx_id):
    t = Transaction.query.filter_by(id=tx_id, user_id=current_user.id).first_or_404()
    return render_template(
        'edit.html',
        tx=t,
        expense_categories=EXPENSE_CATEGORIES,
        income_categories=INCOME_CATEGORIES,
        today=date.today().isoformat(),
    )


@app.route('/edit/<int:tx_id>', methods=['POST'])
@login_required
def edit_post(tx_id):
    t = Transaction.query.filter_by(id=tx_id, user_id=current_user.id).first_or_404()

    description = (request.form.get('description') or '').strip()
    amount_str = (request.form.get('amount') or '').strip()
    category = (request.form.get('category') or '').strip()
    date_str = (request.form.get('date') or '').strip()
    tx_type = (request.form.get('type') or 'expense').strip()

    if tx_type not in ('income', 'expense'):
        tx_type = 'expense'

    if not description or not amount_str or not category:
        flash('Please fill description, amount, category.', 'error')
        return redirect(url_for('edit', tx_id=tx_id))

    if category not in categories_for(tx_type):
        flash('Invalid category for the selected type.', 'error')
        return redirect(url_for('edit', tx_id=tx_id))

    try:
        amount = float(amount_str)
        if amount <= 0:
            raise ValueError
    except ValueError:
        flash('Amount must be a positive number.', 'error')
        return redirect(url_for('edit', tx_id=tx_id))

    d = parse_date_or_none(date_str) or date.today()

    t.description = description[:120]
    t.amount = amount
    t.category = category
    t.type = tx_type
    t.date = d

    db.session.commit()
    flash('Transaction updated.', 'success')
    return redirect(url_for('index'))


# --- Budgets -------------------------------------------------------------

@app.route('/budgets', methods=['GET', 'POST'])
@login_required
def budgets():
    if request.method == 'POST':
        category = (request.form.get('category') or '').strip()
        limit_str = (request.form.get('monthly_limit') or '').strip()

        if category not in EXPENSE_CATEGORIES:
            flash('Invalid category.', 'error')
            return redirect(url_for('budgets'))

        try:
            limit = float(limit_str)
            if limit <= 0:
                raise ValueError
        except ValueError:
            flash('Budget limit must be a positive number.', 'error')
            return redirect(url_for('budgets'))

        existing = Budget.query.filter_by(user_id=current_user.id, category=category).first()
        if existing:
            existing.monthly_limit = limit
        else:
            db.session.add(Budget(user_id=current_user.id, category=category, monthly_limit=limit))
        db.session.commit()
        flash(f'Budget for {category} saved.', 'success')
        return redirect(url_for('budgets'))

    existing_budgets = Budget.query.filter_by(user_id=current_user.id).all()
    return render_template(
        'budgets.html',
        budgets=existing_budgets,
        expense_categories=EXPENSE_CATEGORIES,
    )


@app.route('/budgets/delete/<int:budget_id>', methods=['POST'])
@login_required
def delete_budget(budget_id):
    b = Budget.query.filter_by(id=budget_id, user_id=current_user.id).first_or_404()
    db.session.delete(b)
    db.session.commit()
    flash('Budget removed.', 'success')
    return redirect(url_for('budgets'))


# --- Export ----------------------------------------------------------------

@app.route('/export.csv')
@login_required
def export_csv():
    start_str = (request.args.get('start') or '').strip()
    end_str = (request.args.get('end') or '').strip()
    selected_category = (request.args.get('category') or '').strip()
    selected_type = (request.args.get('type') or '').strip()

    start_date = parse_date_or_none(start_str)
    end_date = parse_date_or_none(end_str)

    q = Transaction.query.filter_by(user_id=current_user.id)

    if start_date:
        q = q.filter(Transaction.date >= start_date)
    if end_date:
        q = q.filter(Transaction.date <= end_date)
    if selected_category:
        q = q.filter(Transaction.category == selected_category)
    if selected_type in ('income', 'expense'):
        q = q.filter(Transaction.type == selected_type)

    rows = q.order_by(Transaction.date, Transaction.id).all()

    lines = ['date,type,description,category,amount']
    for t in rows:
        safe_desc = t.description.replace(',', ';')
        lines.append(f"{t.date.isoformat()},{t.type},{safe_desc},{t.category},{t.amount:.2f}")

    csv_data = '\n'.join(lines)
    filename = f"transactions_{start_str or 'all'}_to_{end_str or 'all'}.csv"

    return Response(
        csv_data,
        headers={
            'Content-Type': 'text/csv',
            'Content-Disposition': f'attachment; filename={filename}',
        },
    )


if __name__ == '__main__':
    app.run(debug=True, port=4848)
