CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resume_filename TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    location TEXT NOT NULL,
    education_level TEXT NOT NULL,
    enrollment_status TEXT NOT NULL,
    openai_score REAL
);
