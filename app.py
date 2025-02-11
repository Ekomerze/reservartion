from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta, time


# Ielādē .env failu
load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///reservations.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key'

# Konfigurē e-pasta sūtīšanu
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

mail = Mail(app)
db = SQLAlchemy(app)

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    time = db.Column(db.DateTime, nullable=False)
    guests = db.Column(db.Integer, nullable=False)
    table_number = db.Column(db.Integer, nullable=True)

class Archive(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    time = db.Column(db.DateTime, nullable=False)
    guests = db.Column(db.Integer, nullable=False)
    table_number = db.Column(db.Integer, nullable=True)

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    total_tables = db.Column(db.Integer, nullable=False, default=10)
    seats_per_table = db.Column(db.Integer, nullable=False, default=4)
    opening_time = db.Column(db.Time, nullable=False, default=time(12, 0))  # 12:00
    closing_time = db.Column(db.Time, nullable=False, default=time(20, 0))  # 20:00

class TableSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    table_number = db.Column(db.Integer, unique=True, nullable=False)
    seats = db.Column(db.Integer, nullable=False, default=4)

class Table(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    table_number = db.Column(db.Integer, unique=True, nullable=False)
    seats = db.Column(db.Integer, nullable=False, default=4)

class DailyTableSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)  # Saglabājam konkrēto dienu
    table_number = db.Column(db.Integer, nullable=False)
    seats = db.Column(db.Integer, nullable=False, default=4)

    __table_args__ = (db.UniqueConstraint('date', 'table_number', name='unique_table_per_day'),)


@app.route('/', methods=['GET', 'POST'])
def index():
    now = datetime.now()
    selected_date = request.args.get('date', now.strftime('%Y-%m-%d'))  # Noklusējuma datums - šodiena
    selected_time = request.args.get('time', now.strftime('%H:%M'))  # Noklusējuma laiks - pašreizējais laiks
    selected_datetime = datetime.strptime(f"{selected_date} {selected_time}", "%Y-%m-%d %H:%M")

    # Atrodam visus galdiņus
    total_tables = Table.query.count()

    # Atrod aizņemtos galdiņus konkrētajā datumā un laikā
    booked_tables = {r.table_number for r in Reservation.query.filter(Reservation.time == selected_datetime).all()}
    
    # Aprēķina brīvos galdiņus
    free_tables = [t.table_number for t in Table.query.all() if t.table_number not in booked_tables]

    available_tables = len(free_tables)  # Pieejamo galdiņu skaits

    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        email = request.form['email']
        time = datetime.strptime(request.form['time'], "%Y-%m-%dT%H:%M")
        guests = int(request.form.get('guests', 1))
        table_number = request.form.get('table_number')

        if not table_number:
            assigned_table = next(
                (t for t in free_tables), None
            )
            table_number = assigned_table if assigned_table else None
        else:
            table_number = int(table_number)

        if table_number is None:
            flash('Nav pieejamu galdiņu šajā laikā.', 'danger')
            return redirect(url_for('index'))

        new_reservation = Reservation(
            name=name, phone=phone, email=email, time=time, guests=guests, table_number=table_number
        )
        db.session.add(new_reservation)
        db.session.commit()
        send_confirmation_email(email, time, guests, table_number)
        flash('Rezervācija veiksmīga!', 'success')
        return redirect(url_for('index'))

    return render_template(
        'index.html',
        available_tables=available_tables,
        selected_date=selected_date,
        selected_time=selected_time,
        free_tables=free_tables
    )

@app.route('/client', methods=['GET', 'POST'])
def client():
    settings = Settings.query.first()

    # 📅 **Iegūstam datumu no URL parametriem (noklusējuma - šodiena)**
    selected_date = request.args.get('date', datetime.today().strftime('%Y-%m-%d'))
    selected_date_obj = datetime.strptime(selected_date, '%Y-%m-%d').date()

    # ⏰ **Iegūstam restorāna darba laiku**
    opening_time = settings.opening_time if settings else time(12, 0)
    closing_time = settings.closing_time if settings else time(20, 0)

    opening_time = datetime.combine(selected_date_obj, opening_time)
    closing_time = datetime.combine(selected_date_obj, closing_time)

    # 🔍 **Atrodam kopējo galdiņu skaitu konkrētajā datumā**
    total_tables = DailyTableSettings.query.filter_by(date=selected_date_obj).count()
    if total_tables == 0:
        total_tables = 10  # Ja nav iestatīti galdiņi, pieņemam 10 kā noklusējumu

    # 🕒 **Ģenerējam pieejamos laikus (ik pa 15 min)**
    available_times = {}
    current_time = opening_time
    while current_time < closing_time:
        # 🔍 **Pārbaudām rezervācijas konkrētajā datumā un divu stundu periodā**
        overlapping_reservations = Reservation.query.filter(
            db.func.date(Reservation.time) == selected_date_obj,  # 💡 **Pārliecināmies, ka filtrējam pēc datuma!**
            Reservation.time >= current_time,
            Reservation.time < current_time + timedelta(hours=2)
        ).count()

        # ✅ **Laiks ir pieejams tikai, ja vēl ir brīvi galdiņi tajā datumā un laikā**
        available_times[current_time.strftime("%Y-%m-%dT%H:%M")] = overlapping_reservations < total_tables
        current_time += timedelta(minutes=15)

    # 📝 **Rezervācijas veikšana**
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        guests = int(request.form.get('guests', 1))
        time_str = request.form.get('time')

        if not all([name, phone, email, time_str]):  # 🔍 **Pārbaudām, vai visi lauki aizpildīti**
            flash('Lūdzu aizpildiet visus laukus un izvēlieties laiku.', 'danger')
            return redirect(url_for('client', date=selected_date))

        try:
            time = datetime.strptime(time_str, "%Y-%m-%dT%H:%M")
        except ValueError:
            flash('Nepareizs laika formāts. Lūdzu, mēģiniet vēlreiz.', 'danger')
            return redirect(url_for('client', date=selected_date))

        # 🔍 **Pārbaudām, vai vēl ir brīvi galdiņi izvēlētajā datumā un divu stundu periodā**
        reservations_count = Reservation.query.filter(
            db.func.date(Reservation.time) == selected_date_obj,
            Reservation.time >= time,
            Reservation.time < time + timedelta(hours=2)
        ).count()

        if reservations_count >= total_tables:
            flash('Diemžēl šajā laikā nav pieejamu galdiņu.', 'danger')
            return redirect(url_for('client', date=selected_date))

        # 📌 **Meklējam pirmo brīvo galdiņu izvēlētajā datumā**
        assigned_table = next(
            (i for i in range(1, total_tables + 1)
             if not Reservation.query.filter(
                 db.func.date(Reservation.time) == selected_date_obj,
                 Reservation.time >= time,
                 Reservation.time < time + timedelta(hours=2),
                 Reservation.table_number == i
             ).first()),
            None
        )

        if assigned_table is None:
            flash('Nav pieejamu galdiņu šajā laikā.', 'danger')
            return redirect(url_for('client', date=selected_date))

        # ✅ **Saglabājam rezervāciju**
        new_reservation = Reservation(name=name, phone=phone, email=email, time=time, guests=guests, table_number=assigned_table)
        db.session.add(new_reservation)
        db.session.commit()

        send_confirmation_email(email, time, guests, assigned_table)
        flash(f'Rezervācija veiksmīga! Galdiņš {assigned_table}, laiks: {time.strftime("%H:%M")}', 'success')
        return redirect(url_for('client', date=selected_date))

    reservations = Reservation.query.filter(db.func.date(Reservation.time) == selected_date_obj).all()
    return render_template('client.html', reservations=reservations, available_times=available_times, selected_date=selected_date)

@app.route('/staff', methods=['GET', 'POST'])
def staff():
    settings = Settings.query.first()

    # Noklusējuma datums = šodiena
    selected_date = request.args.get('date', datetime.today().date().strftime('%Y-%m-%d'))
    selected_date_obj = datetime.strptime(selected_date, '%Y-%m-%d').date()

    # Iegūstam galdiņu iestatījumus konkrētajai dienai
    tables = DailyTableSettings.query.filter_by(date=selected_date_obj).order_by(DailyTableSettings.table_number).all()

    # Ja tabula ir tukša, ģenerējam noklusējuma galdiņus
    if not tables:
        print(f"[DEBUG] Nav tabulu {selected_date_obj}, izveidoju noklusējuma galdiņus.")
        for i in range(1, 11):  # 10 galdiņi ar 4 vietām katrs
            db.session.add(DailyTableSettings(date=selected_date_obj, table_number=i, seats=4))
        db.session.commit()
        tables = DailyTableSettings.query.filter_by(date=selected_date_obj).order_by(DailyTableSettings.table_number).all()

    if request.method == 'POST':
        try:
            opening_time_str = request.form.get('opening_time')
            closing_time_str = request.form.get('closing_time')

            if opening_time_str:
                opening_time_clean = opening_time_str[:5]  # Noņem sekundes ":SS"
                settings.opening_time = datetime.strptime(opening_time_clean, "%H:%M").time()

            if closing_time_str:
                closing_time_clean = closing_time_str[:5]  # Noņem sekundes ":SS"
                settings.closing_time = datetime.strptime(closing_time_clean, "%H:%M").time()

            db.session.commit()  # Saglabājam darba laika izmaiņas

            # Debugging - izvadām POST pieprasījuma datus
            print(f"[DEBUG] Saņemts POST pieprasījums: {request.form}")

            # Atjauninām vietu skaitu katram galdiņam konkrētajā dienā
            changes_made = False
            for table in tables:
                seats_key = f"seats_{table.table_number}"
                if seats_key in request.form:
                    new_seat_count = int(request.form[seats_key])
                    if new_seat_count != table.seats:  # Tikai ja ir izmaiņas
                        print(f"[DEBUG] Galdiņš {table.table_number}: {table.seats} -> {new_seat_count}")
                        table.seats = new_seat_count
                        changes_made = True
                        print(f"[DEBUG] Pēc: Galdiņš {table.table_number}: {table.seats}")

            if changes_made:
                print(f"[DEBUG] Saglabāju izmaiņas datubāzē...")
                db.session.commit()  # Saglabā visas izmaiņas
                print(f"[DEBUG] Izmaiņas saglabātas datubāzē.")
                flash(f'Iestatījumi saglabāti {selected_date}!', 'success')
            else:
                print("[DEBUG] Nekas netika mainīts, commit netika veikts.")
                flash(f'Nav izmaiņu, ko saglabāt {selected_date}.', 'info')

            return redirect(url_for('staff', date=selected_date))

        except ValueError as e:
            print(f"[DEBUG] Kļūda: {e}")
            flash(f'Kļūda datu ievadē: {str(e)}', 'danger')

    return render_template('staff.html', settings=settings, tables=tables, selected_date=selected_date)

@app.route('/staff/add_table', methods=['POST'])
def add_table():
    table_number = request.form.get('table_number')

    # Ja lietotājs nav norādījis galda numuru, tiek piešķirts nākamais pieejamais numurs
    if not table_number:
        existing_tables = TableSettings.query.count()
        table_number = existing_tables + 1  # Noklusējuma numerācija

    else:
        table_number = int(table_number)  # Pārvēršam lietotāja ievadīto numuru par int

    # Pārbaudām, vai šāds galdiņa numurs jau eksistē
    existing_table = TableSettings.query.filter_by(table_number=table_number).first()
    if existing_table:
        flash('Galdiņa numurs jau eksistē!', 'danger')
        return redirect(url_for('staff'))

    new_table = TableSettings(table_number=table_number, seats=4)  # Noklusējums - 4 vietas
    db.session.add(new_table)
    db.session.commit()
    
    flash('Jauns galdiņš pievienots!', 'success')
    return redirect(url_for('staff'))


from flask import request, redirect, url_for, flash
from datetime import datetime
from models import db, DailyTableSettings, Reservation

@app.route('/staff/remove_table', methods=['POST'])
def remove_table():
    selected_date = request.form.get('selected_date')
    table_number = request.form.get('table_number')  # Iespēja norādīt konkrētu galdu

    if not selected_date:
        flash('Nav izvēlēts datums!', 'danger')
        return redirect(url_for('staff'))

    selected_date_obj = datetime.strptime(selected_date, '%Y-%m-%d').date()

    if table_number:
        # Dzēšam konkrēto galdiņu, ja tas norādīts
        table = DailyTableSettings.query.filter_by(date=selected_date_obj, table_number=int(table_number)).first()
    else:
        # Dzēšam pēdējo pievienoto galdiņu, ja nav norādīts numurs
        table = DailyTableSettings.query.filter_by(date=selected_date_obj).order_by(DailyTableSettings.table_number.desc()).first()

    if not table:
        flash('Nav galdiņu, ko noņemt!', 'danger')
    else:
        # Pārbaudām, vai galdiņš ir rezervēts
        existing_reservation = Reservation.query.filter_by(time=selected_date_obj, table_number=table.table_number).first()

        if existing_reservation:
            flash(f'Galdiņu {table.table_number} nevar izdzēst, jo tam ir rezervācija!', 'danger')
        else:
            db.session.delete(table)
            db.session.commit()
            flash(f'Galdiņš {table.table_number} veiksmīgi noņemts!', 'success')

    return redirect(url_for('staff', date=selected_date))


@app.route('/reservation', methods=['GET', 'POST'])
def reservation():
    query = Reservation.query

    # 🔍 Meklēšana pēc vārda, telefona, datuma
    name_search = request.args.get('name', '').strip()
    phone_search = request.args.get('phone', '').strip()
    date_search = request.args.get('date', '').strip()

    if name_search:
        query = query.filter(Reservation.name.ilike(f"%{name_search}%"))
    if phone_search:
        query = query.filter(Reservation.phone.ilike(f"%{phone_search}%"))
    if date_search:
        try:
            date_obj = datetime.strptime(date_search, "%Y-%m-%d").date()
            query = query.filter(db.func.date(Reservation.time) == date_obj)
        except ValueError:
            flash("Nepareizs datuma formāts. Izmantojiet YYYY-MM-DD.", "danger")

    # 📌 **Tagad kārtojam pēc rezervācijas laika!**
    reservations = query.order_by(Reservation.time).all()

    return render_template('reservation.html', reservations=reservations, name_search=name_search, phone_search=phone_search, date_search=date_search)

@app.route('/reservation/edit/<int:id>', methods=['GET', 'POST'])
def edit_reservation(id):
    reservation = Reservation.query.get_or_404(id)
    if request.method == 'POST':
        reservation.name = request.form['name']
        reservation.phone = request.form['phone']
        reservation.email = request.form['email']
        reservation.time = datetime.strptime(request.form['time'], "%Y-%m-%dT%H:%M")
        reservation.guests = int(request.form.get('guests', 1))
        reservation.table_number = int(request.form.get('table_number', reservation.table_number))

        db.session.commit()
        flash('Rezervācija veiksmīgi atjaunināta!', 'success')
        return redirect(url_for('reservation'))

    return render_template('edit_reservation.html', reservation=reservation)

@app.route('/reservation/delete/<int:id>')
def delete_reservation(id):
    res = Reservation.query.get(id)
    if res:
        # Pārvietojam rezervāciju uz arhīvu
        archived_reservation = Archive(
            name=res.name,
            phone=res.phone,
            email=res.email,
            time=res.time,
            guests=res.guests,
            table_number=res.table_number
        )
        db.session.add(archived_reservation)
        db.session.delete(res)  # Tagad droši dzēšam oriģinālo rezervāciju
        db.session.commit()
        flash('Rezervācija pārvietota uz arhīvu!', 'success')
    else:
        flash('Rezervācija nav atrasta.', 'danger')

    return redirect(url_for('reservation'))

@app.route('/reservation_archive')
def reservation_archive():
    archives = Archive.query.order_by(Archive.time.desc()).all()
    return render_template('reservation_archive.html', archives=archives)

@app.route('/restaurant')
def restaurant():
    return render_template('restaurant.html')

def send_confirmation_email(email, time, guests, table_number):
    with app.app_context():
        msg = Message("Rezervācijas apstiprinājums", recipients=[email])
        msg.body = f"Labdien! Jūsu rezervācija ir apstiprināta.\n\nLaiks: {time.strftime('%Y-%m-%d %H:%M')}\nViesu skaits: {guests}\nGalda numurs: {table_number}\n\nPaldies, ka izvēlējāties mūsu restorānu!"
        try:
            mail.send(msg)
            print(f"✅ E-pasts veiksmīgi nosūtīts uz {email}")
        except Exception as e:
            print(f"❌ Kļūda e-pasta sūtīšanā: {e}")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not Settings.query.first():
            db.session.add(Settings())
        if TableSettings.query.count() == 0:
            for i in range(1, 11):  # 10 galdiņi ar 4 vietām
                db.session.add(TableSettings(table_number=i, seats=4))
        db.session.commit()
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
