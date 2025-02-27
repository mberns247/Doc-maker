from flask import Flask, render_template, request, send_file, jsonify
from PyPDF2 import PdfReader, PdfWriter
import os
from werkzeug.utils import secure_filename
import re
import traceback
import logging
from pdfminer.high_level import extract_text_to_fp
from pdfminer.layout import LAParams
from io import StringIO

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def detect_signature_page(pdf_path, page_num):
    """Detect if a page contains signature boxes by looking for signature-related keywords"""
    output = StringIO()
    with open(pdf_path, 'rb') as pdf_file:
        extract_text_to_fp(pdf_file, output, page_numbers=[page_num], laparams=LAParams())
    text = output.getvalue().lower()
    
    # Keywords that typically appear on signature pages
    signature_keywords = [
        'signature', 'sign here', 'authorized signature',
        'date signed', 'witness', 'notary', 'seal',
        'x_____', 'x____', '____x____', 'sign below'
    ]
    
    return any(keyword in text for keyword in signature_keywords)

def find_last_order_form_page(pdf_path):
    """Find the last page of the order form by detecting the signature page"""
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    
    # Start from the beginning and look for signature page
    for i in range(min(10, total_pages)):  # Check first 10 pages max
        if detect_signature_page(pdf_path, i):
            return i + 1  # Return 1-based page number
    
    # If no signature page found, assume it's the first 3 pages
    return min(3, total_pages)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'

# Ensure upload folder exists
upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), app.config['UPLOAD_FOLDER'])
app.config['UPLOAD_FOLDER'] = upload_dir
os.makedirs(upload_dir, exist_ok=True)
logger.info(f"Upload directory: {upload_dir}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze_pdf():
    if 'old_package' not in request.files:
        return jsonify({'error': 'PDF file is required'}), 400
    
    old_package = request.files['old_package']
    if old_package.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # Save uploaded file
    old_package_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(old_package.filename))
    old_package.save(old_package_path)
    
    try:
        # Find signature page
        last_form_page = find_last_order_form_page(old_package_path)
        
        # Get total pages
        reader = PdfReader(old_package_path)
        total_pages = len(reader.pages)
        
        return jsonify({
            'success': True,
            'suggested_form_pages': last_form_page,
            'total_pages': total_pages
        })
    except Exception as e:
        logger.error(f"Error analyzing PDF: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f"Error analyzing PDF: {str(e)}"}), 500
    finally:
        if os.path.exists(old_package_path):
            os.remove(old_package_path)

@app.route('/upload', methods=['POST'])
def upload_files():
    # Get manual page selection if provided
    form_end_page = request.form.get('form_end_page')
    if form_end_page:
        try:
            form_end_page = int(form_end_page)
        except ValueError:
            return jsonify({'error': 'Invalid page number'}), 400
    if 'new_form' not in request.files or 'old_package' not in request.files:
        return jsonify({'error': 'Both PDF files are required'}), 400
    
    new_form = request.files['new_form']
    old_package = request.files['old_package']
    
    if new_form.filename == '' or old_package.filename == '':
        return jsonify({'error': 'No selected files'}), 400

    # Save uploaded files
    new_form_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(new_form.filename))
    old_package_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(old_package.filename))
    
    new_form.save(new_form_path)
    old_package.save(old_package_path)
    
    try:
        logger.info(f"Processing files: new_form={new_form.filename}, old_package={old_package.filename}")
        
        # Create new PDF writer for the output
        output = PdfWriter()
        
        # First, add the new unsigned order form
        new_form_reader = PdfReader(new_form_path)
        for page in new_form_reader.pages:
            output.add_page(page)
        
        # Now process the old package
        old_package_reader = PdfReader(old_package_path)
        
        # Use manual selection if provided, otherwise detect automatically
        last_form_page = form_end_page if form_end_page else find_last_order_form_page(old_package_path)
        
        # Add all pages after the order form (addendums and attachments)
        for i in range(last_form_page, len(old_package_reader.pages)):
            output.add_page(old_package_reader.pages[i])
            
        # Add a processing note to the response
        processing_info = {
            'old_form_pages': last_form_page,
            'total_pages': len(old_package_reader.pages),
            'addendums': len(old_package_reader.pages) - last_form_page
        }
        
        # Save the result
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'result.pdf')
        with open(output_path, 'wb') as output_file:
            output.write(output_file)
        
        return jsonify({
            'success': True,
            'message': 'PDFs processed successfully',
            'details': {
                'old_form_pages_removed': processing_info['old_form_pages'],
                'addendums_preserved': processing_info['addendums'],
                'total_pages_in_new_document': len(new_form_reader.pages) + processing_info['addendums']
            }
        })
    
    except Exception as e:
        logger.error(f"Error processing PDFs: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f"Error processing PDFs: {str(e)}"}), 500
    finally:
        # Clean up uploaded files
        if os.path.exists(new_form_path):
            os.remove(new_form_path)
        if os.path.exists(old_package_path):
            os.remove(old_package_path)

@app.route('/download')
def download_result():
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'result.pdf')
    if os.path.exists(output_path):
        return send_file(output_path, as_attachment=True, download_name='result.pdf')
    return jsonify({'error': 'No processed file found'}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5001)
