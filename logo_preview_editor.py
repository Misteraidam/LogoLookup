"""
Logo Preview Pro (Enhanced Version)
---------------------------------
✅ Single-file Flask app (HTML + CSS + JS)
✅ Works with /static/logos/<batch>/ files
✅ Admin-only Add / Rename / Delete / Mark
✅ Deep red mark color
✅ Upload progress bar + auto refresh
✅ Fixes text overflow & improves visibility
✅ NEW: Upload additional logos to existing brands
✅ NEW: Display ALL logos for each brand (grid view)
✅ NEW: Individual logo upload button per brand
✅ NEW: White backgrounds for better logo visibility
"""

import os
import uuid
from pathlib import Path
from flask import Flask, render_template_string, jsonify, request, send_from_directory, abort

# --- Setup ---
BASE_DIR = Path(__file__).parent
STATIC_LOGOS_ROOT = BASE_DIR / "static" / "logos"
STATIC_LOGOS_ROOT.mkdir(parents=True, exist_ok=True)

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"}
ADMIN_PASSWORD = "aya900"
ADMIN_TOKENS = set()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # 12MB uploads


# --- Helpers ---
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


# --- Template ---
TEMPLATE = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Logo Preview Pro</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
:root{
  --bg:#0b0f14;
  --secondary:#1c1f26;
  --text:#cfd8dc;
  --accent:#22c1ff;
  --mark:#dc143c;
}
html,body{height:100%;margin:0;font-family:Inter,sans-serif;background:var(--bg);color:var(--text);}
.wrap{max-width:1300px;margin:20px auto;padding:20px;}
header{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px;}
h1{margin:0;color:var(--accent);}
.controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap;}
select,input,button{border-radius:6px;padding:6px;border:1px solid #333;background:var(--secondary);color:var(--text);outline:none;}
input[type=search]{width:220px;}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:16px;margin-top:20px;}
.card{background:var(--secondary);border-radius:12px;padding:12px;position:relative;transition:transform .15s;overflow:hidden;}
.card:hover{transform:translateY(-3px);}
.card.done{box-shadow:0 0 0 3px var(--mark);}
.brandTitle{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;font-weight:600;word-wrap:break-word;overflow-wrap:break-word;}
.imageWrap{min-height:130px;display:flex;align-items:center;justify-content:center;background:#ffffff;border-radius:8px;overflow:hidden;margin-bottom:8px;padding:8px;}
.imageWrap img{max-width:100%;max-height:120px;object-fit:contain;}
.logo-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(80px,1fr));gap:8px;margin-top:8px;margin-bottom:8px;}
.logo-item{position:relative;height:70px;display:flex;align-items:center;justify-content:center;background:#ffffff;border-radius:6px;border:1px solid #333;overflow:hidden;cursor:pointer;transition:all 0.2s;}
.logo-item:hover{border-color:var(--accent);transform:scale(1.05);}
.logo-item.marked::after{content:'';position:absolute;top:0;left:0;right:0;bottom:0;background:rgba(220,20,60,0.7);pointer-events:none;}
.logo-item img{max-width:90%;max-height:90%;object-fit:contain;}
.icon-btn{background:none;border:none;color:var(--accent);cursor:pointer;font-size:14px;padding:2px 4px;}
.icon-btn:hover{color:#fff;}
.btn{cursor:pointer;}
.small{font-size:12px;padding:4px 8px;border-radius:4px;border:1px solid #333;background:var(--secondary);color:var(--text);cursor:pointer;margin-right:6px;}
.small:hover{background:#2a2e36;}
.progress-bar{width:100%;background:#222;height:6px;border-radius:4px;overflow:hidden;margin-top:4px;display:none;}
.progress-fill{height:100%;background:var(--accent);width:0%;transition:width 0.2s;}
.card-actions{display:flex;gap:6px;flex-wrap:wrap;align-items:center;}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Logo Preview Pro</h1>
  <div class="controls">
    <button id="loginBtn" class="btn">🔐 Admin Login</button>
    <button id="logoutBtn" class="btn" style="display:none">Logout</button>
    <button id="addBrandBtn" class="btn" style="display:none">+ Add Brand</button>
    <label>Batch:</label>
    <select id="batchSelect" onchange="onBatchChange()">
      <option value="">-- pick batch --</option>
      {% for b in batches %}<option value="{{b}}">{{b}}</option>{% endfor %}
    </select>
    <input type="search" id="searchInput" placeholder="Search brand..." oninput="filterBrands()">
    <button onclick="reloadCurrent()" class="btn">Reload</button>
  </div>
</header>
<main>
  <div id="logoGrid" class="grid"><div style="grid-column:1/-1;color:#888">Select a batch to start.</div></div>
</main>
</div>
<script>
let currentBatch='',brandData=[];
let doneMap=JSON.parse(localStorage.getItem('logo_done_v3')||'{}');
let adminToken=localStorage.getItem('admin_token_v3')||null;
const grid=document.getElementById('logoGrid');
const searchInput=document.getElementById('searchInput');

function saveDone(){localStorage.setItem('logo_done_v3',JSON.stringify(doneMap));}
function saveAdminToken(){if(adminToken)localStorage.setItem('admin_token_v3',adminToken);else localStorage.removeItem('admin_token_v3');}
function setAdminUI(loggedIn){document.getElementById('loginBtn').style.display=loggedIn?'none':'inline-block';document.getElementById('logoutBtn').style.display=loggedIn?'inline-block':'none';document.getElementById('addBrandBtn').style.display=loggedIn?'inline-block':'none';}

setAdminUI(!!adminToken);

document.getElementById('loginBtn').onclick=async ()=>{
  const pw=prompt('Enter admin password:'); if(!pw)return;
  const res=await fetch('/admin_login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})});
  if(!res.ok){alert('Login failed');return;}
  const j=await res.json();adminToken=j.token;saveAdminToken();setAdminUI(true);alert('Admin unlocked');
};

document.getElementById('logoutBtn').onclick=async ()=>{
  if(adminToken)await fetch('/admin_logout',{method:'POST',headers:{'X-Admin-Token':adminToken}});
  adminToken=null;saveAdminToken();setAdminUI(false);alert('Logged out');
};

document.getElementById('addBrandBtn').onclick=()=>{
  const name=prompt('New brand name:');if(!name)return;
  const fileInput=document.createElement('input');fileInput.type='file';fileInput.accept='image/*';
  fileInput.onchange=e=>uploadBrand(name,e.target.files[0]);
  fileInput.click();
};

async function uploadBrand(name,file){
  if(!file||!currentBatch)return;
  const fd=new FormData();
  fd.append('file',file);fd.append('brand',name);fd.append('batch',currentBatch);
  const progressBar=document.createElement('div');
  progressBar.className='progress-bar';
  progressBar.innerHTML='<div class="progress-fill"></div>';
  document.body.appendChild(progressBar);
  progressBar.style.display='block';
  const fill=progressBar.querySelector('.progress-fill');
  const xhr=new XMLHttpRequest();
  xhr.open('POST','/add_brand');
  xhr.setRequestHeader('X-Admin-Token',adminToken);
  xhr.upload.onprogress=(e)=>{if(e.lengthComputable){fill.style.width=(e.loaded/e.total*100)+'%';}};
  xhr.onload=()=>{progressBar.remove();reloadCurrent();};
  xhr.send(fd);
}

async function uploadAdditionalLogo(brandName){
  if(!currentBatch||!adminToken)return;
  const fileInput=document.createElement('input');
  fileInput.type='file';
  fileInput.accept='image/*';
  fileInput.onchange=async (e)=>{
    const file=e.target.files[0];
    if(!file)return;
    const fd=new FormData();
    fd.append('file',file);
    fd.append('brand',brandName);
    fd.append('batch',currentBatch);
    const progressBar=document.createElement('div');
    progressBar.className='progress-bar';
    progressBar.innerHTML='<div class="progress-fill"></div>';
    document.body.appendChild(progressBar);
    progressBar.style.display='block';
    const fill=progressBar.querySelector('.progress-fill');
    const xhr=new XMLHttpRequest();
    xhr.open('POST','/add_brand');
    xhr.setRequestHeader('X-Admin-Token',adminToken);
    xhr.upload.onprogress=(e)=>{if(e.lengthComputable){fill.style.width=(e.loaded/e.total*100)+'%';}};
    xhr.onload=()=>{progressBar.remove();reloadCurrent();};
    xhr.send(fd);
  };
  fileInput.click();
}

async function loadBatch(batch){
  grid.innerHTML='<div style="grid-column:1/-1;color:#888">Loading...</div>';
  try{const res=await fetch(`/api/logos/${batch}`);brandData=await res.json();renderGrid();}
  catch(e){grid.innerHTML='<div style="grid-column:1/-1;color:#888">Failed to load.</div>';}
}

function renderGrid(){
  const term=searchInput.value.toLowerCase();
  grid.innerHTML='';
  const list=brandData.filter(b=>!term||b.brand.toLowerCase().includes(term));
  if(list.length===0){grid.innerHTML='<div style="grid-column:1/-1;color:#888">No logos found.</div>';return;}
  list.forEach(item=>{
    const brandKey=item.brand.replace(/\s+/g,'_');
    const card=document.createElement('div');
    card.className='card';
    const doneKey=currentBatch+'::'+brandKey;
    if(doneMap[doneKey])card.classList.add('done');
    
    const title=document.createElement('div');
    title.className='brandTitle';
    title.textContent=item.brand;
    if(adminToken){
      const renameBtn=document.createElement('button');
      renameBtn.className='icon-btn';
      renameBtn.textContent='✏️';
      renameBtn.title='Rename brand';
      renameBtn.onclick=()=>renameBrandPrompt(item.brand);
      const delBtn=document.createElement('button');
      delBtn.className='icon-btn';
      delBtn.textContent='🗑️';
      delBtn.title='Delete brand';
      delBtn.onclick=()=>deleteBrand(item.brand);
      title.appendChild(renameBtn);
      title.appendChild(delBtn);
    }
    card.appendChild(title);
    
    const logoList=document.createElement('div');
    logoList.className='logo-list';
    item.files.forEach((fn,idx)=>{
      const logoItem=document.createElement('div');
      logoItem.className='logo-item';
      const logoKey=doneKey+'::'+fn;
      if(doneMap[logoKey])logoItem.classList.add('marked');
      
      const img=document.createElement('img');
      img.src=`/logos/${currentBatch}/${fn}`;
      logoItem.appendChild(img);
      
      logoItem.onclick=()=>{
        doneMap[logoKey]=!doneMap[logoKey];
        saveDone();
        logoItem.classList.toggle('marked');
      };
      
      logoList.appendChild(logoItem);
    });
    card.appendChild(logoList);
    
    const actions=document.createElement('div');
    actions.className='card-actions';
    
    const markBtn=document.createElement('button');
    markBtn.textContent=doneMap[doneKey]?'Marked':'Mark All';
    markBtn.className='small btn';
    markBtn.style.background=doneMap[doneKey]?'var(--mark)':'var(--secondary)';
    markBtn.onclick=()=>{
      doneMap[doneKey]=!doneMap[doneKey];
      saveDone();
      markBtn.textContent=doneMap[doneKey]?'Marked':'Mark All';
      markBtn.style.background=doneMap[doneKey]?'var(--mark)':'var(--secondary)';
      card.classList.toggle('done');
    };
    actions.appendChild(markBtn);
    
    if(adminToken){
      const addLogoBtn=document.createElement('button');
      addLogoBtn.textContent='+ Add Logo';
      addLogoBtn.className='small btn';
      addLogoBtn.onclick=()=>uploadAdditionalLogo(item.brand);
      actions.appendChild(addLogoBtn);
    }
    
    card.appendChild(actions);
    grid.appendChild(card);
  });
}

async function deleteBrand(name){
  if(!confirm('Delete all logos for '+name+'?'))return;
  const res=await fetch('/delete_brand',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Token':adminToken},body:JSON.stringify({batch:currentBatch,brand:name})});
  if(res.ok)reloadCurrent();else alert('Delete failed');
}

async function renameBrandPrompt(oldName){
  const newName=prompt('Rename brand:',oldName);
  if(!newName||newName.trim()===oldName)return;
  const res=await fetch('/rename_brand',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Token':adminToken},body:JSON.stringify({batch:currentBatch,old_key:oldName,new_key:newName})});
  if(res.ok)reloadCurrent();else alert('Rename failed');
}

function filterBrands(){renderGrid();}
function reloadCurrent(){if(currentBatch)loadBatch(currentBatch);}
function onBatchChange(){currentBatch=document.getElementById('batchSelect').value;if(!currentBatch){grid.innerHTML='<div style="grid-column:1/-1;color:#888">Select a batch to start.</div>';return;}loadBatch(currentBatch);}
</script>
</body>
</html>
"""

# --- Routes ---
@app.route("/")
def index():
    return render_template_string(TEMPLATE, batches=scan_batches())

@app.route("/api/logos/<path:batch>")
def api_logos(batch):
    batch_dir = STATIC_LOGOS_ROOT / batch
    if not batch_dir.exists(): return jsonify([])
    fns = [p.name for p in sorted(batch_dir.iterdir()) if p.is_file() and allowed_ext(p.name)]
    return jsonify(group_by_brand(fns))

@app.route("/logos/<path:batch>/<path:filename>")
def serve_logo(batch, filename):
    batch_dir = STATIC_LOGOS_ROOT / batch
    if not batch_dir.exists(): return ("Not found", 404)
    requested = safe_join(batch_dir, filename)
    if not requested.exists(): return ("Not found", 404)
    return send_from_directory(str(batch_dir), filename)

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
    token = request.headers.get("X-Admin-Token")
    if token in ADMIN_TOKENS: ADMIN_TOKENS.discard(token)
    return jsonify({"ok": True})

@app.route("/add_brand", methods=["POST"])
def add_brand():
    token = request.headers.get("X-Admin-Token")
    if token not in ADMIN_TOKENS: return jsonify({"error": "Admin required"}), 401
    file = request.files.get("file")
    brand = request.form.get("brand")
    batch = request.form.get("batch")
    if not file or not brand or not batch:
        return jsonify({"error": "Missing data"}), 400
    batch_dir = STATIC_LOGOS_ROOT / batch
    batch_dir.mkdir(exist_ok=True)
    
    brand_key = clean_brand_key(brand)
    existing = [p for p in batch_dir.iterdir() if p.stem.startswith(brand_key)]
    next_num = len(existing) + 1
    
    filename = f"{brand_key}_logo{next_num}{Path(file.filename).suffix}"
    file.save(batch_dir / filename)
    return jsonify({"ok": True})

@app.route("/rename_brand", methods=["POST"])
def rename_brand():
    token = request.headers.get("X-Admin-Token")
    if token not in ADMIN_TOKENS: return jsonify({"error": "Admin required"}), 401
    data = request.get_json() or {}
    batch = data.get("batch", "")
    old_key = clean_brand_key(data.get("old_key", ""))
    new_key = clean_brand_key(data.get("new_key", ""))
    if not batch or not old_key or not new_key:
        return jsonify({"error": "Missing data"}), 400
    batch_dir = STATIC_LOGOS_ROOT / batch
    renamed = []
    for p in sorted(batch_dir.iterdir()):
        if p.is_file() and p.stem.startswith(old_key):
            suffix = p.suffix
            target = batch_dir / f"{new_key}_logo{suffix}"
            if target.exists():
                target = batch_dir / f"{new_key}_{uuid.uuid4().int%1000}{suffix}"
            p.rename(target)
            renamed.append((p.name, target.name))
    return jsonify({"renamed": renamed})

@app.route("/delete_brand", methods=["POST"])
def delete_brand():
    token = request.headers.get("X-Admin-Token")
    if token not in ADMIN_TOKENS: return jsonify({"error": "Admin required"}), 401
    data = request.get_json() or {}
    batch = data.get("batch", "")
    brand = clean_brand_key(data.get("brand", ""))
    if not batch or not brand: return jsonify({"error": "Missing data"}), 400
    batch_dir = STATIC_LOGOS_ROOT / batch
    deleted = []
    for p in sorted(batch_dir.iterdir()):
        if p.is_file() and p.stem.startswith(brand):
            p.unlink()
            deleted.append(p.name)
    return jsonify({"deleted": deleted})

if __name__ == "__main__":
    app.run(debug=True)