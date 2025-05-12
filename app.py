from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Генерирует 24 случайных байта

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Таблица курсов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            creator_id INTEGER NOT NULL,
            FOREIGN KEY (creator_id) REFERENCES users (id)
        )
    ''')
    
    # Таблица уроков
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            broadcast_date TEXT NOT NULL,
            FOREIGN KEY (course_id) REFERENCES courses (id)''')
    
    conn.commit()
    conn.close()

init_db()

# Временное хранилище для уроков (чтобы сохранять их во время редактирования)
# В реальном приложении лучше использовать базу данных или более надежное хранилище
temp_lessons = {}

@app.route('/')
def home():
    if 'username' in session:
        # Получаем список курсов пользователя
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE username = ?', (session['username'],))
        user_id = cursor.fetchone()[0]
        
        cursor.execute('SELECT * FROM courses WHERE creator_id = ?', (user_id,))
        user_courses = cursor.fetchall()
        conn.close()
        
        return render_template('home.html', username=session['username'], courses=user_courses)
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']

        if not username or not password or not email:
            flash('All fields are required!')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)

        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            cursor.execute('INSERT INTO users (username, password, email) VALUES (?, ?, ?)',
                          (username, hashed_password, email))
            conn.commit()
            flash('Registration successful! Please log in.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError as e:
            if 'username' in str(e):
                flash('Username already exists!')
            elif 'email' in str(e):
                flash('Email already registered!')
            return redirect(url_for('register'))
        finally:
            conn.close()

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email_or_username = request.form['email_or_username']
        password = request.form['password']

        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        
        # Пытаемся найти пользователя по email или username
        cursor.execute('SELECT * FROM users WHERE email = ? OR username = ?', 
                      (email_or_username, email_or_username))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['username'] = user[1]  # Сохраняем username в сессии
            session['user_id'] = user[0]   # Сохраняем user_id в сессии
            flash('Logged in successfully!')
            return redirect(url_for('home'))
        else:
            flash('Invalid email/username or password!')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('user_id', None)
    flash('You have been logged out.')
    return redirect(url_for('home'))

@app.route('/create_course', methods=['GET', 'POST'])
def create_course():
    if 'username' not in session:
        flash('You need to login first!')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        price = float(request.form['price'])
        
        if not title or not price:
            flash('Title and price are required!')
            return redirect(url_for('create_course'))
        
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            cursor.execute('INSERT INTO courses (title, description, price, creator_id) VALUES (?, ?, ?, ?)',
                          (title, description, price, session['user_id']))
            course_id = cursor.lastrowid
            conn.commit()
            
            # Сохраняем временные уроки в базу данных
            if course_id in temp_lessons:
                for lesson in temp_lessons[course_id]:
                    cursor.execute('INSERT INTO lessons (course_id, title, description, broadcast_date) VALUES (?, ?, ?, ?)',
                                  (course_id, lesson['title'], lesson['description'], lesson['broadcast_date']))
                conn.commit()
                del temp_lessons[course_id]  # Удаляем временные данные
                
            flash('Course created successfully!')
            return redirect(url_for('home'))
        except Exception as e:
            flash(f'Error creating course: {str(e)}')
            return redirect(url_for('create_course'))
        finally:
            conn.close()
    
    return render_template('create_course.html')

@app.route('/course_editor/<int:course_id>', methods=['GET', 'POST'])
def course_editor(course_id):
    if 'username' not in session:
        flash('You need to login first!')
        return redirect(url_for('login'))
    
    # Проверяем, что курс принадлежит текущему пользователю
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT creator_id FROM courses WHERE id = ?', (course_id,))
    course = cursor.fetchone()
    
    if not course or course[0] != session['user_id']:
        flash('You are not authorized to edit this course!')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        # Добавляем новый урок во временное хранилище
        title = request.form['title']
        description = request.form['description']
        broadcast_date = request.form['broadcast_date']
        
        if not title or not broadcast_date:
            flash('Title and broadcast date are required!')
            return redirect(url_for('course_editor', course_id=course_id))
        
        # Сохраняем урок во временное хранилище
        if course_id not in temp_lessons:
            temp_lessons[course_id] = []
            
        temp_lessons[course_id].append({
            'title': title,
            'description': description,
            'broadcast_date': broadcast_date
        })
        
        flash('Lesson added successfully!')
        return redirect(url_for('course_editor', course_id=course_id))
    
    # Получаем уроки из базы данных и временного хранилища
    cursor.execute('SELECT * FROM lessons WHERE course_id = ?', (course_id,))
    db_lessons = cursor.fetchall()
    
    temp_course_lessons = temp_lessons.get(course_id, [])
    
    # Объединяем уроки из базы и временного хранилища
    all_lessons = []
    for lesson in db_lessons:
        all_lessons.append({
            'id': lesson[0],
            'title': lesson[2],
            'description': lesson[3],
            'broadcast_date': lesson[4]
        })
    
    all_lessons.extend(temp_course_lessons)
    
    conn.close()
    
    return render_template('course_editor.html', course_id=course_id, lessons=all_lessons)

if __name__ == '__main__':
    app.run(debug=True)