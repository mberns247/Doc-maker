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
    """Replace the specified text in the PDF while preserving formatting"""
    try:
        logger.info(f"Starting text replacement for {input_pdf_path}")
        
        # Original text patterns to find
        old_text_patterns = [
            "By accepting this quote, you agree to the terms and conditions in our Terms of Use and Sale for Businesses which can be viewed",
            "below. If you accept this quote on behalf of a company or other legal entity or person, your acceptance also represents that you",
            "have the authority to bind such entity or person to the terms of this quote, including the Terms of Use and Sale for Businesses. The",
            "contract terms referred to below shall govern your use of paid Trustpilot services from the earlier of: (i) the date on which you accept",
            "this order form; and (ii) the \"Subscription start date\" noted above."
        ]
        
        # New replacement text with proper line breaks
        new_text = (
            "By accepting this quote, you agree to the terms and conditions in our Service Subscription Agreement. \n\n"
            "If you accept this quote on behalf of a company or other legal entity or person, your acceptance also represents that you \n"
            "have the authority to bind such entity or person to the terms of this quote, including the Service Subscription Agreement. \n\n"
            "Please refer to the Service Subscription Agreement that has been sent together with this order form."
        )
        
        # Extract text and layout from the original PDF
        laparams = LAParams()
        output_buffer = StringIO()
        
        with open(input_pdf_path, 'rb') as file:
            extract_text_to_fp(file, output_buffer, laparams=laparams)
            text_with_layout = output_buffer.getvalue()
            
        logger.info("Extracted text from PDF:")
        logger.info(text_with_layout)
        
        # Find the position of the old text
        reader = PdfReader(input_pdf_path)
        if len(reader.pages) == 0:
            raise ValueError("PDF has no pages")
        
        # Create a new PDF with the replacement text
        packet = BytesIO()
        can = canvas.Canvas(packet, pagesize=letter)
        
        # Check for presence of key phrases
        text_found = False
        for pattern in old_text_patterns:
            if pattern.lower() in text_with_layout.lower():
                text_found = True
                logger.info(f"Found pattern: {pattern}")
            else:
                logger.info(f"Pattern not found: {pattern}")
        
        if text_found:
            logger.info("Found text to replace")
            
            # Position the text near the bottom of the page, above the signature section
            # Standard letter page height is 792 points (11 inches)
            base_y = 180  # Points from bottom of page - positioned just above signature section
            
            # Create a white rectangle to cover the old text area
            can.setFillColor('white')
            can.rect(50, base_y - 80, 550, 100, fill=True)  # Wider rectangle to ensure coverage
            
            # Set up text formatting
            can.setFillColor('black')
            can.setFont("Helvetica", 9)  # Slightly smaller font to match the original
            
            # Split text into lines and draw
            y_pos = base_y
            line_height = 12
            paragraph_spacing = 6
            
            # Process each line of text
            for line in new_text.split('\n'):
                if line.strip() == '':
                    # Add extra space for paragraph breaks
                    y_pos -= paragraph_spacing
                    continue
                    
                # Word wrap for each line
                words = line.split()
                current_line = []
                x_pos = 72  # Left margin
                
                for word in words:
                    test_line = current_line + [word]
                    line_width = can.stringWidth(' '.join(test_line), "Helvetica", 9)
                    
                    if line_width <= 500:  # Max width
                        current_line.append(word)
                    else:
                        # Draw current line and start new one
                        can.drawString(x_pos, y_pos, ' '.join(current_line))
                        y_pos -= line_height
                        current_line = [word]
                
                # Draw remaining words
                if current_line:
                    can.drawString(x_pos, y_pos, ' '.join(current_line))
                    y_pos -= line_height
        else:
            logger.warning("Did not find text to replace - keeping original text")
        
        can.save()
        logger.info("Created overlay with new text")
        
        # Create the output PDF
        packet.seek(0)
        new_pdf = PdfReader(packet)
        writer = PdfWriter()
        
        # Add all pages from the original PDF
        for i, page in enumerate(reader.pages):
            if i == 0 and text_found:
                # Create a white rectangle to cover the old text
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
        
        # Extract company name and process the new form
        company_name = extract_company_name(new_form_path)
        logger.info(f"Extracted company name: {company_name}")
        
        # Create new PDF writer for the output
        output = PdfWriter()
        
        # Process the new form with text replacement
        logger.info("Processing text replacement")
        modified_form = replace_text_in_pdf(new_form_path)
        
        # Create a temporary file for the modified form
        temp_modified_form = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_modified_form.pdf')
        logger.info(f"Writing modified form to temporary file: {temp_modified_form}")
        with open(temp_modified_form, 'wb') as f:
            modified_form.write(f)
        
        # Verify the temporary file was created
        if not os.path.exists(temp_modified_form):
            raise FileNotFoundError("Failed to create temporary modified form")
        
        # Read the modified form back
        logger.info("Reading back modified form")
        modified_reader = PdfReader(temp_modified_form)
        logger.info(f"Modified form has {len(modified_reader.pages)} pages")
        
        # Add all pages from the modified form
        logger.info("Adding modified form pages to output")
        for page in modified_reader.pages:
            output.add_page(page)
            
        # Clean up temporary file
        os.remove(temp_modified_form)
        
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
        try:
            # Generate filename with company name and today's date
            today_date = datetime.now().strftime('%Y%m%d')
            output_filename = f"Order Form - {company_name} - TP {today_date} - Renewal.pdf"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(output_filename))
            
            logger.info(f"Saving output to: {output_path}")
            with open(output_path, 'wb') as output_file:
                output.write(output_file)
            
            if not os.path.exists(output_path):
                raise FileNotFoundError("Failed to save output file")
                
            logger.info("Output file saved successfully")
            
            return jsonify({
                'success': True,
                'filename': output_filename,
                'message': 'PDFs processed successfully',
                'details': {
                    'old_form_pages_removed': processing_info['old_form_pages'],
                    'addendums_preserved': processing_info['addendums'],
                    'total_pages': processing_info['total_pages']
                }
            })
            
        except Exception as e:
            logger.error(f"Error saving output file: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({'error': f'Error saving output file: {str(e)}'}), 500
    
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

@app.route('/download/<filename>')
def download_result(filename):
    try:
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
        if not os.path.exists(output_path):
            logger.error(f"File not found: {output_path}")
            return jsonify({'error': 'No processed file found'}), 404
            
        return send_file(output_path, as_attachment=True)
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        return jsonify({'error': f'Error downloading file: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
