# Order Form Update Tool

A web application designed to help update order forms by replacing last year's signed order form with this year's unsigned version while preserving all addendums and attachments.

## Features

- Upload new unsigned order form
- Upload last year's complete document package
- Live PDF preview with page navigation
- Automatic signature page detection
- Manual page selection override
- Automatically replaces the old signed form with the new unsigned form
- Preserves all addendums and attachments from the old package
- Modern, responsive UI
- File size limit of 16MB

## Setup

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

3. Open your web browser and navigate to `http://localhost:5000`

## Usage

1. Upload this year's unsigned order form
2. Upload last year's complete document package (including signed order form and all addendums)
3. Click "Update Order Form"
4. Download the resulting PDF using the "Download Result" button

The tool will:
1. Take the new unsigned order form
2. Analyze the old package to find where the order form ends by detecting signature pages
3. Show a preview of the PDF with the detected page range
4. Allow manual adjustment of the form's end page if needed
5. Remove all pages of the old signed order form from last year's package
6. Insert the new unsigned form at the beginning
7. Preserve all addendums and attachments from last year's package

The tool uses intelligent signature page detection to find where the old order form ends by looking for:
- Signature boxes and lines
- Keywords like "signature", "sign here", "authorized signature"
- Notary and witness sections

If no signature page is detected, the tool assumes the order form is the first 3 pages of the document.

## Technical Details

- Backend: Flask
- PDF Processing: PyPDF2
- Frontend: HTML, JavaScript, Tailwind CSS
- Security: Secure filename handling and file size limits
