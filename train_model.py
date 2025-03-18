import sqlite3
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import joblib

# Connect to the database
conn = sqlite3.connect('users.db')

# Fetch performance data with IQ scores
query = """
SELECT p.username, p.level, p.mission, p.completion_time, p.errors, p.retries, p.completed,
       CASE 
           WHEN p.level BETWEEN 1 AND 3 THEN 0
           WHEN p.level BETWEEN 4 AND 6 THEN 1
           WHEN p.level BETWEEN 7 AND 9 THEN 2
           WHEN p.level BETWEEN 10 AND 12 THEN 3
           WHEN p.level BETWEEN 13 AND 15 THEN 4
           WHEN p.level BETWEEN 16 AND 18 THEN 5
           WHEN p.level BETWEEN 19 AND 21 THEN 6
           WHEN p.level BETWEEN 22 AND 24 THEN 7
           WHEN p.level BETWEEN 25 AND 27 THEN 8
           WHEN p.level BETWEEN 28 AND 30 THEN 9
       END AS category,
       i.score AS iq_score
FROM performance p
LEFT JOIN iq_scores i ON p.username = i.username AND i.test_type = 'baseline'
"""
data = pd.read_sql_query(query, conn)
conn.close()

# Preprocess data
data = data.dropna()  # Drop rows with missing IQ scores for initial training
X = data[['level', 'mission', 'completion_time', 'errors', 'retries', 'completed', 'category']]
y = data['iq_score']

# Normalize features
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# Train Random Forest model
model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(X_scaled, y)

# Save the model and scaler
joblib.dump(model, 'iq_model.pkl')
joblib.dump(scaler, 'scaler.pkl')

print("Model trained and saved!")