from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText

import os
from dotenv import load_dotenv

load_dotenv()


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///reservations.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key'

db = SQLAlchemy(app)

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    time = db.Column(db.DateTime, nullable=False)
    table_number = db.Column(db.Integer, nullable=True)

class Archive(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    time = db.Column(db.DateTime, nullable=False)
    table_number = db.Column(db.Integer, nullable=True)

from flask_mail import Mail, Message

app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT'))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

mail = Mail(app)

@app.route('/')
def index():
    now = datetime.now()
    available_tables = 10 - Reservation.query.filter(Reservation.time >= now, Reservation.time < now + timedelta(hours=1)).count()
    return render_template('index.html', available_tables=available_tables)

@app.route('/client', methods=['GET', 'POST'])
def client():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        email = request.form['email']
        time = datetime.strptime(request.form['time'], "%Y-%m-%dT%H:%M")
        
        if Reservation.query.filter_by(time=time).count() < 10:
            new_reservation = Reservation(name=name, phone=phone, email=email, time=time)
            db.session.add(new_reservation)
            db.session.commit()
            send_confirmation_email(email, time)
            flash('Reservation confirmed!', 'success')
        else:
            flash('No available tables at this time.', 'danger')
        return redirect(url_for('client'))
    return render_template('client.html')

@app.route('/reservation')
def reservation():
    reservations = Reservation.query.all()
    return render_template('reservation.html', reservations=reservations)

@app.route('/reservation/delete/<int:id>')
def delete_reservation(id):
    res = Reservation.query.get(id)
    if res:
        db.session.delete(res)
        db.session.commit()
    return redirect(url_for('reservation'))

@app.route('/reservation_archive')
def reservation_archive():
    archives = Archive.query.all()
    return render_template('reservation_archive.html', archives=archives)

@app.route('/restaurant')
def restaurant():
    return render_template('restaurant.html')

def send_confirmation_email(email, time):
    msg = Message("Rezervācijas apstiprinājums",
                  recipients=[email])
    msg.body = f"Labdien! Jūsu rezervācija ir apstiprināta.\n\nLaiks: {time.strftime('%Y-%m-%d %H:%M')}\n\nPaldies, ka izvēlējāties mūsu restorānu!"
    
    try:
        mail.send(msg)
        print(f"E-pasts nosūtīts uz {email}")
    except Exception as e:
        print(f"Kļūda e-pasta sūtīšanā: {e}")


if __name__ == '__main__':
   with app.app_context():
    db.create_all()
    app.run(debug=True)

# HTML Files:
# index.html
# client.html
# reservation.html
# restaurant.html
# reservation_archive.html

# index.html
# <html>
# <head><title>Restaurant Reservation System</title></head>
# <body>
# <h1>Restaurant Reservations</h1>
# <p>Available Tables: {{ available_tables }}</p>
# <a href="/client">Make a Reservation</a>
# <a href="/reservation">Manage Reservations</a>
# </body>
# </html>

# client.html
# <html>
# <head><title>Client Reservation</title></head>
# <body>
# <h1>Make a Reservation</h1>
# <form method="POST">
# Name: <input type="text" name="name"><br>
# Phone: <input type="text" name="phone"><br>
# Email: <input type="text" name="email"><br>
# Time: <input type="datetime-local" name="time" min="2025-01-01T12:00" max="2025-12-31T20:00" step="900"><br>
# <input type="submit" value="Reserve">
# </form>
# </body>
# </html>

# reservation.html, restaurant.html, reservation_archive.html will follow similar structure
