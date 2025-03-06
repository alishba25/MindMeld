import sqlite3

conn = sqlite3.connect('users.db')
cursor = conn.cursor()
cursor.execute("UPDATE users SET unlocked_levels = ? WHERE username = ?", ('1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16', 'alishba25ansari'))
conn.commit()
conn.close()