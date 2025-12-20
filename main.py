from curl_cffi import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright # <--- The Heavy Artillery
import json
import os
import re

# --- CONFIG ---
WEBHOOK_URL = os.environ.get("DISCORD_URL") 
DB_FILE = "price_history.json"
TRACKING_FILE = "tracking_list.json"

# --- 1. THE BROWSER ENGINE (For Aritzia / Difficult Sites) ---
def fetch_with_browser(url):
    print(f"🎭 Playwright Browser: Launching for {url}", flush=True)
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            # Create a 1080p window so the layout matches your screenshot
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()
            
            print("   -> Loading Page...", flush=True)
            page.goto(url, timeout=90000)

            # --- INTERACTION STEP ---
            # Click "Select a Size" to force the price to load
            try:
                print("   -> Clicking 'Select a Size'...", flush=True)
                # We target the specific text from your screenshot
                page.click("text=Select a Size", timeout=5000)
                page.wait_for_timeout(1000)
                
                # Click the first available size in the dropdown
                # This usually triggers the "Price Update" event
                page.keyboard.press("ArrowDown")
                page.keyboard.press("Enter")
                print("   -> Selected a size (S/M/L).", flush=True)
                page.wait_for_timeout(3000) # Give it 3s to update the price
            except:
                print("   -> Could not select size (might be one-size or different layout).", flush=True)

            # --- EVIDENCE ---
            page.screenshot(path="aritzia_final.png")
            print("   📸 Screenshot saved: aritzia_final.png", flush=True)

            # --- FINAL PRICE EXTRACT ---
            # Now we look for the ID from your OTHER screenshot (image_e0be46.png)
            content = page.content()
            browser.close()
            
            soup = BeautifulSoup(content, "html.parser")
            
            # 1. The ID you found in the inspector
            price_tag = soup.find(attrs={"data-testid": "product-list-price-text"})
            
            # 2. Fallback: Search for the text "$425" (or whatever number) visually
            if not price_tag:
                 # Look for any text that starts with $ and has digits
                import re
                body_text = soup.get_text()
                # Find "$ 425" or "$425"
                match = re.search(r'\$\s*(\d{2,5})', body_text)
                if match:
                    print(f"   ✅ Found Price in Text: {match.group(1)}", flush=True)
                    return float(match.group(1))

            if price_tag:
                raw_text = price_tag.text.strip()
                print(f"   ✅ FOUND RAW TEXT: {raw_text}", flush=True)
                clean = raw_text.replace("C", "").replace("$", "").replace("CAD", "").replace(",", "").strip()
                return float(clean)
                
            print("❌ Price still hidden. (Check aritzia_final.png)", flush=True)
            return None

    except Exception as e:
        print(f"❌ Browser Error: {e}", flush=True)
        return None
    
# --- 2. THE REQUEST ENGINE (For eBay / Fast Sites) ---
def fetch_ebay(url):
    clean_url = url.split("?")[0]
    print(f"🕵️  eBay Detected: {clean_url}", flush=True)
    try:
        response = requests.get(clean_url, impersonate="chrome110", timeout=30)
        soup = BeautifulSoup(response.text, "html.parser")
        price_element = soup.find('div', class_='x-price-primary')
        if not price_element: price_element = soup.find('span', id='prcIsum')
        if not price_element: price_element = soup.find('div', class_='main-price-with-shipping')

        if price_element:
            text = price_element.text.strip().replace("C", "").replace("US", "").replace("$", "").replace(",", "")
            if "Approx" in text: text = text.split("Approx")[1]
            return float(text.strip())
        return None
    except Exception as e:
        print(f"❌ eBay Error: {e}", flush=True)
        return None

def fetch_toscrape(url):
    try:
        response = requests.get(url, impersonate="chrome110", timeout=30)
        soup = BeautifulSoup(response.text, "html.parser")
        price = soup.find('p', class_='price_color')
        if price: return float(price.text[1:])
    except: pass
    return None

# --- ROUTER ---
def get_price(url):
    if "ebay" in url: return fetch_ebay(url)
    elif "toscrape" in url: return fetch_toscrape(url)
    elif "aritzia" in url: return fetch_with_browser(url) # <--- USE BROWSER
    elif "zara" in url: return fetch_with_browser(url)    # <--- USE BROWSER
    else: 
        print(f"⚠️ No parser for {url}")
        return None

# --- MAIN LOOP ---
def load_tracking_list():
    if os.path.exists(TRACKING_FILE):
        with open(TRACKING_FILE, 'r') as f:
            return json.load(f)
    print(f"⚠️ {TRACKING_FILE} not found.", flush=True)
    return []

def check_prices():
    print("--- 🤖 STARTING HYBRID MONITOR ---", flush=True)
    items = load_tracking_list()
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            history = json.load(f)
    else:
        history = {}

    for item in items:
        url = item.get("url")
        note = item.get("note", "Unknown Item")
        
        print(f"\n🔎 Checking {note}...", flush=True)
        current_price = get_price(url)
        
        if current_price:
            print(f"   ✅ Price: {current_price}", flush=True)
            clean_url = url.split("?")[0]
            
            if clean_url in history:
                old_price = history[clean_url]
                if current_price != old_price:
                    msg = f"🚨 PRICE CHANGE: {note} moved from {old_price} to {current_price}!\nLink: {clean_url}"
                    if WEBHOOK_URL:
                        requests.post(WEBHOOK_URL, json={"content": msg})
                        print("   -> Alert Sent!", flush=True)
                    history[clean_url] = current_price
            else:
                history[clean_url] = current_price
                print("   -> First time tracking. Saved.", flush=True)
        else:
            print("   ❌ Failed to get price.", flush=True)

    with open(DB_FILE, 'w') as f:
        json.dump(history, f)
    print("\n--- 🏁 RUN COMPLETE ---", flush=True)

if __name__ == "__main__":
    check_prices()