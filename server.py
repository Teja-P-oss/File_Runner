import os
import sys
import stat
import subprocess
from flask import Flask, jsonify, request
from flask_cors import CORS

# Configuration
app = Flask(__name__)
CORS(app)
ROOT_DIR = os.getcwd()

# Allowed root directories
ALLOWED_ROOTS = ['Tests', 'Calibration', 'src']

def get_directory_contents(rel_path):
    """
    Optimization: Non-recursive. 
    Returns list of items in a specific directory only.
    """
    abs_path = os.path.join(ROOT_DIR, rel_path)
    
    # Security check: ensure we don't traverse up out of root
    if not os.path.commonpath([ROOT_DIR, abs_path]) == ROOT_DIR:
        return []

    if not os.path.exists(abs_path):
        return []

    items = []
    try:
        # Get entries
        entries = os.scandir(abs_path)
        
        # Sort: Directories first, then files, case-insensitive
        sorted_entries = sorted(entries, key=lambda e: (not e.is_dir(), e.name.lower()))
        
        for entry in sorted_entries:
            items.append({
                "name": entry.name,
                "path": os.path.join(rel_path, entry.name).replace("\\", "/"), # Normalize for web
                "type": "dir" if entry.is_dir() else "file"
            })
    except PermissionError:
        pass
        
    return items

@app.route('/api/files', methods=['GET'])
def list_files():
    """
    Optimization: Returns contents of a specific path.
    If no path is provided, returns the hardcoded root folders.
    """
    req_path = request.args.get('path', '')
    
    if not req_path:
        # Root Level: Only return specific allowed folders
        data = []
        for folder in ALLOWED_ROOTS:
            full_path = os.path.join(ROOT_DIR, folder)
            if os.path.exists(full_path):
                data.append({
                    "name": folder,
                    "path": folder,
                    "type": "dir"
                })
        return jsonify(data)
    else:
        # Sub-directory Level
        return jsonify(get_directory_contents(req_path))

@app.route('/api/read', methods=['GET'])
def read_file():
    """Reads a file and checks if it is locked"""
    rel_path = request.args.get('path')
    full_path = os.path.join(ROOT_DIR, rel_path)
    
    if not os.path.exists(full_path):
        return jsonify({"error": "File not found"}), 404

    try:
        # Check write permission
        is_locked = not os.access(full_path, os.W_OK)
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return jsonify({"content": content, "locked": is_locked})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/save', methods=['POST'])
def save_file():
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
    data = request.json
    full_path = os.path.join(ROOT_DIR, data['path'])
    try:
        os.chmod(full_path, stat.S_IWRITE)
        return jsonify({"status": "unlocked"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/run-test', methods=['POST'])
def run_test():
    data = request.json
    target_file = os.path.join(ROOT_DIR, data['target'])
    script_path = os.path.join(ROOT_DIR, 'src', 'main.py')
    
    cmd = [sys.executable, script_path, target_file]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout + "\n" + result.stderr
        return jsonify({"output": output})
    except Exception as e:
        return jsonify({"output": f"Error running test: {str(e)}"})

@app.route('/api/open-external', methods=['POST'])
def open_external():
    data = request.json
    rel_path = data['path']
    full_path = os.path.join(ROOT_DIR, rel_path)
    
    try:
        if os.name == 'nt':
            os.startfile(full_path)
        elif sys.platform == 'darwin':
            subprocess.call(('open', full_path))
        else:
            subprocess.call(('xdg-open', full_path))
        return jsonify({"status": "opened"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print(f"Server running in {ROOT_DIR}")
    app.run(port=5000, debug=True)
