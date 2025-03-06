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

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("MindMeld")

clients = {}
game_rooms = {}

def init_db():
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                          (username TEXT PRIMARY KEY, password TEXT, score INTEGER DEFAULT 0, 
                           badges TEXT DEFAULT '', unlocked_levels TEXT DEFAULT '1')''')
        conn.commit()

init_db()

def timer(room_id):
    room = game_rooms.get(room_id)
    if not room:
        return
    while room["active"] and room["time_left"] > 0:
        time.sleep(1)
        room["time_left"] -= 1
        emit('timer_update', room["time_left"], room=room_id)
    if room["active"] and room["time_left"] <= 0:
        emit('game_over', "Time's up! Try again!", room=room_id)
        room["state"] = room["mission_states"][room["missions_completed"]]
        emit('init_game', {"state": room["state"], "time_left": room["time_left"]}, room=room_id)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def update_score_and_badges(room, username):
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT score, badges, unlocked_levels FROM users WHERE username = ?", (username,))
        score, badges, unlocked = cursor.fetchone()
        score = score + 10 if score else 10
        badges = badges.split(',') if badges else []
        unlocked = set(map(int, unlocked.split(','))) if unlocked else {1}
        
        if room["missions_completed"] == 3 and room["level"] % 3 == 0:
            badge = f"Badge_{room['level'] // 3}"
            if badge not in badges:
                badges.append(badge)
                emit('message', f"{username} earned {badge}!", room=room["room_id"])
        
        next_level = room["level"] + 1
        if next_level <= 30:
            unlocked.add(next_level)
        
        cursor.execute("UPDATE users SET score = ?, badges = ?, unlocked_levels = ? WHERE username = ?",
                       (score, ','.join(badges), ','.join(map(str, unlocked)), username))
        conn.commit()
    
    if room["missions_completed"] == 3:
        emit('level_complete', f"Level {room['level']} completed by {username}!", room=room["room_id"])
        room["active"] = False

def generate_unique_states(level):
    states = []
    if level <= 3:  # Path Finder
        for _ in range(3):
            size = 3 + (level - 1)
            grid = [""] * (size * size)
            grid[0] = "🤖"
            grid[-1] = "🏁"
            obstacles = (level - 1) * 2 + random.randint(0, 1)
            obstacle_positions = set()
            while len(obstacle_positions) < obstacles:
                pos = random.randint(1, size * size - 2)
                if pos not in obstacle_positions:
                    obstacle_positions.add(pos)
                    grid[pos] = "💀"
            states.append({"type": "path", "grid": grid.copy(), "size": size, "pos": 0, "moves": 5 + (level - 1) * 2})
    elif level <= 6:  # Shape Sorter
        shape_sets = [["⬜", "◯"], ["◯", "△", "★"], ["⬜", "★", "⬟"]]
        for shapes in shape_sets[:level - 3]:
            grid = shapes + shapes
            random.shuffle(grid)
            states.append({"type": "shape", "grid": grid.copy(), "sorted": []})
    elif level <= 9:  # Number Crunch
        targets = [10, 15, 20]
        for i in range(3):
            target = targets[level - 7]
            size = 5 + (level - 7)
            tiles = []
            remaining = target
            subset_size = random.randint(2, 4)
            for _ in range(subset_size - 1):
                num = random.randint(1, min(remaining - (subset_size - len(tiles) - 1), 5))
                tiles.append(num)
                remaining -= num
            tiles.append(remaining)
            for _ in range(size - subset_size):
                tiles.append(random.randint(1, 5))
            random.shuffle(tiles)
            states.append({"type": "number", "grid": tiles.copy(), "target": target, "sum": 0, "used": []})
    elif level <= 12:  # Word Weaver (Hangman-style)
        word_sets = [
            [
                {"word": "PYTHON", "hint": "I’m a snake and a programming language."},
                {"word": "CODE", "hint": "I’m what programmers write."},
                {"word": "SCRIPT", "hint": "I’m a set of instructions for computers."}
            ],  # Level 10
            [
                {"word": "HANGMAN", "hint": "I’m a word-guessing game."},
                {"word": "GUESS", "hint": "I’m what you do to solve a puzzle."},
                {"word": "RIDDLE", "hint": "I’m a question that tricks you."}
            ],  # Level 11
            [
                {"word": "DEVELOPER", "hint": "I build software."},
                {"word": "PROGRAMMING", "hint": "I’m the art of coding."},
                {"word": "CHALLENGE", "hint": "I’m a tough task to overcome."}
            ]  # Level 12
        ]
        word_data = word_sets[level - 10]
        for data in word_data:
            states.append({
                "type": "word",
                "word": data["word"],
                "progress": ['_' for _ in data["word"]],
                "attempts_left": 6,
                "guessed_letters": [],
                "hintSentence": data["hint"]
            })
    elif level <= 15:  # Switch Swap
        def toggle(grid, size, index):
            for i in [index, index - size, index + size, index - 1, index + 1]:
                if 0 <= i < size * size and (i // size == index // size or i % size == index % size):
                    grid[i] = 1 - grid[i]
        
        if level == 13:  # Predefined solvable states for 3x3 grid
            # Mission 1: Toggle corners (0, 2) - solvable with 2 moves
            grid1 = [1, 1, 1, 1, 1, 1, 1, 1, 1]
            toggle(grid1, 3, 0)  # Top-left
            toggle(grid1, 3, 2)  # Top-right
            states.append({"type": "switch", "grid": grid1.copy(), "size": 3})
            
            # Mission 2: Toggle (1, 3, 5) - solvable with 3 moves
            grid2 = [1, 1, 1, 1, 1, 1, 1, 1, 1]
            toggle(grid2, 3, 1)  # Top-middle
            toggle(grid2, 3, 3)  # Middle-left
            toggle(grid2, 3, 5)  # Middle-right
            states.append({"type": "switch", "grid": grid2.copy(), "size": 3})
            
            # Mission 3: Toggle (0, 4, 8) - solvable with 3 moves
            grid3 = [1, 1, 1, 1, 1, 1, 1, 1, 1]
            toggle(grid3, 3, 0)  # Top-left
            toggle(grid3, 3, 4)  # Center
            toggle(grid3, 3, 8)  # Bottom-right
            states.append({"type": "switch", "grid": grid3.copy(), "size": 3})
        else:
            # Levels 14 (4x4) and 15 (5x5) use random solvable states
            for i in range(3):
                size = 3 + (level - 13)
                grid = [1] * (size * size)  # Start with all lights on
                toggle_count = min(size * size, 2 + i + random.randint(0, 2))  # 2-5 toggles
                toggle_positions = random.sample(range(size * size), toggle_count)
                for pos in toggle_positions:
                    toggle(grid, size, pos)
                states.append({"type": "switch", "grid": grid.copy(), "size": size})
    elif level <= 18:  # Treasure Tap
        treasure_counts = [1, 2, 3]
        for treasures in treasure_counts[:level - 15]:
            size = 3 + (level - 16)
            grid = ["🏴‍☠️"] * treasures + ["💀"] * (size * size - treasures)
            random.shuffle(grid)
            states.append({"type": "treasure", "grid": grid.copy(), "revealed": [], "taps": 3 + (level - 16) * 2})
    elif level <= 21:  # Unscramble Words
        phrase_sets = [["CAT", "HAT"], ["BIG", "DOG", "PIG"], ["RUN", "FUN", "SUN"]]
        for phrase in phrase_sets[level - 19]:
            letters = list("".join(phrase.split()))
            random.shuffle(letters)
            states.append({"type": "unscramble", "phrase": phrase, "letters": letters.copy(), "guess": []})
    elif level <= 24:  # Pattern Recognition
        pattern_sets = [[[1, 2, 3], 4], [[2, 4, 6], 8], [[1, 3, 5], 7]]
        for pattern, correct in pattern_sets[:level - 21]:
            options = [correct] + [correct + random.randint(1, 5) for _ in range(3)]
            random.shuffle(options)
            states.append({"type": "pattern", "pattern": pattern.copy(), "options": options.copy(), "correct": correct})
    elif level <= 27:  # Jigsaw Puzzle
        for i in range(3):
            size = 2 + (level - 25)
            pieces = [f"{x},{y}" for x in range(size) for y in range(size)]
            random.shuffle(pieces)
            states.append({"type": "jigsaw", "size": size, "pieces": pieces.copy(), "placed": []})
    elif level <= 30:  # Riddles
        riddle_sets = [
            [("I’m tall and green, what am I?", "Tree", ["Car", "Dog", "Tree"])],
            [("I fly without wings, what am I?", "Kite", ["Bird", "Plane", "Kite"]),
             ("I’m round and bright, what am I?", "Sun", ["Moon", "Star", "Sun"])],
            [("I’m full of holes but hold water, what am I?", "Sponge", ["Net", "Bucket", "Sponge"]),
             ("I’m cold and sweet, what am I?", "Ice", ["Snow", "Cake", "Ice"]),
             ("I bark but don’t bite, what am I?", "Dog", ["Cat", "Wolf", "Dog"])]
        ]
        for riddle in riddle_sets[level - 28]:
            states.append({"type": "riddle", "question": riddle[0], "options": riddle[2].copy(), "correct": riddle[1]})
    return states

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('hub'))
    return render_template('login.html')  # Default to login page

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect('users.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT password FROM users WHERE username = ?", (username,))
            result = cursor.fetchone()
            if result and result[0] == password:
                session['username'] = username
                return redirect(url_for('hub'))
            else:
                return render_template('login.html', error="Invalid username or password")
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect('users.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM users WHERE username = ?", (username,))
            if cursor.fetchone():
                return render_template('signup.html', error="Username already exists")
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            session['username'] = username
            return redirect(url_for('hub'))
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/hub')
@login_required
def hub():
    username = session['username']
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT score FROM users WHERE username = ?", (username,))
        score = cursor.fetchone()[0] or 0
    return render_template('hub.html', username=username, score=score)

@app.route('/levels')
@login_required
def levels():
    username = session['username']
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT unlocked_levels FROM users WHERE username = ?", (username,))
        unlocked = set(map(int, cursor.fetchone()[0].split(',')))
    categories = [
        "Path Finder", "Shape Sorter", "Number Crunch", "Word Weaver",
        "Switch Swap", "Treasure Tap", "Unscramble Words", "Pattern Recognition",
        "Jigsaw Puzzle", "Riddles"
    ]
    return render_template('levels.html', categories=categories, unlocked=unlocked)

@app.route('/leaderboard')
@login_required
def leaderboard():
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, score FROM users ORDER BY score DESC LIMIT 10")
        leaders = cursor.fetchall()
    return render_template('leaderboard.html', leaders=leaders, username=session['username'])

@app.route('/badges')
@login_required
def badges():
    username = session['username']
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT badges FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()
        badges = result[0].split(',') if result and result[0] else []
    return render_template('badges.html', badges=badges)

@app.route('/learn/<int:level>')
@login_required
def learn(level):
    if level < 1 or level > 30:
        return redirect(url_for('levels'))
    return render_template('learn.html', level=level)

@app.route('/game/<int:level>')
@login_required
def game(level):
    if level < 1 or level > 30:
        return redirect(url_for('levels'))
    username = session['username']
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT unlocked_levels FROM users WHERE username = ?", (username,))
        unlocked = set(map(int, cursor.fetchone()[0].split(',')))
    if level not in unlocked:
        return redirect(url_for('levels'))
    return render_template('game.html', level=level)

@socketio.on('join')
def handle_join(data):
    level = data['level']
    username = session['username']
    room_id = f"level_{level}"
    
    join_room(room_id)
    clients[request.sid] = {"username": username, "room": room_id}
    
    if room_id not in game_rooms:
        game_rooms[room_id] = {
            "players": set(),
            "active": False,
            "level": level,
            "time_left": 60,
            "missions_completed": 0,
            "mission_states": [],
            "state": None,
            "timer_thread": None,
            "room_id": room_id
        }
    
    room = game_rooms[room_id]
    room["players"].add(username)
    room["active"] = True
    room["time_left"] = 60
    room["mission_states"] = generate_unique_states(level)
    room["state"] = room["mission_states"][0]
    room["missions_completed"] = 0
    
    logger.debug(f"{username} joined {room_id}, initial state: {room['state']}")
    emit('init_game', {"state": room["state"], "time_left": room["time_left"]}, room=room_id)
    emit('message', f"{username} joined Level {level}!", room=room_id)
    
    if room["timer_thread"] and room["timer_thread"].is_alive():
        room["active"] = False
        room["timer_thread"].join()
    import threading
    room["timer_thread"] = threading.Thread(target=timer, args=(room_id,), daemon=True)
    room["timer_thread"].start()

@socketio.on('game_action')
def handle_game_action(data):
    room_id = clients[data['sid']]["room"]
    username = clients[data['sid']]["username"]
    action = data['action']
    room = game_rooms[room_id]
    
    if not room["active"]:
        logger.debug(f"Room {room_id} not active, action ignored")
        return
    
    state = room["state"]
    logger.debug(f"Processing action for {state['type']} - Mission {room['missions_completed'] + 1}, State: {state}")
    
    if state["type"] == "path":
        index = action["index"]
        moves = [(0, 1), (1, 0), (0, -1), (-1, 0)]
        row, col = divmod(state["pos"], state["size"])
        new_row, new_col = divmod(index, state["size"])
        for dr, dc in moves:
            if row + dr == new_row and col + dc == new_col and 0 <= index < state["size"] * state["size"] and state["grid"][index] != "💀":
                state["grid"][state["pos"]] = ""
                state["grid"][index] = "🤖"
                state["pos"] = index
                state["moves"] -= 1
                emit('update_path', {"grid": state["grid"], "moves": state["moves"]}, room=room_id)
                if index == state["size"] * state["size"] - 1:
                    room["missions_completed"] += 1
                    logger.debug(f"Path Finder: Mission {room['missions_completed']} completed")
                    emit('mission_complete', f"Mission {room['missions_completed']}/3 done!", room=room_id)
                    emit('animate_win', room=room_id)
                    if room["missions_completed"] < 3:
                        room["state"] = room["mission_states"][room["missions_completed"]]
                        room["time_left"] = 60
                        logger.debug(f"Transitioning to mission {room['missions_completed'] + 1}, New state: {room['state']}")
                        emit('round_transition', room=room_id)
                        emit('init_game', {"state": room["state"], "time_left": room["time_left"]}, room=room_id)
                    else:
                        logger.debug(f"Level {room['level']} completed")
                        update_score_and_badges(room, username)
                elif state["moves"] <= 0:
                    emit('game_over', "Out of moves! Try again!", room=room_id)
                    room["state"] = room["mission_states"][room["missions_completed"]]
                    emit('init_game', {"state": room["state"], "time_left": room["time_left"]}, room=room_id)
                break
    elif state["type"] == "shape":
        index = action["index"]
        slot = action["slot"]
        if len(state["sorted"]) < len(state["grid"]) // 2 and state["grid"][index] not in state["sorted"]:
            state["sorted"].append(state["grid"][index])
            emit('place_shape', {"index": index, "slot": slot, "shape": state["grid"][index]}, room=room_id)
            if len(state["sorted"]) == len(state["grid"]) // 2:
                room["missions_completed"] += 1
                logger.debug(f"Shape Sorter: Mission {room['missions_completed']} completed")
                emit('mission_complete', f"Mission {room['missions_completed']}/3 done!", room=room_id)
                emit('animate_win', room=room_id)
                if room["missions_completed"] < 3:
                    room["state"] = room["mission_states"][room["missions_completed"]]
                    room["time_left"] = 60
                    logger.debug(f"Transitioning to mission {room['missions_completed'] + 1}, New state: {room['state']}")
                    emit('round_transition', room=room_id)
                    emit('init_game', {"state": room["state"], "time_left": room["time_left"]}, room=room_id)
                else:
                    logger.debug(f"Level {room['level']} completed")
                    update_score_and_badges(room, username)
    elif state["type"] == "number":
        index = action["index"]
        if index not in state["used"] and 0 <= index < len(state["grid"]):
            state["sum"] += state["grid"][index]
            state["used"].append(index)
            emit('update_sum', {"sum": state["sum"], "used": state["used"]}, room=room_id)
            logger.debug(f"Number Crunch: Sum={state['sum']}, Target={state['target']}, Used={state['used']}")
            if state["sum"] == state["target"]:
                room["missions_completed"] += 1
                logger.debug(f"Number Crunch: Mission {room['missions_completed']} completed")
                emit('mission_complete', f"Mission {room['missions_completed']}/3 done!", room=room_id)
                emit('animate_win', room=room_id)
                if room["missions_completed"] < 3:
                    logger.debug(f"Preparing transition to mission {room['missions_completed'] + 1}")
                    room["state"] = room["mission_states"][room["missions_completed"]]
                    room["state"]["sum"] = 0
                    room["state"]["used"] = []
                    room["time_left"] = 60
                    logger.debug(f"Transitioning to mission {room['missions_completed'] + 1}, New state: {room['state']}")
                    emit('round_transition', room=room_id)
                    emit('init_game', {"state": room["state"], "time_left": room["time_left"]}, room=room_id)
                else:
                    logger.debug(f"Level {room['level']} completed")
                    update_score_and_badges(room, username)
            elif state["sum"] > state["target"] or len(state["used"]) == len(state["grid"]):
                emit('game_over', "Sum wrong or no moves left! Try again!", room=room_id)
                room["state"] = room["mission_states"][room["missions_completed"]]
                room["state"]["sum"] = 0
                room["state"]["used"] = []
                emit('init_game', {"state": room["state"], "time_left": room["time_left"]}, room=room_id)
    elif state["type"] == "word":
        letter = action["letter"].upper()
        logger.debug(f"Word Weaver: Guessing letter '{letter}' for word {state['word']}")
        
        if len(letter) != 1 or not letter.isalpha():
            emit('message', "Please enter a single letter!", room=room_id)
            return
        
        if letter in state["guessed_letters"]:
            emit('message', "Letter already guessed!", room=room_id)
            return
        
        state["guessed_letters"].append(letter)
        if letter in state["word"]:
            for i, char in enumerate(state["word"]):
                if char == letter:
                    state["progress"][i] = letter
        else:
            state["attempts_left"] -= 1
        
        emit('word_update', {
            "word": " ".join(state["progress"]),
            "attempts": state["attempts_left"],
            "guessed": state["guessed_letters"]
        }, room=room_id)
        
        if '_' not in state["progress"]:
            room["missions_completed"] += 1
            logger.debug(f"Word Weaver: Mission {room['missions_completed']} completed")
            emit('mission_complete', f"Mission {room['missions_completed']}/3 done! Word was '{state['word']}'.", room=room_id)
            emit('animate_win', room=room_id)
            if room["missions_completed"] < 3:
                room["state"] = room["mission_states"][room["missions_completed"]]
                room["time_left"] = 60
                logger.debug(f"Transitioning to mission {room['missions_completed'] + 1}, New state: {room['state']}")
                emit('round_transition', room=room_id)
                emit('init_game', {"state": room["state"], "time_left": room["time_left"]}, room=room_id)
            else:
                logger.debug(f"Level {room['level']} completed")
                update_score_and_badges(room, username)
        elif state["attempts_left"] <= 0:
            emit('game_over', f"Game Over! The word was '{state['word']}'.", room=room_id)
            room["state"] = room["mission_states"][room["missions_completed"]]
            room["time_left"] = 60
            emit('init_game', {"state": room["state"], "time_left": room["time_left"]}, room=room_id)
    elif state["type"] == "switch":
        index = action["index"]
        size = state["size"]
        for i in [index, index - size, index + size, index - 1, index + 1]:
            if 0 <= i < size * size and (i // size == index // size or i % size == index % size):
                state["grid"][i] = 1 - state["grid"][i]
        logger.debug(f"Switch action on {index}, new grid: {state['grid']}")  # Debug switch action
        emit('update_switch', {"grid": state["grid"]}, room=room_id)
        if all(state["grid"]):
            room["missions_completed"] += 1
            logger.debug(f"Switch Swap: Mission {room['missions_completed']} completed")
            emit('mission_complete', f"Mission {room['missions_completed']}/3 done!", room=room_id)
            emit('animate_win', room=room_id)
            if room["missions_completed"] < 3:
                room["state"] = room["mission_states"][room["missions_completed"]]
                room["time_left"] = 60
                logger.debug(f"Transitioning to mission {room['missions_completed'] + 1}, New state: {room['state']}")
                emit('round_transition', room=room_id)
                emit('init_game', {"state": room["state"], "time_left": room["time_left"]}, room=room_id)
            else:
                logger.debug(f"Level {room['level']} completed")
                update_score_and_badges(room, username)
    elif state["type"] == "treasure":
        index = action["index"]
        if index not in state["revealed"] and state["taps"] > 0:
            state["revealed"].append(index)
            state["taps"] -= 1
            emit('reveal_treasure', {"index": index, "value": state["grid"][index], "taps": state["taps"]}, room=room_id)
            if state["grid"][index] == "🏴‍☠️":
                room["missions_completed"] += 1
                logger.debug(f"Treasure Tap: Mission {room['missions_completed']} completed")
                emit('mission_complete', f"Mission {room['missions_completed']}/3 done!", room=room_id)
                emit('animate_win', room=room_id)
                if room["missions_completed"] < 3:
                    room["state"] = room["mission_states"][room["missions_completed"]]
                    room["time_left"] = 60
                    logger.debug(f"Transitioning to mission {room['missions_completed'] + 1}, New state: {room['state']}")
                    emit('round_transition', room=room_id)
                    emit('init_game', {"state": room["state"], "time_left": room["time_left"]}, room=room_id)
                else:
                    logger.debug(f"Level {room['level']} completed")
                    update_score_and_badges(room, username)
            elif state["taps"] <= 0:
                emit('game_over', "No taps left! Try again!", room=room_id)
                room["state"] = room["mission_states"][room["missions_completed"]]
                emit('init_game', {"state": room["state"], "time_left": room["time_left"]}, room=room_id)
    elif state["type"] == "unscramble":
        index = action["index"]
        state["guess"].append(state["letters"][index])
        emit('update_unscramble', {"guess": state["guess"]}, room=room_id)
        if len(state["guess"]) == len(state["phrase"].replace(" ", "")):
            guess_str = "".join(state["guess"])
            if guess_str == state["phrase"].replace(" ", ""):
                room["missions_completed"] += 1
                logger.debug(f"Unscramble: Mission {room['missions_completed']} completed")
                emit('mission_complete', f"Mission {room['missions_completed']}/3 done!", room=room_id)
                emit('animate_win', room=room_id)
                if room["missions_completed"] < 3:
                    room["state"] = room["mission_states"][room["missions_completed"]]
                    room["time_left"] = 60
                    logger.debug(f"Transitioning to mission {room['missions_completed'] + 1}, New state: {room['state']}")
                    emit('round_transition', room=room_id)
                    emit('init_game', {"state": room["state"], "time_left": room["time_left"]}, room=room_id)
                else:
                    logger.debug(f"Level {room['level']} completed")
                    update_score_and_badges(room, username)
            else:
                emit('message', "Wrong phrase! Try again.", room=room_id)
                state["guess"] = []
                emit('reset_unscramble', room=room_id)
    elif state["type"] == "pattern":
        choice = action["choice"]
        if choice == state["correct"]:
            room["missions_completed"] += 1
            logger.debug(f"Pattern: Mission {room['missions_completed']} completed")
            emit('mission_complete', f"Mission {room['missions_completed']}/3 done!", room=room_id)
            emit('animate_win', room=room_id)
            if room["missions_completed"] < 3:
                room["state"] = room["mission_states"][room["missions_completed"]]
                room["time_left"] = 60
                logger.debug(f"Transitioning to mission {room['missions_completed'] + 1}, New state: {room['state']}")
                emit('round_transition', room=room_id)
                emit('init_game', {"state": room["state"], "time_left": room["time_left"]}, room=room_id)
            else:
                logger.debug(f"Level {room['level']} completed")
                update_score_and_badges(room, username)
        else:
            emit('message', "Wrong number! Try again.", room=room_id)
            room["state"] = room["mission_states"][room["missions_completed"]]
            emit('init_game', {"state": room["state"], "time_left": room["time_left"]}, room=room_id)
    elif state["type"] == "jigsaw":
        index = action["index"]
        slot = action["slot"]
        piece = state["pieces"][index]
        if piece not in state["placed"]:
            state["placed"].append(piece)
            emit('place_piece', {"index": index, "slot": slot, "piece": piece}, room=room_id)
            if len(state["placed"]) == state["size"] * state["size"]:
                room["missions_completed"] += 1
                logger.debug(f"Jigsaw: Mission {room['missions_completed']} completed")
                emit('mission_complete', f"Mission {room['missions_completed']}/3 done!", room=room_id)
                emit('animate_win', room=room_id)
                if room["missions_completed"] < 3:
                    room["state"] = room["mission_states"][room["missions_completed"]]
                    room["time_left"] = 60
                    logger.debug(f"Transitioning to mission {room['missions_completed'] + 1}, New state: {room['state']}")
                    emit('round_transition', room=room_id)
                    emit('init_game', {"state": room["state"], "time_left": room["time_left"]}, room=room_id)
                else:
                    logger.debug(f"Level {room['level']} completed")
                    update_score_and_badges(room, username)
    elif state["type"] == "riddle":
        choice = action["choice"]
        if choice == state["correct"]:
            room["missions_completed"] += 1
            logger.debug(f"Riddle: Mission {room['missions_completed']} completed")
            emit('mission_complete', f"Mission {room['missions_completed']}/3 done!", room=room_id)
            emit('animate_win', room=room_id)
            if room["missions_completed"] < 3:
                room["state"] = room["mission_states"][room["missions_completed"]]
                room["time_left"] = 60
                logger.debug(f"Transitioning to mission {room['missions_completed'] + 1}, New state: {room['state']}")
                emit('round_transition', room=room_id)
                emit('init_game', {"state": room["state"], "time_left": room["time_left"]}, room=room_id)
            else:
                logger.debug(f"Level {room['level']} completed")
                update_score_and_badges(room, username)
        else:
            emit('message', "Wrong answer! Try again.", room=room_id)
            room["state"] = room["mission_states"][room["missions_completed"]]
            emit('init_game', {"state": room["state"], "time_left": room["time_left"]}, room=room_id)

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in clients:
        username = clients[request.sid]["username"]
        room_id = clients[request.sid]["room"]
        if room_id in game_rooms:
            room = game_rooms[room_id]
            room["players"].discard(username)
            emit('message', f"{username} left the game.", room=room_id)
            if not room["players"]:
                room["active"] = False
                del game_rooms[room_id]
        del clients[request.sid]

if __name__ == "__main__":
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)