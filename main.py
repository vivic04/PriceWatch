from curl_cffi import requests
from bs4 import BeautifulSoup
import json
import os
import re

# --- CONFIG ---
WEBHOOK_URL = os.environ.get("DISCORD_URL") 
DB_FILE = "price_history.json"
TRACKING_FILE = "tracking_list.json"

# --- PARSERS ---

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
    
def fetch_aritzia(url):
    print(f"👗 Aritzia Detected: {url}", flush=True)
    try:
        clean_url = url.split("?")[0]
        
        # TRICK 1: Pretend to be an iPhone (Mobile User-Agent)
        # This often forces the server to send pre-loaded HTML
        mobile_headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
        }
        
        # Note: We pass headers=mobile_headers explicitly here
        response = requests.get(clean_url, headers=mobile_headers, impersonate="chrome110", timeout=30)
        
        # TRICK 2: The "Ctrl+F" Search (Regex)
        # We ignore HTML structure and just hunt for the JSON data keys
        # We look for patterns like: "price": 425.0 or "salePrice": 425
        
        import re
        
        # Pattern A: Look for "sale_price" or "price" followed by a number
        # Matches: "price": 425.00  OR  "price":425
        matches = re.findall(r'["\'](?:sale_price|price|original_price)["\']\s*:\s*["\']?(\d+\.?\d*)["\']?', response.text)
        
        if matches:
            # We might find multiple prices (e.g. 0.0, 425.0). 
            # Convert all to floats and pick the largest logical one (usually the real price)
            valid_prices = []
            for m in matches:
                try:
                    p = float(m)
                    if p > 0: valid_prices.append(p)
                except: continue
            
            if valid_prices:
                # Aritzia sometimes lists the price in cents (e.g. 42500)
                # If we find a huge number, divide by 100
                final_price = max(valid_prices)
                if final_price > 1000: 
                    final_price = final_price / 100
                    
                print(f"   Found Price via Regex Scan: {final_price}", flush=True)
                return float(final_price)

        # TRICK 3: Look for the specific 'utag_data' (Aritzia's analytics layer)
        if "utag_data" in response.text:
             # Look for "product_price":["425.00"]
             utag_match = re.search(r'["\']product_price["\']\s*:\s*\[?["\'](\d+\.?\d*)["\']', response.text)
             if utag_match:
                 print(f"   Found Price in Data Layer: {utag_match.group(1)}", flush=True)
                 return float(utag_match.group(1))

        print("❌ Aritzia data completely hidden. They require a Browser (Selenium) to view.", flush=True)
        return None

    except Exception as e:
        print(f"❌ Aritzia Error: {e}", flush=True)
        return None
        return None
def fetch_toscrape(url):
    # Sandbox parser for testing
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
    elif "aritzia" in url: return fetch_aritzia(url)  # <--- NEW LINE
    else: 
        print(f"⚠️ No parser for {url}")
        return None

# --- MAIN ENGINE ---
def load_tracking_list():
    if os.path.exists(TRACKING_FILE):
        with open(TRACKING_FILE, 'r') as f:
            return json.load(f)
    print(f"⚠️ {TRACKING_FILE} not found.", flush=True)
    return []

def check_prices():
    print("--- 🤖 STARTING MONITOR ---", flush=True)
    
    # 1. Load Data
    items = load_tracking_list()
    if not items:
        print("No items to track.", flush=True)
        return

    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            history = json.load(f)
    else:
        history = {}

    # 2. Check Each Item
    for item in items:
        url = item.get("url")
        note = item.get("note", "Unknown Item")
        
        print(f"\n🔎 Checking {note}...", flush=True)
        current_price = get_price(url)
        
        if current_price:
            print(f"   ✅ Price: {current_price}", flush=True)
            clean_url = url.split("?")[0]
            
            # 3. Compare & Alert
            if clean_url in history:
                old_price = history[clean_url]
                if current_price != old_price:
                    msg = f"🚨 PRICE CHANGE: {note} moved from {old_price} to {current_price}!\nLink: {clean_url}"
                    if WEBHOOK_URL:
                        requests.post(WEBHOOK_URL, json={"content": msg})
                        print("   -> Discord Alert Sent!", flush=True)
                    history[clean_url] = current_price
            else:
                history[clean_url] = current_price
                print("   -> First time tracking. Saved to history.", flush=True)
        else:
            print("   ❌ Failed to get price.", flush=True)

    # 4. Save State
    with open(DB_FILE, 'w') as f:
        json.dump(history, f)
    print("\n--- 🏁 RUN COMPLETE ---", flush=True)

if __name__ == "__main__":
    check_prices()