# logo_preview_pro.py
"""
Logo Preview Pro - Dark Mode with Admin Dashboard
- Public viewer at /
- Admin dashboard at /admin (admin login required)
- Upload / Replace / Delete / Rename / Mark done (admin-only)
- Files stored in static/logos/<batch>/
Run:
    python logo_preview_pro.py
"""
import os
import uuid
import json
import datetime
from pathlib import Path
from flask import (
    Flask, render_template_string, jsonify, request, send_from_directory,
    abort, redirect, url_for
)

BASE_DIR = Path(__file__).parent.resolve()
STATIC_LOGOS_ROOT = BASE_DIR / "static" / "logos"
STATIC_LOGOS_ROOT.mkdir(parents=True, exist_ok=True)

MARKS_FILE = BASE_DIR / "admin_marks.json"
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"}
ADMIN_PASSWORD = "aya900"
ADMIN_TOKENS = set()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20MB uploads allowed


# -------------------- Utilities --------------------
def allowed_ext(filename: str):
    return Path(filename).suffix.lower() in ALLOWED_EXT


def scan_batches():
    """Return sorted batch folder names"""
    return sorted([p.name for p in STATIC_LOGOS_ROOT.iterdir() if p.is_dir()])


def group_by_brand(filenames):
    """Group filenames into brand entries"""
    groups = {}
    for fn in filenames:
        stem = Path(fn).stem
        low = stem.lower()
        if "_logo" in low:
            brand_key = stem.rsplit("_logo", 1)[0]
        else:
            parts = stem.rsplit("_", 1)
            brand_key = parts[0] if len(parts) == 2 and parts[1].isdigit() else stem
        brand_display = brand_key.replace("_", " ")
        groups.setdefault(brand_key, {"brand": brand_display, "files": []})
        groups[brand_key]["files"].append(fn)
    # convert to sorted list
    return [groups[k] for k in sorted(groups.keys(), key=lambda x: groups[x]["brand"].lower())]


def safe_join(base: Path, *paths):
    """Join paths safely and ensure result stays within base"""
    p = base.joinpath(*paths).resolve()
    if str(p).startswith(str(base.resolve())):
        return p
    abort(403)


def clean_brand_key(text: str):
    import re
    s = re.sub(r'[<>:"/\\|?*]', '', text)
    s = s.strip().replace(" ", "_")
    s = re.sub(r'__+', "_", s)
    return s[:120]


def read_marks():
    if MARKS_FILE.exists():
        try:
            return json.loads(MARKS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def write_marks(data):
    try:
        MARKS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def require_admin_token():
    token = request.headers.get("X-Admin-Token") or request.form.get("admin_token") or request.args.get("admin_token")
    if not token or token not in ADMIN_TOKENS:
        abort(401, "Admin token missing or invalid")


# -------------------- TEMPLATES --------------------
# Keep the templates inside Python string for single-file convenience
INDEX_TEMPLATE = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Logo Preview Pro - Viewer</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{
  --bg:#0b0f14; --secondary:#0f1418; --card:#111418; --muted:#90a0b0; --text:#cfe6ef; --accent:#22c1ff; --mark:#b71c1c;
}
body{margin:0;font-family:Inter,system-ui,Segoe UI,Roboto,Arial;background:var(--bg);color:var(--text);}
.container{max-width:1200px;margin:18px auto;padding:18px;}
.header{display:flex;align-items:center;justify-content:space-between;gap:12px}
h1{margin:0;color:var(--accent)}
.controls{display:flex;gap:10px;align-items:center}
select,input{background:var(--secondary);border:1px solid #182129;color:var(--text);padding:8px;border-radius:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px;margin-top:18px}
.card{background:var(--card);padding:14px;border-radius:10px;box-shadow:0 6px 18px rgba(0,0,0,0.6)}
.brand{font-weight:600;margin-bottom:8px}
.imgwrap{height:110px;border-radius:8px;background:#07111a;display:flex;align-items:center;justify-content:center;padding:8px;overflow:hidden}
.imgwrap img{max-height:100%; max-width:100%; object-fit:contain}
.info{font-size:13px;color:var(--muted);margin-top:8px;display:flex;justify-content:space-between;align-items:center}
.small{font-size:12px;padding:6px 8px;border-radius:8px;background:#0d1a22;border:1px solid #152129;color:var(--text);cursor:pointer}
.badge{background:#071a24;padding:4px 8px;border-radius:999px;color:var(--muted)}
.footer{margin-top:18px;color:var(--muted);font-size:13px}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>Logo Preview</h1>
      <div style="color:var(--muted)">Pick a batch to preview logos</div>
    </div>
    <div class="controls">
      <label style="color:var(--muted)">Batch:</label>
      <select id="batchSelect"><option value="">-- pick batch --</option>{% for b in batches %}<option value="{{b}}">{{b}}</option>{% endfor %}</select>
      <input id="search" placeholder="Search brand..." />
      <button class="small" onclick="reload()">Reload</button>
      <a href="/admin" style="text-decoration:none"><button class="small">Admin</button></a>
    </div>
  </div>

  <div id="grid" class="grid">
    <div style="grid-column:1/-1;color:var(--muted)">Select a batch to start.</div>
  </div>

  <div class="footer">
    Tip: Admins can manage logos in the Admin Dashboard.
  </div>
</div>

<script>
const batchSelect = document.getElementById('batchSelect');
const grid = document.getElementById('grid');
const searchInput = document.getElementById('search');

batchSelect.onchange = ()=> loadBatch(batchSelect.value);
searchInput.oninput = ()=> renderGrid(currentData);

let currentBatch = '';
let currentData = [];

function reload(){ if(currentBatch) loadBatch(currentBatch); }

async function loadBatch(batch){
  currentBatch = batch;
  grid.innerHTML = '';
  for(let i=0;i<6;i++){ const s=document.createElement('div'); s.style.height='120px'; s.style.background='linear-gradient(90deg,#07121a,#0b2633)'; s.style.borderRadius='8px'; grid.appendChild(s); }
  if(!batch){ grid.innerHTML = '<div style="grid-column:1/-1;color:#8393a1">Select a batch to start.</div>'; return; }
  try{
    const res = await fetch(`/api/logos/${batch}`);
    const json = await res.json();
    currentData = json;
    renderGrid(json);
  }catch(e){
    grid.innerHTML = '<div style="grid-column:1/-1;color:#c77">Failed to load batch.</div>';
  }
}

function renderGrid(list){
  const term = searchInput.value.trim().toLowerCase();
  grid.innerHTML = '';
  if(!list || list.length===0){ grid.innerHTML = '<div style="grid-column:1/-1;color:#8393a1">No logos found in this batch.</div>'; return; }
  const filtered = list.filter(b => !term || b.brand.toLowerCase().includes(term));
  if(filtered.length===0){ grid.innerHTML = '<div style="grid-column:1/-1;color:#8393a1">No matches.</div>'; return; }
  filtered.forEach(item=>{
    const card = document.createElement('div'); card.className='card';
    const brandTitle = document.createElement('div'); brandTitle.className='brand'; brandTitle.textContent = item.brand;
    card.appendChild(brandTitle);
    const imgwrap = document.createElement('div'); imgwrap.className='imgwrap';
    const img = document.createElement('img');
    img.onerror = ()=> img.src = '/static/broken.png';
    img.src = (item.files && item.files.length) ? `/logos/${currentBatch}/${item.files[0]}` : '/static/broken.png';
    imgwrap.appendChild(img);
    card.appendChild(imgwrap);
    const info = document.createElement('div'); info.className='info';
    const count = document.createElement('div'); count.className='badge'; count.textContent = (item.files?item.files.length:0) + ' logos';
    info.appendChild(count);
    const view = document.createElement('div');
    view.innerHTML = '<button class="small" onclick="openBrand(\\'' + encodeURIComponent(item.brand) + '\\')">Open</button>';
    info.appendChild(view);
    card.appendChild(info);
    grid.appendChild(card);
  });
}

function openBrand(brand){
  // simple expand to show all logos in a modal-like new window
  const win = window.open('', '_blank', 'width=700,height=600');
  const escaped = encodeURIComponent(brand);
  win.location = `/viewer_brand?batch=${encodeURIComponent(currentBatch)}&brand=${escaped}`;
}
</script>
</body>
</html>
"""

ADMIN_TEMPLATE = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Logo Preview Pro - Admin</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{
  --bg:#0b0f14; --panel:#0f1720; --muted:#90a0b0; --text:#cfe6ef; --accent:#22c1ff; --danger:#b71c1c;
}
body{margin:0;font-family:Inter,system-ui,Segoe UI,Roboto,Arial;background:var(--bg);color:var(--text)}
.container{max-width:1200px;margin:18px auto;padding:18px}
.header{display:flex;align-items:center;justify-content:space-between}
h1{margin:0;color:var(--accent)}
.controls{display:flex;gap:10px;align-items:center}
select,input,button{background:var(--panel);border:1px solid #121722;color:var(--text);padding:8px;border-radius:8px}
.grid{display:grid;grid-template-columns:1fr 2fr;gap:18px;margin-top:18px}
.left{background:var(--panel);padding:12px;border-radius:10px;min-height:420px}
.right{background:var(--panel);padding:12px;border-radius:10px;min-height:420px;overflow:auto}
.batch-item{padding:10px;border-radius:8px;margin-bottom:8px;cursor:pointer;border:1px dashed transparent}
.batch-item:hover{border-color:#172a36}
.brand-row{display:flex;align-items:center;justify-content:space-between;padding:8px;border-radius:8px;background:rgba(0,0,0,0.15);margin-bottom:8px}
.brand-name{font-weight:600}
.logo-list{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.logo-thumb{width:120px;height:72px;border-radius:6px;overflow:hidden;background:#07111a;display:flex;align-items:center;justify-content:center;border:1px solid #0c1720}
.logo-thumb img{max-width:100%;max-height:100%;object-fit:contain}
.controls-row{display:flex;gap:8px;margin-top:10px}
.small{padding:8px 10px;border-radius:8px;cursor:pointer}
.danger{background:var(--danger);color:#fff;border:none}
.primary{background:linear-gradient(180deg,var(--accent),#0b7fb2);color:#021627;border:none}
.help{color:var(--muted);font-size:13px;margin-top:8px}
.uploader{border:2px dashed #172a36;padding:12px;border-radius:8px;text-align:center;color:var(--muted)}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>Admin Dashboard</h1>
      <div class="help">Manage batches, brands and logos. All actions are logged locally.</div>
    </div>
    <div class="controls">
      <button id="logout" class="small">Logout</button>
      <select id="batchSelect"><option value="">-- pick batch --</option>{% for b in batches %}<option value="{{b}}">{{b}}</option>{% endfor %}</select>
    </div>
  </div>

  <div class="grid">
    <div class="left">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <strong>Batches</strong>
        <button id="newBatchBtn" class="small">+ New Batch</button>
      </div>
      <div id="batchesList"></div>
      <div class="help">Create a new batch folder or click a batch to manage its brands.</div>
    </div>

    <div class="right">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <strong id="batchTitle">Select a batch</strong>
          <div class="help" id="batchInfo"></div>
        </div>
        <div>
          <button id="addBrandBtn" class="small primary">+ Add New Brand</button>
          <button id="refreshBtn" class="small">Refresh</button>
        </div>
      </div>

      <div style="margin-top:12px">
        <div class="uploader" id="dropArea">Drag & drop images here to upload (adds to brand or creates new brand)</div>
      </div>

      <div id="brandsArea" style="margin-top:12px"></div>
    </div>
  </div>
</div>

<script>
let adminToken = localStorage.getItem('admin_token_v3') || null;
if(!adminToken) { alert('Not logged in - go to / and login as admin first'); window.location = '/'; }

const batchSelect = document.getElementById('batchSelect');
const batchesList = document.getElementById('batchesList');
const batchTitle = document.getElementById('batchTitle');
const batchInfo = document.getElementById('batchInfo');
const brandsArea = document.getElementById('brandsArea');
const dropArea = document.getElementById('dropArea');

let currentBatch = '';

document.getElementById('logout').onclick = async ()=>{
  await fetch('/admin_logout',{method:'POST',headers:{'X-Admin-Token':adminToken}});
  localStorage.removeItem('admin_token_v3');
  alert('Logged out'); window.location = '/';
};

document.getElementById('refreshBtn').onclick = ()=> loadBatches();
document.getElementById('newBatchBtn').onclick = async ()=>{
  const name = prompt('New batch folder name (e.g. batch_55a):'); if(!name) return;
  const res = await fetch('/admin/create_batch',{method:'POST',headers:{'X-Admin-Token':adminToken,'Content-Type':'application/json'},body:JSON.stringify({batch:name})});
  if(!res.ok) return alert('Failed to create'); loadBatches();
};

document.getElementById('addBrandBtn').onclick = async ()=>{
  if(!currentBatch){ alert('Pick a batch'); return; }
  const brand = prompt('New brand display name (e.g. My Brand):'); if(!brand) return;
  const fileInput = document.createElement('input'); fileInput.type='file'; fileInput.accept='image/*';
  fileInput.onchange = async e => {
    const f = e.target.files[0]; if(!f) return;
    const fd = new FormData(); fd.append('file', f); fd.append('brand', brand); fd.append('batch', currentBatch);
    const res = await fetch('/admin/add_brand',{method:'POST',headers:{'X-Admin-Token':adminToken},body:fd});
    if(!res.ok) { alert('Add brand failed'); return; }
    loadBatch(currentBatch);
  };
  fileInput.click();
}

batchSelect.onchange = ()=> { chooseBatch(batchSelect.value); };

async function loadBatches(){
  batchesList.innerHTML = '';
  const res = await fetch('/api/batches');
  const arr = await res.json();
  arr.forEach(b => {
    const el = document.createElement('div'); el.className='batch-item'; el.textContent = b; el.onclick = ()=> { chooseBatch(b); batchSelect.value = b; };
    batchesList.appendChild(el);
  });
}

async function chooseBatch(batch){
  currentBatch = batch;
  batchTitle.textContent = batch;
  const res = await fetch(`/api/logos/${batch}`);
  const data = await res.json();
  batchInfo.textContent = `${data.length} brands`;
  renderBrands(data);
}

function renderBrands(list){
  brandsArea.innerHTML = '';
  if(!list || list.length===0){ brandsArea.innerHTML = '<div class="help">No brands yet</div>'; return; }
  list.forEach(item => {
    const row = document.createElement('div'); row.className='brand-row';
    const left = document.createElement('div'); left.style.display='flex'; left.style.alignItems='center'; left.style.gap='12px';
    const name = document.createElement('div'); name.className='brand-name'; name.textContent = item.brand;
    left.appendChild(name);
    const logoList = document.createElement('div'); logoList.className='logo-list';
    item.files.forEach(f => {
      const thumb = document.createElement('div'); thumb.className='logo-thumb';
      const img = document.createElement('img'); img.src = `/logos/${currentBatch}/${f}`; img.onerror = ()=> img.src = '/static/broken.png';
      thumb.appendChild(img); logoList.appendChild(thumb);
      // add small buttons over thumb
      const del = document.createElement('button'); del.className='small'; del.textContent='Delete'; del.style.marginLeft='6px';
      del.onclick = async ()=> {
        if(!confirm('Delete this logo?')) return;
        const filename = f;
        const r = await fetch('/admin/delete_logo',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Token':adminToken},body:JSON.stringify({batch:currentBatch,filename})});
        if(!r.ok) return alert('Delete failed');
        chooseBatch(currentBatch);
      };
      thumb.appendChild(del);
    });
    left.appendChild(logoList);
    row.appendChild(left);

    const right = document.createElement('div');
    const renameBtn = document.createElement('button'); renameBtn.className='small'; renameBtn.textContent='Rename';
    renameBtn.onclick = async ()=> {
      const newName = prompt('New display name:', item.brand); if(!newName) return;
      const res = await fetch('/admin/rename_brand',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Token':adminToken},body:JSON.stringify({batch:currentBatch, old_key:item.brand.replace(/\s+/g,'_'), new_key:newName.replace(/\s+/g,'_')})});
      if(!res.ok) return alert('Rename failed');
      chooseBatch(currentBatch);
    };

    const replaceBtn = document.createElement('button'); replaceBtn.className='small'; replaceBtn.textContent='Replace/Add';
    replaceBtn.onclick = ()=> {
      const input = document.createElement('input'); input.type='file'; input.accept='image/*';
      input.onchange = async e => {
        const f = e.target.files[0]; if(!f) return;
        const fd = new FormData(); fd.append('file', f); fd.append('brand', item.brand); fd.append('batch', currentBatch);
        const r = await fetch('/admin/upload_logo',{method:'POST',headers:{'X-Admin-Token':adminToken},body:fd});
        if(!r.ok) return alert('Upload failed');
        chooseBatch(currentBatch);
      };
      input.click();
    };

    const markBtn = document.createElement('button'); markBtn.className='small'; markBtn.textContent='Mark Done';
    markBtn.onclick = async ()=> {
      const r = await fetch('/admin/mark',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Token':adminToken},body:JSON.stringify({batch:currentBatch,brand:item.brand})});
      if(!r.ok) return alert('Mark failed');
      alert('Marked');
      chooseBatch(currentBatch);
    };

    right.appendChild(renameBtn); right.appendChild(replaceBtn); right.appendChild(markBtn);
    row.appendChild(right);
    brandsArea.appendChild(row);
  });
}

// Drag & drop support for batch uploads
;['dragenter','dragover','dragleave','drop'].forEach(evt => dropArea.addEventListener(evt, e => e.preventDefault()));
dropArea.addEventListener('drop', async (e) => {
  if(!currentBatch){ alert('Pick a batch first'); return; }
  const files = Array.from(e.dataTransfer.files);
  for(const f of files){
    const brand = prompt('Brand display name for this file (leave blank to use filename):', f.name.replace(/\.[^/.]+$/, '').replace(/_/g,' '));
    if(!brand) continue;
    const fd = new FormData(); fd.append('file', f); fd.append('brand', brand); fd.append('batch', currentBatch);
    await fetch('/admin/upload_logo',{method:'POST',headers:{'X-Admin-Token':adminToken},body:fd});
  }
  chooseBatch(currentBatch);
});

async function initAdmin(){
  await loadBatches();
  const q = new URLSearchParams(window.location.search).get('batch');
  if(q){ chooseBatch(q); batchSelect.value = q; }
}
initAdmin();
</script>
</body>
</html>
"""

# -------------------- ROUTES: Public viewer --------------------
@app.route("/")
def index():
    return render_template_string(INDEX_TEMPLATE, batches=scan_batches())


@app.route("/viewer_brand")
def viewer_brand():
    # simple viewer tab for a brand; used by main viewer openBrand
    batch = request.args.get('batch', '')
    brand = request.args.get('brand', '')
    if not batch or not brand:
        return "Missing params", 400
    # decode brand
    try:
        brand_dec = Path(brand).name
    except Exception:
        brand_dec = brand
    # find files
    batch_dir = STATIC_LOGOS_ROOT / batch
    if not batch_dir.exists():
        return "Batch not found", 404
    files = [p.name for p in sorted(batch_dir.iterdir()) if p.is_file() and p.name.lower().startswith(brand_dec.replace('%20',' ').replace('%2F','/').replace('_',' ').replace(' ','_').split()[0])]
    # simple list page
    html = "<h2>Brand: %s in %s</h2><div>" % (brand_dec, batch)
    for f in files:
        html += f'<div style="margin:8px"><img src="/logos/{batch}/{f}" style="max-width:400px;height:auto;border:1px solid #222;padding:6px;background:#fff" /></div>'
    html += "</div>"
    return html


# -------------------- API: batch & logos --------------------
@app.route("/api/batches")
def api_batches():
    return jsonify(scan_batches())


@app.route("/api/logos/<path:batch>")
def api_logos(batch):
    batch_dir = STATIC_LOGOS_ROOT / batch
    if not batch_dir.exists() or not batch_dir.is_dir():
        return jsonify([])
    fns = [p.name for p in sorted(batch_dir.iterdir()) if p.is_file() and allowed_ext(p.name)]
    return jsonify(group_by_brand(fns))


@app.route("/logos/<path:batch>/<path:filename>")
def serve_logo(batch, filename):
    # secure serve
    batch_dir = STATIC_LOGOS_ROOT / batch
    if not batch_dir.exists():
        return ("Not found", 404)
    requested = safe_join(batch_dir, filename)
    if not requested.exists():
        return ("Not found", 404)
    return send_from_directory(str(requested.parent), requested.name)


# -------------------- Admin auth routes --------------------
@app.route("/admin_login", methods=["POST"])
def admin_login():
    data = request.get_json() or {}
    if data.get("password") == ADMIN_PASSWORD:
        token = str(uuid.uuid4())
        ADMIN_TOKENS.add(token)
        return jsonify({"token": token})
    return jsonify({"error": "Bad password"}), 401


@app.route("/admin_logout", methods=["POST"])
def admin_logout():
    token = request.headers.get("X-Admin-Token") or (request.get_json() or {}).get("token")
    if token and token in ADMIN_TOKENS:
        ADMIN_TOKENS.discard(token)
    return jsonify({"ok": True})


# -------------------- Admin UI page --------------------
@app.route("/admin")
def admin_ui():
    token = request.headers.get("X-Admin-Token") or request.args.get("admin_token")
    # client uses localStorage token; ensure they logged in
    if not token or token not in ADMIN_TOKENS:
        # redirect to root where admin login button is shown
        return redirect(url_for('index'))
    return render_template_string(ADMIN_TEMPLATE, batches=scan_batches())


# -------------------- Admin actions --------------------
@app.route("/admin/create_batch", methods=["POST"])
def admin_create_batch():
    require_admin_token()
    data = request.get_json() or {}
    batch = data.get("batch", "")
    if not batch:
        return jsonify({"error": "Missing batch name"}), 400
    folder = STATIC_LOGOS_ROOT / batch
    try:
        folder.mkdir(parents=True, exist_ok=True)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/add_brand", methods=["POST"])
def admin_add_brand():
    require_admin_token()
    file = request.files.get("file")
    brand = request.form.get("brand")
    batch = request.form.get("batch")
    if not batch or not brand or not file:
        return jsonify({"error": "Missing data"}), 400
    if not allowed_ext(file.filename):
        return jsonify({"error": "Bad extension"}), 400
    brand_key = clean_brand_key(brand)
    batch_dir = STATIC_LOGOS_ROOT / batch
    batch_dir.mkdir(parents=True, exist_ok=True)
    # create filename with timestamp to avoid overwrite
    ext = Path(file.filename).suffix
    filename = f"{brand_key}_logo_{int(datetime.datetime.utcnow().timestamp())}{ext}"
    target = batch_dir / filename
    file.save(target)
    return jsonify({"ok": True, "filename": filename})


@app.route("/admin/upload_logo", methods=["POST"])
def admin_upload_logo():
    require_admin_token()
    file = request.files.get("file")
    brand = request.form.get("brand")
    batch = request.form.get("batch")
    if not file or not brand or not batch:
        return jsonify({"error": "Missing data"}), 400
    if not allowed_ext(file.filename):
        return jsonify({"error": "Bad extension"}), 400
    brand_key = clean_brand_key(brand)
    batch_dir = STATIC_LOGOS_ROOT / batch
    batch_dir.mkdir(parents=True, exist_ok=True)
    # store as brand_key_logo_timestamp.ext (not replacing)
    ext = Path(file.filename).suffix
    filename = f"{brand_key}_logo_{int(datetime.datetime.utcnow().timestamp())}{ext}"
    target = batch_dir / filename
    file.save(target)
    return jsonify({"ok": True, "filename": filename})


@app.route("/upload_or_replace_logo", methods=["POST"])
def upload_or_replace_logo():
    """Compatibility endpoint used by old UI - replaces existing brand logos (removes those starting with brand_key_logo)"""
    require_admin_token()
    file = request.files.get("file")
    brand = request.form.get("brand")
    batch = request.form.get("batch")
    if not file or not brand or not batch:
        return jsonify({"error": "Missing data"}), 400
    if not allowed_ext(file.filename):
        return jsonify({"error": "Bad extension"}), 400
    brand_key = clean_brand_key(brand)
    batch_dir = STATIC_LOGOS_ROOT / batch
    batch_dir.mkdir(parents=True, exist_ok=True)
    # remove existing brand_key_logo* files
    for p in batch_dir.iterdir():
        if p.is_file() and p.name.startswith(f"{brand_key}_logo"):
            try:
                p.unlink()
            except Exception:
                pass
    ext = Path(file.filename).suffix
    filename = f"{brand_key}_logo{ext}"
    target = batch_dir / filename
    file.save(target)
    return jsonify({"ok": True, "filename": filename})


@app.route("/admin/delete_logo", methods=["POST"])
def admin_delete_logo():
    require_admin_token()
    data = request.get_json() or {}
    batch = data.get("batch", "")
    filename = data.get("filename", "")
    if not batch or not filename:
        return jsonify({"error": "Missing data"}), 400
    batch_dir = STATIC_LOGOS_ROOT / batch
    if not batch_dir.exists():
        return jsonify({"error": "Batch not found"}), 404
    target = safe_join(batch_dir, filename)
    if not target.exists():
        return jsonify({"error": "File not found"}), 404
    try:
        target.unlink()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/rename_brand", methods=["POST"])
def admin_rename_brand():
    require_admin_token()
    data = request.get_json() or {}
    batch = data.get("batch", "")
    old_key = data.get("old_key", "")
    new_key_raw = data.get("new_key", "")
    if not batch or not old_key or not new_key_raw:
        return jsonify({"error": "Missing data"}), 400
    new_key = clean_brand_key(new_key_raw)
    old_key_clean = old_key
    batch_dir = STATIC_LOGOS_ROOT / batch
    if not batch_dir.exists():
        return jsonify({"error": "Batch not found"}), 404
    renamed = []
    for p in sorted(batch_dir.iterdir()):
        if p.is_file() and p.stem.startswith(old_key_clean):
            suffix = p.name[len(p.stem):]  # keeps extension
            new_name = f"{new_key}{suffix}"
            target = batch_dir / new_name
            if target.exists():
                new_name = f"{new_key}_{uuid.uuid4().hex[:6]}{suffix}"
                target = batch_dir / new_name
            p.rename(target)
            renamed.append((p.name, new_name))
    return jsonify({"renamed": renamed})


@app.route("/admin/mark", methods=["POST"])
def admin_mark():
    """Admin-only mark endpoint: saves mark in admin_marks.json"""
    require_admin_token()
    data = request.get_json() or {}
    batch = data.get("batch", "")
    brand = data.get("brand", "")
    if not batch or not brand:
        return jsonify({"error": "Missing data"}), 400
    marks = read_marks()
    key = f"{batch}::{brand}"
    marks[key] = {"marked_by": "admin", "ts": datetime.datetime.utcnow().isoformat()}
    write_marks(marks)
    return jsonify({"ok": True})


# -------------------- fallback broken image --------------------
@app.route("/static/broken.png")
def broken():
    p = BASE_DIR / "static" / "broken.png"
    if p.exists():
        return send_from_directory(str(p.parent), p.name)
    svg = "<svg xmlns='http://www.w3.org/2000/svg' width='300' height='200'><rect width='100%' height='100%' fill='#08101a'/><text x='50%' y='50%' fill='#889' font-size='16' text-anchor='middle' dominant-baseline='middle'>Image missing</text></svg>"
    return svg, 200, {"Content-Type": "image/svg+xml"}


# -------------------- start --------------------
if __name__ == "__main__":
    # ensure static broken exists
    (BASE_DIR / "static").mkdir(exist_ok=True)
    b = BASE_DIR / "static" / "broken.png"
    if not b.exists():
        try:
            import requests
            resp = requests.get("https://upload.wikimedia.org/wikipedia/commons/a/ac/No_image_available.svg", timeout=5)
            b.write_bytes(resp.content)
        except Exception:
            b.write_bytes(b"")
    print("🚀 Logo Preview Pro running at http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
