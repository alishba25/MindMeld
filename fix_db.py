import sqlite3

# Connect to the database
conn = sqlite3.connect('C:/Users/User/OneDrive/Desktop/MindMeld/users.db')
cursor = conn.cursor()

# Add the score column if it doesn’t exist
cursor.execute("ALTER TABLE users ADD COLUMN score INTEGER DEFAULT 0")

# Commit the change
conn.commit()

# Verify the schema
cursor.execute("PRAGMA table_info(users)")
print("Table schema after update:", cursor.fetchall())

# Close the connection
conn.close()