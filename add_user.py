import sqlite3

conn = sqlite3.connect('users.db')
cursor = conn.cursor()
cursor.execute("INSERT INTO users (username, password, unlocked_levels) VALUES (?, ?, ?)", ('alishba25ansari', 'ButterChicken', '1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16'))
conn.commit()
conn.close()
print("User added successfully!")