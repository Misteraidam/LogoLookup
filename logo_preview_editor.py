# logo_preview_editor.py
"""
Logo Preview Editor (single-file Flask app)

Features:
- Combined preview + admin editor UI (single page)
- Reads logos from static/logos/<batch>/
- Admin password protected (default 'aya900')
- Overwrite uploads (replace existing file), add new brand, delete, rename
- Toggle multiple logos per brand
- "Mark done" persisted in browser localStorage (admin-only toggle)
- Serve logos via /logos/<batch>/<filename>

Run:
    python logo_preview_editor.py

Open:
    http://127.0.0.1:5000
"""
import os
import uuid
import shutil
from pathlib import Path
from flask import Flask, render_template_string, jsonify, request, send_from_directory, abort

# ---------- CONFIG ----------
BASE_DIR = Path(__file__).parent.resolve()
STATIC_LOGOS_ROOT = BASE_DIR / "static" / "logos"
STATIC_LOGOS_ROOT.mkdir(parents=True, exist_ok=True)

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"}
ADMIN_PASSWORD = "aya900"             # admin password (change if you like)
ADMIN_TOKENS = set()                  # in-memory tokens (fine for local use)

app = Flask(__name__, static_folder=str(BASE_DIR / "static"))
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB

# ---------- HELPERS ----------
def allowed_ext(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXT

def scan_batches():
    """Return sorted list of batch folder names under static/logos/"""
    batches = []
    for p in sorted(STATIC_LOGOS_ROOT.iterdir()):
        if p.is_dir():
            batches.append(p.name)
    return batches

def group_by_brand(filenames):
    """
    Given filenames (list of str) returns list of {brand, key, files}
    brand: display name (spaces)
    key: brand_key used in filenames (underscores)
    files: list of filenames for that brand
    """
    groups = {}
    for fn in filenames:
        stem = Path(fn).stem
        lower = stem.lower()
        if "_logo" in lower:
            brand_key = stem.rsplit("_logo", 1)[0]
        else:
            parts = stem.rsplit("_", 1)
            if len(parts) == 2 and parts[1].isdigit():
                brand_key = parts[0]
            else:
                brand_key = stem
        brand_display = brand_key.replace("_", " ")
        groups.setdefault(brand_key, {"brand": brand_display, "files": []})
        groups[brand_key]["files"].append(fn)
    # sort by brand display
    out = [groups[k] for k in sorted(groups.keys(), key=lambda x: groups[x]["brand"].lower())]
    return out

def safe_join(base: Path, *paths):
    """Return normalized path; abort if path tries to escape base"""
    p = base.joinpath(*paths).resolve()
    if str(p).startswith(str(base.resolve())):
        return p
    abort(403)

def clean_brand_key(text: str):
    import re
    s = re.sub(r'[<>:"/\\|?*]', '', text)
    s = s.strip().replace(" ", "_")
    s = re.sub(r'__+', "_", s)
    return s[:80]

def require_admin_token_from_headers():
    token = request.headers.get("X-Admin-Token") or request.form.get("admin_token") or request.args.get("admin_token")
    if not token or token not in ADMIN_TOKENS:
        abort(401, "Admin token missing or invalid")
    return token

# ---------- TEMPLATE (single-page) ----------
TEMPLATE = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>Logo Preview Editor</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0b0f14; --panel:#0f1720; --muted:#98a8b3; --text:#d7e6ef; --accent:#2ab7ff; --mark:#b71c1c;
}
*{box-sizing:border-box}
html,body{height:100%;margin:0;background:var(--bg);color:var(--text);font-family:Inter,system-ui,Segoe UI,Roboto,Arial}
.container{max-width:1200px;margin:18px auto;padding:18px}
.header{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}
h1{margin:0;color:var(--accent);font-size:20px}
.controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
select,input,button{border-radius:8px;padding:8px;border:1px solid rgba(255,255,255,0.03);background:var(--panel);color:var(--text);outline:none}
input[type=search]{width:240px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px;margin-top:16px}
.card{background:linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01));padding:12px;border-radius:10px;transition:transform .12s;position:relative}
.card:hover{transform:translateY(-4px)}
.card.done{box-shadow:0 0 0 3px rgba(183,28,28,0.12)}
.title{font-weight:600;display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.imageWrap{height:120px;display:flex;align-items:center;justify-content:center;border-radius:8px;background:#07111a;overflow:hidden;margin-bottom:8px;border:1px solid rgba(255,255,255,0.02)}
.imageWrap img{max-width:100%;max-height:110px;object-fit:contain}
.logo-list{display:none;flex-wrap:wrap;gap:8px;margin-top:8px}
.logo-item{display:flex;flex-direction:column;align-items:center;gap:6px}
.logo-item img{width:86px;height:56px;object-fit:contain;border-radius:6px;background:#07111a;border:1px solid rgba(255,255,255,0.02)}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:8px}
.btn{padding:6px 10px;border-radius:8px;border:none;background:linear-gradient(180deg,#17313c,#0f2a34);color:var(--text);cursor:pointer}
.btn.ghost{background:transparent;border:1px solid rgba(255,255,255,0.04)}
.icon-btn{background:transparent;border:none;color:var(--accent);cursor:pointer;font-size:16px}
.small{padding:6px 8px;font-size:13px;border-radius:8px}
.muted{color:var(--muted);font-size:13px}
.footer{margin-top:20px;color:var(--muted);font-size:13px}
.header .admin{display:flex;gap:8px;align-items:center}
.hidden-file{display:none}
.badge{background:rgba(255,255,255,0.02);padding:4px 8px;border-radius:999px;color:var(--muted);font-size:12px}
.rename{width:160px;padding:6px;border-radius:6px;background:#0b1418;border:1px solid rgba(255,255,255,0.02);color:var(--text)}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>Logo Preview Editor</h1>
      <div class="muted">Combined preview + admin editor — batches folder: <strong>/static/logos/</strong></div>
    </div>

    <div class="controls">
      <div class="admin" id="adminControls">
        <button id="loginBtn" class="btn">Admin Login</button>
        <button id="logoutBtn" class="btn" style="display:none">Logout</button>
        <button id="addBrandBtn" class="btn" style="display:none">+ Add New Brand</button>
      </div>

      <label class="muted">Batch:</label>
      <select id="batchSelect" onchange="onBatchChange()">
        <option value="">-- pick batch --</option>
        {% for b in batches %}
          <option value="{{b}}">{{b}}</option>
        {% endfor %}
      </select>

      <input id="search" type="search" placeholder="Search brand..." oninput="filterBrands()" />
      <button class="btn ghost" onclick="reloadBatch()">Reload</button>
    </div>
  </div>

  <div id="grid" class="grid">
    <div style="grid-column:1/-1;color:var(--muted)">Select a batch to start.</div>
  </div>

  <div class="footer muted">
    Tip: Admin can add/replace/delete/rename. "Mark" (done) persists in browser localStorage.
  </div>
</div>

<script>
const grid = document.getElementById('grid');
const batchSelect = document.getElementById('batchSelect');
const searchInput = document.getElementById('search');
const loginBtn = document.getElementById('loginBtn');
const logoutBtn = document.getElementById('logoutBtn');
const addBrandBtn = document.getElementById('addBrandBtn');

let currentBatch = '';
let data = []; // [{brand, files: []}]
let adminToken = sessionStorage.getItem('admin_token') || null;
let doneMap = JSON.parse(localStorage.getItem('lp_done') || '{}');

function setAdminUI(v){
  loginBtn.style.display = v ? 'none' : 'inline-block';
  logoutBtn.style.display = v ? 'inline-block' : 'none';
  addBrandBtn.style.display = v ? 'inline-block' : 'none';
}
setAdminUI(!!adminToken);

loginBtn.onclick = async () => {
  const pw = prompt('Enter admin password:');
  if(!pw) return;
  try {
    const res = await fetch('/admin_login', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({password: pw})
    });
    if(!res.ok){ alert('Login failed'); return; }
    const j = await res.json();
    adminToken = j.token;
    sessionStorage.setItem('admin_token', adminToken);
    setAdminUI(true);
    alert('Admin unlocked');
  } catch(e){ alert('Login error'); console.error(e); }
}

logoutBtn.onclick = async () => {
  if(!adminToken) return;
  await fetch('/admin_logout', {method:'POST', headers: {'Content-Type':'application/json','X-Admin-Token': adminToken}, body: JSON.stringify({token: adminToken})});
  adminToken = null; sessionStorage.removeItem('admin_token');
  setAdminUI(false); alert('Logged out');
}

addBrandBtn.onclick = () => {
  if(!currentBatch){ alert('Pick batch first'); return; }
  const name = prompt('New brand name:');
  if(!name) return;
  const input = document.createElement('input'); input.type='file'; input.accept='image/*';
  input.onchange = async (e) => {
    const f = e.target.files[0]; if(!f) return;
    await addNewBrand(name, f);
  };
  input.click();
};

async function addNewBrand(name, file){
  if(!adminToken){ alert('Admin required'); return; }
  const fd = new FormData();
  fd.append('brand', name);
  fd.append('batch', currentBatch);
  fd.append('file', file, file.name);
  const res = await fetch('/add_brand', {method:'POST', body: fd, headers: {'X-Admin-Token': adminToken}});
  if(!res.ok){ const j = await res.json().catch(()=>({})); alert('Add brand failed: '+(j.error||res.status)); return; }
  await loadBatch(currentBatch);
}

function onBatchChange(){
  currentBatch = batchSelect.value;
  searchInput.value = '';
  if(!currentBatch){
    grid.innerHTML = '<div style="grid-column:1/-1;color:var(--muted)">Select a batch to start.</div>';
    return;
  }
  loadBatch(currentBatch);
}

function reloadBatch(){ if(currentBatch) loadBatch(currentBatch); }

async function loadBatch(batch){
  grid.innerHTML = '';
  // skeleton placeholders
  for(let i=0;i<6;i++){ const s = document.createElement('div'); s.style.height='120px'; s.className='card'; s.style.opacity=0.6; grid.appendChild(s); }
  try{
    const res = await fetch(`/api/logos/${batch}`);
    data = await res.json();
    renderGrid();
  }catch(e){
    grid.innerHTML = '<div style="grid-column:1/-1;color:var(--muted)">Failed to load batch.</div>';
    console.error(e);
  }
}

function renderGrid(){
  const q = (searchInput.value||'').toLowerCase().trim();
  grid.innerHTML = '';
  if(!data || data.length===0){
    grid.innerHTML = '<div style="grid-column:1/-1;color:var(--muted)">No logos found in this batch folder.</div>';
    return;
  }
  const list = data.filter(b => !q || b.brand.toLowerCase().includes(q));
  if(list.length===0){ grid.innerHTML = '<div style="grid-column:1/-1;color:var(--muted)">No matches.</div>'; return; }

  list.forEach(item=>{
    const brandKey = item.brand.replace(/\s+/g,'_');
    const doneKey = `${currentBatch}::${brandKey}`;
    const card = document.createElement('div'); card.className='card'; if(doneMap[doneKey]) card.classList.add('done');

    const title = document.createElement('div'); title.className='title';
    const name = document.createElement('div'); name.textContent = item.brand;
    title.appendChild(name);

    if(adminToken){
      const renameBtn = document.createElement('button'); renameBtn.className='icon-btn'; renameBtn.title='Rename';
      renameBtn.textContent = '✏️'; renameBtn.onclick = ()=> renameBrand(item.brand);
      const delBrandBtn = document.createElement('button'); delBrandBtn.className='icon-btn'; delBrandBtn.title='Delete brand (remove all files)';
      delBrandBtn.textContent = '🗑️'; delBrandBtn.onclick = ()=> deleteBrandConfirm(brandKey);
      title.appendChild(renameBtn); title.appendChild(delBrandBtn);
    }
    card.appendChild(title);

    const imgWrap = document.createElement('div'); imgWrap.className='imageWrap';
    const mainImg = document.createElement('img'); mainImg.alt = item.brand;
    mainImg.src = getFirstSrc(currentBatch, brandKey, item.files);
    mainImg.onerror = ()=> mainImg.src='/static/broken.png';
    imgWrap.appendChild(mainImg);
    card.appendChild(imgWrap);

    // small logos list (toggle)
    const logosDiv = document.createElement('div'); logosDiv.className='logo-list';
    const all = getAllSrcs(currentBatch, brandKey, item.files);
    all.forEach(s => {
      const li = document.createElement('div'); li.className='logo-item';
      const sm = document.createElement('img'); sm.src = s; sm.onerror = ()=> sm.src='/static/broken.png';
      const lbl = document.createElement('div'); lbl.className='muted'; lbl.style.fontSize='12px'; lbl.style.maxWidth='90px'; lbl.style.overflow='hidden'; lbl.style.textOverflow='ellipsis'; lbl.style.whiteSpace='nowrap';
      lbl.textContent = s.split('/').pop();
      li.appendChild(sm); li.appendChild(lbl);

      if(adminToken){
        const overwriteBtn = document.createElement('button'); overwriteBtn.className='small'; overwriteBtn.textContent='Replace';
        overwriteBtn.onclick = ()=> chooseFileToReplace(s);
        const del = document.createElement('button'); del.className='small'; del.textContent='Delete';
        del.onclick = ()=> deleteLogoConfirm(s);
        li.appendChild(overwriteBtn); li.appendChild(del);
      }

      logosDiv.appendChild(li);
    });
    card.appendChild(logosDiv);

    // actions row
    const row = document.createElement('div'); row.className='row';
    const toggleBtn = document.createElement('button'); toggleBtn.className='small btn'; toggleBtn.textContent = 'Show all logos';
    toggleBtn.onclick = ()=> {
      const visible = logosDiv.style.display === 'flex';
      logosDiv.style.display = visible ? 'none' : 'flex';
      logosDiv.style.flexWrap = 'wrap';
      toggleBtn.textContent = visible ? 'Show all logos' : 'Hide logos';
    };
    row.appendChild(toggleBtn);

    if(adminToken){
      const addBtn = document.createElement('button'); addBtn.className='small btn'; addBtn.textContent = '+ Add logo';
      addBtn.onclick = ()=> chooseFileToAdd(brandKey);
      row.appendChild(addBtn);
    }

    const markBtn = document.createElement('button'); markBtn.className='small btn';
    markBtn.textContent = doneMap[doneKey] ? 'Marked' : 'Mark';
    markBtn.style.background = doneMap[doneKey] ? 'var(--mark)' : '';
    markBtn.onclick = async ()=> {
      if(!adminToken){ alert('Admin only'); return; }
      doneMap[doneKey] = !doneMap[doneKey];
      localStorage.setItem('lp_done', JSON.stringify(doneMap));
      markBtn.textContent = doneMap[doneKey] ? 'Marked' : 'Mark';
      markBtn.style.background = doneMap[doneKey] ? 'var(--mark)' : '';
      card.classList.toggle('done');
    };
    row.appendChild(markBtn);

    card.appendChild(row);
    grid.appendChild(card);
  });
}

// helpers for sources
function getFirstSrc(batch, brandKey, files){
  // priority: overrides (session/local) are not persisted to server on this version; the server files are canonical.
  if(files && files.length) return `/logos/${batch}/${files[0]}`;
  return '/static/broken.png';
}
function getAllSrcs(batch, brandKey, files){
  const arr = [];
  if(files && files.length) files.forEach(f => arr.push(`/logos/${batch}/${f}`));
  return arr;
}

// admin actions
function chooseFileToReplace(url){
  if(!adminToken){ alert('Admin only'); return; }
  // extract filename
  const filename = url.split('/').pop();
  const input = document.createElement('input'); input.type='file'; input.accept='image/*';
  input.onchange = async (e) => {
    const f = e.target.files[0]; if(!f) return;
    await uploadReplace(currentBatch, filename, f);
  };
  input.click();
}

function chooseFileToAdd(brandKey){
  if(!adminToken){ alert('Admin only'); return; }
  const input = document.createElement('input'); input.type='file'; input.accept='image/*';
  input.onchange = async (e) => {
    const f = e.target.files[0]; if(!f) return;
    await uploadAddToBrand(currentBatch, brandKey, f);
  };
  input.click();
}

async function uploadReplace(batch, filename, file){
  if(!adminToken){ alert('Admin only'); return; }
  const fd = new FormData();
  fd.append('file', file, filename); // use same filename to overwrite
  fd.append('batch', batch);
  fd.append('target', filename);
  const res = await fetch('/upload', { method:'POST', body: fd, headers: {'X-Admin-Token': adminToken} });
  const j = await res.json().catch(()=>({}));
  if(!res.ok){ alert('Replace failed: '+(j.error||res.status)); return; }
  await loadBatch(batch);
}

async function uploadAddToBrand(batch, brandKey, file){
  if(!adminToken){ alert('Admin only'); return; }
  // generate new filename: <brandKey>_logo<next><ext>
  const ext = (file.name && file.name.includes('.')) ? file.name.slice(file.name.lastIndexOf('.')) : '.png';
  // ask server for next index or let server handle; we will request 'add_logo' endpoint
  const fd = new FormData();
  fd.append('file', file, `${brandKey}_logo_new${ext}`);
  fd.append('batch', batch);
  fd.append('brand_key', brandKey);
  const res = await fetch('/add_logo', {method:'POST', body: fd, headers: {'X-Admin-Token': adminToken}});
  const j = await res.json().catch(()=>({}));
  if(!res.ok){ alert('Add logo failed: '+(j.error||res.status)); return; }
  await loadBatch(batch);
}

async function deleteLogoConfirm(url){
  if(!adminToken){ alert('Admin only'); return; }
  if(!confirm('Delete this logo?')) return;
  const filename = url.split('/').pop();
  const res = await fetch('/delete_logo', {method:'POST', headers: {'Content-Type':'application/json','X-Admin-Token': adminToken}, body: JSON.stringify({batch: currentBatch, filename})});
  const j = await res.json().catch(()=>({}));
  if(!res.ok){ alert('Delete failed: '+(j.error||res.status)); return; }
  await loadBatch(currentBatch);
}

async function deleteBrandConfirm(brandKey){
  if(!adminToken){ alert('Admin only'); return; }
  if(!confirm('Delete all logos for this brand? This will remove files from disk.')) return;
  const res = await fetch('/delete_brand', {method:'POST', headers: {'Content-Type':'application/json','X-Admin-Token': adminToken}, body: JSON.stringify({batch: currentBatch, brand_key: brandKey})});
  const j = await res.json().catch(()=>({}));
  if(!res.ok){ alert('Delete brand failed: '+(j.error||res.status)); return; }
  await loadBatch(currentBatch);
}

async function renameBrand(oldDisplay){
  if(!adminToken){ alert('Admin only'); return; }
  const newName = prompt('Rename brand (display name):', oldDisplay);
  if(!newName || newName.trim()===oldDisplay) return;
  const oldKey = oldDisplay.replace(/\s+/g,'_');
  const newKey = newName.replace(/\s+/g,'_');
  const res = await fetch('/rename_brand', {method:'POST', headers: {'Content-Type':'application/json','X-Admin-Token': adminToken}, body: JSON.stringify({batch: currentBatch, old_key: oldKey, new_key: newKey})});
  const j = await res.json().catch(()=>({}));
  if(!res.ok){ alert('Rename failed: '+(j.error||res.status)); return; }
  await loadBatch(currentBatch);
}

function filterBrands(){ renderGrid(); }

// init
(function(){
  if(adminToken) setAdminUI(true);
})();
</script>
</body>
</html>
"""

# ---------- ROUTES ----------
@app.route("/")
def index():
    batches = scan_batches()
    return render_template_string(TEMPLATE, batches=batches)

@app.route("/api/logos/<path:batch>")
def api_logos(batch):
    batch_dir = STATIC_LOGOS_ROOT / batch
    if not batch_dir.exists() or not batch_dir.is_dir():
        return jsonify([])
    fns = [p.name for p in sorted(batch_dir.iterdir()) if p.is_file() and allowed_ext(p.name)]
    grouped = group_by_brand(fns)
    return jsonify(grouped)

@app.route("/logos/<path:batch>/<path:filename>")
def serve_logo(batch, filename):
    batch_dir = STATIC_LOGOS_ROOT / batch
    if not batch_dir.exists():
        return ("Not found", 404)
    requested = safe_join(batch_dir, filename)
    if not requested.exists():
        return ("Not found", 404)
    return send_from_directory(str(batch_dir), filename)

# ---------- Admin endpoints ----------
@app.route("/admin_login", methods=["POST"])
def admin_login():
    data = request.get_json() or {}
    if data.get("password") == ADMIN_PASSWORD:
        token = str(uuid.uuid4())
        ADMIN_TOKENS.add(token)
        return jsonify({"token": token})
    return (jsonify({"error": "Bad password"}), 401)

@app.route("/admin_logout", methods=["POST"])
def admin_logout():
    data = request.get_json() or {}
    token = data.get("token") or request.headers.get("X-Admin-Token")
    if token and token in ADMIN_TOKENS:
        ADMIN_TOKENS.discard(token)
    return jsonify({"ok": True})

@app.route("/upload", methods=["POST"])
def upload():
    # Overwrite upload: requires admin token
    token = request.headers.get("X-Admin-Token") or request.form.get("admin_token")
    if not token or token not in ADMIN_TOKENS:
        return (jsonify({"error": "Admin token required"}), 401)

    batch = request.form.get("batch", "")
    target = request.form.get("target", "")  # optional -> overwrite filename
    file = request.files.get("file")
    if not file or not batch:
        return (jsonify({"error": "Missing file or batch"}), 400)
    filename = target or file.filename
    filename = os.path.basename(filename)
    if not allowed_ext(filename):
        return (jsonify({"error": "Bad extension"}), 400)
    batch_dir = STATIC_LOGOS_ROOT / batch
    batch_dir.mkdir(parents=True, exist_ok=True)
    save_path = batch_dir / filename
    # Overwrite existing file: simply save (this will replace)
    file.save(str(save_path))
    return jsonify({"success": True, "filename": filename})

@app.route("/add_brand", methods=["POST"])
def add_brand():
    token = request.headers.get("X-Admin-Token")
    if not token or token not in ADMIN_TOKENS:
        return (jsonify({"error": "Admin token required"}), 401)
    brand = request.form.get("brand", "")
    batch = request.form.get("batch", "")
    file = request.files.get("file")
    if not brand or not batch or not file:
        return (jsonify({"error": "Missing data"}), 400)
    batch_dir = STATIC_LOGOS_ROOT / batch
    batch_dir.mkdir(parents=True, exist_ok=True)
    brand_key = clean_brand_key(brand)
    ext = Path(file.filename).suffix or ".png"
    filename = f"{brand_key}_logo1{ext}"
    file.save(batch_dir / filename)
    return jsonify({"ok": True, "filename": filename})

@app.route("/add_logo", methods=["POST"])
def add_logo():
    token = request.headers.get("X-Admin-Token")
    if not token or token not in ADMIN_TOKENS:
        return (jsonify({"error": "Admin token required"}), 401)
    batch = request.form.get("batch", "")
    brand_key = request.form.get("brand_key", "")
    file = request.files.get("file")
    if not batch or not brand_key or not file:
        return (jsonify({"error": "Missing data"}), 400)
    batch_dir = STATIC_LOGOS_ROOT / batch
    batch_dir.mkdir(parents=True, exist_ok=True)
    # compute next index
    existing = [p for p in batch_dir.iterdir() if p.is_file() and p.stem.startswith(brand_key)]
    nums = []
    for p in existing:
        s = p.stem
        # find trailing digits after '_logo' or last underscore
        if "_logo" in s:
            base, rest = s.rsplit("_logo", 1)
            try:
                nums.append(int(rest))
            except:
                pass
    next_idx = max(nums) + 1 if nums else (len(existing) + 1)
    ext = Path(file.filename).suffix or ".png"
    filename = f"{brand_key}_logo{next_idx}{ext}"
    file.save(batch_dir / filename)
    return jsonify({"ok": True, "filename": filename})

@app.route("/delete_logo", methods=["POST"])
def delete_logo():
    token = request.headers.get("X-Admin-Token")
    if not token or token not in ADMIN_TOKENS:
        return (jsonify({"error": "Admin token required"}), 401)
    data = request.get_json() or {}
    batch = data.get("batch", "")
    filename = data.get("filename", "")
    if not batch or not filename:
        return (jsonify({"error": "Missing data"}), 400)
    batch_dir = STATIC_LOGOS_ROOT / batch
    if not batch_dir.exists():
        return (jsonify({"error": "Batch not found"}), 404)
    target = safe_join(batch_dir, filename)
    if target.exists():
        try:
            target.unlink()
            return jsonify({"success": True})
        except Exception as e:
            return (jsonify({"error": str(e)}), 500)
    return (jsonify({"error": "File not found"}), 404)

@app.route("/delete_brand", methods=["POST"])
def delete_brand():
    token = request.headers.get("X-Admin-Token")
    if not token or token not in ADMIN_TOKENS:
        return (jsonify({"error": "Admin token required"}), 401)
    data = request.get_json() or {}
    batch = data.get("batch", "")
    brand_key = data.get("brand_key", "")
    if not batch or not brand_key:
        return (jsonify({"error": "Missing data"}), 400)
    batch_dir = STATIC_LOGOS_ROOT / batch
    if not batch_dir.exists(): return (jsonify({"error":"Batch not found"}), 404)
    removed = []
    for p in list(batch_dir.iterdir()):
        if p.is_file() and p.stem.startswith(brand_key):
            try:
                p.unlink()
                removed.append(p.name)
            except: pass
    return jsonify({"removed": removed})

@app.route("/rename_brand", methods=["POST"])
def rename_brand():
    token = request.headers.get("X-Admin-Token")
    if not token or token not in ADMIN_TOKENS:
        return (jsonify({"error": "Admin token required"}), 401)
    data = request.get_json() or {}
    batch = data.get("batch", "")
    old_key = data.get("old_key", "")
    new_key = clean_brand_key(data.get("new_key", ""))
    if not batch or not old_key or not new_key:
        return (jsonify({"error": "Missing data"}), 400)
    batch_dir = STATIC_LOGOS_ROOT / batch
    if not batch_dir.exists(): return (jsonify({"error": "Batch not found"}), 404)
    renamed = []
    for p in sorted(batch_dir.iterdir()):
        if p.is_file() and p.stem.startswith(old_key):
            suffix = p.name[len(p.stem):]  # includes extension
            new_name = f"{new_key}{suffix}"
            target = batch_dir / new_name
            if target.exists():
                new_name = f"{new_key}_{uuid.uuid4().hex[:6]}{suffix}"
                target = batch_dir / new_name
            p.rename(target)
            renamed.append((p.name, new_name))
    return jsonify({"renamed": renamed})

# static fallback for broken image
@app.route("/static/broken.png")
def broken():
    p = BASE_DIR / "static" / "broken.png"
    if p.exists():
        return send_from_directory(str(p.parent), p.name)
    svg = "<svg xmlns='http://www.w3.org/2000/svg' width='400' height='200'><rect width='100%' height='100%' fill='#08101a'/><text x='50%' y='50%' fill='#889' font-size='16' text-anchor='middle' dominant-baseline='middle'>No image</text></svg>"
    return svg, 200, {"Content-Type": "image/svg+xml"}

# ---------- START ----------
if __name__ == "__main__":
    print("🚀 Logo Preview Editor running at http://127.0.0.1:5000")
    print(f"  • Logos root: {STATIC_LOGOS_ROOT}")
    app.run(host="127.0.0.1", port=5000, debug=True)
