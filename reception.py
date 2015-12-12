# -*- coding: utf-8 -*-

#
import SimpleHTTPServer
import SocketServer

PORT = 8000

Handler = SimpleHTTPServer.SimpleHTTPRequestHandler

httpd = SocketServer.TCPServer(("", PORT), Handler)

print "serving at port", PORT
httpd.serve_forever()
#

from flask import Flask
from flask import request
from flask import jsonify
from flask import render_template
import sqlite3
from flask import g
from flask import abort
from flask import send_file
import uuid
import time
import os
import mimetypes
import StringIO
from smtplib import SMTP_SSL
from email.Header import Header
from email.MIMEText import MIMEText
from email.MIMEMultipart import MIMEMultipart
from email.mime.application import MIMEApplication
import qrcode

IMAGE_EXTENSIONS = set(['.png', '.jpg', '.jpeg', '.gif'])
UPLOAD_FOLDER = './images'

app = Flask(__name__)
app.config['DEBUG'] = True
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

app.config['SMTP_HOST'] = 'smtp.gmail.com'
app.config['SMTP_PORT'] = 465
app.config['SMTP_USERNAME'] = ''
app.config['SMTP_PASSWORD'] = ''
app.config['EMAIL_DEFAULT_ENCODING'] = 'iso-2022-jp'
app.config['EMAIL_FROM'] = app.config['SMTP_USERNAME']

@app.route("/api/<appointment>/checkin")
def checkin(appointment):
    conn = get_db()
    c = conn.execute("select starttime,endtime,guestname,ownername,ownermail,greeting,visit " +
                     "from appointment where id=?;", (appointment,))
    data = c.fetchone()
    if data is None:
        return jsonify(id=appointment, status='Error', error='Not found')
    (starttime, endtime, guestname, ownername, ownermail, greeting, visit) = data
    print("CheckIn: %s - %s-%s - %s - %s"
          % (appointment, starttime, endtime, guestname, ownername))

    visit += 1
    conn.execute("update appointment set visit=? where id=?;",
                 (visit, appointment))

    curtime = time.strftime("%Y/%m/%d %H:%M:%S")
    conn.execute("insert into history(appointment, time)" +
                 " values(?, ?);", (appointment, curtime))
    conn.commit()
    
    send_mail(ownermail, u'訪問通知',
              u'%s さん\n\n%s 様が受付されました。\n' % (ownername, guestname))
    
    c = conn.execute("select imagepath,speech from greeting where id=?;", (greeting,))
    (imagepath, speech) = c.fetchone()
    greeting = {'speech': speech, 'image': '/greeting/image/' + greeting}

    solitaries = []
    c = conn.execute("select greeting.id, greeting.name, greeting.speech, solitary.enabled from greeting left outer join solitary on greeting.id = solitary.greeting;")
    for (rowid, name, speech, enabled) in c:
        enabled = enabled if enabled is not None else 0
        if enabled != 0:
            solitaries.append({'speech': speech, 'image': '/greeting/image/' + rowid})
    
    return jsonify(id=appointment, status='Success', visit=visit, greeting=greeting, solitaries=solitaries)


@app.route("/appointment/detail/<appointment>")
def detail(appointment):
    c = get_db().execute("select * from appointment where id=?;",
                         (appointment,))
    (rowid, starttime, endtime, guestcompany, guestname, guestmail, room, ownername, ownermail, greeting, visit) = c.fetchone()
    return render_template("appointment-detail.html", id=rowid, starttime=starttime,
                           endtime=endtime, guestcompany=guestcompany,
                           guestname=guestname, guestmail=guestmail,
                           room=room, ownername=ownername,
                           ownermail=ownermail, greeting=greeting,
                           visit=visit)


@app.route("/")
def index():
    return render_template('index.html')


@app.route("/appointment/add-form")
def add_form():
    greetings = []
    c = get_db().execute("select id, name from greeting;")
    for (rowid, name) in c:
        greetings.append({"id": rowid, "name": name})
    return render_template('appointment-add-form.html', greetings=greetings)


@app.route("/appointment/add", methods=['POST'])
def add():
    newid = uuid.uuid1()
    names = ['starttime', 'endtime', 'guestcompany', 'guestname', 'guestmail',
             'room', 'ownername', 'ownermail', 'greeting']
    values = [request.form[name] for name in names]
    conn = get_db()
    conn.execute("insert into appointment values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0);",
                 tuple([str(newid)] + values))
    conn.commit()
    
    params = dict(zip(names, values))
    
    qrimgdata = StringIO.StringIO()
    qrimg = qrcode.make(str(newid))
    qrimg.save(qrimgdata, 'PNG')
    send_mail(params['guestmail'], u'アポイントメント情報',
              u'%s 様\n\n開始予定時刻: %s\n終了予定時刻: %s\n' % (params['guestname'], params['starttime'], params['endtime']),
              [("qrcode.png", qrimgdata.getvalue())])
    return render_template("appointment-add.html", id=newid, **params)


@app.route("/appointment/list")
def list():
    appointments = []
    c = get_db().execute("select id, starttime, guestname, ownername, visit from appointment order by starttime desc;")
    for (rowid, starttime, guestname, ownername, visit) in c:
        appointments.append({"id": rowid, "starttime": starttime,
                             "guestname": guestname, "ownername": ownername,
                             "visit": visit})
    return render_template('appointment-list.html', appointments=appointments)


@app.route("/history/<appointment>")
def history(appointment):
    history = []
    if appointment == 'all':
        c = get_db().execute("select * from history order by time desc;")
    else:
        c = get_db().execute("select * from history where appointment=? " +
                             "order by time desc;", (appointment, ))
    for (rowid, appointment, time) in c:
        history.append({"id": rowid, "time": time, "appointment": appointment})
    return render_template('history.html', history=history)


@app.route("/greeting/add-form")
def greeting_add_form():
    return render_template('greeting-add-form.html')


@app.route("/greeting/add", methods=['POST'])
def greeting_add():
    newid = uuid.uuid1()
    image = request.files['image']
    image_ext = os.path.splitext(image.filename)[1]
    if image_ext not in IMAGE_EXTENSIONS:
        abort(500)
    imagepath = str(newid) + image_ext
    image.save(os.path.join(app.config['UPLOAD_FOLDER'], imagepath))
    names = ['name', 'speech']
    values = [request.form[name] for name in names]
    solitary = 0
    if "solitary" in request.form and request.form["solitary"] == "enabled":
        solitary = 1
    conn = get_db()
    conn.execute("insert into greeting values(?, ?, ?, ?);",
                 tuple([str(newid)] + [imagepath] + values))
    conn.execute("insert into solitary(greeting, enabled) values(?, ?);",
                 (str(newid), solitary))
    conn.commit()
    params = dict(zip(names, values))
    return render_template("greeting-add.html", id=newid, imagepath=imagepath,
                           **params)


@app.route("/greeting/list")
def greeting_list():
    greetings = []
    c = get_db().execute("select greeting.id, greeting.name, greeting.imagepath, greeting.speech, solitary.enabled from greeting left outer join solitary on greeting.id = solitary.greeting;")
    for (rowid, name, imagepath, speech, enabled) in c:
        enabled = enabled if enabled is not None else 0
        greetings.append({"id": rowid, "imagepath": imagepath,
                          "name": name, "speech": speech, "enabled": enabled})
    return render_template('greeting-list.html', greetings=greetings)


@app.route("/greeting/detail/<greeting>")
def greeting_detail(greeting):
    c = get_db().execute("select * from greeting where id=?;",
                         (greeting,))
    (rowid, imagepath, name, speech) = c.fetchone()
    return render_template("greeting-detail.html", id=rowid, name=name,
                           imagepath=imagepath, speech=speech)


@app.route("/greeting/image/<greeting>")
def greeting_image(greeting):
    c = get_db().execute("select imagepath from greeting where id=?;",
                         (greeting,))
    (imagepath, ) = c.fetchone()
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], imagepath),
                     mimetypes.types_map[os.path.splitext(imagepath)[1]])


@app.route("/greeting/solitary-edit-form")
def greeting_solitary_edit_form():
    greetings = []
    c = get_db().execute("select greeting.id, greeting.name, greeting.imagepath, greeting.speech, solitary.enabled from greeting left outer join solitary on greeting.id = solitary.greeting;")
    for (rowid, name, imagepath, speech, enabled) in c:
        enabled = enabled if enabled is not None else 0
        greetings.append({"id": rowid, "imagepath": imagepath,
                          "name": name, "speech": speech, "enabled": enabled})
    return render_template('solitary-edit-form.html', greetings=greetings)


@app.route("/greeting/solitary-edit", methods=['POST'])
def greeting_solitary_edit():
    conn = get_db()
    c = conn.execute("select greeting.id, solitary.enabled from greeting left outer join solitary on greeting.id = solitary.greeting;")
    for (rowid, enabled) in c:
        if rowid not in request.form:
            value = None
        else:
            value = request.form[rowid]
        if value:
            if enabled is None:
                conn.execute("insert into solitary(greeting, enabled) values(?, ?);",
                             (rowid, 1))
            elif enabled == 0:
                conn.execute("update solitary set enabled=? where greeting=?",
                             (1, rowid))
        else:
            if enabled == 1:
                conn.execute("update solitary set enabled=? where greeting=?",
                             (0, rowid))
    conn.commit()
    greetings = []
    c = get_db().execute("select greeting.id, greeting.name, greeting.imagepath, greeting.speech, solitary.enabled from greeting left outer join solitary on greeting.id = solitary.greeting;")
    for (rowid, name, imagepath, speech, enabled) in c:
        enabled = enabled if enabled is not None else 0
        greetings.append({"id": rowid, "imagepath": imagepath,
                          "name": name, "speech": speech, "enabled": enabled})
    return render_template('greeting-list.html', greetings=greetings)


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = connect_db()
    return db


def connect_db():
    conn = sqlite3.connect('reception.db')
    with app.open_resource('schema.sql') as f:
        conn.executescript(f.read())
    return conn


@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()
        
def send_mail(to, subject, message, files=None):
    conn = SMTP_SSL(app.config['SMTP_HOST'], app.config['SMTP_PORT'])
    conn.login(app.config['SMTP_USERNAME'], app.config['SMTP_PASSWORD'])
    charset = app.config['EMAIL_DEFAULT_ENCODING']
    msg = MIMEMultipart()
    msg['Subject'] = Header(subject, charset)
    msg['From'] = app.config['EMAIL_FROM']
    msg['To'] = to

    msg.attach(MIMEText(message, 'plain', charset))
    if files is not None:
        for (filename, data) in files:
            part = MIMEApplication(data)
            part.add_header('Content-Disposition', 'attachment', filename=filename)
            msg.attach(part)
    conn.sendmail(app.config['EMAIL_FROM'], [to], msg.as_string()) 
    conn.close()
    

if __name__ == "__main__":
    if not os.path.exists("images"):
        os.mkdir("images")
    app.run(host='0.0.0.0')
