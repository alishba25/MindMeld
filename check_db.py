import sqlite3

try:
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    print("Users in the database:")
    for user in users:
        print(user)
    conn.close()
except sqlite3.DatabaseError as e:
    print(f"Database error: {e}")