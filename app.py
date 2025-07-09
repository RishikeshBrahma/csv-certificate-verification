from flask import Flask, request, render_template, redirect, url_for, send_file
import mysql.connector
import pandas as pd
import qrcode
import os
from dotenv import load_dotenv
from typing import Optional

app = Flask(__name__)

# Load environment variables
load_dotenv()
db_config = {
    'user': os.getenv('MYSQL_USER'),
    'password': os.getenv('MYSQL_PASSWORD'),
    'host': os.getenv('MYSQL_HOST'),
    'database': os.getenv('MYSQL_DB')
}

# Directories for uploads and QR codes
UPLOAD_FOLDER = 'Uploads'
QR_FOLDER = 'static/qrcodes'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Homepage route
@app.route('/')
def index():
    return render_template('base.html')

# Handle CSV upload and process certificates
@app.route('/upload', methods=['GET', 'POST'])
def upload_csv():
    if request.method == 'GET':
        return render_template('upload.html')
    
    if 'csv_file' not in request.files:
        return render_template('upload.html', error='No file uploaded')
    file = request.files['csv_file']
    filename = file.filename
    if filename is None or filename == '':
        return render_template('upload.html', error='No file selected')
    if file and filename.endswith('.csv'):
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        try:
            df = pd.read_csv(file_path)
            required_columns = ['certificate_id', 'recipient_name', 'course_title', 'issue_date']
            if not all(col in df.columns for col in required_columns):
                return render_template('upload.html', error='Invalid CSV format. Required columns: certificate_id, recipient_name, course_title, issue_date')
            
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()
            
            for _, row in df.iterrows():
                certificate_id = row['certificate_id']
                verification_url = f'http:// 192.168.141.51:5000/verify_download/{certificate_id}'
                qr = qrcode.QRCode(version=1, box_size=10, border=5)
                qr.add_data(verification_url)
                qr.make(fit=True)
                qr_img = qr.make_image(fill='black', back_color='white')
                qr_path = os.path.join(QR_FOLDER, f'{certificate_id}.png')
                with open(qr_path, 'wb') as f:
                    qr_img.save(f)
                
                query = """
                    INSERT INTO certificates (certificate_id, recipient_name, course_title, issue_date, verification_url, csv_file_path)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                values = (
                    certificate_id,
                    row['recipient_name'],
                    row['course_title'],
                    row['issue_date'],
                    verification_url,
                    file_path
                )
                cursor.execute(query, values)
            
            conn.commit()
            cursor.close()
            conn.close()
            return render_template('upload.html', success='Certificates processed successfully!')
        except Exception as e:
            return render_template('upload.html', error=f'Error processing CSV: {str(e)}')
    return render_template('upload.html', error='Invalid file format. Only CSV files are allowed.')

# Verification route (for displaying QR code)
@app.route('/verify', methods=['GET'])
def verify():
    certificate_id = request.args.get('certificate_id')
    if not certificate_id:
        return render_template('verify.html')
    
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        query = "SELECT csv_file_path FROM certificates WHERE certificate_id = %s"
        cursor.execute(query, (certificate_id,))
        certificate = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not certificate or 'csv_file_path' not in certificate or not certificate.get('csv_file_path'): # type: ignore
            return render_template('verify.html', error='Certificate or CSV file not found', certificate_id=certificate_id)
        
        return render_template('verify.html', certificate_id=certificate_id)
    except Exception as e:
        return render_template('verify.html', error=f'Error retrieving certificate: {str(e)}', certificate_id=certificate_id)

# Download route (for QR code scan or manual download)
@app.route('/verify_download/<certificate_id>', methods=['GET'])
def verify_download(certificate_id):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        query = "SELECT csv_file_path FROM certificates WHERE certificate_id = %s"
        cursor.execute(query, (certificate_id,))
        certificate = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not certificate or 'csv_file_path' not in certificate:
            return render_template('verify.html', error='Certificate or CSV file not found', certificate_id=certificate_id)
        
        csv_file_path = certificate['csv_file_path'] # type: ignore
        if not isinstance(csv_file_path, str):
            return render_template('verify.html', error='Invalid file path format', certificate_id=certificate_id)
        
        if not os.path.exists(csv_file_path):
            return render_template('verify.html', error='CSV file not found on server', certificate_id=certificate_id)
        
        return send_file(csv_file_path, as_attachment=True, download_name=f'certificate_{certificate_id}.csv')
    except Exception as e:
        return render_template('verify.html', error=f'Error retrieving CSV file: {str(e)}', certificate_id=certificate_id)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)