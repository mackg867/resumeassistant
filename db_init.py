from app import app, init_db  # Import both 'app' and 'init_db' from 'app.py'

# Initialize the database
init_db()

# Now you can run the Flask app if needed (optional, depending on your need)
if __name__ == "__main__":
    app.run(debug=True)
