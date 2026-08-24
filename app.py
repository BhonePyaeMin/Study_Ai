"""
AI-Based Study Assistant
A beginner-friendly AI study web app for university students.
Built with Flask, SQLite, and the Gemini API.
"""

import os
import sqlite3

import google.genai as genai
from google.genai import types as genai_types
from dotenv import load_dotenv
from flask import Flask, g, jsonify, render_template, request, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import pypdf
from datetime import date, timedelta

# ── Load environment variables from .env ────────────────────────────────────
load_dotenv()

# ── App factory ─────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super-secret-study-key")

DATABASE = os.getenv("DATABASE_URL", "study_assistant.db")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# ── Gemini AI initialisation ─────────────────────────────────────────────────
_GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
_PLACEHOLDER = "your-gemini-api-key-here"
_gemini_model = None          # kept server-side; never sent to client


def _init_gemini() -> bool:
    """
    Configure the Gemini client using the key from .env.
    Returns True if successful, False otherwise.
    The API key is read once at startup and is NEVER exposed to the frontend.
    """
    global _gemini_model

    if not _GEMINI_KEY or _GEMINI_KEY == _PLACEHOLDER:
        print(
            "[StudyAI] [WARN] Gemini API key not configured. "
            "Set GEMINI_API_KEY in your .env file."
        )
        return False

    try:
        client = genai.Client(api_key=_GEMINI_KEY)
        _gemini_model = client
        print("[StudyAI] [OK] Gemini API ready (model: gemini-2.5-flash)")
        return True
    except Exception as exc:
        print(f"[StudyAI] [ERR] Gemini initialisation failed: {exc}")
        return False


_init_gemini()


# ── Database helpers ─────────────────────────────────────────────────────────
def get_db():
    """Open a per-request SQLite connection."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create database tables if they don't exist yet."""
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS study_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            task TEXT NOT NULL,
            due_date DATE NOT NULL,
            priority TEXT NOT NULL,
            completed BOOLEAN NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS quiz_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            topic TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            score INTEGER NOT NULL,
            total_questions INTEGER NOT NULL,
            percentage INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            original_text TEXT NOT NULL,
            summary_text TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS flashcard_decks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            cards_json TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """
    )
    db.commit()


# ── Page routes ──────────────────────────────────────────────────────────────
@app.route("/")
def index():
    """Landing / home page."""
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        
        if not username or not password:
            flash("Username and password are required.", "error")
            return redirect(url_for("register"))
            
        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, generate_password_hash(password))
            )
            db.commit()
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username already exists.", "error")
            return redirect(url_for("register"))
            
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))
            
        flash("Invalid username or password.", "error")
        return redirect(url_for("login"))
        
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    """User dashboard."""
    db = get_db()
    
    results = db.execute(
        "SELECT topic, difficulty, score, total_questions, percentage, created_at FROM quiz_results WHERE user_id = ? ORDER BY created_at ASC",
        (session["user_id"],)
    ).fetchall()
    
    quizzes = [dict(r) for r in results]
    total_quizzes = len(quizzes)
    avg_score = sum(q['percentage'] for q in quizzes) // total_quizzes if total_quizzes > 0 else 0
    recent_activity = sorted(quizzes, key=lambda x: x['created_at'], reverse=True)[:5]

    # Tasks Completed
    tasks_completed = db.execute(
        "SELECT COUNT(*) as count FROM study_tasks WHERE user_id = ? AND completed = 1",
        (session["user_id"],)
    ).fetchone()["count"]
    
    # Calculate Overall Progress
    total_tasks = db.execute(
        "SELECT COUNT(*) as count FROM study_tasks WHERE user_id = ?",
        (session["user_id"],)
    ).fetchone()["count"]
    overall_progress = int((tasks_completed / total_tasks * 100)) if total_tasks > 0 else 0

    # Activity calculation for Chart and Streak
    activity_query = """
        SELECT DATE(created_at) as act_date FROM quiz_results WHERE user_id = ?
        UNION SELECT DATE(created_at) as act_date FROM study_tasks WHERE user_id = ? AND completed = 1
        UNION SELECT DATE(created_at) as act_date FROM notes WHERE user_id = ?
        UNION SELECT DATE(created_at) as act_date FROM flashcard_decks WHERE user_id = ?
    """
    uid = session["user_id"]
    activities = db.execute(activity_query, (uid, uid, uid, uid)).fetchall()
    active_dates = sorted(list(set([a["act_date"] for a in activities])))

    # Calculate streak
    today = date.today()
    streak = 0
    curr_date = today
    while curr_date.isoformat() in active_dates:
        streak += 1
        curr_date -= timedelta(days=1)
    
    # Keep streak alive if they did something yesterday but not yet today
    if streak == 0:
        curr_date = today - timedelta(days=1)
        while curr_date.isoformat() in active_dates:
            streak += 1
            curr_date -= timedelta(days=1)

    # Calculate weekly activity (last 5 days)
    weekly_activity = []
    max_count = 0
    for i in range(4, -1, -1):
        d = today - timedelta(days=i)
        d_str = d.isoformat()
        
        q_count = db.execute("SELECT COUNT(*) as count FROM quiz_results WHERE user_id = ? AND DATE(created_at) = ?", (uid, d_str)).fetchone()["count"]
        t_count = db.execute("SELECT COUNT(*) as count FROM study_tasks WHERE user_id = ? AND completed = 1 AND DATE(created_at) = ?", (uid, d_str)).fetchone()["count"]
        
        day_total = q_count + t_count
        if day_total > max_count:
            max_count = day_total
            
        weekly_activity.append({
            'label': d.strftime('%a'),
            'count': day_total
        })
        
    for day in weekly_activity:
        day['percentage'] = (day['count'] / max_count * 100) if max_count > 0 else 0

    return render_template(
        "dashboard.html", 
        total_quizzes=total_quizzes, 
        avg_score=avg_score,
        quizzes=quizzes,
        recent_activity=recent_activity,
        tasks_completed=tasks_completed,
        overall_progress=overall_progress,
        streak=streak,
        weekly_activity=weekly_activity,
        current_date=today.strftime("%A, %d %B %Y")
    )


@app.route("/about")
def about():
    """About page."""
    return render_template("about.html")


@app.route("/notes")
@login_required
def notes():
    """Study Notes page."""
    return render_template("notes.html")


@app.route("/quiz")
@login_required
def quiz():
    """AI Quiz Generator page."""
    return render_template("quiz.html")


@app.route("/flashcards")
@login_required
def flashcards():
    """AI Flashcards Generator page."""
    return render_template("flashcards.html")

@app.route("/settings")
@login_required
def settings():
    """Application settings page."""
    return render_template("settings.html")


@app.route("/planner")
@login_required
def planner():
    """Study Planner page."""
    return render_template("planner.html")


@app.route("/tutor")
@login_required
def tutor():
    """
    AI Tutor page for direct Q&A.
    Passes api_ready flag to the template.
    """
    return render_template("tutor.html", api_ready=(_gemini_model is not None))


# ── API endpoints ─────────────────────────────────────────────────────────────
@app.route("/api/health")
def health():
    """Health-check endpoint — also reports Gemini status without the key."""
    return jsonify({
        "status": "ok",
        "app": "AI-Based Study Assistant",
        "gemini_ready": _gemini_model is not None,
        "model": "gemini-2.5-flash" if _gemini_model else None,
    })


@app.route("/api/ask", methods=["POST"])
@login_required
def api_ask():
    """
    Send a question to Gemini and return the AI answer as JSON.
    """
    if not request.is_json:
        return jsonify({"success": False, "error": "Request body must be JSON."}), 400

    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()

    if not question:
        return jsonify({"success": False, "error": "Question cannot be empty."}), 400

    MAX_LEN = 2_000
    if len(question) > MAX_LEN:
        return jsonify({
            "success": False,
            "error": f"Question is too long ({len(question):,} chars). Maximum is {MAX_LEN:,} characters.",
        }), 400

    if _gemini_model is None:
        return jsonify({
            "success": False,
            "error": "Gemini API is not configured. Please add a valid GEMINI_API_KEY to your .env file and restart the server.",
        }), 503

    try:
        response = _gemini_model.models.generate_content(
            model="gemini-2.5-flash",
            contents=question,
        )
        return jsonify({
            "success": True,
            "answer": response.text,
            "model": "gemini-2.5-flash",
        })

    except Exception as exc:
        err_upper = str(exc).upper()
        print(f"[StudyAI] Gemini error on /api/ask -- {exc}")
        if any(k in err_upper for k in ("API_KEY", "INVALID", "PERMISSION", "UNAUTHENTICATED")):
            return jsonify({"success": False, "error": "Invalid API key."}), 401
        elif "429" in err_upper or "QUOTA" in err_upper:
            return jsonify({"success": False, "error": "Rate limit exceeded. Please try again later."}), 429
        elif "SAFETY" in err_upper or "BLOCKED" in err_upper:
            return jsonify({"success": False, "error": "The response was blocked by safety settings."}), 422
        elif "TIMEOUT" in err_upper:
            return jsonify({"success": False, "error": "The request timed out. Please try again."}), 504
        return jsonify({"success": False, "error": "An unexpected error occurred while contacting the AI."}), 500


@app.route("/api/notes", methods=["POST"])
@login_required
def api_notes():
    """
    Handle actions for the Study Notes feature.
    Request JSON: { "text": "...", "action": "summarize" }
    """
    if not request.is_json:
        return jsonify({"success": False, "error": "Request body must be JSON."}), 400

    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    action = data.get("action", "").strip()

    if not text:
        return jsonify({"success": False, "error": "Study material cannot be empty."}), 400

    if len(text) > 10_000:
        return jsonify({
            "success": False,
            "error": "Study material is too long. Maximum is 10,000 characters.",
        }), 400

    if _gemini_model is None:
        return jsonify({"success": False, "error": "Gemini API is not configured."}), 503

    # Define the prompts for each action
    prompts = {
        "summarize": "Summarize the following study material clearly and concisely:\n\n{text}",
        "key_points": "Extract the most important key points from the following study material as a bulleted list:\n\n{text}",
        "explain": "Explain the following study material simply, as if you were teaching a beginner, using analogies if helpful:\n\n{text}",
        "quiz": "Generate a short 3-question multiple-choice quiz based on the following study material. Provide the answers at the end:\n\n{text}",
        "flashcards": "Create 5 study flashcards based on the following material. Format them clearly as 'Front: [Question/Term]' and 'Back: [Answer/Definition]':\n\n{text}"
    }

    if action not in prompts:
        return jsonify({"success": False, "error": "Invalid action requested."}), 400

    prompt = prompts[action].format(text=text)

    try:
        response = _gemini_model.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return jsonify({
            "success": True,
            "answer": response.text,
        })
    except Exception as exc:
        err_upper = str(exc).upper()
        print(f"[StudyAI] Gemini error on /api/notes -- {exc}")
        if any(k in err_upper for k in ("API_KEY", "INVALID", "PERMISSION", "UNAUTHENTICATED")):
            return jsonify({"success": False, "error": "API Key is invalid or unauthorized."}), 401
        elif "429" in err_upper or "QUOTA" in err_upper:
            return jsonify({"success": False, "error": "Rate limit exceeded. Please try again later."}), 429
        elif "SAFETY" in err_upper or "BLOCKED" in err_upper:
            return jsonify({"success": False, "error": "The response was blocked by safety settings."}), 422
        elif "TIMEOUT" in err_upper:
            return jsonify({"success": False, "error": "The request timed out. Please try again."}), 504
        return jsonify({"success": False, "error": "An unexpected error occurred while contacting the AI."}), 500


@app.route("/api/quiz/generate", methods=["POST"])
@login_required
def api_quiz_generate():
    """
    Generate a structured multiple-choice quiz using Gemini.
    """
    if request.is_json:
        data = request.get_json(silent=True) or {}
        topic = data.get("topic", "").strip()
        material = data.get("material", "").strip()
        difficulty = data.get("difficulty", "Medium").strip()
        count_val = data.get("count", 5)
    else:
        topic = request.form.get("topic", "").strip()
        material = request.form.get("material", "").strip()
        difficulty = request.form.get("difficulty", "Medium").strip()
        count_val = request.form.get("count", 5)

    if "file" in request.files:
        file = request.files["file"]
        if file and file.filename.endswith(".pdf"):
            try:
                reader = pypdf.PdfReader(file)
                pdf_text = []
                for page in reader.pages:
                    pdf_text.append(page.extract_text() or "")
                extracted = "\n".join(pdf_text).strip()
                if extracted:
                    material = (material + "\n\n--- Extracted PDF Content ---\n" + extracted).strip()
            except Exception as e:
                print(f"[StudyAI] PDF error: {e}")
                return jsonify({"success": False, "error": "Failed to read the PDF file."}), 400
    
    try:
        count = int(count_val)
    except ValueError:
        count = 5

    if not topic and not material:
        return jsonify({"success": False, "error": "Please provide a topic or study material."}), 400

    if count not in [5, 10, 15]:
        return jsonify({"success": False, "error": "Invalid question count."}), 400

    if len(topic) + len(material) > 10_000:
        return jsonify({"success": False, "error": "Input text is too long."}), 400

    if _gemini_model is None:
        return jsonify({"success": False, "error": "Gemini API is not configured."}), 503

    prompt = f"Generate a {difficulty} difficulty multiple-choice quiz with exactly {count} questions.\n"
    if topic:
        prompt += f"Topic: {topic}\n"
    if material:
        prompt += f"Study Material: {material}\n"

    prompt += """
You MUST return a raw JSON array of objects. Do not wrap in markdown code blocks.
Each object must have exactly these keys:
- "question" (string)
- "options" (array of exactly 4 strings)
- "correct_index" (integer 0, 1, 2, or 3 representing the correct option)
- "explanation" (string explaining why the answer is correct)
"""

    try:
        response = _gemini_model.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        import json
        quiz_data = json.loads(response.text)
        if not isinstance(quiz_data, list):
            quiz_data = [quiz_data]
        return jsonify({"success": True, "quiz": quiz_data})

    except json.JSONDecodeError:
        print(f"[StudyAI] Failed to parse JSON from Gemini: {response.text[:200]}")
        return jsonify({"success": False, "error": "AI generated invalid data format."}), 500
    except Exception as exc:
        err_upper = str(exc).upper()
        print(f"[StudyAI] Gemini error on /api/quiz/generate -- {exc}")
        if any(k in err_upper for k in ("API_KEY", "INVALID", "PERMISSION", "UNAUTHENTICATED")):
            return jsonify({"success": False, "error": "API Key is invalid or unauthorized."}), 401
        elif "429" in err_upper or "QUOTA" in err_upper:
            return jsonify({"success": False, "error": "Rate limit exceeded."}), 429
        elif "SAFETY" in err_upper or "BLOCKED" in err_upper:
            return jsonify({"success": False, "error": "Response blocked by safety filters."}), 422
        elif "TIMEOUT" in err_upper:
            return jsonify({"success": False, "error": "Request timed out."}), 504
        return jsonify({"success": False, "error": "An unexpected error occurred."}), 500

@app.route("/api/quiz/save_result", methods=["POST"])
@login_required
def api_quiz_save_result():
    if not request.is_json:
        return jsonify({"success": False, "error": "Request must be JSON"}), 400
    
    data = request.get_json()
    topic = data.get("topic", "General").strip()
    difficulty = data.get("difficulty", "Medium").strip()
    score = int(data.get("score", 0))
    total_questions = int(data.get("total_questions", 0))
    percentage = int(data.get("percentage", 0))

    db = get_db()
    db.execute(
        "INSERT INTO quiz_results (user_id, topic, difficulty, score, total_questions, percentage) VALUES (?, ?, ?, ?, ?, ?)",
        (session["user_id"], topic, difficulty, score, total_questions, percentage)
    )
    db.commit()
    return jsonify({"success": True}), 201


@app.route("/api/flashcards/generate", methods=["POST"])
@login_required
def api_flashcards_generate():
    """
    Generate structured flashcards using Gemini.
    Request JSON: { "topic": "...", "material": "...", "count": 5 }
    """
    if not request.is_json:
        return jsonify({"success": False, "error": "Request body must be JSON."}), 400

    data = request.get_json(silent=True) or {}
    topic = data.get("topic", "").strip()
    material = data.get("material", "").strip()
    
    try:
        count = int(data.get("count", 5))
    except ValueError:
        count = 5

    if not topic and not material:
        return jsonify({"success": False, "error": "Please provide a topic or study material."}), 400

    if count not in [5, 10, 15, 20]:
        return jsonify({"success": False, "error": "Invalid flashcard count."}), 400

    if len(topic) + len(material) > 10_000:
        return jsonify({"success": False, "error": "Input text is too long."}), 400

    if _gemini_model is None:
        return jsonify({"success": False, "error": "Gemini API is not configured."}), 503

    prompt = f"Create exactly {count} study flashcards.\n"
    if topic:
        prompt += f"Topic: {topic}\n"
    if material:
        prompt += f"Study Material: {material}\n"

    prompt += """
You MUST return a raw JSON array of objects. Do not wrap in markdown code blocks.
Each object must have exactly these keys:
- "front" (string - the question, concept, or term)
- "back" (string - the detailed answer or explanation)
"""

    try:
        response = _gemini_model.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        import json
        cards_data = json.loads(response.text)
        if not isinstance(cards_data, list):
            cards_data = [cards_data]
        return jsonify({"success": True, "flashcards": cards_data})

    except json.JSONDecodeError:
        print(f"[StudyAI] Failed to parse JSON from Gemini: {response.text[:200]}")
        return jsonify({"success": False, "error": "AI generated invalid data format."}), 500
    except Exception as exc:
        err_upper = str(exc).upper()
        print(f"[StudyAI] Gemini error on /api/flashcards/generate -- {exc}")
        if any(k in err_upper for k in ("API_KEY", "INVALID", "PERMISSION", "UNAUTHENTICATED")):
            return jsonify({"success": False, "error": "API Key is invalid or unauthorized."}), 401
        elif "429" in err_upper or "QUOTA" in err_upper:
            return jsonify({"success": False, "error": "Rate limit exceeded."}), 429
        elif "SAFETY" in err_upper or "BLOCKED" in err_upper:
            return jsonify({"success": False, "error": "Response blocked by safety filters."}), 422
        elif "TIMEOUT" in err_upper:
            return jsonify({"success": False, "error": "Request timed out."}), 504
        return jsonify({"success": False, "error": "An unexpected error occurred."}), 500


# ── Study Planner API ────────────────────────────────────────────────────────
@app.route("/api/tasks", methods=["GET"])
@login_required
def get_tasks():
    db = get_db()
    # Order by due date, then priority (High > Medium > Low) using a CASE statement
    tasks = db.execute('''
        SELECT id, subject, task, due_date, priority, completed, created_at 
        FROM study_tasks 
        WHERE user_id = ?
        ORDER BY completed ASC, due_date ASC, 
        CASE priority 
            WHEN 'High' THEN 1 
            WHEN 'Medium' THEN 2 
            WHEN 'Low' THEN 3 
            ELSE 4 
        END
    ''', (session["user_id"],)).fetchall()
    
    return jsonify({
        "success": True, 
        "tasks": [dict(t) for t in tasks]
    })

@app.route("/api/tasks", methods=["POST"])
@login_required
def create_task():
    if not request.is_json:
        return jsonify({"success": False, "error": "Request must be JSON"}), 400
    
    data = request.get_json()
    subject = data.get("subject", "").strip()
    task = data.get("task", "").strip()
    due_date = data.get("due_date", "").strip()
    priority = data.get("priority", "Medium").strip()

    if not subject or not task or not due_date:
        return jsonify({"success": False, "error": "Missing required fields"}), 400

    db = get_db()
    cursor = db.execute(
        "INSERT INTO study_tasks (user_id, subject, task, due_date, priority) VALUES (?, ?, ?, ?, ?)",
        (session["user_id"], subject, task, due_date, priority)
    )
    db.commit()
    return jsonify({"success": True, "id": cursor.lastrowid}), 201

@app.route("/api/tasks/<int:task_id>", methods=["PUT"])
@login_required
def update_task(task_id):
    if not request.is_json:
        return jsonify({"success": False, "error": "Request must be JSON"}), 400
    
    data = request.get_json()
    completed = 1 if data.get("completed") else 0

    db = get_db()
    db.execute("UPDATE study_tasks SET completed = ? WHERE id = ? AND user_id = ?", (completed, task_id, session["user_id"]))
    db.commit()
    return jsonify({"success": True})

@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
@login_required
def delete_task(task_id):
    db = get_db()
    db.execute("DELETE FROM study_tasks WHERE id = ? AND user_id = ?", (task_id, session["user_id"]))
    db.commit()
    return jsonify({"success": True})

# ── Notes API ──────────────────────────────────────────────────────────────
@app.route("/api/notes/list", methods=["GET"])
@login_required
def api_notes_list():
    db = get_db()
    notes = db.execute(
        "SELECT id, title, created_at FROM notes WHERE user_id = ? ORDER BY created_at DESC",
        (session["user_id"],)
    ).fetchall()
    return jsonify({"success": True, "notes": [dict(n) for n in notes]})

@app.route("/api/notes/<int:note_id>", methods=["GET"])
@login_required
def api_notes_get(note_id):
    db = get_db()
    note = db.execute(
        "SELECT * FROM notes WHERE id = ? AND user_id = ?",
        (note_id, session["user_id"])
    ).fetchone()
    if not note:
        return jsonify({"success": False, "error": "Note not found"}), 404
    return jsonify({"success": True, "note": dict(note)})

@app.route("/api/notes/save", methods=["POST"])
@login_required
def api_notes_save():
    if not request.is_json:
        return jsonify({"success": False, "error": "Request must be JSON"}), 400
    
    data = request.get_json()
    title = data.get("title", "Untitled Note").strip()
    original_text = data.get("original_text", "").strip()
    summary_text = data.get("summary_text", "").strip()

    if not original_text or not summary_text:
        return jsonify({"success": False, "error": "Missing content"}), 400

    db = get_db()
    cursor = db.execute(
        "INSERT INTO notes (user_id, title, original_text, summary_text) VALUES (?, ?, ?, ?)",
        (session["user_id"], title, original_text, summary_text)
    )
    db.commit()
    return jsonify({"success": True, "id": cursor.lastrowid}), 201

@app.route("/api/notes/<int:note_id>", methods=["DELETE"])
@login_required
def api_notes_delete(note_id):
    db = get_db()
    db.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, session["user_id"]))
    db.commit()
    return jsonify({"success": True})

# ── Flashcards API ─────────────────────────────────────────────────────────
@app.route("/api/flashcards/list", methods=["GET"])
@login_required
def api_flashcards_list():
    db = get_db()
    decks = db.execute(
        "SELECT id, title, created_at FROM flashcard_decks WHERE user_id = ? ORDER BY created_at DESC",
        (session["user_id"],)
    ).fetchall()
    return jsonify({"success": True, "decks": [dict(d) for d in decks]})

@app.route("/api/flashcards/<int:deck_id>", methods=["GET"])
@login_required
def api_flashcards_get(deck_id):
    db = get_db()
    deck = db.execute(
        "SELECT * FROM flashcard_decks WHERE id = ? AND user_id = ?",
        (deck_id, session["user_id"])
    ).fetchone()
    if not deck:
        return jsonify({"success": False, "error": "Deck not found"}), 404
    return jsonify({"success": True, "deck": dict(deck)})

@app.route("/api/flashcards/save", methods=["POST"])
@login_required
def api_flashcards_save():
    if not request.is_json:
        return jsonify({"success": False, "error": "Request must be JSON"}), 400
    
    import json
    data = request.get_json()
    title = data.get("title", "Untitled Deck").strip()
    cards = data.get("cards", [])

    if not cards:
        return jsonify({"success": False, "error": "Missing cards"}), 400

    db = get_db()
    cursor = db.execute(
        "INSERT INTO flashcard_decks (user_id, title, cards_json) VALUES (?, ?, ?)",
        (session["user_id"], title, json.dumps(cards))
    )
    db.commit()
    return jsonify({"success": True, "id": cursor.lastrowid}), 201

@app.route("/api/flashcards/<int:deck_id>", methods=["DELETE"])
@login_required
def api_flashcards_delete(deck_id):
    db = get_db()
    db.execute("DELETE FROM flashcard_decks WHERE id = ? AND user_id = ?", (deck_id, session["user_id"]))
    db.commit()
    return jsonify({"success": True})

@app.route("/api/clear-data", methods=["POST"])
@login_required
def clear_data():
    db = get_db()
    db.execute("DELETE FROM study_tasks WHERE user_id = ?", (session["user_id"],))
    db.execute("DELETE FROM quiz_results WHERE user_id = ?", (session["user_id"],))
    db.execute("DELETE FROM notes WHERE user_id = ?", (session["user_id"],))
    db.execute("DELETE FROM flashcard_decks WHERE user_id = ?", (session["user_id"],))
    db.commit()
    return jsonify({"success": True})

# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
