import os
import glob
import uuid
import engine
import mysql.connector
from mysql.connector import Error
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.utils import secure_filename
from PIL import Image  # For validating image uploads

app = Flask(__name__)
app.secret_key = "edumorph_secret"

# ---------------- CONFIG ----------------
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('static/output/final_videos', exist_ok=True)  # Ensure output folder exists

# ---------------- DATABASE CONFIG ----------------
db_config = {
    "host": "localhost",
    "user": "root",
    "password": "tamil",
    "database": "edumorph"
}

def get_db_connection():
    """Returns a new MySQL connection."""
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except Error as e:
        print(f"Database connection error: {e}")
        return None

# ================= FRONTEND =================

@app.route("/")
def landing():
    return render_template("first.html")

@app.route("/owl")
def owl():
    return render_template("owl_animation.html")

@app.route("/home")
def dashboard():
    if "user_id" not in session:
        return redirect("/")
    return render_template("home1.html")

@app.context_processor
def inject_user():
    if "user_id" not in session:
        return dict(user=None)

    conn = get_db_connection()
    if not conn:
        return dict(user=None)

    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, fname, lname, email
        FROM users1
        WHERE id = %s
    """, (session["user_id"],))

    user = cursor.fetchone()

    cursor.close()
    conn.close()

    return dict(user=user)

@app.route("/slider")
def slider():
    conn = get_db_connection()
    files = []
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM uploads")
            files = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

    uploaded_file = session.get("uploaded_file")
    video_file = session.pop("video", None)
    comic_file = session.pop("comic", None)
    flowchart_file = session.pop("flowchart", None)

    
    return render_template(
        "slider.html", 
        files=files, 
        uploaded_file=uploaded_file,
        video=video_file,
        comic=comic_file,
        flowchart=flowchart_file
    )
@app.route("/library")
def library():
    if "user_id" not in session:
        return redirect("/")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT id, title, file_type, file_size, created_at, file_path
        FROM user_library
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (session["user_id"],))

    library_items = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("library.html", library_items=library_items)



@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect("/")

    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500

    cursor = conn.cursor(dictionary=True)

    # ✅ Get user details from users1 table
    cursor.execute("""
        SELECT id, fname, lname, email
        FROM users1
        WHERE id = %s
    """, (session["user_id"],))
    user = cursor.fetchone()

    # ✅ Count total generated items (videos + comics + flowcharts)
    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM user_library
        WHERE user_id = %s
    """, (session["user_id"],))
    result = cursor.fetchone()
    total_generated = result["total"]

    cursor.close()
    conn.close()

    return render_template(
        "user-profile.html",
        user=user,
        total_generated=total_generated
    )
# -------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set!")

@app.route("/quiz")
def quiz():
    questions = engine.generate_quiz()

    # ✅ DEBUG: check in terminal
    print("DEBUG /quiz route questions:", questions)

    session["quiz_questions"] = questions
    return render_template("quiz.html", questions=questions)




# -------------------------
# Route to submit quiz answers
# -------------------------
@app.route("/submit_quiz", methods=["POST"])
def submit_quiz():
    questions = session.get("quiz_questions", [])
    score = 0

    for i, q in enumerate(questions):
        selected = request.form.get(f"q{i}")
        if selected == q["answer"]:
            score += 1

    return render_template("quiz.html", questions=questions, score=score)

# ================= AUTH =================

@app.route("/register", methods=["POST"])
def register():
    data = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Database connection failed"})

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users1 WHERE email=%s", (data['email'],))
        if cursor.fetchone():
            return jsonify({"success": False, "message": "User already exists"})

        cursor.execute(
            "INSERT INTO users1 (fname, lname, email, password) VALUES (%s, %s, %s, %s)",
            (data['firstname'], data['lastname'], data['email'], data['password'])
        )
        conn.commit()
        return jsonify({"success": True, "msg": "Registered Successfully"})
    except mysql.connector.Error as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        cursor.close()
        conn.close()

@app.route("/login", methods=["POST"])
def login():
    data = request.json

    if not data or "email" not in data or "password" not in data:
        return jsonify({"success": False, "message": "Missing email or password"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Database connection failed"}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM users1 WHERE email=%s AND password=%s",
            (data['email'], data['password'])
        )

        user = cursor.fetchone()

        if user:
            # ✅ STORE USER SESSION (VERY IMPORTANT)
            session["user_id"] = user["id"]
            session["user_email"] = user["email"]
            session["user_name"] = user["fname"]

            return jsonify({
                "success": True,
                "msg": "Login Success"
            })

        return jsonify({
            "success": False,
            "msg": "Invalid Credentials"
        }), 401

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

    finally:
        cursor.close()
        conn.close()

# ================= FRONTEND UPLOAD =================

@app.route("/home/upload", methods=["POST"])
def home_upload():

    file = request.files["file"]

    # Validate uploaded file is an image
    try:
        img = Image.open(file)
        img.verify()
    except Exception as e:
        return f"Uploaded file is not a valid image: {str(e)}", 400

    # Make filename safe and unique
    safe_filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4().hex}_{safe_filename}"

    # Save original file
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
    file.seek(0)
    file.save(filepath)

    # Process using engine with the actual uploaded file
    engine.process_file(filepath)

    # Store uploaded filename in Flask session
    session["uploaded_file"] = unique_filename

    # Redirect back to slider page
    return redirect(url_for("slider"))


# ================= BACKEND GENERATION =================

@app.route("/animate", methods=["POST"])
def animate():

    if "user_id" not in session:
        return redirect("/")

    video_id = uuid.uuid4().hex
    filename = f"final_{video_id}.mp4"

    out_path = os.path.join(
        "static",
        "output",
        "final_videos",
        filename
    )

    engine.run_animation(out_path)

    # Save into database
    conn = get_db_connection()
    cursor = conn.cursor()

    db_path = f"output/final_videos/{filename}"

    cursor.execute("""
        INSERT INTO user_library
        (user_id, title, file_type, file_size, file_path)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        session["user_id"],
        "Generated Animation",
        "MP4",
        "0",
        db_path
    ))

    conn.commit()
    cursor.close()
    conn.close()

    return render_template("slider.html", video_file=db_path)

@app.route("/comic", methods=["POST"])
def comic():

    if "user_id" not in session:
        return redirect("/")

    path = engine.run_comic()

    filename = os.path.basename(path)
    db_path = f"comic/{filename}"

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO user_library
        (user_id, title, file_type, file_size, file_path)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        session["user_id"],
        "Generated Comic",
        "PDF",
        "0",
        db_path
    ))

    conn.commit()
    cursor.close()
    conn.close()

    return render_template("slider.html", comic_file=db_path)
@app.route("/flowchart", methods=["POST"])
def flowchart():

    if "user_id" not in session:
        return redirect("/")

    path = engine.run_flowchart()

    filename = os.path.basename(path)
    db_path = f"flowchart/{filename}"

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO user_library
        (user_id, title, file_type, file_size, file_path)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        session["user_id"],
        "Generated Flowchart",
        "PNG",
        "0",
        db_path
    ))

    conn.commit()
    cursor.close()
    conn.close()

    return render_template("slider.html", flowchart_file=db_path)


# ================= RUN =================

if __name__ == "__main__":
    
    app.run(debug=True)
