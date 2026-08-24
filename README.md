# AI-Based Study Assistant

A beginner-friendly AI study web application for university students, built with **Flask**, **SQLite**, and the **Gemini API**.

---

## ✦ Features

- 🤖 AI Tutor — instant Q&A powered by Gemini
- 📝 Quiz Generator — auto-create practice questions from any topic or PDF
- 📇 Flashcards — automatically generate interactive flashcards
- 📅 Study Planner — personalised schedules based on your goals
- 📚 Note Summariser — paste lecture notes, get concise summaries
- 📈 Progress Tracker — visualise study sessions and quiz scores

---

## 🛠 Tech Stack

| Layer    | Technology          |
|----------|---------------------|
| Frontend | HTML, CSS, JavaScript |
| Backend  | Python 3 + Flask    |
| AI       | Google Gemini API   |
| Database | SQLite              |

---

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/your-username/ai-study-assistant.git
cd ai-study-assistant
```

### 2. Create a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env` and fill in your values:

```bash
# Already exists — just edit it:
# SECRET_KEY=...
# GEMINI_API_KEY=your-real-key-here
```

> **Get a free Gemini API key** at [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)

### 5. Run the application

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

---

## 📁 Project Structure

```
AI-Based Study Assistant/
├── app.py                # Flask application & routes
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables (not committed)
├── .gitignore
├── README.md
├── templates/
│   ├── base.html         # Shared layout
│   ├── index.html        # Home / landing page
│   ├── dashboard.html    # User dashboard (placeholder)
│   └── about.html        # About page
└── static/
    ├── css/style.css     # Global stylesheet
    ├── js/main.js        # Client-side JavaScript
    └── images/           # Image assets
```

---

## 🤝 Contributing

Pull requests are welcome! Please open an issue first to discuss what you'd like to change.

---

## 📄 License

MIT License — see `LICENSE` for details.
