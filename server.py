import os
import sys
import stat
import subprocess
from flask import Flask, jsonify, request
from flask_cors import CORS

# Configuration
app = Flask(__name__)
CORS(app)  # Allow the HTML file to talk to this script
ROOT_DIR = os.getcwd()

def get_file_tree(start_path):
    """Recursively builds a JSON tree of the directory"""
    tree = {}
    try:
        # specific sorting: folders first, then files
        items = os.listdir(start_path)
        items.sort(key=lambda x: (not os.path.isdir(os.path.join(start_path, x)), x.lower()))
        
        for item in items:
            path = os.path.join(start_path, item)
            if os.path.isdir(path):
                tree[item] = get_file_tree(path)
            else:
                # Mark as file
                tree[item] = "__FILE__" 
    except PermissionError:
        pass
    return tree

@app.route('/api/files', methods=['GET'])
def list_files():
    """Returns the structure of Tests, Calibration, and src"""
    data = {}
    for folder in ['Tests', 'Calibration', 'src']:
        path = os.path.join(ROOT_DIR, folder)
        if os.path.exists(path):
            data[folder] = get_file_tree(path)
    return jsonify(data)

@app.route('/api/read', methods=['GET'])
def read_file():
    """Reads a file and checks if it is locked"""
    rel_path = request.args.get('path')
    full_path = os.path.join(ROOT_DIR, rel_path)
    
    if not os.path.exists(full_path):
        return jsonify({"error": "File not found"}), 404

    try:
        is_locked = not os.access(full_path, os.W_OK)
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return jsonify({"content": content, "locked": is_locked})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/save', methods=['POST'])
def save_file():
    """Saves content to file"""
    data = request.json
    full_path = os.path.join(ROOT_DIR, data['path'])
    
    try:
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(data['content'])
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/unlock', methods=['POST'])
def unlock_file():
    """Removes Read-Only attribute"""
    data = request.json
    full_path = os.path.join(ROOT_DIR, data['path'])
    try:
        os.chmod(full_path, stat.S_IWRITE)
        return jsonify({"status": "unlocked"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/run-test', methods=['POST'])
def run_test():
    """Runs python ../src/main.py <file>"""
    data = request.json
    target_file = os.path.join(ROOT_DIR, data['target'])
    script_path = os.path.join(ROOT_DIR, 'src', 'main.py')
    
    # Command: python script.py target_file
    # We use Popen to run it in a separate shell window if possible
    cmd = [sys.executable, script_path, target_file]
    
    try:
        # Capture output or open new window depending on OS preferences
        # Here we run it and capture output to show in the HTML terminal
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout + "\n" + result.stderr
        return jsonify({"output": output})
    except Exception as e:
        return jsonify({"output": f"Error running test: {str(e)}"})

@app.route('/api/open-external', methods=['POST'])
def open_external():
    """Opens a file with the default OS application"""
    data = request.json
    # The path comes in as "Calibration/file.dat", we need full path
    rel_path = data['path']
    full_path = os.path.join(ROOT_DIR, rel_path)
    
    try:
        if os.name == 'nt': # Windows
            os.startfile(full_path)
        elif sys.platform == 'darwin': # Mac
            subprocess.call(('open', full_path))
        else: # Linux
            subprocess.call(('xdg-open', full_path))
        return jsonify({"status": "opened"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print(f"Server running in {ROOT_DIR}")
    app.run(port=5000, debug=True)
