import matplotlib
matplotlib.use('Agg')  # Non-GUI backend for web/server

import pandas as pd
import sqlite3
from flask import Flask, render_template, request, redirect, url_for
import matplotlib.pyplot as plt
import io
import base64
import os

app = Flask(__name__)

CSV_FILE = "student_commute_fake.csv"
DB_FILE = "commute_project.db"

# --- Step 1: Load CSV and insert into SQLite ---
df = pd.read_csv(CSV_FILE)

# Convert numeric columns
numeric_cols = ['distance_km', 'travel_time_min', 'travel_cost_rs', 'satisfaction_rating']
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors='coerce')

# Connect to SQLite
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# Create table with UNIQUE student_id
cursor.execute("""
CREATE TABLE IF NOT EXISTS student_commute (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT UNIQUE,
    gender TEXT,
    branch TEXT,
    year_of_study TEXT,
    area TEXT,
    distance_km REAL,
    mode_of_transport TEXT,
    travel_time_min INTEGER,
    travel_cost_rs REAL,
    monthly_pass TEXT,
    satisfaction_rating INTEGER
);
""")
conn.commit()

# Insert CSV data safely (ignore duplicates)
df = df[['student_id','gender','branch','year_of_study','area',
         'distance_km','mode_of_transport','travel_time_min',
         'travel_cost_rs','monthly_pass','satisfaction_rating']]
df.to_sql("student_commute", conn, if_exists="append", index=False, method='multi')

conn.close()

# --- Step 2: Flask routes ---

@app.route("/", methods=["GET", "POST"])
def index():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    # Fetch unique filters
    years = ['All'] + [row['year_of_study'] for row in conn.execute(
        "SELECT DISTINCT year_of_study FROM student_commute").fetchall()]
    modes = ['All'] + [row['mode_of_transport'] for row in conn.execute(
        "SELECT DISTINCT mode_of_transport FROM student_commute").fetchall()]

    selected_year = request.form.get("year_of_study", "All")
    selected_mode = request.form.get("mode_of_transport", "All")

    # Filtered table
    query = "SELECT * FROM student_commute WHERE 1=1"
    if selected_year != "All":
        query += f" AND year_of_study='{selected_year}'"
    if selected_mode != "All":
        query += f" AND mode_of_transport='{selected_mode}'"
    df_filtered = pd.read_sql(query, conn).drop(columns=['id'], errors='ignore')
    df_filtered_records = df_filtered.to_dict(orient='records') if not df_filtered.empty else []

    # Average stats by mode
    stats_records = []
    if not df_filtered.empty:
        stats_query = """
        SELECT mode_of_transport,
               AVG(travel_time_min) AS avg_time,
               AVG(travel_cost_rs) AS avg_cost,
               AVG(satisfaction_rating) AS avg_rating
        FROM student_commute
        WHERE 1=1
        """
        if selected_year != "All":
            stats_query += f" AND year_of_study='{selected_year}'"
        if selected_mode != "All":
            stats_query += f" AND mode_of_transport='{selected_mode}'"
        stats_query += " GROUP BY mode_of_transport"
        stats_df = pd.read_sql(stats_query, conn)
        stats_records = stats_df.to_dict(orient='records')

    # Dynamic chart
    chart_query = "SELECT mode_of_transport, COUNT(*) AS total FROM student_commute WHERE 1=1"
    if selected_year != "All":
        chart_query += f" AND year_of_study='{selected_year}'"
    if selected_mode != "All":
        chart_query += f" AND mode_of_transport='{selected_mode}'"
    chart_query += " GROUP BY mode_of_transport"
    chart_df = pd.read_sql(chart_query, conn)

    fig, ax = plt.subplots()
    ax.bar(chart_df['mode_of_transport'], chart_df['total'], color='#3498db')
    ax.set_xlabel("Transport Mode")
    ax.set_ylabel("Number of Students")
    ax.set_title("Students per Transport Mode")
    plt.xticks(rotation=45)
    img = io.BytesIO()
    plt.tight_layout()
    fig.savefig(img, format='png')
    img.seek(0)
    chart = base64.b64encode(img.getvalue()).decode()
    plt.close(fig)

    conn.close()
    return render_template(
        "index.html",
        df_filtered=df_filtered_records,
        stats=stats_records,
        chart=chart,
        years=years,
        modes=modes,
        selected_year=selected_year,
        selected_mode=selected_mode
    )

# --- Add Record ---
@app.route("/add", methods=["POST"])
def add_record():
    data = request.form.to_dict()
    new_student_id = data.get("student_id")

    # Load existing CSV to prevent duplicates
    if os.path.exists(CSV_FILE):
        csv_df = pd.read_csv(CSV_FILE)
        if new_student_id in csv_df['student_id'].values:
            return redirect(url_for('index'))  # Already exists

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO student_commute
            (student_id, gender, branch, year_of_study, area, distance_km,
             mode_of_transport, travel_time_min, travel_cost_rs, monthly_pass, satisfaction_rating)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            new_student_id,
            data.get("gender"),
            data.get("branch"),
            data.get("year_of_study"),
            data.get("area"),
            float(data.get("distance_km", 0)),
            data.get("mode_of_transport"),
            int(data.get("travel_time_min", 0)),
            float(data.get("travel_cost_rs", 0)),
            data.get("monthly_pass"),
            int(data.get("satisfaction_rating", 0))
        ))
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # duplicate student_id, ignore
    conn.close()

    # Append to CSV if not duplicate
    if not os.path.exists(CSV_FILE):
        csv_df = pd.DataFrame(columns=['student_id','gender','branch','year_of_study','area',
                                       'distance_km','mode_of_transport','travel_time_min',
                                       'travel_cost_rs','monthly_pass','satisfaction_rating'])
    else:
        csv_df = pd.read_csv(CSV_FILE)

    if new_student_id not in csv_df['student_id'].values:
        new_row = pd.DataFrame([{
            'student_id': data.get("student_id"),
            'gender': data.get("gender"),
            'branch': data.get("branch"),
            'year_of_study': data.get("year_of_study"),
            'area': data.get("area"),
            'distance_km': float(data.get("distance_km", 0)),
            'mode_of_transport': data.get("mode_of_transport"),
            'travel_time_min': int(data.get("travel_time_min", 0)),
            'travel_cost_rs': float(data.get("travel_cost_rs", 0)),
            'monthly_pass': data.get("monthly_pass"),
            'satisfaction_rating': int(data.get("satisfaction_rating", 0))
        }])
        csv_df = pd.concat([csv_df, new_row], ignore_index=True)
        csv_df.to_csv(CSV_FILE, index=False)

    return redirect(url_for('index'))

# --- Delete Record ---
@app.route("/delete", methods=["POST"])
def delete_record():
    student_id = request.form.get("student_id")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM student_commute WHERE student_id=?", (student_id,))
    conn.commit()
    conn.close()

    # Remove from CSV as well
    if os.path.exists(CSV_FILE):
        csv_df = pd.read_csv(CSV_FILE)
        csv_df = csv_df[csv_df['student_id'] != student_id]
        csv_df.to_csv(CSV_FILE, index=False)

    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(debug=True)
