from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room
import sqlite3
import random
import time
import logging
from functools import wraps

app = Flask(__name__)
app.secret_key = "mindmeld_secret"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Logging setup
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("MindMeld")

# Database setup with migration
def init_db():
    conn = sqlite3.connect('users.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password TEXT,
        unlocked_levels TEXT,
        total_score INTEGER DEFAULT 0
    )''')
    c.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in c.fetchall()]
    if "learned_levels" not in columns:
        logger.info("Adding learned_levels column to users table")
        c.execute("ALTER TABLE users ADD COLUMN learned_levels TEXT DEFAULT ''")
    conn.commit()
    conn.close()

init_db()

# User and game state
clients = {}
game_rooms = {}

# Pre-initialize all rooms (6 levels)
for level in range(1, 7):
    room_id = f"level_{level}"
    game_rooms[room_id] = {
        "level": level,
        "puzzle": None,
        "answer": None,
        "time_left": 60,
        "scores": {},
        "active": False,
        "players": set(),
        "timer_thread": None,
        "questions_asked": [],
        "correct_count": 0
    }

# Puzzle generators for Play (3 unique questions)
def animal_code_play():
    puzzles = [
        ("CAT", "I purr and chase mice! Shift my name by 1-5 letters."),
        ("DOG", "I bark and wag my tail! Shift my name by 1-5 letters."),
        ("FOX", "I’m sly and live in the woods! Shift my name by 1-5 letters.")
    ]
    return puzzles

def space_signals_play():
    morse_dict = {"M": "--", "O": "---", "N": "-.", "S": "...", "T": "-", "A": ".-", "R": ".-."}
    puzzles = [
        ("MOON", "Beep boop! I glow at night: -- --- --- -."),
        ("STAR", "Beep boop! I twinkle in the sky: ... - .- .-."),
        ("MARS", "Beep boop! I’m a red planet: -- .- .-. ...")
    ]
    return puzzles

def superhero_riddles_play():
    puzzles = [
        ("CAPE", "I flap when a hero flies! What am I?"),
        ("MASK", "I hide a hero’s face! What am I?"),
        ("BOOM", "I’m the sound of a hero’s punch! What am I?")
    ]
    return puzzles

def robot_words_play():
    binary_dict = {"B": "01000010", "E": "01000101", "P": "01010000", "O": "01001111", 
                   "Z": "01011010", "A": "01000001"}
    puzzles = [
        ("BEEP", "Robot says: 01000010 01000101 01000101 01010000"),
        ("BOOP", "Robot says: 01000010 01001111 01001111 01010000"),
        ("ZAP", "Robot says: 01011010 01000001 01010000")
    ]
    return puzzles

def magic_letters_play():
    puzzles = [
        ("WAND", "A wizard waves me! Shift this spell by 1-5 letters."),
        ("POOF", "I make things vanish! Shift this spell by 1-5 letters."),
        ("SPARK", "I light up magic! Shift this spell by 1-5 letters.")
    ]
    return puzzles

def number_adventures_play():
    puzzles = [
        ("10", "How many fingers do you have?"),
        ("4", "How many legs does a dog have?"),
        ("6", "How many legs does a bug have?")
    ]
    return puzzles

PUZZLES = {
    1: animal_code_play,
    2: space_signals_play,
    3: superhero_riddles_play,
    4: robot_words_play,
    5: magic_letters_play,
    6: number_adventures_play
}

# Learn examples (1 unique question per level, different from Play)
LEARN_PUZZLES = {
    1: ("PIG", "Shift it: QJH (by 2) → What’s the animal? Answer: PIG 🐷"),
    2: ("SUN", "Decode: ... ..- -. → What’s this bright thing? Answer: SUN ☀️", {"S": "...", "U": "..-", "N": "-."}),
    3: ("BAM", "I’m a hero’s kick sound! What am I? Answer: BAM 💥"),
    4: ("ZIP", "Robot says: 01011010 01001001 01010000 → What’s this? Answer: ZIP ⚡", {"Z": "01011010", "I": "01001001", "P": "01010000"}),
    5: ("ZAP", "Shift it: ABQ (by 1) → What’s the spell? Answer: ZAP ⚡"),
    6: ("8", "How many legs does a spider have? Answer: 8 🕷️")
}

# Generate puzzle based on level (for Play)
def generate_puzzle(room):
    level = room["level"]
    puzzles = PUZZLES[level]()
    available = [(a, q) for a, q in puzzles if a not in room["questions_asked"]]
    if not available:
        return None, None
    answer, puzzle = random.choice(available)
    if level == 1 or level == 5:  # Caesar/Substitution Cipher
        shift = random.randint(1, 5)
        shifted = "".join(chr((ord(c) - 65 + shift) % 26 + 65) for c in answer)
        puzzle = f"{puzzle.split('!')[0]}! Here's the code: {shifted}"
    logger.debug(f"Level {level} Puzzle: {puzzle}, Answer: {answer}")
    return puzzle, answer

# Timer function
def timer(room_id):
    room = game_rooms[room_id]
    logger.debug(f"Timer started for {room_id}")
    while room["active"] and room["time_left"] > 0 and room["correct_count"] < 3:
        room["time_left"] -= 1
        socketio.emit('timer_update', room["time_left"], room=room_id)
        time.sleep(1)
    if room["time_left"] <= 0 and room["correct_count"] < 3:
        room["active"] = False
        socketio.emit('game_over', f"Time's up! Answer was {room['answer']}", room=room_id)
        socketio.sleep(0.5)
        start_game(room_id)

# Start game
def start_game(room_id):
    start_time = time.time()
    room = game_rooms[room_id]
    if room["correct_count"] >= 3:
        room["active"] = False
        socketio.emit('level_complete', "Level Complete! Return to the hub.", room=room_id)
        logger.debug(f"Level {room['level']} completed in {room_id}")
        return
    room["puzzle"], room["answer"] = generate_puzzle(room)
    if room["puzzle"] is None:
        room["active"] = False
        socketio.emit('level_complete', "Level Complete! Return to the hub.", room=room_id)
        logger.debug(f"Level {room['level']} completed in {room_id} - all questions asked")
        return
    room["questions_asked"].append(room["answer"])
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
            c.execute("INSERT INTO users (username, password, unlocked_levels, learned_levels) VALUES (?, ?, ?, ?)",
                     (username, password, "1", ""))
            conn.commit()
            session['username'] = username
            session['unlocked_levels'] = [1]
            session['learned_levels'] = []
            conn.close()
            return render_template('index.html', logged_in=True, levels=session['unlocked_levels'], 
                                 learned=session['learned_levels'], username=username)
        
        elif action == "login":
            try:
                c.execute("SELECT password, unlocked_levels, total_score, learned_levels FROM users WHERE username = ?", (username,))
                result = c.fetchone()
            except sqlite3.OperationalError as e:
                logger.error(f"Database error during login: {e}")
                conn.close()
                return render_template('index.html', error="Server error, please try again later.")
            conn.close()
            if result and result[0] == password:
                session['username'] = username
                session['unlocked_levels'] = [int(x) for x in result[1].split(',')] if result[1] else [1]
                session['learned_levels'] = [int(x) for x in result[3].split(',')] if result[3] else []
                session['total_score'] = result[2]
                return render_template('index.html', logged_in=True, levels=session['unlocked_levels'], 
                                     learned=session['learned_levels'], username=username)
            return render_template('index.html', error="Invalid credentials!")
    
    if "username" in session:
        return render_template('index.html', logged_in=True, levels=session.get('unlocked_levels', [1]), 
                             learned=session.get('learned_levels', []), username=session['username'])
    return render_template('index.html')

@app.route('/learn/<int:level>')
@login_required
def learn(level):
    if level not in session.get('unlocked_levels', []):
        return redirect(url_for('index'))
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    if level not in session.get('learned_levels', []):
        session['learned_levels'].append(level)
        c.execute("UPDATE users SET learned_levels = ? WHERE username = ?",
                 (",".join(map(str, session['learned_levels'])), session['username']))
        conn.commit()
    conn.close()
    return render_template('learn.html', level=level, learn_puzzle=LEARN_PUZZLES[level])

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
    session.pop('learned_levels', None)
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
    
    if not room["active"]:
        room["questions_asked"] = []
        room["correct_count"] = 0
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
            room["correct_count"] += 1
            emit('message', f"{username} solved it! Answer: {room['answer']} ({room['correct_count']}/3)", room=room_id)
            emit('update_scores', room["scores"], room=room_id)
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute("UPDATE users SET total_score = total_score + 10 WHERE username = ?", (username,))
            current_level = room["level"]
            if current_level < 6 and room["correct_count"] == 3:
                next_level = current_level + 1
                if next_level not in session['unlocked_levels']:
                    session['unlocked_levels'].append(next_level)
                    c.execute("UPDATE users SET unlocked_levels = ? WHERE username = ?",
                             (",".join(map(str, session['unlocked_levels'])), username))
                    emit('message', f"Level {next_level} unlocked!", room=room_id)
                    emit('update_levels', session['unlocked_levels'], to=data['sid'])
                    logger.debug(f"Unlocked Level {next_level} for {username}")
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