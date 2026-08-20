from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import cv2
import numpy as np
import pytesseract
import re
import operator
from datetime import datetime

app = Flask(__name__)

# Dictionary mapping string operators to actual math functions
ops = {
    '+': operator.add,
    '-': operator.sub,
    '*': operator.mul,
    '/': operator.truediv
}

def solve_captcha(image_bytes):
    """
    Processes the captcha image to remove noise and extracts the math equation.
    Returns the calculated integer answer.
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    # Convert image to HSV for precise color masking
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # Isolate blue dotted text
    lower_blue = np.array([100, 50, 50])
    upper_blue = np.array([140, 255, 255])
    mask = cv2.inRange(hsv, lower_blue, upper_blue)
    
    # Apply morphological closing to connect dots
    kernel = np.ones((3,3), np.uint8)
    processed_img = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    
    # OCR Extraction with strict math-only configuration
    text = pytesseract.image_to_string(
        processed_img, 
        config='--psm 6 -c tessedit_char_whitelist=0123456789+-*=/?'
    )
    
    # Parse equation and calculate
    match = re.search(r'(\d+)\s*([\+\-\*\/])\s*(\d+)', text)
    if match:
        num1 = int(match.group(1))
        op_symbol = match.group(2)
        num2 = int(match.group(3))
        
        if op_symbol in ops:
            return ops[op_symbol](num1, num2)
            
    return None

@app.route('/birth', methods=['GET'])
def get_birth_record():
    """
    API endpoint: /birth?brn={17_digit}&dob={YYYY-MM-DD}
    Automates the process of solving captcha and extracting data.
    """
    brn = request.args.get('brn')
    dob = request.args.get('dob')
    
    # --- POWERFUL FEATURE: Strict Input Validation ---
    
    # 1. Check if both parameters are provided
    if not brn or not dob:
        return jsonify({"success": False, "error": "Missing 'brn' or 'dob' query parameters."}), 400
        
    # 2. Validate BRN: Must be exactly 17 digits
    if not re.match(r'^\d{17}$', brn):
        return jsonify({"success": False, "error": "Invalid BRN. It must be exactly 17 digits."}), 400
        
    # 3. Validate DOB: Must match YYYY-MM-DD format
    try:
        datetime.strptime(dob, '%Y-%m-%d')
    except ValueError:
        return jsonify({"success": False, "error": "Invalid DOB format. Please use YYYY-MM-DD."}), 400

    # --- End of Validation ---

    try:
        with sync_playwright() as p:
            # Launch Chromium browser
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Replace with your actual target URL for testing
            page.goto("https://everify.bdris.gov.bd/")
            
            # Fill the validated inputs
            page.fill('input[name="ubrn"]', brn) 
            page.fill('input[name="BirthDate"]', dob) 
            
            # Locate and capture captcha
            captcha_element = page.locator('img[src*="captcha"]') 
            image_bytes = captcha_element.screenshot()
            
            # Solve captcha
            answer = solve_captcha(image_bytes)
            
            if answer is None:
                browser.close()
                return jsonify({"success": False, "error": "Failed to extract OCR data."}), 500
                
            # Submit the form
            page.fill('input[id="Answer"]', str(answer)) 
            page.click('button[type="submit"]') 
            
            # Wait for the result table
            try:
                page.wait_for_selector('table', timeout=10000) 
            except:
                browser.close()
                return jsonify({"success": False, "error": "Result data not found or request timed out."}), 404
            
            # Scrape the table data
            extracted_data = {}
            rows = page.locator('table tr').all()
            
            for row in rows:
                cells = row.locator('td').all_inner_texts()
                if len(cells) >= 2:
                    key = cells[0].strip().replace(':', '')
                    value = cells[1].strip()
                    extracted_data[key] = value
                    
            browser.close()
            
            return jsonify({
                "success": True,
                "captcha_solved": answer,
                "data": extracted_data
            })
            
    except Exception as e:
        return jsonify({"success": False, "error": f"Automation error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
