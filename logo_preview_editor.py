# logo_preview_editor.py
"""
Logo Preview Editor - All-In-One Dark Mode Version

Features:
✅ Admin login required for add/rename/delete/upload
✅ Add new brand (with progress bar)
✅ Auto-refresh after upload
✅ Delete logos directly
✅ Mark/done highlighting (deep red)
✅ Works on Render or local Flask

Run:
    python logo_preview_editor.py
Then open: http://127.0.0.1:5000
"""
import os
import uuid
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify, send_from_directory, abort

BASE_DIR = Path(__file__).parent
STATIC_LOGOS_ROOT = BASE_DIR / "static" / "logos"
STATIC_LOGOS_ROOT.mkdir(parents=True, exist_ok=True)

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"}
ADMIN_PASSWORD = "aya900"
ADMIN_TOKENS = set()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB uploads


# ---------------- HELPERS ----------------
def allowed_ext(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXT


def scan_batches():
    return sorted([p.name for p in STATIC_LOGOS_ROOT.iterdir() if p.is_dir()])


def group_by_brand(filenames):
    groups = {}
    for fn in filenames:
        stem = Path(fn).stem
        if "_logo" in stem.lower():
            brand_key = stem.rsplit("_logo", 1)[0]
        else:
            parts = stem.rsplit("_", 1)
            brand_key = parts[0] if len(parts) == 2 and parts[1].isdigit() else stem
        brand_display = brand_key.replace("_", " ")
        groups.setdefault(brand_key, {"brand": brand_display, "files": []})
        groups[brand_key]["files"].append(fn)
    return [groups[k] for k in sorted(groups.keys(), key=lambda x: groups[x]["brand"].lower())]


def safe_join(base: Path, *paths):
    p = base.joinpath(*paths).resolve()
    if not str(p).startswith(str(base.resolve())):
        abort(403)
    return p


def require_admin_token():
    token = (
        request.headers.get("X-Admin-Token")
        or request.form.get("admin_token")
        or request.args.get("admin_token")
    )
    if not token or token not in ADMIN_TOKENS:
        abort(401, "Admin token missing or invalid")


def clean_brand_key(text: str):
    import re

    s = re.sub(r'[<>:"/\\|?*]', "", text)
    s = s.strip().replace(" ", "_")
    s = re.sub(r"__+", "_", s)
    return s[:80]


# ---------------- TEMPLATE ----------------
TEMPLATE = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Logo Preview Editor</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
:root {
  --bg: #0b0f14;
  --secondary: #1c1f26;
  --text: #cfd8dc;
  --accent: #22c1ff;
  --mark: #ff1744;
  --done: #ff1744;
}
html,body{margin:0;height:100%;font-family:Inter,sans-serif;background:var(--bg);color:var(--text);}
.wrap{max-width:1300px;margin:20px auto;padding:20px;}
header{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px;}
h1{margin:0;color:var(--accent);}
.controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap;}
select,input,button{border-radius:6px;padding:6px;border:1px solid #333;background:var(--secondary);color:var(--text);}
input[type=search]{width:220px;}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:16px;margin-top:20px;}
.card{background:var(--secondary);border-radius:12px;padding:12px;position:relative;transition:transform .15s;}
.card:hover{transform:translateY(-3px);}
.card.done{box-shadow:0 0 0 3px var(--done);}
.brandTitle{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;font-weight:600;}
.imageWrap{height:130px;display:flex;align-items:center;justify-content:center;background:#07111a;border-radius:8px;overflow:hidden;margin-bottom:8px;}
.imageWrap img{max-width:100%;max-height:120px;object-fit:contain;}
.logo-list{display:none;gap:6px;flex-wrap:wrap;margin-top:6px;}
.logo-item{display:flex;align-items:center;gap:6px;}
.logo-item img{width:80px;height:56px;object-fit:contain;border-radius:4px;background:#07111a;border:1px solid #111;}
.icon-btn{background:none;border:none;color:var(--accent);cursor:pointer;font-size:15px;}
.btn{cursor:pointer;}
.small{font-size:12px;padding:4px 6px;border-radius:4px;border:1px solid #333;background:var(--secondary);color:var(--text);}
.progress-bar{width:100%;height:6px;background:#222;border-radius:4px;margin-top:4px;overflow:hidden;}
.progress-fill{height:100%;width:0;background:var(--accent);transition:width .2s;}
.delete-btn{color:#ff1744;border:1px solid #ff1744;background:none;}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Logo Preview Editor</h1>
  <div class="controls">
    <button id="loginBtn" class="btn">Admin Login</button>
    <button id="logoutBtn" class="btn" style="display:none">Logout</button>
    <button id="addBrandBtn" class="btn" style="display:none">+ Add Brand</button>
    <label>Batch:</label>
    <select id="batchSelect" onchange="onBatchChange()"><option value="">-- select batch --</option>{% for b in batches %}<option value="{{b}}">{{b}}</option>{% endfor %}</select>
    <input type="search" id="searchInput" placeholder="Search brand..." oninput="filterBrands()">
    <button onclick="reloadCurrent()" class="btn">Reload</button>
  </div>
</header>
<main>
  <div id="logoGrid" class="grid"><div style="grid-column:1/-1;color:#888">Select a batch to begin.</div></div>
</main>
</div>

<script>
let currentBatch='', brandData=[], adminToken=localStorage.getItem('admin_token_v3')||null;
let doneMap=JSON.parse(localStorage.getItem('logo_done_v3')||'{}');

function saveDone(){localStorage.setItem('logo_done_v3',JSON.stringify(doneMap));}
function saveAdminToken(){if(adminToken)localStorage.setItem('admin_token_v3',adminToken);else localStorage.removeItem('admin_token_v3');}
function setAdminUI(on){document.getElementById('loginBtn').style.display=on?'none':'inline-block';document.getElementById('logoutBtn').style.display=on?'inline-block':'none';document.getElementById('addBrandBtn').style.display=on?'inline-block':'none';}

setAdminUI(!!adminToken);

document.getElementById('loginBtn').onclick=async()=>{
  const pw=prompt('Admin password:'); if(!pw)return;
  const res=await fetch('/admin_login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})});
  if(!res.ok){alert('Wrong password');return;}
  const j=await res.json(); adminToken=j.token; saveAdminToken(); setAdminUI(true); alert('Admin logged in');
};

document.getElementById('logoutBtn').onclick=async()=>{
  await fetch('/admin_logout',{method:'POST',headers:{'X-Admin-Token':adminToken}});
  adminToken=null; saveAdminToken(); setAdminUI(false); alert('Logged out');
};

document.getElementById('addBrandBtn').onclick=()=>{
  if(!currentBatch){alert('Select a batch first');return;}
  const name=prompt('New brand name:'); if(!name)return;
  const fileInput=document.createElement('input');fileInput.type='file';fileInput.accept='image/*';
  fileInput.onchange=e=>uploadNewBrand(name,e.target.files[0]);
  fileInput.click();
};

async function uploadNewBrand(name,file){
  const fd=new FormData();
  fd.append('file',file);
  fd.append('brand',name);
  fd.append('batch',currentBatch);
  const bar=document.createElement('div');bar.className='progress-bar';
  const fill=document.createElement('div');fill.className='progress-fill';bar.appendChild(fill);
  document.body.appendChild(bar);
  const xhr=new XMLHttpRequest();
  xhr.upload.onprogress=e=>{if(e.lengthComputable){fill.style.width=(e.loaded/e.total*100)+'%';}};
  xhr.onload=()=>{bar.remove();if(xhr.status==200){alert('Uploaded');loadBatch(currentBatch);}else alert('Upload failed');};
  xhr.open('POST','/add_brand');
  xhr.setRequestHeader('X-Admin-Token',adminToken);
  xhr.send(fd);
}

function onBatchChange(){
  currentBatch=document.getElementById('batchSelect').value;
  if(!currentBatch){document.getElementById('logoGrid').innerHTML='<div style="grid-column:1/-1;color:#888">Select a batch.</div>';return;}
  loadBatch(currentBatch);
}

async function loadBatch(batch){
  const res=await fetch('/api/logos/'+batch);
  brandData=await res.json();
  renderGrid();
}

function reloadCurrent(){if(currentBatch)loadBatch(currentBatch);}
function filterBrands(){renderGrid();}

function renderGrid(){
  const grid=document.getElementById('logoGrid');
  grid.innerHTML='';
  const term=document.getElementById('searchInput').value.toLowerCase();
  const list=brandData.filter(b=>!term||b.brand.toLowerCase().includes(term));
  if(list.length==0){grid.innerHTML='<div style="grid-column:1/-1;color:#888">No matches.</div>';return;}
  list.forEach(item=>{
    const brandKey=item.brand.replace(/\s+/g,'_');
    const doneKey=currentBatch+'::'+brandKey;
    const card=document.createElement('div');
    card.className='card'; if(doneMap[doneKey])card.classList.add('done');
    const header=document.createElement('div');header.className='brandTitle';
    const nameSpan=document.createElement('div');nameSpan.textContent=item.brand;header.appendChild(nameSpan);
    if(adminToken){
      const renameBtn=document.createElement('button');renameBtn.className='icon-btn';renameBtn.textContent='✏️';renameBtn.onclick=()=>renameBrand(item.brand);
      header.appendChild(renameBtn);
      const delBtn=document.createElement('button');delBtn.className='icon-btn delete-btn';delBtn.textContent='🗑️';delBtn.onclick=()=>deleteBrand(item.brand);
      header.appendChild(delBtn);
    }
    card.appendChild(header);
    const imageWrap=document.createElement('div');imageWrap.className='imageWrap';
    const img=document.createElement('img');img.src='/logos/'+currentBatch+'/'+item.files[0];
    imageWrap.appendChild(img);card.appendChild(imageWrap);
    const mark=document.createElement('button');mark.className='small btn';mark.textContent=doneMap[doneKey]?'Marked':'Mark';
    mark.style.background=doneMap[doneKey]?'var(--done)':'var(--secondary)';
    mark.onclick=()=>{doneMap[doneKey]=!doneMap[doneKey];saveDone();mark.textContent=doneMap[doneKey]?'Marked':'Mark';mark.style.background=doneMap[doneKey]?'var(--done)':'var(--secondary)';card.classList.toggle('done');};
    card.appendChild(mark);
    grid.appendChild(card);
  });
}

async function renameBrand(oldName){
  const newName=prompt('Rename brand:',oldName);
  if(!newName||newName==oldName)return;
  const res=await fetch('/rename_brand',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Token':adminToken},body:JSON.stringify({batch:currentBatch,old_key:oldName.replace(/\s+/g,'_'),new_key:newName})});
  if(res.ok){loadBatch(currentBatch);}else alert('Rename failed');
}

async function deleteBrand(brand){
  if(!confirm('Delete brand '+brand+'?'))return;
  const res=await fetch('/delete_brand',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Token':adminToken},body:JSON.stringify({batch:currentBatch,brand:brand.replace(/\s+/g,'_')})});
  if(res.ok){loadBatch(currentBatch);}else alert('Delete failed');
}
</script>
</body>
</html>
"""

# ---------------- ROUTES ----------------
@app.route("/")
def index():
    return render_template_string(TEMPLATE, batches=scan_batches())


@app.route("/api/logos/<path:batch>")
def api_logos(batch):
    batch_dir = STATIC_LOGOS_ROOT / batch
    if not batch_dir.exists():
        return jsonify([])
    files = [p.name for p in batch_dir.iterdir() if p.is_file() and allowed_ext(p.name)]
    return jsonify(group_by_brand(files))


@app.route("/logos/<path:batch>/<path:filename>")
def serve_logo(batch, filename):
    batch_dir = STATIC_LOGOS_ROOT / batch
    requested = safe_join(batch_dir, filename)
    if not requested.exists():
        return "Not found", 404
    return send_from_directory(str(batch_dir), filename)


@app.route("/admin_login", methods=["POST"])
def admin_login():
    data = request.get_json() or {}
    if data.get("password") == ADMIN_PASSWORD:
        token = str(uuid.uuid4())
        ADMIN_TOKENS.add(token)
        return jsonify({"token": token})
    return jsonify({"error": "bad password"}), 401


@app.route("/admin_logout", methods=["POST"])
def admin_logout():
    token = request.headers.get("X-Admin-Token")
    if token in ADMIN_TOKENS:
        ADMIN_TOKENS.remove(token)
    return jsonify({"ok": True})


@app.route("/add_brand", methods=["POST"])
def add_brand():
    require_admin_token()
    file = request.files.get("file")
    brand = request.form.get("brand")
    batch = request.form.get("batch")
    if not file or not brand or not batch:
        return jsonify({"error": "missing data"}), 400
    batch_dir = STATIC_LOGOS_ROOT / batch
    batch_dir.mkdir(exist_ok=True)
    ext = Path(file.filename).suffix
    filename = f"{clean_brand_key(brand)}_logo{ext}"
    file.save(batch_dir / filename)
    return jsonify({"ok": True, "filename": filename})


@app.route("/rename_brand", methods=["POST"])
def rename_brand():
    require_admin_token()
    data = request.get_json() or {}
    batch = data.get("batch")
    old_key = data.get("old_key")
    new_key = clean_brand_key(data.get("new_key", ""))
    batch_dir = STATIC_LOGOS_ROOT / batch
    for p in batch_dir.iterdir():
        if p.is_file() and p.stem.startswith(old_key):
            p.rename(batch_dir / f"{new_key}{p.suffix}")
    return jsonify({"ok": True})


@app.route("/delete_brand", methods=["POST"])
def delete_brand():
    require_admin_token()
    data = request.get_json() or {}
    batch = data.get("batch")
    brand = data.get("brand")
    if not batch or not brand:
        return jsonify({"error": "missing data"}), 400
    batch_dir = STATIC_LOGOS_ROOT / batch
    deleted = []
    for p in batch_dir.iterdir():
        if p.is_file() and p.stem.startswith(brand):
            p.unlink()
            deleted.append(p.name)
    return jsonify({"deleted": deleted})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
