from flask import Flask, render_template, request, redirect, url_for, flash, g
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user,
)
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # مفتاح سري عشوائي

# ------ إعداد Flask-Login ------ #
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ------ نموذج المستخدم ------ #
class User(UserMixin):
    def __init__(self, user_id):
        self.id = user_id

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

# ------ إعداد قاعدة البيانات ------ #
DATABASE = "tasks.db"

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        # إنشاء جدول المستخدمين أولاً
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)
        # ثم إنشاء جدول التصنيفات
        db.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        # وأخيراً إنشاء جدول المهام
        db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                category_id INTEGER,
                due_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (category_id) REFERENCES categories (id)
            )
        """)
        db.commit()

# إعادة تهيئة قاعدة البيانات
def reset_db():
    with app.app_context():
        db = get_db()
        # حذف الجداول القديمة
        db.execute("DROP TABLE IF EXISTS tasks")
        db.execute("DROP TABLE IF EXISTS categories")
        db.execute("DROP TABLE IF EXISTS users")
        db.commit()
        # إنشاء الجداول من جديد
        init_db()

init_db()

# ------ الروابط الجديدة للتسجيل وتسجيل الدخول ------ #
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        db = get_db()

        try:
            db.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, generate_password_hash(password)),
            )
            db.commit()
            flash("تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("اسم المستخدم موجود مسبقًا!", "error")

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        db = get_db()

        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user and check_password_hash(user["password"], password):
            user_obj = User(user["id"])
            login_user(user_obj)
            return redirect(url_for("index"))
        else:
            flash("بيانات الدخول غير صحيحة!", "error")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ------ تعديل الروابط الحالية ------ #
@app.route("/")
@login_required
def index():
    db = get_db()
    sort_by = request.args.get('sort', 'created_at')
    order = request.args.get('order', 'desc')
    category_filter = request.args.get('category', '')

    query = """
        SELECT t.*, c.name as category_name 
        FROM tasks t 
        LEFT JOIN categories c ON t.category_id = c.id 
        WHERE t.user_id = ?
    """
    params = [current_user.id]

    if category_filter:
        query += " AND t.category_id = ?"
        params.append(category_filter)

    query += f" ORDER BY t.{sort_by} {order}"
    
    tasks = db.execute(query, params).fetchall()
    categories = db.execute(
        "SELECT * FROM categories WHERE user_id = ?", 
        (current_user.id,)
    ).fetchall()
    
    return render_template('index.html', tasks=tasks, categories=categories)

@app.route("/add", methods=["POST"])
@login_required
def add():
    title = request.form.get('title')
    description = request.form.get('description')
    category_id = request.form.get('category_id')
    due_date = request.form.get('due_date')

    if title:
        db = get_db()
        db.execute(
            """INSERT INTO tasks (title, description, category_id, due_date, user_id) 
            VALUES (?, ?, ?, ?, ?)""",
            (title, description, category_id, due_date, current_user.id)
        )
        db.commit()
    return redirect(url_for("index"))

@app.route("/edit/<int:task_id>", methods=["POST"])
@login_required
def edit_task(task_id):
    title = request.form.get('title')
    description = request.form.get('description')
    category_id = request.form.get('category_id')
    due_date = request.form.get('due_date')

    if title:
        db = get_db()
        db.execute(
            """UPDATE tasks 
            SET title = ?, description = ?, category_id = ?, due_date = ?
            WHERE id = ? AND user_id = ?""",
            (title, description, category_id, due_date, task_id, current_user.id)
        )
        db.commit()
    return redirect(url_for("index"))

@app.route("/categories", methods=["POST"])
@login_required
def add_category():
    name = request.form.get('name')
    if name:
        db = get_db()
        db.execute(
            "INSERT INTO categories (name, user_id) VALUES (?, ?)",
            (name, current_user.id)
        )
        db.commit()
    return redirect(url_for("index"))

@app.route("/delete/<int:task_id>", methods=["POST"])
@login_required
def delete(task_id):
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, current_user.id))
    db.commit()
    return redirect(url_for("index"))

if __name__ == "__main__":
    reset_db()  # أضف هذا السطر مؤقتاً
    app.run(debug=True)