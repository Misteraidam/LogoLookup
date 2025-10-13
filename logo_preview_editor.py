# logo_preview_pro.py
"""
Logo Preview Pro - Dark Mode
Single-file Flask app:
- Admin login required for add/rename/upload/delete
- Add new brand, add logo to brand
- Toggle multiple logos
- Mark done (client-side persisted)
- Dark interface, ChatGPT-style
- Files saved to static/logos/<batch>/

Run:
    python logo_preview_pro.py
Open:
    http://127.0.0.1:5000
"""
import os
import uuid
from pathlib import Path
from flask import Flask, render_template_string, jsonify, request, send_from_directory, abort

BASE_DIR = Path(__file__).parent
STATIC_LOGOS_ROOT = BASE_DIR / "static" / "logos"
STATIC_LOGOS_ROOT.mkdir(parents=True, exist_ok=True)
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"}
ADMIN_PASSWORD = "aya900"
ADMIN_TOKENS = set()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # 12MB uploads

# ---------- HELPERS ----------
def allowed_ext(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXT

def scan_batches():
    return sorted([p.name for p in STATIC_LOGOS_ROOT.iterdir() if p.is_dir()])

def group_by_brand(filenames):
    groups = {}
    for fn in filenames:
        stem = Path(fn).stem
        if "_logo" in stem.lower():
            brand_key = stem.rsplit("_logo",1)[0]
        else:
            parts = stem.rsplit("_",1)
            brand_key = parts[0] if len(parts)==2 and parts[1].isdigit() else stem
        brand_display = brand_key.replace("_"," ")
        groups.setdefault(brand_key, {"brand":brand_display, "files":[]})
        groups[brand_key]["files"].append(fn)
    return [groups[k] for k in sorted(groups.keys(), key=lambda x: groups[x]["brand"].lower())]

def safe_join(base: Path, *paths):
    p = base.joinpath(*paths).resolve()
    if str(p).startswith(str(base.resolve())):
        return p
    abort(403)

def require_admin_token():
    token = request.headers.get("X-Admin-Token") or request.form.get("admin_token") or request.args.get("admin_token")
    if not token or token not in ADMIN_TOKENS:
        abort(401, "Admin token missing or invalid")

def clean_brand_key(text: str):
    import re
    s = re.sub(r'[<>:"/\\|?*]', '', text)
    s = s.strip().replace(" ", "_")
    s = re.sub(r'__+', "_", s)
    return s[:80]

# ---------- TEMPLATE ----------
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
  --bg:#0b0f14; --secondary:#1c1f26; --text:#cfd8dc; --accent:#22c1ff; --mark:#b71c1c; --done:#b71c1c;
}
html,body{height:100%;margin:0;font-family:Inter,sans-serif;background:var(--bg);color:var(--text);}
.wrap{max-width:1300px;margin:20px auto;padding:20px;}
header{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px;}
h1{margin:0;color:var(--accent);}
.controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap;}
select,input,button{border-radius:6px;padding:6px;border:1px solid #333;background:var(--secondary);color:var(--text);outline:none;}
input[type=search]{width:220px;}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:16px;margin-top:20px;}
.card{background:var(--secondary);border-radius:12px;padding:12px;position:relative;transition:transform .15s;}
.card:hover{transform:translateY(-3px);}
.card.done{box-shadow:0 0 0 2px var(--done);}
.brandTitle{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;font-weight:600;}
.imageWrap{height:130px;display:flex;align-items:center;justify-content:center;background:#07111a;border-radius:8px;overflow:hidden;margin-bottom:8px;}
.imageWrap img{max-width:100%;max-height:120px;object-fit:contain;}
.logo-list{display:none;gap:6px;flex-wrap:wrap;margin-top:6px;}
.logo-item{display:flex;align-items:center;gap:6px;}
.logo-item img{width:80px;height:56px;object-fit:contain;border-radius:4px;background:#07111a;border:1px solid #111;}
.icon-btn{background:none;border:none;color:var(--accent);cursor:pointer;}
.btn{cursor:pointer;}
.small{font-size:12px;padding:4px 6px;border-radius:4px;border:1px solid #333;background:var(--secondary);color:var(--text);}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Logo Preview Pro</h1>
  <div class="controls">
    <div id="adminBar">
      <button id="loginBtn" class="btn">Admin Login</button>
      <button id="logoutBtn" class="btn" style="display:none">Logout</button>
      <button id="addBrandBtn" class="btn" style="display:none">+ Add New Brand</button>
    </div>
    <label>Batch:</label>
    <select id="batchSelect" onchange="onBatchChange()"><option value="">-- pick batch --</option>{% for b in batches %}<option value="{{b}}">{{b}}</option>{% endfor %}</select>
    <input type="search" id="searchInput" placeholder="Search brand..." oninput="filterBrands()">
    <button onclick="reloadCurrent()" class="btn">Reload</button>
  </div>
</header>
<main>
  <div id="logoGrid" class="grid"><div style="grid-column:1/-1;color:#888">Select a batch to start.</div></div>
</main>
</div>
<script>
let currentBatch='';
let brandData=[];
let overrides=JSON.parse(localStorage.getItem('logo_overrides_v3')||'{}');
let doneMap=JSON.parse(localStorage.getItem('logo_done_v3')||'{}');
let adminToken=localStorage.getItem('admin_token_v3')||null;

function saveOverrides(){localStorage.setItem('logo_overrides_v3',JSON.stringify(overrides));}
function saveDone(){localStorage.setItem('logo_done_v3',JSON.stringify(doneMap));}
function saveAdminToken(){if(adminToken)localStorage.setItem('admin_token_v3',adminToken);else localStorage.removeItem('admin_token_v3');}

function setAdminUI(loggedIn){
  document.getElementById('loginBtn').style.display=loggedIn?'none':'inline-block';
  document.getElementById('logoutBtn').style.display=loggedIn?'inline-block':'none';
  document.getElementById('addBrandBtn').style.display=loggedIn?'inline-block':'none';
}
setAdminUI(!!adminToken);

document.getElementById('loginBtn').onclick=async ()=>{
  const pw=prompt('Enter admin password:'); if(!pw) return;
  const res=await fetch('/admin_login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})});
  if(!res.ok){alert('Login failed'); return;}
  const j=await res.json(); adminToken=j.token; saveAdminToken(); setAdminUI(true); alert('Admin unlocked');
};

document.getElementById('logoutBtn').onclick=async ()=>{
  if(adminToken) await fetch('/admin_logout',{method:'POST',headers:{'X-Admin-Token':adminToken},body:JSON.stringify({token:adminToken})});
  adminToken=null; saveAdminToken(); setAdminUI(false); alert('Logged out');
};

document.getElementById('addBrandBtn').onclick=()=>{
  const name=prompt('New brand name:'); if(!name) return;
  const fileInput=document.createElement('input'); fileInput.type='file'; fileInput.accept='image/*';
  fileInput.onchange=async (e)=>{await uploadNewBrand(name,e.target.files[0]);};
  fileInput.click();
};

async function uploadNewBrand(name,file){
  const fd=new FormData(); fd.append('file',file); fd.append('brand',name); fd.append('batch',currentBatch);
  const res=await fetch('/add_brand',{method:'POST',body:fd,headers:{'X-Admin-Token':adminToken}});
  if(!res.ok){alert('Failed'); return;} renderGrid(); 
}

function onBatchChange(){currentBatch=document.getElementById('batchSelect').value;searchInput.value='';if(!currentBatch){grid.innerHTML='<div style="grid-column:1/-1;color:#888">Select a batch to start.</div>';return;} loadBatch(currentBatch);}
function reloadCurrent(){if(currentBatch) loadBatch(currentBatch);}
async function loadBatch(batch){grid.innerHTML='';for(let i=0;i<6;i++){const sk=document.createElement('div');sk.style.height='120px';grid.appendChild(sk);}
  try{const res=await fetch(`/api/logos/${batch}`);brandData=await res.json();renderGrid();}catch(e){grid.innerHTML='<div style="grid-column:1/-1;color:#888">Failed to load batch.</div>';}
}

const grid=document.getElementById('logoGrid');
const searchInput=document.getElementById('searchInput');

function renderGrid(){
  const term=searchInput.value.toLowerCase();
  grid.innerHTML='';
  if(!brandData||brandData.length===0){grid.innerHTML='<div style="grid-column:1/-1;color:#888">No logos found.</div>';return;}
  const list=brandData.filter(b=>!term||b.brand.toLowerCase().includes(term));
  if(list.length===0){grid.innerHTML='<div style="grid-column:1/-1;color:#888">No matches.</div>';return;}
  list.forEach(item=>{
    const brandKey=item.brand.replace(/\s+/g,'_'); const card=document.createElement('div'); card.className='card'; const doneKey=currentBatch+'::'+brandKey; if(doneMap[doneKey]) card.classList.add('done');
    const inner=document.createElement('div');
    const titleDiv=document.createElement('div'); titleDiv.className='brandTitle'; const nameSpan=document.createElement('div'); nameSpan.textContent=item.brand; titleDiv.appendChild(nameSpan);
    if(adminToken){const renameBtn=document.createElement('button');renameBtn.className='icon-btn';renameBtn.innerHTML='✏️'; renameBtn.onclick=()=>renameBrandPrompt(item.brand); titleDiv.appendChild(renameBtn);}
    inner.appendChild(titleDiv);
    const imageWrap=document.createElement('div'); imageWrap.className='imageWrap';
    const img=document.createElement('img'); img.src=getFirstSrc(currentBatch,brandKey,item.files); imageWrap.appendChild(img); inner.appendChild(imageWrap);
    const logoList=document.createElement('div'); logoList.className='logo-list'; const all=getAllSrcs(currentBatch,brandKey,item.files);
    all.forEach(s=>{const li=document.createElement('div'); li.className='logo-item'; const smallImg=document.createElement('img'); smallImg.src=s; li.appendChild(smallImg); logoList.appendChild(li);});
    inner.appendChild(logoList);
    const toggleBtn=document.createElement('button'); toggleBtn.textContent='Show all logos'; toggleBtn.className='small btn'; toggleBtn.onclick=()=>{logoList.style.display=logoList.style.display==='flex'?'none':'flex'; toggleBtn.textContent=logoList.style.display==='flex'?'Hide logos':'Show all logos';};
    inner.appendChild(toggleBtn);
    const markBtn=document.createElement('button'); markBtn.textContent=doneMap[doneKey]?'Marked':'Mark'; markBtn.className='small btn'; markBtn.style.background=doneMap[doneKey]? 'var(--done)':'var(--secondary)'; markBtn.onclick=()=>{doneMap[doneKey]=!doneMap[doneKey]; saveDone(); markBtn.textContent=doneMap[doneKey]?'Marked':'Mark'; markBtn.style.background=doneMap[doneKey]?'var(--done)':'var(--secondary)'; card.classList.toggle('done');};
    inner.appendChild(markBtn);
    card.appendChild(inner); grid.appendChild(card);
  });
}

function getFirstSrc(batch,brandKey,files){
  if(overrides[batch]&&overrides[batch][brandKey]&&overrides[batch][brandKey].length) return overrides[batch][brandKey][0];
  if(files&&files.length) return `/logos/${batch}/${files[0]}`;
  return '/static/broken.png';
}

function getAllSrcs(batch,brandKey,files){
  const arr=[]; if(overrides[batch]&&overrides[batch][brandKey]) arr.push(...overrides[batch][brandKey]); if(files&&files.length) files.forEach(f=>arr.push(`/logos/${batch}/${f}`)); return arr;
}

async function renameBrandPrompt(oldDisplay){
  if(!adminToken){alert('Admin only'); return;}
  const newName=prompt('Rename brand:',oldDisplay); if(!newName||newName.trim()===oldDisplay) return;
  const oldKey=oldDisplay.replace(/\s+/g,'_'); const newKey=newName.replace(/\s+/g,'_');
  try{const res=await fetch('/rename_brand',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Token':adminToken},body:JSON.stringify({batch:currentBatch,old_key:oldKey,new_key:newKey})});
  if(!res.ok){alert('Rename failed'); return;} loadBatch(currentBatch);}catch(e){alert('Rename error'); console.error(e);}
}

function filterBrands(){renderGrid();}
(function init(){if(adminToken)setAdminUI(true);})();
</script>
</body>
</html>
"""

# ---------- ROUTES ----------
@app.route("/")
def index():
    batches=scan_batches()
    return render_template_string(TEMPLATE,batches=batches)

@app.route("/api/logos/<path:batch>")
def api_logos(batch):
    batch_dir=STATIC_LOGOS_ROOT/batch
    if not batch_dir.exists() or not batch_dir.is_dir(): return jsonify([])
    fns=[p.name for p in sorted(batch_dir.iterdir()) if p.is_file() and allowed_ext(p.name)]
    return jsonify(group_by_brand(fns))

@app.route("/logos/<path:batch>/<path:filename>")
def serve_logo(batch,filename):
    batch_dir=STATIC_LOGOS_ROOT/batch
    if not batch_dir.exists(): return ("Not found",404)
    requested=safe_join(batch_dir,filename)
    if not requested.exists(): return ("Not found",404)
    return send_from_directory(str(batch_dir),filename)

@app.route("/admin_login",methods=["POST"])
def admin_login():
    data=request.get_json() or {}
    if data.get("password")==ADMIN_PASSWORD:
        token=str(uuid.uuid4()); ADMIN_TOKENS.add(token)
        return jsonify({"token":token})
    return jsonify({"error":"Bad password"}),401

@app.route("/admin_logout",methods=["POST"])
def admin_logout():
    data=request.get_json() or {}
    token=data.get("token") or request.headers.get("X-Admin-Token")
    if token in ADMIN_TOKENS: ADMIN_TOKENS.discard(token)
    return jsonify({"ok":True})

@app.route("/add_brand",methods=["POST"])
def add_brand():
    token=request.headers.get("X-Admin-Token"); 
    if token not in ADMIN_TOKENS: return jsonify({"error":"Admin required"}),401
    file=request.files.get("file"); brand=request.form.get("brand"); batch=request.form.get("batch")
    if not file or not brand or not batch: return jsonify({"error":"Missing data"}),400
    batch_dir=STATIC_LOGOS_ROOT/batch; batch_dir.mkdir(exist_ok=True)
    filename=f"{clean_brand_key(brand)}_logo{Path(file.filename).suffix}"; file.save(batch_dir/filename)
    return jsonify({"ok":True,"filename":filename})

@app.route("/rename_brand",methods=["POST"])
def rename_brand():
    token=request.headers.get("X-Admin-Token")
    if token not in ADMIN_TOKENS: return jsonify({"error":"Admin required"}),401
    data=request.get_json() or {}
    batch=data.get("batch",""); old_key=data.get("old_key",""); new_key=clean_brand_key(data.get("new_key",""))
    if not batch or not old_key or not new_key: return jsonify({"error":"Missing data"}),400
    batch_dir=STATIC_LOGOS_ROOT/batch; renamed=[]
    for p in sorted(batch_dir.iterdir()):
        if p.is_file() and p.stem.startswith(old_key):
            suffix=p.name[len(p.stem):]; target=batch_dir/f"{new_key}{suffix}"; 
            if target.exists(): target=batch_dir/f"{new_key}_{uuid.uuid4().int%10000}{suffix}"
            p.rename(target); renamed.append((p.name,str(target.name)))
    return jsonify({"renamed":renamed})

@app.route("/static/broken.png")
def broken():
    p=BASE_DIR/"static"/"broken.png"
    if p.exists(): return send_from_directory(str(p.parent),p.name)
    svg="<svg xmlns='http://www.w3.org/2000/svg' width='300' height='200'><rect width='100%' height='100%' fill='#08101a'/><text x='50%' y='50%' fill='#889' font-size='16' text-anchor='middle' dominant-baseline='middle'>Image missing</text></svg>"
    return svg,200,{"Content-Type":"image/svg+xml"}

if __name__=="__main__":
    app.run(debug=True)
