import re
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

# Point to the parent directory (Project Root) instead of current working dir
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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

@app.route('/api/search', methods=['GET'])
def search_files():
    query = request.args.get('q', '').lower()
    if not query or len(query) < 2: 
        return jsonify([])
    
    results = []
    for root_folder in ALLOWED_ROOTS:
        start_dir = os.path.join(ROOT_DIR, root_folder)
        if not os.path.exists(start_dir): continue
        
        for dirpath, dirnames, filenames in os.walk(start_dir):
            for f in filenames:
                if query in f.lower():
                    full_p = os.path.join(dirpath, f)
                    rel_p = os.path.relpath(full_p, ROOT_DIR).replace("\\", "/")
                    results.append({"name": f, "path": rel_p, "type": "file"})
            
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
    test_id = data.get('testId')
    
    cmd = [sys.executable, script_path, target_file]
    
    try:
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
            proc.kill() 
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
        
@app.route('/api/p4-sync', methods=['POST'])
def sync_p4():
    data = request.json
    full_path = os.path.join(ROOT_DIR, data.get('path', ''))
    
    if not os.path.exists(full_path):
        return jsonify({"output": "Error: File not found on disk."})

    try:
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f: content = f.read()

        pattern = r'(?:\.?)(?:Calibration|bin|Content|Tests)[\\/][\w\-\.\\/]+'
        matches = sorted(list(set(re.findall(pattern, content, re.IGNORECASE))))
        
        if not matches: return jsonify({"output": "No syncable paths found in this file."})

        depot_base = "//projects/camerasystems/PC-sim3.0/dev/FlowSim/"
        
        # Batch generation: Force CWD and attempt to load P4 Config
        bat_lines = [
            "@echo off", 
            "title FlowSim P4 Sync",
            f"cd /d \"{ROOT_DIR}\"", 
            "if exist p4config.txt set P4CONFIG=p4config.txt",
            "if exist .p4config set P4CONFIG=.p4config",
            "echo CWD: %CD%", 
            "echo P4CONFIG: %P4CONFIG%",
            "echo.",
            "echo Starting Sync...", 
            "echo ---------------------------------------"
        ]
        
        for item in matches:
            clean = item.lstrip('.').replace('\\', '/').rstrip('/')
            # Determine if folder (/*) or file
            suffix = "" if os.path.splitext(clean)[1] else "/*"
            p4_path = f"{depot_base}{clean}{suffix}"
            
            # Use -d flag to force P4 to use ROOT_DIR context
            cmd = f"p4 -d \"{ROOT_DIR}\" sync \"{p4_path}\""
            bat_lines.extend([f"echo ^> {cmd}", cmd])
            
        bat_lines.extend(["echo.", "echo ---------------------------------------", "echo Sync Process Finished.", "pause"])
        
        bat_path = os.path.join(ROOT_DIR, 'temp_p4_sync.bat')
        with open(bat_path, 'w') as f: f.write('\n'.join(bat_lines))
            
        subprocess.Popen(['start', 'cmd', '/k', bat_path], shell=True)
        return jsonify({"output": "P4 Sync launched in external terminal."})

    except Exception as e:
        return jsonify({"output": f"Error initiating sync: {str(e)}"})
        
if __name__ == '__main__':
    print(f"FlowSim Manager running in {ROOT_DIR}")
    app.run(port=5000, debug=True, threaded=True)
