"""
MULTI-BATCH LOGO DOWNLOADER
---------------------------------------------------------
Downloads actual logo images for multiple batches using
the official client logo Excel sheet.

SETUP:
1. Place this script in your LogoLookup folder
2. Make sure you have `client_logo_master.xlsx` in the same folder
3. Install dependencies:
      pip install pandas openpyxl requests pillow
4. Run:
      python logo_lookup_multi.py
"""

import os
import re
import pandas as pd
import requests
from urllib.parse import urlparse, unquote
from datetime import datetime
from pathlib import Path

# ========== CONFIGURATION ==========
CLIENT_LOGO_FILE = "client_logo_master.xlsx"

# --- Define all batches and brands ---
BATCHES = {
    "54a": [
        "Air Canada", "Amazon", "American Airlines", "AutoNation",
        "Canada Life Insurance", "Enterprise", "Firestone", "Highmark",
        "Lenovo", "PNC", "Scotiabank", "TD", "Xcel Energy", "YMCA"
    ],
    "54b": [
        "Amerant Bank", "BJC Healthcare", "Caesars Sportsbook", "Calian Group",
        "Childrens National", "Key Bank", "RBC", "SkipTheDishes",
        "Telus", "Vanderbilt University"
    ],
    "54c": [
        "Amalie Oil Co.", "Belle Tire", "Bold Penguin", "CarShield",
        "Climate Pledge", "Clio", "Energy Transfer Partners",
        "First National Bank", "Gamesense", "IMA Financial",
        "Iron Bow Technologies", "Kiewit Corporation", "Kinaxis",
        "La Croix", "MSA Safety", "Muckleshoot Casino",
        "NAVQVI Injury Law", "NexGen Energy", "OC Health Care Agency",
        "Oreo", "Play Alberta", "Prudential", "Rapid 7",
        "RWJBarnabas Health", "Solo Stove", "TRIA Orthopedics",
        "Trusted Nurse Staffing", "Viam AI", "Visit Anaheim",
        "Visit Lauderdale", "Western National Property Management"
    ]
}

# =========================================================
# ------------------ HELPER FUNCTIONS ---------------------
# =========================================================

def clean_filename(text):
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    return text.replace(' ', '_').strip()[:80]

def get_file_extension(url, default='.png'):
    parsed = urlparse(url)
    path = unquote(parsed.path)
    for ext in ['.png', '.jpg', '.jpeg', '.svg', '.gif', '.webp']:
        if ext in path.lower():
            return ext
    # handle Wikipedia special cases
    if 'wikipedia' in url.lower():
        if '.svg' in url.lower(): return '.svg'
        if '.png' in url.lower(): return '.png'
        if '.jpg' in url.lower(): return '.jpg'
    return default

def find_best_match(search_name, df):
    search_lower = search_name.strip().lower()

    # Exact match
    exact = df[df['Brand_Lower'] == search_lower]
    if not exact.empty:
        return exact.iloc[0], 'EXACT', exact.iloc[0]['Brand']

    # Contains match
    contains = df[df['Brand_Lower'].str.contains(search_lower, na=False)]
    if not contains.empty:
        return contains.iloc[0], 'CONTAINS', contains.iloc[0]['Brand']

    # Partial word overlap
    for _, row in df.iterrows():
        brand_lower = str(row['Brand_Lower'])
        if brand_lower in search_lower or search_lower in brand_lower:
            return row, 'PARTIAL', row['Brand']

    return None, 'NOT_FOUND', None

def download_image(url, save_path):
    """Downloads the image from a URL and saves it to disk."""
    try:
        if not url or not isinstance(url, str) or not url.startswith("http"):
            return False

        # Special handling for Wikipedia file pages
        if 'wikipedia.org/wiki/File:' in url:
            html = requests.get(url, timeout=10).text
            match = re.search(r'href="(//upload\.wikimedia\.org/wikipedia/[^"]+)"', html)
            if match:
                url = 'https:' + match.group(1)

        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, stream=True, timeout=10)
        r.raise_for_status()

        with open(save_path, 'wb') as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)

        # Verify non-empty file
        if os.path.getsize(save_path) < 100:
            os.remove(save_path)
            return False
        return True

    except Exception as e:
        return False

# =========================================================
# ------------------ MAIN DOWNLOAD LOGIC ------------------
# =========================================================

def download_batch(batch_number, brands, logo_df):
    print(f"\n{'='*70}")
    print(f"🎯 DOWNLOADING LOGOS FOR BATCH {batch_number.upper()}")
    print(f"{'='*70}")

    output_folder = Path(f"batch_{batch_number}_logos")
    output_folder.mkdir(exist_ok=True)

    results = []
    stats = {'found':0, 'not_found':0, 'failed':0, 'images':0}

    for i, brand in enumerate(brands, 1):
        print(f"\n{i:2d}. {brand}")
        matched_row, match_type, matched_name = find_best_match(brand, logo_df)

        if matched_row is None:
            print("   ❌ No match found in sheet.")
            results.append({'Brand': brand, 'Matched_As': 'NOT FOUND'})
            stats['not_found'] += 1
            continue

        if match_type != 'EXACT':
            print(f"   🔗 Matched as: {matched_name} [{match_type}]")

        stats['found'] += 1
        safe_name = clean_filename(matched_name)
        downloaded = []

        for n in range(1, 4):
            url = str(matched_row.get(f'Logo{n}', '')).strip()
            if not url or url.lower() == 'nan':
                continue
            ext = get_file_extension(url)
            file_path = output_folder / f"{safe_name}_logo{n}{ext}"
            print(f"   Logo{n}: ", end="")
            if download_image(url, file_path):
                print(f"✓ Downloaded → {file_path.name}")
                stats['images'] += 1
                downloaded.append(file_path.name)
            else:
                print("❌ Failed")
                stats['failed'] += 1

        results.append({
            'Brand': brand,
            'Matched_As': matched_name,
            'Match_Type': match_type,
            'Downloaded': ', '.join(downloaded) if downloaded else 'None'
        })

    # Export Excel report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    report_name = f"batch_{batch_number}_download_report_{timestamp}.xlsx"
    pd.DataFrame(results).to_excel(report_name, index=False)

    print("\n📊 SUMMARY")
    print("------------------------------------------------------")
    print(f"   Found: {stats['found']}")
    print(f"   Not Found: {stats['not_found']}")
    print(f"   Failed Downloads: {stats['failed']}")
    print(f"   Total Images: {stats['images']}")
    print(f"   Folder: {output_folder}/")
    print(f"   Report: {report_name}")
    print("=======================================================")

# =========================================================
# ---------------------- MAIN ENTRY -----------------------
# =========================================================

if __name__ == "__main__":
    print("📂 Loading client logo master file...")
    if not Path(CLIENT_LOGO_FILE).exists():
        print(f"❌ ERROR: {CLIENT_LOGO_FILE} not found in this folder.")
        exit()

    logo_df = pd.read_excel(CLIENT_LOGO_FILE)
    logo_df.columns = logo_df.columns.str.strip()
    logo_df["Brand_Lower"] = logo_df["Brand"].astype(str).str.strip().str.lower()

    print(f"✓ Loaded {len(logo_df)} brands from client sheet.")

    for batch_id, brand_list in BATCHES.items():
        download_batch(batch_id, brand_list, logo_df)

    print("\n🎉 All batches completed successfully!")
