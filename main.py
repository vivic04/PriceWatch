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
import random # Add this at the top if missing

def fetch_with_browser(url):
    print(f"🎭 Playwright Browser: Launching for {url}", flush=True)
    
    try:
        with sync_playwright() as p:
            # LAUNCH: We use a larger window and extra args to look like a real PC
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled", 
                    "--no-sandbox", 
                    "--start-maximized"
                ]
            )
            
            # CONTEXT: Force Canada + Real User Agent
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-CA",
                timezone_id="America/Toronto"
            )
            
            # Inject Cookies to force CAD currency
            context.add_cookies([
                {"name": "countryCode", "value": "CA", "domain": ".aritzia.com", "path": "/"},
                {"name": "currencyCode", "value": "CAD", "domain": ".aritzia.com", "path": "/"}
            ])
            
            page = context.new_page()
            
            # --- 1. THE HUMAN LOADER ---
            print("   -> Loading Page...", flush=True)
            page.goto(url, timeout=90000)
            
            # CHECK TITLE: Are we blocked?
            page_title = page.title()
            print(f"   🔎 PAGE TITLE: {page_title}", flush=True)
            if "Attention Required" in page_title or "Just a moment" in page_title:
                print("   🛑 CLOUDFLARE BLOCK DETECTED.", flush=True)
                return None

            # --- 2. THE MOUSE WIGGLE ---
            # Bots don't move mice. Humans do. We simulate random movement.
            print("   -> Simulating human mouse movement...", flush=True)
            for i in range(5):
                x = random.randint(100, 800)
                y = random.randint(100, 800)
                page.mouse.move(x, y, steps=10) # 'steps' makes it smooth, not instant
                page.wait_for_timeout(random.randint(200, 500))

            # --- 3. SCROLL DOWN SLOWLY ---
            page.mouse.wheel(0, 600)
            page.wait_for_timeout(2000)

            # --- 4. EXTRACT PRICE (Regex Scan) ---
            # We scan the raw text for ANY dollar amount now that we've "woken up" the page
            import re
            body_text = page.inner_text("body")
            
            # Look for "$ 425", "$425", "425 CAD"
            matches = re.findall(r'(?:CAD|\$)\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', body_text)
            
            browser.close()

            if matches:
                # Filter out small numbers (likely shipping/promos)
                prices = []
                for m in matches:
                    try:
                        val = float(m.replace(",", ""))
                        if val > 20: prices.append(val) # Filter out junk like "$5 shipping"
                    except: continue
                
                if prices:
                    final_price = max(prices)
                    print(f"   ✅ Found Price via Human Scan: {final_price}", flush=True)
                    return final_price

            print("❌ No price found. (We might be fully IP blocked)", flush=True)
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