import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, flash, url_for, session
from werkzeug.utils import secure_filename
import sqlite3
from flask import g
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import generate_blob_sas, BlobSasPermissions
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# Retrieve admin credentials from environment variables
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
account_key = os.getenv('ACCOUNT_KEY')


# Database connection
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect('app.db')
    return db

# Check if the uploaded file is of an allowed type
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'pdf', 'doc', 'docx'}

# Route for the form page
@app.route('/')
def upload_form():
    return render_template('upload.html')

@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Check if the entered credentials match the environment variables
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect('/admin')  # Redirect to the admin page after successful login
        else:
            error = 'Invalid username or password'
            return render_template('admin_login.html', error=error)

    return render_template('admin_login.html')

@app.route('/admin', methods=['GET'])
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect('/admin-login')

    # Get filter values from the GET request
    location = request.args.get('location')
    education_level = request.args.get('education_level')
    enrollment_status = request.args.get('enrollment_status')

    # Start building the SQL query
    query = "SELECT resume_filename, location, education_level, enrollment_status FROM submissions WHERE 1=1"
    params = []

    # Apply filters if they are provided
    if location:
        query += " AND location = ?"
        params.append(location)
    
    if education_level:
        query += " AND education_level = ?"
        params.append(education_level)
    
    if enrollment_status:
        query += " AND enrollment_status = ?"
        params.append(enrollment_status)

    # Execute the filtered query
    db = get_db()
    cursor = db.cursor()
    cursor.execute(query, params)
    submissions = cursor.fetchall()

    # Initialize Azure Blob Storage client
    blob_service_client = BlobServiceClient.from_connection_string(
        "DefaultEndpointsProtocol=https;AccountName=resumeuploads3568;AccountKey=YOUR_ACCOUNT_KEY_GOES_HERE!!!!!;EndpointSuffix=core.windows.net"
    )
    container_client = blob_service_client.get_container_client("resumes")

    submission_data = []

    # Check if each resume exists in Azure Blob Storage
    for submission in submissions:
        filename = submission[0]
        try:
            blob_client = container_client.get_blob_client(filename)
            blob_client.get_blob_properties()  # Check if the file exists

            # Generate a SAS token valid for 1 hour
            sas_token = generate_blob_sas(
                account_name="resumeuploads3568",
                container_name="resumes",
                blob_name=filename,
                account_key=account_key,  # Correctly load the account key
                permission=BlobSasPermissions(read=True),
                expiry=datetime.utcnow() + timedelta(hours=1)
            )

            # Construct the download link with the SAS token
            download_link = f"{blob_client.url}?{sas_token}"
            file_status = "Exists"
        except ResourceNotFoundError:
            file_status = "File Not Found"
            download_link = None

        submission_data.append({
            "filename": filename,
            "location": submission[1],
            "education_level": submission[2],
            "enrollment_status": submission[3],
            "file_status": file_status,
            "download_link": download_link
        })

    return render_template('admin.html', submissions=submission_data)

@app.route('/admin/delete/<filename>', methods=['POST'])
def delete_resume(filename):
    # Check if the admin is logged in
    if not session.get('admin_logged_in'):
        return redirect('/admin-login')

    # Initialize Azure Blob Storage client
    blob_service_client = BlobServiceClient.from_connection_string("DefaultEndpointsProtocol=https;AccountName=resumeuploads3568;AccountKey=YOUR_ACCOUNT_KEY_GOES_HERE!!!!!;EndpointSuffix=core.windows.net")
    container_client = blob_service_client.get_container_client("resumes")

    # Try to delete the blob (resume file) from Azure
    try:
        blob_client = container_client.get_blob_client(filename)
        blob_client.delete_blob()
    except ResourceNotFoundError:
        flash(f'Resume file "{filename}" not found in Blob Storage.')

    # Delete the corresponding entry from SQLite database
    db = get_db()
    cursor = db.cursor()
    cursor.execute('DELETE FROM submissions WHERE resume_filename = ?', (filename,))
    db.commit()

    flash(f'Resume "{filename}" and its data were successfully deleted.')
    return redirect('/admin')



@app.route('/admin')
def admin_view():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM submissions')
    submissions = cursor.fetchall()

    return render_template('admin.html', submissions=submissions)

@app.route('/logout')
def logout():
    # Clear the session when the admin logs out
    session.pop('admin_logged_in', None)
    return redirect('/admin-login')

# Route for handling the file upload
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'resume' not in request.files:
        flash('No file part')
        return redirect(request.url)

    file = request.files['resume']

    # Validate form fields
    location = request.form.get('location')
    education_level = request.form.get('education_level')
    enrollment_status = request.form.get('enrollment_status')

    if not (location and education_level and enrollment_status):
        flash('All fields are required.')
        return redirect(request.url)

    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)

        # Directly upload resume to Azure Blob Storage
        blob_service_client = BlobServiceClient.from_connection_string("DefaultEndpointsProtocol=https;AccountName=resumeuploads3568;AccountKey=YOUR_ACCOUNT_KEY_GOES_HERE!!!!!;EndpointSuffix=core.windows.net")
        blob_client = blob_service_client.get_blob_client(container="resumes", blob=filename)
        blob_client.upload_blob(file.stream)  # Upload file directly to Azure

        # Save the metadata and file info to SQLite database
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO submissions (resume_filename, location, education_level, enrollment_status)
            VALUES (?, ?, ?, ?)
        ''', (filename, location, education_level, enrollment_status))
        db.commit()

        # Instead of flash messages, pass a flag to show success
        return render_template('upload.html', success=True)

    flash('Allowed file types are pdf, doc, docx')
    return redirect(request.url)


# Teardown database connection
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

if __name__ == '__main__':
    app.run(debug=True)
