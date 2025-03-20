import sqlite3

# List of players to add with their credentials
players = [
    ('davindern', 'PunjabLassi', '1,2,3,4,5,6,7,8,9'),
    ('ipshita69', 'GasFromBhopal', '1,2,3,4,5,6,7,8,9,10,11,12'),
    ('ananyag', 'OnkarB', '1,2,3,4,5,6,7,8'),
    ('adityak9892', 'SeatFirst', '1,2,3,4,5,6,7,8,9,10'),
    ('krishna101', 'KrishuValo', '1,2,3,4,5,6,7,8')
]

try:
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    # Add each player
    for username, password, levels in players:
        try:
            cursor.execute(
                "INSERT INTO users (username, password, unlocked_levels) VALUES (?, ?, ?)",
                (username, password, levels)
            )
            print(f"Added user: {username}")
        except sqlite3.IntegrityError:
            print(f"User {username} already exists, skipping...")
    
    conn.commit()
    print("\nAll users added successfully!")

except sqlite3.Error as e:
    print(f"Database error: {e}")

finally:
    conn.close()
