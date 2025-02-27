from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room
import sqlite3
import random
import time
import logging
from functools import wraps  # Added this import

app = Flask(__name__)
app.secret_key = "mindmeld_secret"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Logging setup for diagnostics
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("MindMeld")

# Database setup
def init_db():
    conn = sqlite3.connect('users.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password TEXT,
        unlocked_levels TEXT,
        total_score INTEGER DEFAULT 0
    )''')
    conn.commit()
    conn.close()

init_db()

# User and game state
clients = {}
game_rooms = {}

# Pre-initialize all rooms at startup
for level in range(1, 4):
    room_id = f"level_{level}"
    game_rooms[room_id] = {
        "level": level,
        "puzzle": None,
        "answer": None,
        "time_left": 60,
        "scores": {},
        "active": False,
        "players": set(),
        "timer_thread": None
    }

# Puzzle generators
def caesar_cipher():
    words = ["HELLO", "WORLD", "PYTHON", "CODE"]
    answer = random.choice(words)
    shift = random.randint(1, 5)
    puzzle = "".join(chr((ord(c) - 65 + shift) % 26 + 65) for c in answer)
    return f"Caesar Cipher (Shift 1-5): {puzzle}", answer

def morse_code():
    morse_dict = {"H": "....", "E": ".", "L": ".-..", "O": "---", "W": ".--", "R": ".-.", "D": "-.."}
    words = ["HELLO", "WORLD", "CODE"]
    answer = random.choice(words)
    puzzle = " ".join(morse_dict[c] for c in answer)
    return f"Morse Code: {puzzle}", answer

def logic_puzzle():
    puzzles = [
        ("CLOCK", "I tick but don’t tock, have hands but don’t knock. What am I?"),
        ("RIVER", "I flow but never walk, have banks but no money. What am I?")
    ]
    answer, puzzle = random.choice(puzzles)
    return f"Logic Puzzle: {puzzle}", answer

PUZZLES = {1: caesar_cipher, 2: morse_code, 3: logic_puzzle}

# Timer function
def timer(room_id):
    room = game_rooms[room_id]
    logger.debug(f"Timer started for {room_id}")
    while room["active"] and room["time_left"] > 0:
        room["time_left"] -= 1
        socketio.emit('timer_update', room["time_left"], room=room_id)
        time.sleep(1)
    if room["time_left"] <= 0:
        room["active"] = False
        socketio.emit('game_over', f"Time's up! Answer was {room['answer']}", room=room_id)
        socketio.sleep(0.5)
        start_game(room_id)

# Start game
def start_game(room_id):
    start_time = time.time()
    room = game_rooms[room_id]
    room["puzzle"], room["answer"] = PUZZLES[room["level"]]()
    room["time_left"] = 60
    room["active"] = True
    socketio.emit('new_game', {"puzzle": room["puzzle"], "time_left": room["time_left"]}, room=room_id)
    logger.debug(f"Game started for {room_id} in {time.time() - start_time:.3f}s")

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        action = request.form.get('action')
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        
        if action == "signup":
            c.execute("SELECT username FROM users WHERE username = ?", (username,))
            if c.fetchone():
                conn.close()
                return render_template('index.html', error="Username already exists!")
            c.execute("INSERT INTO users (username, password, unlocked_levels) VALUES (?, ?, ?)",
                     (username, password, "1"))
            conn.commit()
            session['username'] = username
            session['unlocked_levels'] = [1]
            conn.close()
            return render_template('index.html', logged_in=True, levels=session['unlocked_levels'], username=username)
        
        elif action == "login":
            c.execute("SELECT password, unlocked_levels, total_score FROM users WHERE username = ?", (username,))
            result = c.fetchone()
            conn.close()
            if result and result[0] == password:
                session['username'] = username
                session['unlocked_levels'] = [int(x) for x in result[1].split(',')] if result[1] else [1]
                session['total_score'] = result[2]
                return render_template('index.html', logged_in=True, levels=session['unlocked_levels'], username=username)
            return render_template('index.html', error="Invalid credentials!")
    
    if "username" in session:
        return render_template('index.html', logged_in=True, levels=session.get('unlocked_levels', [1]), username=session['username'])
    return render_template('index.html')

@app.route('/game/<int:level>')
@login_required
def game(level):
    if level not in session.get('unlocked_levels', []):
        return redirect(url_for('index'))
    return render_template('game.html', level=level)

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('unlocked_levels', None)
    return redirect(url_for('index'))

# Socket events
@socketio.on('join')
def handle_join(data):
    start_time = time.time()
    level = data['level']
    username = session['username']
    room_id = f"level_{level}"
    
    join_room(room_id)
    clients[request.sid] = {"username": username, "room": room_id}
    
    room = game_rooms[room_id]
    room["scores"][username] = room["scores"].get(username, 0)
    room["players"].add(username)
    
    emit('init', {
        "username": username,
        "puzzle": room["puzzle"] or "Starting soon...",
        "time_left": room["time_left"],
        "scores": room["scores"],
        "players": list(room["players"])
    })
    emit('message', f"{username} joined Level {level}!", room=room_id)
    
    if not room["active"] and len(room["players"]) >= 1:
        start_game(room_id)
        if not room["timer_thread"] or not room["timer_thread"].is_alive():
            import threading
            room["timer_thread"] = threading.Thread(target=timer, args=(room_id,), daemon=True)
            room["timer_thread"].start()
    
    logger.debug(f"Join completed for {room_id} in {time.time() - start_time:.3f}s")

@socketio.on('message')
def handle_message(data):
    room_id = clients[data['sid']]["room"]
    username = clients[data['sid']]["username"]
    msg = data['msg']
    room = game_rooms[room_id]
    if msg.startswith("solve "):
        guess = msg[6:].strip().upper()
        if guess == room["answer"] and room["active"]:
            room["scores"][username] += 10
            room["active"] = False
            emit('message', f"{username} solved it! Answer: {room['answer']}", room=room_id)
            emit('update_scores', room["scores"], room=room_id)
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute("UPDATE users SET total_score = total_score + 10 WHERE username = ?", (username,))
            current_level = room["level"]
            if current_level < 3:
                next_level = current_level + 1
                if next_level not in session['unlocked_levels']:
                    session['unlocked_levels'].append(next_level)
                    c.execute("UPDATE users SET unlocked_levels = ? WHERE username = ?",
                             (",".join(map(str, session['unlocked_levels'])), username))
            conn.commit()
            conn.close()
            socketio.sleep(0.5)
            start_game(room_id)
        else:
            emit('message', "Wrong guess!", to=data['sid'])
    else:
        emit('message', f"{username}: {msg}", room=room_id)

@socketio.on('disconnect')
def handle_disconnect():
    client = clients.pop(request.sid, None)
    if client:
        room_id = client["room"]
        username = client["username"]
        room = game_rooms[room_id]
        room["players"].discard(username)
        if username in room["scores"]:
            del room["scores"][username]
        emit('message', f"{username} left the game!", room=room_id)
        emit('update_scores', room["scores"], room=room_id)
        emit('update_players', list(room["players"]), room=room_id)

if __name__ == "__main__":
    logger.info("Server starting...")
    socketio.run(app, host='0.0.0.0', port=5000)

    