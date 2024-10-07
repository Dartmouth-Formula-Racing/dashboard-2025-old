import config
from flask import Flask, jsonify, render_template
from flask_socketio import SocketIO
import logging

UPDATE_INTERVAL = 1/config.DASH_UPDATE_FREQUENCY

app = Flask(__name__)
socketio = SocketIO(app)
state = None
thread = None
log = logging.getLogger('werkzeug')

def run(state_):
    global state
    state = state_
    socketio.run(app, host='0.0.0.0', port=5000, use_reloader=False, debug=config.DEBUG, allow_unsafe_werkzeug=True)

def background_thread():
    global state
    while True:
        socketio.sleep(UPDATE_INTERVAL)
        socketio.emit('data', state._getvalue())

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/data')
def data():
    global state
    return jsonify(state._getvalue())

@socketio.on('connect')
def connect():
    global thread
    if thread is None:
        thread = socketio.start_background_task(target=background_thread)