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
    print(f"👗 Aritzia Detected: Checking SEO data for {url}", flush=True)
    try:
        # Aritzia requires a clean URL (no extra tracking garbage)
        clean_url = url.split("?")[0]
        
        # 1. Fetch with Chrome Impersonation
        response = requests.get(clean_url, impersonate="chrome110", timeout=30)
        soup = BeautifulSoup(response.text, "html.parser")

        # 2. Strategy A: The SEO Data (Golden Ticket)
        # Aritzia puts product data in a script tag for Google Shopping
        schema_tags = soup.find_all("script", type="application/ld+json")
        
        for tag in schema_tags:
            try:
                data = json.loads(tag.string)
                
                # Check 1: Is it a direct Product?
                if data.get("@type") == "Product":
                    offers = data.get("offers", {})
                    if isinstance(offers, list): 
                        price = offers[0].get("price")
                    else:
                        price = offers.get("price")
                    
                    if price:
                        return float(price)

                # Check 2: Sometimes Aritzia wraps it in a "Graph"
                if "@graph" in data:
                    for item in data["@graph"]:
                        if item.get("@type") == "Product":
                            offers = item.get("offers", {})
                            if isinstance(offers, list): 
                                price = offers[0].get("price")
                            else:
                                price = offers.get("price")
                            if price: return float(price)
            except:
                continue

        # 3. Strategy B: Visual Selector (Fallback)
        # If SEO fails, look for the visual price tag
        # Aritzia often uses these classes:
        selectors = [
            ".price-default", 
            ".js-product-price", 
            ".product-price__amount"
        ]
        
        for sel in selectors:
            element = soup.select_one(sel)
            if element:
                clean = element.text.strip().replace("C$", "").replace("$", "").replace("CAD", "")
                return float(clean)

        print("❌ Aritzia data missing. (Might need cookies/proxies)", flush=True)
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