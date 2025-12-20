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
        response = requests.get(clean_url, impersonate="chrome110", timeout=30)
        soup = BeautifulSoup(response.text, "html.parser")

        # STRATEGY 1: The "Test ID" (From your screenshot)
        # We look for any tag that has this specific data-testid attribute
        price_tag = soup.find(attrs={"data-testid": "product-list-price-text"})
        
        # Backup: Sometimes it's called 'product-price-text' (the parent container)
        if not price_tag:
            price_tag = soup.find(attrs={"data-testid": "product-price-text"})

        if price_tag:
            raw_text = price_tag.text.strip()
            print(f"   Found Raw Price: {raw_text}", flush=True)
            
            # Clean it: "$425" -> 425.0
            # Remove symbols, CAD, and whitespace
            clean_text = raw_text.replace("C", "").replace("$", "").replace("CAD", "").replace(",", "").strip()
            
            # Handle ranges (e.g. "100 - 150") by taking the first number
            if "-" in clean_text:
                clean_text = clean_text.split("-")[0].strip()
                
            return float(clean_text)

        print("❌ Aritzia price tag not found. (Page might be loading via JavaScript)", flush=True)
        return None

    except Exception as e:
        print(f"❌ Aritzia Error: {e}", flush=True)
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