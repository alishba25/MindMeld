import sqlite3

def clear_sample_data():
    try:
        with sqlite3.connect('users.db') as conn:
            cursor = conn.cursor()
            
            # Clear analytics data
            cursor.execute("DELETE FROM user_analytics")
            
            # Clear cognitive progress data
            cursor.execute("DELETE FROM cognitive_progress")
            
            # Reset user scores to 0
            cursor.execute("UPDATE users SET score = 0")
            
            conn.commit()
            print("Successfully cleared all sample data!")
            
            # Print count of remaining records
            cursor.execute("SELECT COUNT(*) FROM user_analytics")
            analytics_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM cognitive_progress")
            progress_count = cursor.fetchone()[0]
            
            print(f"\nVerification:")
            print(f"User analytics records: {analytics_count}")
            print(f"Cognitive progress records: {progress_count}")
            
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    clear_sample_data()