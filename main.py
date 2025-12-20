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
            # Launch options to look real
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080} # Desktop size
            )
            page = context.new_page()
            
            print("   -> Loading Page...", flush=True)
            page.goto(url, timeout=90000)
            
            # --- POPUP KILLER ---
            # Aritzia often shows a "Select Region" modal. We try to click "Stay on this site" or "Close".
            try:
                page.wait_for_timeout(3000) # Wait 3s for popup to animate
                print("   -> Checking for popups...", flush=True)
                
                # List of common Aritzia popup close buttons / "Stay" buttons
                popup_selectors = [
                    'button[aria-label="Close"]', 
                    '.close-button',
                    'button:has-text("Stay on this Site")', 
                    'button:has-text("No, thanks")',
                    'div[role="dialog"] button' 
                ]
                
                for sel in popup_selectors:
                    if page.is_visible(sel):
                        page.click(sel)
                        print(f"   -> 💥 Smashed a popup: {sel}", flush=True)
                        page.wait_for_timeout(1000) # Wait for it to disappear
            except Exception as e:
                print(f"   -> Popup check error (ignoring): {e}", flush=True)

            # --- SCROLL TO REVEAL ---
            # Aritzia lazily loads prices. We must scroll down slightly.
            page.mouse.wheel(0, 500)
            page.wait_for_timeout(2000)

            # --- TAKE EVIDENCE ---
            page.screenshot(path="aritzia_debug.png")
            print("   📸 Screenshot saved: aritzia_debug.png", flush=True)

            # --- EXTRACT PRICE ---
            # We use the EXACT ID from your screenshot
            # data-testid="product-list-price-text"
            try:
                # Wait explicitly for the element you saw in the inspector
                page.wait_for_selector('[data-testid="product-list-price-text"]', timeout=10000)
            except:
                print("   -> Target ID not found immediately, checking backup...", flush=True)

            content = page.content()
            browser.close()
            
            soup = BeautifulSoup(content, "html.parser")
            
            # 1. Primary Target (From your Screenshot)
            price_tag = soup.find(attrs={"data-testid": "product-list-price-text"})
            
            # 2. Backup Target (Parent container)
            if not price_tag:
                price_tag = soup.find(attrs={"data-testid": "product-price-text"})

            if price_tag:
                raw_text = price_tag.text.strip()
                print(f"   ✅ FOUND RAW TEXT: {raw_text}", flush=True)
                
                # Clean "$425" -> 425.0
                clean = raw_text.replace("C", "").replace("$", "").replace("CAD", "").replace(",", "").strip()
                if "-" in clean: clean = clean.split("-")[0].strip()
                return float(clean)
                
            print("❌ Price tag not found in HTML (Check screenshot artifact)", flush=True)
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