"""
BATCH LOGO DOWNLOADER
Downloads actual logo images from URLs in client's sheet

SETUP:
1. pip install pandas openpyxl requests pillow
2. Download client's logo sheet
3. Update BATCH_LIST below
4. Run: python logo_lookup.py

OUTPUT: 
- Folder with all logo images
- Excel file with image paths
- Ready to insert into Google Sheets
"""

import pandas as pd
import requests
from pathlib import Path
from datetime import datetime
import os
import re
from urllib.parse import urlparse, unquote
import numpy as np

# ===== CONFIGURATION =====
CLIENT_LOGO_FILE = 'client_logo_master.xlsx'
BATCH_NUMBER = '54'

# ===== PASTE YOUR BATCH HERE =====
BATCH_LIST = """
Air Canada
Amazon
American Airlines
AutoNation
Canada Life Insurance
Enterprise
Firestone
Highmark
Lenovo
PNC
Scotiabank
TD
Xcel Energy
YMCA
""".strip()

# ===== HELPER FUNCTIONS =====
def find_best_match(search_name, logo_df):
    """Find best match for brand name using multiple strategies"""
    search_lower = search_name.strip().lower()
    
    # Strategy 1: Exact match
    exact = logo_df[logo_df['Brand_Lower'] == search_lower]
    if not exact.empty:
        return exact.iloc[0], 'EXACT', exact.iloc[0]['Brand']
    
    # Strategy 2: Contains search term
    contains = logo_df[logo_df['Brand_Lower'].str.contains(search_lower, na=False, regex=False)]
    if not contains.empty:
        return contains.iloc[0], 'CONTAINS', contains.iloc[0]['Brand']
    
    # Strategy 3: Search term contains brand name
    for idx, row in logo_df.iterrows():
        brand_lower = str(row['Brand_Lower'])
        if brand_lower in search_lower:
            return row, 'PARTIAL', row['Brand']
    
    # Strategy 4: Word-by-word match
    search_words = set(search_lower.split())
    best_match = None
    best_score = 0
    
    for idx, row in logo_df.iterrows():
        brand_words = set(str(row['Brand_Lower']).split())
        common_words = search_words & brand_words
        score = len(common_words)
        
        if score > best_score and score >= 2:  # At least 2 words match
            best_score = score
            best_match = row
    
    if best_match is not None:
        return best_match, f'FUZZY({best_score})', best_match['Brand']
    
    return None, 'NOT_FOUND', None

def clean_filename(text):
    """Create safe filename from brand name"""
    # Remove special characters
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    # Replace spaces with underscores
    text = text.replace(' ', '_')
    # Limit length
    return text[:50]

def get_file_extension(url, default='.png'):
    """Extract file extension from URL"""
    # Parse URL
    parsed = urlparse(url)
    path = unquote(parsed.path)
    
    # Check for common image extensions
    for ext in ['.png', '.jpg', '.jpeg', '.svg', '.gif', '.webp']:
        if ext in path.lower():
            return ext
    
    # Check for Wikipedia special case
    if 'wikipedia' in url.lower():
        if '.svg' in url.lower():
            return '.svg'
        elif '.png' in url.lower():
            return '.png'
        elif '.jpg' in url.lower() or '.jpeg' in url.lower():
            return '.jpg'
    
    return default

def download_image(url, save_path, timeout=10):
    """Download image from URL"""
    if not url or url == 'nan' or 'NOT FOUND' in str(url):
        return False
    
    try:
        # Handle Wikipedia file pages - try to extract direct image URL
        if 'wikipedia.org/wiki/File:' in url or 'wikipedia.org/wiki/Image:' in url:
            print(f"Wikipedia page - attempting to find direct image link...")
            # Try to get the actual image from the page
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                # Look for the actual image URL in the page
                import re
                # Find the full resolution image link
                match = re.search(r'href="(//upload\.wikimedia\.org/wikipedia/[^"]+)"', response.text)
                if match:
                    url = 'https:' + match.group(1)
                    print(f"      Found direct link: {url[:60]}...")
                else:
                    print(f"      ❌ Could not extract image from Wikipedia page")
                    return False
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=timeout, stream=True)
        response.raise_for_status()
        
        # Save the image
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Check if file is valid (has content)
        if os.path.getsize(save_path) < 100:  # Less than 100 bytes is suspicious
            os.remove(save_path)
            return False
        
        return True
    
    except requests.exceptions.Timeout:
        print(f"      ⏱️  Timeout")
        return False
    except requests.exceptions.RequestException as e:
        print(f"      ❌ Download failed: {str(e)[:50]}")
        return False
    except Exception as e:
        print(f"      ❌ Error: {str(e)[:50]}")
        return False

# ===== MAIN FUNCTION =====
def download_batch_logos():
    print("=" * 70)
    print(f"🎯 BATCH {BATCH_NUMBER} LOGO DOWNLOADER")
    print("=" * 70)
    
    # Check if client file exists
    if not Path(CLIENT_LOGO_FILE).exists():
        print(f"\n❌ ERROR: Cannot find {CLIENT_LOGO_FILE}")
        print("\n📝 Make sure the file is in the same folder as this script")
        return
    
    print(f"\n📂 Loading client logo database...")
    
    # Load client's master logo list
    try:
        if CLIENT_LOGO_FILE.endswith('.csv'):
            logo_df = pd.read_csv(CLIENT_LOGO_FILE)
        else:
            logo_df = pd.read_excel(CLIENT_LOGO_FILE)
    except Exception as e:
        print(f"\n❌ ERROR reading file: {e}")
        return
    
    print(f"   ✓ Loaded {len(logo_df)} brands from database")
    
    # Create output folder for images
    output_folder = f'batch_{BATCH_NUMBER}_logos'
    Path(output_folder).mkdir(exist_ok=True)
    print(f"\n📁 Created folder: {output_folder}/")
    
    # Normalize brand names
    logo_df['Brand_Lower'] = logo_df['Brand'].str.strip().str.lower()
    
    # Parse batch list
    batch_brands = [b.strip() for b in BATCH_LIST.split('\n') if b.strip()]
    
    print(f"\n📥 Downloading logos for {len(batch_brands)} brands...")
    print("-" * 70)
    
    results = []
    download_stats = {
        'found': 0,
        'not_found': 0,
        'logo1_downloaded': 0,
        'logo2_downloaded': 0,
        'logo3_downloaded': 0,
        'failed': 0
    }
    
    for i, brand in enumerate(batch_brands, 1):
        brand_clean = brand.strip()
        
        print(f"\n{i:2d}. {brand_clean}")
        
        # Find best match
        matched_row, match_type, matched_name = find_best_match(brand_clean, logo_df)
        
        if matched_row is None:
            print(f"    ❌ Not found in database")
            results.append({
                'Brand': brand_clean,
                'Matched_As': 'NOT FOUND',
                'Logo1_Path': 'NOT FOUND',
                'Logo2_Path': '',
                'Logo3_Path': '',
                'Logo1_URL': '',
                'Logo2_URL': '',
                'Logo3_URL': ''
            })
            download_stats['not_found'] += 1
            continue
        
        # Show match info
        if match_type != 'EXACT':
            print(f"    🔗 Matched as: \"{matched_name}\" [{match_type}]")
        
        row = matched_row
        download_stats['found'] += 1
        
        # Prepare safe filename
        safe_name = clean_filename(brand_clean)
        
        logo_paths = {}
        logo_urls = {}
        
        # Download each logo variant
        for logo_num in range(1, 4):
            logo_col = f'Logo{logo_num}'
            url = row.get(logo_col, '')
            
            # Handle empty cells (pandas reads as NaN/float)
            if pd.isna(url) or url == '':
                logo_urls[f'Logo{logo_num}_URL'] = ''
                logo_paths[f'Logo{logo_num}_Path'] = ''
                continue
            
            # Convert to string if not already
            url = str(url).strip()
            logo_urls[f'Logo{logo_num}_URL'] = url
            
            if url and url != '':
                ext = get_file_extension(url)
                filename = f"{safe_name}_logo{logo_num}{ext}"
                filepath = Path(output_folder) / filename
                
                print(f"    Logo{logo_num}: ", end='')
                
                if download_image(url, filepath):
                    print(f"✓ Downloaded → {filename}")
                    logo_paths[f'Logo{logo_num}_Path'] = str(filepath)
                    download_stats[f'logo{logo_num}_downloaded'] += 1
                else:
                    logo_paths[f'Logo{logo_num}_Path'] = f'FAILED: {url[:50]}'
                    download_stats['failed'] += 1
            else:
                logo_paths[f'Logo{logo_num}_Path'] = ''
        
        results.append({
            'Brand': brand_clean,
            'Matched_As': matched_name if match_type != 'EXACT' else brand_clean,
            **logo_paths,
            **logo_urls
        })
    
    # Create Excel report
    output_df = pd.DataFrame(results)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    excel_filename = f'batch_{BATCH_NUMBER}_download_report_{timestamp}.xlsx'
    
    with pd.ExcelWriter(excel_filename, engine='openpyxl') as writer:
        output_df.to_excel(writer, index=False, sheet_name='Download Report')
        worksheet = writer.sheets['Download Report']
        
        # Auto-adjust column widths
        for column in worksheet.columns:
            max_length = 0
            column = [cell for cell in column]
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(cell.value)
                except:
                    pass
            adjusted_width = min(max_length + 2, 60)
            worksheet.column_dimensions[column[0].column_letter].width = adjusted_width
    
    # Print summary
    print("\n" + "=" * 70)
    print("📊 DOWNLOAD SUMMARY")
    print("=" * 70)
    print(f"   Total Brands:        {len(batch_brands)}")
    print(f"   ✓ Found in DB:       {download_stats['found']}")
    print(f"   ✗ Not in DB:         {download_stats['not_found']}")
    print(f"\n   📥 Downloads:")
    print(f"      Logo1: {download_stats['logo1_downloaded']} downloaded")
    print(f"      Logo2: {download_stats['logo2_downloaded']} downloaded")
    print(f"      Logo3: {download_stats['logo3_downloaded']} downloaded")
    print(f"      Failed: {download_stats['failed']} failed")
    
    total_downloaded = (download_stats['logo1_downloaded'] + 
                       download_stats['logo2_downloaded'] + 
                       download_stats['logo3_downloaded'])
    
    print(f"\n   🎉 Total Images Downloaded: {total_downloaded}")
    
    print(f"\n✅ OUTPUT FILES:")
    print(f"   📁 Images folder: {output_folder}/")
    print(f"   📄 Report: {excel_filename}")
    
    print("\n" + "=" * 70)
    print("📋 HOW TO USE IN GOOGLE SHEETS:")
    print("=" * 70)
    print(f"   1. Open the '{output_folder}' folder")
    print(f"   2. Select all images and upload to Google Drive")
    print(f"   3. In Google Sheets: Insert > Image > Image in cell")
    print(f"   4. Or use: Insert > Image > Image over cells")
    print("=" * 70)
    
    return output_df

# ===== ALTERNATIVE: DIRECT GOOGLE SHEETS UPLOAD =====
def create_google_sheets_instructions():
    """
    Creates a helper guide for uploading to Google Sheets
    """
    instructions = """
    
    ╔═══════════════════════════════════════════════════════════════════╗
    ║           UPLOADING LOGOS TO GOOGLE SHEETS - QUICK GUIDE          ║
    ╚═══════════════════════════════════════════════════════════════════╝
    
    METHOD 1: Upload to Google Drive First (Recommended)
    ────────────────────────────────────────────────────────────────────
    1. Upload all images from batch_XX_logos folder to Google Drive
    2. In Google Sheets, click the cell where you want the image
    3. Insert > Image > Image in cell
    4. Select "Drive" and choose your uploaded image
    
    
    METHOD 2: Direct Upload from Computer
    ────────────────────────────────────────────────────────────────────
    1. In Google Sheets, click the cell
    2. Insert > Image > Image in cell
    3. Choose "Upload" tab
    4. Select image from batch_XX_logos folder
    
    
    METHOD 3: Using IMAGE Formula (For URLs only)
    ────────────────────────────────────────────────────────────────────
    If you have image URLs (not downloaded files):
    =IMAGE("your-image-url-here")
    
    Note: This won't work with local files
    
    
    ⚡ BATCH UPLOAD TIP:
    ────────────────────────────────────────────────────────────────────
    - Upload ALL images to a Google Drive folder first
    - Share that folder with your team
    - Then insert images one by one into your sheet
    - Or use Google Apps Script to automate insertion
    
    """
    print(instructions)

# ===== RUN THE SCRIPT =====
if __name__ == '__main__':
    df = download_batch_logos()
    create_google_sheets_instructions()
    
    print("\n🚀 All done! Check the output folder for your images.")