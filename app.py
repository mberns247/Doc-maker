from flask import Flask, render_template, request, send_file, jsonify
from PyPDF2 import PdfReader, PdfWriter
import os
from werkzeug.utils import secure_filename
import re
import traceback
import logging
from datetime import datetime
from pdfminer.high_level import extract_text_to_fp, extract_text
from pdfminer.layout import LAParams
from io import StringIO, BytesIO
from PyPDF2 import PdfReader, PdfWriter, PdfFileReader
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

def extract_company_name(pdf_path):
    """Extract company name from the PDF"""
    text = extract_text(pdf_path)
    # Look for common patterns that might precede company name
    patterns = [
        r'Company\s*Name\s*:\s*([^\n]+)',
        r'Company:\s*([^\n]+)',
        r'Bill\s*To:\s*([^\n]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return 'Unknown'

def replace_text_in_pdf(input_pdf_path):
    """Replace the specified text in the PDF"""
    try:
        logger.info(f"Starting text replacement for {input_pdf_path}")
        
        # Original text to find (normalized for comparison)
        old_text = "By accepting this quote, you agree to the terms and conditions in our Terms of Use and Sale for Businesses which can be viewed below. If you accept this quote on behalf of a company or other legal entity or person, your acceptance also represents that you have the authority to bind such entity or person to the terms of this quote, including the Terms of Use and Sale for Businesses. The contract terms referred to below shall govern your use of paid Trustpilot services from the earlier of: (i) the date on which you accept this order form; and (ii) the \"Subscription start date\" noted above. Terms of Use and Sale for Businesses"
        
        # New replacement text
        new_text = "By accepting this quote, you agree to the terms and conditions in our Service Subscription Agreement. If you accept this quote on behalf of a company or other legal entity or person, your acceptance also represents that you have the authority to bind such entity or person to the terms of this quote, including the Service Subscription Agreement. Please refer to the Service Subscription Agreement that has been sent together with this order form."
        
        # Create a temporary PDF with the new text
        packet = BytesIO()
        can = canvas.Canvas(packet, pagesize=letter)
        
        # Extract text from the original PDF
        reader = PdfReader(input_pdf_path)
        if len(reader.pages) == 0:
            raise ValueError("PDF has no pages")
            
        text = extract_text(input_pdf_path)
        logger.info("Successfully extracted text from PDF")
        
        # Normalize texts for comparison (remove extra spaces and newlines)
        normalized_old_text = ' '.join(old_text.replace('\n', ' ').split())
        normalized_pdf_text = ' '.join(text.replace('\n', ' ').split())
        
        # If we find the old text, replace it with new text
        if normalized_old_text in normalized_pdf_text:
            logger.info("Found text to replace")
            # Add the new text (you might need to adjust coordinates)
            can.setFont("Helvetica", 10)
            y_position = 400  # Adjust this value based on your needs
            text_lines = new_text.split('\n')
            for line in text_lines:
                can.drawString(72, y_position, line)
                y_position -= 12
        else:
            logger.warning("Did not find text to replace - keeping original text")
        
        can.save()
        logger.info("Created overlay with new text")
        
        # Move to the beginning of the StringIO buffer
        packet.seek(0)
        new_pdf = PdfReader(packet)
        
        # Create the output PDF
        writer = PdfWriter()
        
        # Add all pages from the original PDF
        for i, page in enumerate(reader.pages):
            if i == 0 and normalized_old_text in normalized_pdf_text:
                # Merge the first page with our new text
                page.merge_page(new_pdf.pages[0])
            writer.add_page(page)
        
        logger.info("Successfully created new PDF with replaced text")
        return writer
        
    except Exception as e:
        logger.error(f"Error in replace_text_in_pdf: {str(e)}")
        logger.error(traceback.format_exc())
        # Return the original PDF without modifications if there's an error
        writer = PdfWriter()
        reader = PdfReader(input_pdf_path)
        for page in reader.pages:
            writer.add_page(page)
        return writer

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

# Configure upload folder to use /tmp for Render compatibility
app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
logger.info(f"Upload directory: {app.config['UPLOAD_FOLDER']}")

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

    try:
        # Save uploaded files
        new_form_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(new_form.filename))
        old_package_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(old_package.filename))
        
        logger.info(f"Saving files to: {new_form_path} and {old_package_path}")
        new_form.save(new_form_path)
        old_package.save(old_package_path)
        
        # Verify files were saved
        if not os.path.exists(new_form_path) or not os.path.exists(old_package_path):
            raise FileNotFoundError("Failed to save uploaded files")
            
        logger.info("Files saved successfully")
        
        logger.info(f"Processing files: new_form={new_form.filename}, old_package={old_package.filename}")
        
        # Create new PDF writer for the output
        output = PdfWriter()
        
        try:
            # Process the new form with text replacement
            logger.info("Extracting company name")
            company_name = extract_company_name(new_form_path)
            logger.info(f"Found company name: {company_name}")
            
            logger.info("Processing text replacement")
            modified_form = replace_text_in_pdf(new_form_path)
            
            # Add all pages from the modified form
            logger.info("Adding modified form pages to output")
            for page in modified_form.pages:
                output.add_page(page)
        except Exception as e:
            logger.error(f"Error processing new form: {str(e)}")
            logger.error(traceback.format_exc())
            raise
        
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
        # Generate filename with company name and today's date
        today_date = datetime.now().strftime('%Y%m%d')
        output_filename = f"Order Form - {company_name} - TP {today_date} - Renewal.pdf"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
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
