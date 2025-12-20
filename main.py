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
            
            # 1. CREATE CONTEXT WITH CANADIAN COOKIES
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            
            # Force Aritzia to show the Canadian site (CAD prices)
            context.add_cookies([
                {"name": "countryCode", "value": "CA", "domain": ".aritzia.com", "path": "/"},
                {"name": "currencyCode", "value": "CAD", "domain": ".aritzia.com", "path": "/"}
            ])
            
            page = context.new_page()
            
            print("   -> Loading Page (Forcing Canada Region)...", flush=True)
            page.goto(url, timeout=90000)
            
            # 2. WAIT FOR NETWORK IDLE (Let the data load)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except: pass

            # 3. GOD MODE: STEAL THE INTERNAL DATA (Bypasses Visual HTML)
            # We execute JavaScript to read the 'utag_data' (Tealium Analytics) 
            # or 'digitalData' which stores the clean product info.
            print("   -> Extracting internal data layer...", flush=True)
            
            product_data = page.evaluate("() => { \
                try { \
                    return window.utag_data || window.digitalData.product[0].productInfo || {}; \
                } catch(e) { return {}; } \
            }")
            
            # Check if we found the price in the analytics data
            # utag_data usually has 'product_price': ['425.00']
            if product_data:
                # print(f"   🔎 DEBUG DATA: {str(product_data)[:200]}...", flush=True) # Uncomment to see raw data
                
                # Check for 'product_price' (List or String)
                price_list = product_data.get("product_price", [])
                if isinstance(price_list, list) and len(price_list) > 0:
                    raw_price = price_list[0]
                    print(f"   ✅ Found Price in Data Layer: {raw_price}", flush=True)
                    return float(raw_price)
                
                # Check for 'basePrice' or 'price'
                if "price" in product_data:
                    return float(product_data["price"])

            # 4. FALLBACK: VISUAL SCAN (With Canada Cookie now active)
            print("   -> Data layer empty, scanning text...", flush=True)
            content = page.content()
            browser.close()
            
            soup = BeautifulSoup(content, "html.parser")
            price_tag = soup.find(attrs={"data-testid": "product-list-price-text"})
            
            if price_tag:
                clean = price_tag.text.strip().replace("C", "").replace("$", "").replace("CAD", "").replace(",", "").strip()
                return float(clean)
            
            # Last ditch: Find any "$425" pattern
            import re
            match = re.search(r'(?:CAD|\$)\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', soup.get_text())
            if match:
                return float(match.group(1).replace(",", ""))

            print("❌ Price not found (Even with Canada Cookies).", flush=True)
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