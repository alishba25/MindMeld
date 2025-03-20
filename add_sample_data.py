import sqlite3
import random
from datetime import datetime, timedelta

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

def add_sample_data():
    # Add the usernames you want to generate data for
    users = ['alishba25ansari', 'davindern', 'ipshita69', 'ananyag', 'adityak9892', 'krishna101']
    game_types = ['path', 'shape', 'number', 'word', 'unscramble', 'riddle']
    
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        
        # Add initial scores for users
        for user in users:
            cursor.execute("""
                UPDATE users 
                SET score = ?
                WHERE username = ?
            """, (random.randint(100, 1000), user))
            
        # Add sample analytics data with clear improvement trend
        for user in users:
            # Generate 30 days of data
            for days_ago in range(30, -1, -1):
                date = datetime.now() - timedelta(days=days_ago)
                
                # Define base accuracy that starts lower and improves more significantly
                if days_ago > 15:  # First half (older data)
                    base_accuracy = random.uniform(40, 60)  # Lower initial performance
                else:  # Second half (recent data)
                    base_accuracy = random.uniform(70, 90)  # Higher recent performance
                
                # Generate 2-4 game sessions per day
                for _ in range(random.randint(2, 4)):
                    game_type = random.choice(game_types)
                    
                    # Add some random variation to the base accuracy
                    accuracy = min(100, base_accuracy + random.uniform(-5, 5))
                    
                    # Completion time improves over time
                    if days_ago > 15:
                        completion_time = random.randint(90, 120)  # Slower initially
                    else:
                        completion_time = random.randint(30, 60)   # Faster recently
                    
                    cursor.execute("""
                        INSERT INTO user_analytics 
                        (username, game_type, level, completion_time, attempts, 
                         accuracy, timestamp, cognitive_area)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user,
                        game_type,
                        random.randint(1, 30),
                        completion_time,
                        random.randint(1, 5),
                        accuracy,
                        date.replace(
                            hour=random.randint(9, 21),
                            minute=random.randint(0, 59)
                        ),
                        get_cognitive_area(game_type)
                    ))
            
            # Add cognitive progress data with clear improvement trend
            for days_ago in range(30, -1, -1):
                date = datetime.now() - timedelta(days=days_ago)
                
                # Define base scores that show clear progression
                if days_ago > 15:  # First half (older data)
                    base_score = random.uniform(40, 55)  # Lower initial scores
                else:  # Second half (recent data)
                    base_score = random.uniform(75, 90)  # Higher recent scores
                
                # Add slight random variation to each cognitive area
                cursor.execute("""
                    INSERT INTO cognitive_progress 
                    (username, memory_score, logic_score, pattern_score, 
                     spatial_score, verbal_score, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    user,
                    min(100, base_score + random.uniform(-5, 5)),
                    min(100, base_score + random.uniform(-5, 5)),
                    min(100, base_score + random.uniform(-5, 5)),
                    min(100, base_score + random.uniform(-5, 5)),
                    min(100, base_score + random.uniform(-5, 5)),
                    date
                ))
        
        conn.commit()
        print("Sample data added successfully!")

if __name__ == "__main__":
    add_sample_data()



