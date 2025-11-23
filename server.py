import os
import sys
import stat
import subprocess
import signal
from flask import Flask, jsonify, request
from flask_cors import CORS

# Configuration
app = Flask(__name__)
CORS(app)
ROOT_DIR = os.getcwd()

# Allowed root directories
ALLOWED_ROOTS = ['Tests', 'Calibration', 'Interfaces']

# Global registry for running processes { 'test_id': subprocess.Popen }
active_tests = {}

def get_directory_contents(rel_path):
    abs_path = os.path.join(ROOT_DIR, rel_path)
    if not os.path.commonpath([ROOT_DIR, abs_path]) == ROOT_DIR:
        return []
    if not os.path.exists(abs_path):
        return []
    items = []
    try:
        entries = os.scandir(abs_path)
        sorted_entries = sorted(entries, key=lambda e: (not e.is_dir(), e.name.lower()))
        for entry in sorted_entries:
            items.append({
                "name": entry.name,
                "path": os.path.join(rel_path, entry.name).replace("\\", "/"),
                "type": "dir" if entry.is_dir() else "file"
            })
    except PermissionError:
        pass
    return items

@app.route('/api/files', methods=['GET'])
def list_files():
    req_path = request.args.get('path', '')
    if not req_path:
        data = []
        for folder in ALLOWED_ROOTS:
            full_path = os.path.join(ROOT_DIR, folder)
            if os.path.exists(full_path):
                data.append({"name": folder, "path": folder, "type": "dir"})
        return jsonify(data)
    else:
        return jsonify(get_directory_contents(req_path))

# Change 1: Added Search Endpoint (Optimized for allowed roots)
@app.route('/api/search', methods=['GET'])
def search_files():
    query = request.args.get('q', '').lower()
    if not query or len(query) < 2: 
        return jsonify([])
    
    results = []
    # Only search within allowed roots to limit scope
    for root_folder in ALLOWED_ROOTS:
        start_dir = os.path.join(ROOT_DIR, root_folder)
        if not os.path.exists(start_dir): continue
        
        for dirpath, dirnames, filenames in os.walk(start_dir):
            # Check filenames
            for f in filenames:
                if query in f.lower():
                    full_p = os.path.join(dirpath, f)
                    rel_p = os.path.relpath(full_p, ROOT_DIR).replace("\\", "/")
                    results.append({"name": f, "path": rel_p, "type": "file"})
            
            # Optional: Limit results to avoid massive payloads
            if len(results) > 100: 
                break
        if len(results) > 100: break
            
    return jsonify(results)

@app.route('/api/read', methods=['GET'])
def read_file():
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
    test_id = data.get('testId') # Frontend provides ID to allow stopping
    
    cmd = [sys.executable, script_path, target_file]
    
    try:
        # Use Popen to allow tracking
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if test_id:
            active_tests[test_id] = proc
            
        stdout, stderr = proc.communicate()
        
        if test_id and test_id in active_tests:
            del active_tests[test_id]

        output = stdout + "\n" + stderr
        return jsonify({"output": output})
    except Exception as e:
        return jsonify({"output": f"Error running test: {str(e)}"})

@app.route('/api/stop-test', methods=['POST'])
def stop_test():
    data = request.json
    test_id = data.get('testId')
    
    if test_id in active_tests:
        proc = active_tests[test_id]
        try:
            proc.kill() # Force kill
            del active_tests[test_id]
            return jsonify({"status": "stopped", "output": "\n[Process stopped by user]\n"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "No active test found"}), 404

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
    print(f"FlowSim Manager running in {ROOT_DIR}")
    app.run(port=5000, debug=True, threaded=True)
