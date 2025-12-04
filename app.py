import matplotlib
matplotlib.use('Agg')  # Use non-GUI backend suitable for web/server

import pandas as pd
import sqlite3
from flask import Flask, render_template, request
import matplotlib.pyplot as plt
import io
import base64

app = Flask(__name__)

# --- Step 1: Load CSV and insert into SQLite ---
df = pd.read_csv("student_commute_fake.csv")

# Convert numeric columns
numeric_cols = ['distance_km', 'travel_time_min', 'travel_cost_rs', 'satisfaction_rating']
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors='coerce')

# Connect to SQLite
conn = sqlite3.connect("commute_project.db")
cursor = conn.cursor()

# Create table
cursor.execute("""
CREATE TABLE IF NOT EXISTS student_commute (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT,
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

# Clear old data
cursor.execute("DELETE FROM student_commute;")
conn.commit()

# Insert CSV data
df = df[['student_id','gender','branch','year_of_study','area',
         'distance_km','mode_of_transport','travel_time_min',
         'travel_cost_rs','monthly_pass','satisfaction_rating']]
df.to_sql("student_commute", conn, if_exists="append", index=False)

conn.close()

# --- Step 2: Flask route ---
@app.route("/", methods=["GET", "POST"])
def index():
    conn = sqlite3.connect("commute_project.db")
    conn.row_factory = sqlite3.Row  # for dict-like rows

    # Fetch unique filters
    years = ['All'] + [row['year_of_study'] for row in conn.execute("SELECT DISTINCT year_of_study FROM student_commute").fetchall()]
    modes = ['All'] + [row['mode_of_transport'] for row in conn.execute("SELECT DISTINCT mode_of_transport FROM student_commute").fetchall()]

    selected_year = request.form.get("year_of_study", "All")
    selected_mode = request.form.get("mode_of_transport", "All")

    # Build SQL query
    query = "SELECT * FROM student_commute WHERE 1=1"
    if selected_year != "All":
        query += f" AND year_of_study='{selected_year}'"
    if selected_mode != "All":
        query += f" AND mode_of_transport='{selected_mode}'"

    df_filtered = pd.read_sql(query, conn)

    # --- Safely drop 'id' if exists ---
    df_filtered = df_filtered.drop(columns=['id'], errors='ignore')

    df_filtered_records = df_filtered.to_dict(orient='records') if not df_filtered.empty else []

    # Average stats by mode for filtered data
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

    # Chart: Overall students per transport mode
    chart_query = "SELECT mode_of_transport, COUNT(*) AS total FROM student_commute GROUP BY mode_of_transport"
    chart_df = pd.read_sql(chart_query, conn)
    fig, ax = plt.subplots()
    ax.bar(chart_df['mode_of_transport'], chart_df['total'], color='#3498db')
    ax.set_xlabel("Transport Mode")
    ax.set_ylabel("Number of Students")
    ax.set_title("Overall Students per Transport Mode")
    plt.xticks(rotation=45)

    # Convert plot to PNG image for HTML
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

if __name__ == "__main__":
    app.run(debug=True)
