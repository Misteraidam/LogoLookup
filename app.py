from flask import Flask, request, jsonify, send_from_directory, render_template
import os, shutil
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder='static', template_folder='templates')

UPLOAD_FOLDER = os.path.join(app.static_folder, 'logos')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ADMIN_PASSWORD = "password"  # change this

@app.route('/')
def index():
    return render_template('logo_preview_editor.html')

@app.route('/logos')
def get_logos():
    logos = []
    for root, _, files in os.walk(UPLOAD_FOLDER):
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.svg', '.gif')):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, app.static_folder)
                brand = os.path.basename(os.path.dirname(full_path))
                logos.append({
                    'brand': brand,
                    'url': f'/static/{rel_path.replace("\\", "/")}'
                })
    return jsonify(sorted(logos, key=lambda x: x['brand'].lower()))

@app.route('/upload', methods=['POST'])
def upload_logo():
    if 'logos' not in request.files:
        return jsonify({'error': 'No files'}), 400

    files = request.files.getlist('logos')
    for file in files:
        if file.filename == '':
            continue
        filename = secure_filename(file.filename)
        target_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(target_path)
    return jsonify({'message': 'Uploaded successfully'})

@app.route('/add_brand', methods=['POST'])
def add_brand():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403

    brand = data.get('brand')
    if not brand:
        return jsonify({'error': 'No brand provided'}), 400

    new_folder = os.path.join(UPLOAD_FOLDER, brand.replace(" ", "_"))
    os.makedirs(new_folder, exist_ok=True)
    return jsonify({'message': f'Brand {brand} added'})

@app.route('/rename_brand', methods=['POST'])
def rename_brand():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403

    old = os.path.join(UPLOAD_FOLDER, data.get('oldName', '').replace(" ", "_"))
    new = os.path.join(UPLOAD_FOLDER, data.get('newName', '').replace(" ", "_"))
    if os.path.exists(old):
        os.rename(old, new)
        return jsonify({'message': 'Renamed successfully'})
    return jsonify({'error': 'Old brand not found'}), 404

@app.route('/delete_brand', methods=['POST'])
def delete_brand():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403

    brand = os.path.join(UPLOAD_FOLDER, data.get('brand', '').replace(" ", "_"))
    if os.path.exists(brand):
        shutil.rmtree(brand)
        return jsonify({'message': 'Deleted successfully'})
    return jsonify({'error': 'Brand not found'}), 404

@app.route('/delete_logo', methods=['POST'])
def delete_logo():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403

    rel_path = data.get('url', '').replace('/static/', '')
    abs_path = os.path.join(app.static_folder, rel_path)
    if os.path.exists(abs_path):
        os.remove(abs_path)
        return jsonify({'message': 'Deleted successfully'})
    return jsonify({'error': 'Logo not found'}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)
