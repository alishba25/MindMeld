from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room
import sqlite3
import random
import time
import logging
import math
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
        # Existing table
        cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                          (username TEXT PRIMARY KEY, 
                           password TEXT, 
                           score INTEGER DEFAULT 0, 
                           badges TEXT DEFAULT '', 
                           unlocked_levels TEXT DEFAULT '1')''')
        
        # New analytics table
        cursor.execute('''CREATE TABLE IF NOT EXISTS user_analytics
                          (id INTEGER PRIMARY KEY AUTOINCREMENT,
                           username TEXT,
                           game_type TEXT,
                           level INTEGER,
                           completion_time INTEGER,
                           attempts INTEGER,
                           accuracy FLOAT,
                           timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                           cognitive_area TEXT,
                           FOREIGN KEY (username) REFERENCES users(username))''')
        
        # Cognitive areas progress table
        cursor.execute('''CREATE TABLE IF NOT EXISTS cognitive_progress
                          (id INTEGER PRIMARY KEY AUTOINCREMENT,
                           username TEXT,
                           memory_score INTEGER DEFAULT 0,
                           logic_score INTEGER DEFAULT 0,
                           pattern_score INTEGER DEFAULT 0,
                           spatial_score INTEGER DEFAULT 0,
                           verbal_score INTEGER DEFAULT 0,
                           timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                           FOREIGN KEY (username) REFERENCES users(username))''')
        conn.commit()

init_db()

def timer(room_id):
    room = game_rooms.get(room_id)
    if room:
        with app.app_context():
            while room["time_left"] > 0:
                time.sleep(1)
                room["time_left"] -= 1
                socketio.emit('timer_update', room["time_left"], room=room_id)

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
        # Define shape sets with increasing number of shapes per level
        shape_sets = {
            4: [
                ["⬜", "◯", "△"],  # 3 shapes for level 4
                ["⬜", "◯", "△"],
                ["⬜", "◯", "△"]
            ],
            5: [
                ["⬜", "◯", "△", "★", "⬟"],  # 5 shapes for level 5
                ["⬜", "◯", "△", "★", "⬟"],
                ["⬜", "◯", "△", "★", "⬟"]
            ],
            6: [
                ["⬜", "◯", "△", "★", "⬟", "❤️", "⬢"],  # 7 shapes for level 6
                ["⬜", "◯", "△", "★", "⬟", "❤️", "⬢"],
                ["⬜", "◯", "△", "★", "⬟", "❤️", "⬢"]
            ]
        }
        
        # Get the shape sets for current level
        current_shape_sets = shape_sets[level]
        
        # Generate three missions for the current level
        for shapes in current_shape_sets:
            grid = shapes + shapes  # Double the shapes to create pairs
            random.shuffle(grid)    # Randomize the order
            states.append({
                "type": "shape",
                "grid": grid.copy(),
                "sorted": []
            })
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
    
        if level == 13:  # 3x3 grid with simpler patterns
            # Mission 1: Single toggle at center (4) - solvable with 1 move
            grid1 = [1] * 9  # All lights on
            toggle(grid1, 3, 4)  # Toggle center
            states.append({"type": "switch", "grid": grid1.copy(), "size": 3})
            
            # Mission 2: Two adjacent toggles - solvable with 2 moves
            grid2 = [1] * 9
            toggle(grid2, 3, 1)  # Toggle top-middle
            toggle(grid2, 3, 4)  # Toggle center
            states.append({"type": "switch", "grid": grid2.copy(), "size": 3})
            
            # Mission 3: Two diagonal toggles - solvable with 2 moves
            grid3 = [1] * 9
            toggle(grid3, 3, 0)  # Toggle top-left
            toggle(grid3, 3, 8)  # Toggle bottom-right
            states.append({"type": "switch", "grid": grid3.copy(), "size": 3})
            
        elif level == 14:  # 4x4 grid with simple patterns
            for i in range(3):
                grid = [1] * 16  # Start with all lights on
                # Create simple patterns requiring 2-3 moves
                if i == 0:
                    # Toggle center squares - solvable with 2 moves
                    toggle(grid, 4, 5)
                    toggle(grid, 4, 10)
                elif i == 1:
                    # Toggle corners - solvable with 2 moves
                    toggle(grid, 4, 0)
                    toggle(grid, 4, 15)
                else:
                    # Toggle middle row - solvable with 3 moves
                    toggle(grid, 4, 5)
                    toggle(grid, 4, 6)
                states.append({"type": "switch", "grid": grid.copy(), "size": 4})
                
        else:  # level 15 - 5x5 grid with medium patterns
            for i in range(3):
                grid = [1] * 25
                # Create patterns requiring 2-3 moves
                if i == 0:
                    # Toggle center and adjacent - solvable with 2 moves
                    toggle(grid, 5, 12)
                    toggle(grid, 5, 13)
                elif i == 1:
                    # Toggle diagonal - solvable with 2 moves
                    toggle(grid, 5, 0)
                    toggle(grid, 5, 24)
                else:
                    # Toggle center cross - solvable with 3 moves
                    toggle(grid, 5, 12)
                    toggle(grid, 5, 7)
                    toggle(grid, 5, 17)
                states.append({"type": "switch", "grid": grid.copy(), "size": 5})
    elif level <= 18:  # Treasure Tap
    # Increase randomness with a range of treasures
        treasure_range = [1, 2, 3, 4]  # More possible treasures
        for _ in range(3):  # Generate 3 states per level
            size = 3 + (level - 16)
        # Random number of treasures between 1 and half the grid size
            treasures = random.randint(1, size * size // 2)
        # Add extra obstacles for randomness
            obstacles = random.randint(size, size * size - treasures - 1)
            grid = ["🏴‍☠️"] * treasures + ["💀"] * obstacles + ["?"] * (size * size - treasures - obstacles)
            random.shuffle(grid)  # Shuffle multiple times for more randomness
            for _ in range(3):  # Shuffle 3 times
                random.shuffle(grid)
            print(f"Level {level}: Size = {size}, Treasures = {treasures}, Obstacles = {obstacles}, Total tiles = {len(grid)}")
        # Increase taps for easier gameplay
            taps = 5 + (level - 16) * 3  # More tries (e.g., 5 for Level 16, 8 for Level 17, 11 for Level 18)
            states.append({"type": "treasure", "grid": grid.copy(), "revealed": [], "taps": taps})
    elif level <= 21:  # Unscramble Words
        phrase_sets = [["CAT", "HAT", "MAT"], ["BIG", "DOG", "PIG"], ["RUN", "FUN", "SUN"]]
        for phrase in phrase_sets[level - 19]:
            letters = list("".join(phrase.split()))
            random.shuffle(letters)
            states.append({"type": "unscramble", "phrase": phrase, "letters": letters.copy(), "guess": []})
    elif level <= 24:  # Pattern Recognition
    # Define 9 unique patterns
        all_patterns = [
            [[1, 2, 3], 4],          # Pattern 1: +1 sequence
            [[2, 4, 6], 8],          # Pattern 2: +2 sequence
            [[1, 3, 5], 7],          # Pattern 3: +2 odd sequence
            [[3, 6, 9], 12],         # Pattern 4: +3 sequence
            [[4, 8, 12], 16],        # Pattern 5: +4 sequence
            [[5, 10, 15], 20],       # Pattern 6: +5 sequence
            [[2, 4, 8], 16],         # Pattern 7: x2 sequence
            [[1, 4, 9], 16],         # Pattern 8: squares (1, 4, 9)
            [[2, 6, 12], 20]         # Pattern 9: +4, +6, +8
        ]
    # Assign 3 patterns per level (22, 23, 24)
        if level == 22:
            selected_patterns = all_patterns[0:3]  # Patterns 1, 2, 3
        elif level == 23:
            selected_patterns = all_patterns[3:6]  # Patterns 4, 5, 6
        elif level == 24:
            selected_patterns = all_patterns[6:9]  # Patterns 7, 8, 9
    
        for pattern, correct in selected_patterns:
            options = [correct] + [correct + random.randint(1, 5) for _ in range(3)]
            random.shuffle(options)
            states.append({"type": "pattern", "pattern": pattern.copy(), "options": options.copy(), "correct": correct})
    
    elif level <= 27:  # Number-Alphabet Sequence
        base_length = 2 + (level - 25)  # Base length increases with level (2, 3, 4)
        for _ in range(3):  # 3 missions per level
            sequence = []
            for i in range(base_length * 2):  # Double length for alternating pattern
                if i % 2 == 0:
                    sequence.append(str(i // 2 + 1))  # Numbers: 1, 2, 3...
                else:
                    sequence.append(chr(65 + i // 2))  # Letters: A, B, C...
            
            # Create grid with sequence plus additional items
            grid = sequence.copy()
            extras = []
            for i in range(16 - len(sequence)):  # Fill remaining spots in 4x4 grid
                if i % 2 == 0:
                    extras.append(str(len(sequence) // 2 + i // 2 + 1))
                else:
                    extras.append(chr(65 + len(sequence) // 2 + i // 2))
            
            grid.extend(extras)
            random.shuffle(grid)
            
            states.append({
                "type": "sequence",
                "grid": grid,
                "sequence": sequence,
                "selected": [],
                "size": 4  # 4x4 grid
            })

    elif level <= 30:  # Riddles
        riddle_sets = {
            28: [  # Level 28 riddles
                ("I'm tall and green, what am I?", "Tree", ["Car", "Dog", "Tree"]),
                ("I have keys but no locks, space but no room, you can enter but not go in. What am I?", "Keyboard", ["Phone", "Keyboard", "Door"]),
                ("I'm always hungry; I must always be fed. The finger I touch, will soon turn red. What am I?", "Fire", ["Water", "Fire", "Wind"])
            ],
            29: [  # Level 29 riddles
                ("What has keys, but no locks; space, but no room; and you can enter, but not go in?", "Piano", ["Guitar", "Piano", "Drum"]),
                ("What gets wetter and wetter the more it dries?", "Towel", ["Sponge", "Towel", "Paper"]),
                ("What has a head and a tail that will never meet?", "Coin", ["Snake", "Coin", "Rope"])
            ],
            30: [  # Level 30 riddles
                ("I have cities, but no houses. I have mountains, but no trees. I have water, but no fish. I have roads, but no cars. What am I?", "Map", ["Globe", "Map", "Picture"]),
                ("What is always in front of you but can't be seen?", "Future", ["Past", "Future", "Present"]),
                ("I speak without a mouth and hear without ears. I have no body, but I come alive with wind. What am I?", "Echo", ["Music", "Echo", "Voice"])
            ]
        }
        
        current_riddles = riddle_sets[level]
        for riddle in current_riddles:
            states.append({
                "type": "riddle",
                "question": riddle[0],
                "options": riddle[2].copy(),
                "correct": riddle[1]
            })
    return states

def generate_sequence_level(level):
    size = 4  # 4x4 grid
    if level == 25:
        # Numbers sequence
        sequence = [str(i) for i in range(1, 7)]  # 1,2,3,4,5,6
        grid = sequence + [str(i) for i in range(7, 17)]  # Fill rest with numbers
    elif level == 26:
        # Alphabet sequence
        sequence = ['A', 'B', 'C', 'D', 'E', 'F']
        grid = sequence + [chr(ord('G') + i) for i in range(10)]  # Fill rest with letters
    else:  # level 27
        # Mixed sequence
        sequence = ['1', 'A', '2', 'B', '3', 'C']
        grid = sequence + ['4', 'D', '5', 'E', '6', 'F', '7', 'G', '8', 'H']

    # Shuffle the grid while keeping track of correct positions
    positions = list(range(len(grid)))
    random.shuffle(positions)
    shuffled_grid = [grid[i] for i in positions]

    return {
        "type": "sequence",
        "size": size,
        "grid": shuffled_grid,
        "sequence": sequence,
        "selected": [],
        "completed": False
    }

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('hub'))
    return render_template('auth.html')  # Use new combined auth template

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
        unlocked = list(map(int, cursor.fetchone()[0].split(',')))
    if level not in unlocked:
        return redirect(url_for('levels'))
    # Initialize game state for the level
    states = generate_unique_states(level)
    initial_state = states[0] if states else {"grid": [], "size": 4}
    print(f"Initial state for Level {level}: {initial_state}")
    grid_size = initial_state.get("size")
    if grid_size is None:
        grid_len = len(initial_state.get("grid", []))
        grid_size = int(math.sqrt(grid_len)) if grid_len > 0 else 4
    shape = initial_state.get("shape", "Unknown Shape")
    print(f"Passing grid_size = {grid_size}, shape = {shape} to game.html for Level {level}")
    session['current_level'] = level
    session['game_state'] = initial_state
    return render_template('game.html', level=level, grid_size=grid_size, shape=shape)

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

@socketio.on('tile_click')
def handle_tile_click(data):
    room_id = clients.get(request.sid, {}).get('room')
    if not room_id or room_id not in game_rooms:
        return
    
    room = game_rooms[room_id]
    state = room['state']
    index = data.get('index')
    
    if room['level'] in range(25, 28):  # Sequence levels
        if index is None or index >= len(state['grid']):
            return
            
        # Prevent double-clicking the same tile
        if index in state['selected']:
            return
            
        current_pos = len(state['selected'])
        clicked_value = state['grid'][index]
        
        if clicked_value == state['sequence'][current_pos]:
            state['selected'].append(index)
            emit('update_sequence', {
                'index': index,
                'value': clicked_value,
                'selected': state['selected']  # Send full selected array
            }, room=room_id)
            
            if len(state['selected']) == len(state['sequence']):
                room['missions_completed'] += 1
                emit('mission_complete', f"Mission {room['missions_completed']}/3 complete!", room=room_id)
                
                if room['missions_completed'] < 3:
                    room['state'] = room['mission_states'][room['missions_completed']]
                    room['state']['selected'] = []  # Reset selected for new mission
                    emit('init_game', {'state': room['state']}, room=room_id)
                else:
                    update_score_and_badges(room, session.get('username'))
                    emit('level_complete', room=room_id)
        else:
            state['selected'] = []
            emit('sequence_reset', room=room_id)
            emit('message', "Wrong sequence! Try again!", room=room_id)
    elif room['level'] in range(16, 19):  # Treasure Tap
        state = room['state']
        if index is not None and index < len(state['grid']) and index not in state['revealed']:
            state['revealed'].append(index)
            state['taps'] -= 1
            if state['grid'][index] == "🏴‍☠️":
                emit('game_result', {'result': 'win'}, room=room_id)
            elif state['taps'] <= 0:
                emit('game_result', {'result': 'lose'}, room=room_id)
            emit('update_game', {'state': state}, room=room_id)
    else:
        return

@socketio.on('place_piece')
def handle_place_piece(data):
    room = clients.get(request.sid)
    if not room:
        return
    game = game_rooms.get(room)
    if not game or game['level'] not in range(25, 28):
        return
    state = game['state']
    x, y = data['x'], data['y']
    piece_index = data['pieceIndex']
    # Check if the position is already occupied
    if any(p['x'] == x and p['y'] == y for p in state['placed']):
        return
    # Get the piece to place
    unplaced = [p for p in state['pieces'] if not any(p['pos'] == placed['piece']['pos'] for placed in state['placed'])]
    if piece_index >= len(unplaced):
        return
    piece = unplaced[piece_index]
    # Place the piece
    state['placed'].append({'x': x, 'y': y, 'piece': piece})
    # Check if the puzzle is solved
    pattern = state['pattern']
    all_correct = all(
        any(p['x'] == px and p['y'] == py and p['piece']['pos'] == f"{px},{py}" for p in state['placed'])
        for px in range(state['size'])
        for py in range(state['size'])
        if pattern[px][py] == 1
    )
    if all_correct:
        emit('game_result', {'result': 'win'}, room=room)
    emit('update_game', {'state': state}, room=room)

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

def calculate_improvement(cognitive_progress):
    if not cognitive_progress or len(cognitive_progress) < 2:
        return 0.0
        
    # Split data into two periods
    mid_point = len(cognitive_progress) // 2
    first_period = cognitive_progress[:mid_point]
    second_period = cognitive_progress[mid_point:]
    
    if not first_period or not second_period:
        return 0.0
    
    # Calculate average for first and last entry
    def calculate_average(entry):
        return sum(entry[:5]) / 5  # First 5 elements are the cognitive scores
    
    initial_avg = calculate_average(first_period[0])
    current_avg = calculate_average(second_period[-1])
    
    # Calculate improvement percentage
    if initial_avg == 0:
        return 0.0
    
    improvement = ((current_avg - initial_avg) / initial_avg * 100)
    return round(improvement, 1)

@app.route('/analytics/<username>')
@login_required
def user_analytics(username):
    if username != session['username']:
        return redirect(url_for('hub'))
        
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        
        # Get overall progress for each game type
        cursor.execute("""
            SELECT game_type, 
                   ROUND(AVG(accuracy), 2) as avg_accuracy,
                   COUNT(*) as games_played,
                   ROUND(AVG(completion_time), 1) as avg_time
            FROM user_analytics
            WHERE username = ?
            GROUP BY game_type
        """, (username,))
        overall_stats = cursor.fetchall()
        
        # Get latest cognitive scores
        cursor.execute("""
            SELECT memory_score, logic_score, pattern_score,
                   spatial_score, verbal_score, 
                   strftime('%Y-%m-%d', timestamp) as date
            FROM cognitive_progress
            WHERE username = ?
            ORDER BY timestamp DESC
            LIMIT 10
        """, (username,))
        cognitive_progress = cursor.fetchall()
        
        # Get recent activity
        cursor.execute("""
            SELECT game_type, level, accuracy, completion_time,
                   strftime('%Y-%m-%d %H:%M', timestamp) as formatted_time
            FROM user_analytics
            WHERE username = ?
            ORDER BY timestamp DESC
            LIMIT 5
        """, (username,))
        recent_activity = cursor.fetchall()
        
        # If no data exists, provide default values
        if not cognitive_progress:
            cognitive_progress = [(0, 0, 0, 0, 0, 'No data')]
        
        if not overall_stats:
            overall_stats = [('No games played', 0, 0, 0)]
            
    improvement = calculate_improvement(cognitive_progress)
    
    return render_template('analytics.html',
                         username=username,
                         overall_stats=overall_stats,
                         cognitive_progress=cognitive_progress,
                         recent_activity=recent_activity,
                         improvement=improvement)

def update_analytics(username, game_type, level, completion_time, attempts, accuracy):
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        
        # Update game analytics
        cursor.execute("""
            INSERT INTO user_analytics 
            (username, game_type, level, completion_time, attempts, accuracy, cognitive_area)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (username, game_type, level, completion_time, attempts, accuracy, 
              get_cognitive_area(game_type)))
        
        # Update cognitive scores
        cognitive_scores = calculate_cognitive_scores(username)
        cursor.execute("""
            INSERT INTO cognitive_progress 
            (username, memory_score, logic_score, pattern_score, spatial_score, verbal_score)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username, cognitive_scores['memory'], cognitive_scores['logic'],
              cognitive_scores['pattern'], cognitive_scores['spatial'],
              cognitive_scores['verbal']))
        conn.commit()

def get_cognitive_area(game_type):
    cognitive_mapping = {
        'path': 'spatial',
        'shape': 'pattern',
        'number': 'logic',
        'word': 'verbal',
        'unscramble': 'verbal',
        'riddle': 'logic'
    }
    return cognitive_mapping.get(game_type, 'general')

def calculate_cognitive_scores(username):
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT cognitive_area, AVG(accuracy) 
            FROM user_analytics 
            WHERE username = ? 
            GROUP BY cognitive_area
        """, (username,))
        scores = dict(cursor.fetchall())
        
        return {
            'memory': int(scores.get('memory', 0)),
            'logic': int(scores.get('logic', 0)),
            'pattern': int(scores.get('pattern', 0)),
            'spatial': int(scores.get('spatial', 0)),
            'verbal': int(scores.get('verbal', 0))
        }

if __name__ == "__main__":
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)

