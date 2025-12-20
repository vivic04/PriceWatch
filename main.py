from curl_cffi import requests
from bs4 import BeautifulSoup
import json
import os
import re

# --- CONFIG ---
WEBHOOK_URL = os.environ.get("DISCORD_URL") 
DB_FILE = "price_history.json"

# --- 1. ZARA (The SEO Strategy) ---
def fetch_zara(url):
    print(f"👗 Zara Detected: Checking public SEO data for {url}", flush=True)
    try:
        response = requests.get(url, impersonate="chrome110", timeout=30)
        soup = BeautifulSoup(response.text, "html.parser")

        # Strategy: Look for the data Zara sends to Google (ld+json)
        schema_tags = soup.find_all("script", type="application/ld+json")
        
        for tag in schema_tags:
            try:
                data = json.loads(tag.string)
                if isinstance(data, list): data = data[0]
                
                # Check if this is the product info
                if data.get("@type") == "Product":
                    offers = data.get("offers", {})
                    if isinstance(offers, list): price = offers[0].get("price")
                    else: price = offers.get("price")
                        
                    if price:
                        return float(price)
            except:
                continue
                
        print("❌ Zara SEO data missing. (Bot detection might be high today)", flush=True)
        return None
    except Exception as e:
        print(f"❌ Zara Error: {e}", flush=True)
        return None

# --- 2. AMAZON (The Clean URL Strategy) ---
def fetch_amazon(url):
    clean_url = url.split("?")[0]
    print(f"📦 Amazon Detected: {clean_url}", flush=True)
    try:
        response = requests.get(clean_url, impersonate="chrome110", timeout=30)
        
        # Check for CAPTCHA
        if "api-services-support@amazon.com" in response.text or "Enter the characters" in response.text:
            print("🛑 AMAZON BLOCKED YOU (CAPTCHA Page).", flush=True)
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        
        # Try all price selectors
        selectors = [".a-price .a-offscreen", "#priceblock_ourprice", ".a-price-whole"]
        for sel in selectors:
            element = soup.select_one(sel)
            if element:
                clean = element.text.strip().replace("$", "").replace(",", "")
                # Find the first valid number
                match = re.search(r"(\d+\.\d+)", clean)
                if match:
                    return float(match.group(1))
                    
        print("❌ Amazon page loaded, but price not found (Layout mismatch)", flush=True)
        return None
    except Exception as e:
        print(f"❌ Amazon Error: {e}", flush=True)
        return None

# --- 3. EBAY (The Proven Method) ---
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
        
        print("❌ eBay price not found", flush=True)
        return None
    except Exception as e:
        print(f"❌ eBay Error: {e}", flush=True)
        return None

# --- ROUTER ---
def get_price(url):
    if "zara" in url: return fetch_zara(url)
    elif "amazon" in url: return fetch_amazon(url)
    elif "ebay" in url: return fetch_ebay(url)
    else: return None

# --- MAIN LOOP ---
def check_prices():
    print("--- STARTING PRICE CHECK ---", flush=True)
    
    # HARDCODED LIST for immediate testing
    items_to_track = [
        {"url": "https://www.ebay.ca/itm/376654197486", "note": "eBay Test"},
        {"url": "https://www.amazon.ca/Bluetooth-Anker-SoundCore-Dual-Driver-Distortion/dp/B016XTADG2", "note": "Amazon Test"},
        {"url": "https://www.zara.com/ca/en/textured-pocket-cardigan-p09598402.html", "note": "Zara Test"}
    ]

    for item in items_to_track:
        url = item["url"]
        note = item["note"]
        
        print(f"\n🔎 Checking {note}...", flush=True)
        price = get_price(url)
        
        if price:
            print(f"   ✅ SUCCESS: {price}", flush=True)
        else:
            print(f"   ❌ FAILED: Could not retrieve price.", flush=True)

    print("\n--- CHECK COMPLETE ---", flush=True)

if __name__ == "__main__":
    check_prices()