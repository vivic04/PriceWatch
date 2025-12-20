import requests
from bs4 import BeautifulSoup
import json
import os
from urllib.parse import urlparse

# --- CONFIG ---
WEBHOOK_URL = os.environ.get("DISCORD_URL") 
DB_FILE = "price_history.json"

# --- THE "HEAVY ARMOR" (For eBay) ---
# We use this ONLY for big retail sites
def fetch_ebay(url):
    print(f"🕵️  eBay Detected: Putting on the Tuxedo for {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate", # eBay likes compression
        "Connection": "keep-alive",
    }

    try:
        # CLEAN THE URL (Strip the tracking junk)
        clean_url = url.split("?")[0]
        
        response = requests.get(clean_url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"⚠️ eBay Blocked or Error: Status {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        
        # PARSING LOGIC
        # 1. Try Main Price
        price_element = soup.find('div', class_='x-price-primary')
        # 2. Try ID Price
        if not price_element:
            price_element = soup.find('span', id='prcIsum')
        # 3. Try Shipping Included Price
        if not price_element:
             price_element = soup.find('div', class_='main-price-with-shipping')

        if price_element:
            text = price_element.text.strip()
            # Clean: "C $20.00" -> "20.00"
            clean_text = text.replace("C", "").replace("US", "").replace("$", "").replace(",", "").strip()
            if "Approx" in clean_text:
                clean_text = clean_text.split("Approx")[1]
            return float(clean_text)
        else:
            print("❌ eBay loaded, but price tag not found (Check HTML)")
            return None

    except Exception as e:
        print(f"❌ eBay Error: {e}")
        return None


# --- THE "LIGHT ARMOR" (For Sandbox) ---
# We use this for simple sites that break if we send complex headers
def fetch_toscrape(url):
    print(f"👶 Sandbox Detected: Going nicely for {url}")
    
    # NO HEADERS. Just be a normal Python script.
    try:
        response = requests.get(url, timeout=30)
        soup = BeautifulSoup(response.text, "html.parser")
        
        price_element = soup.find('p', class_='price_color')
        if price_element:
            # "£51.77" -> 51.77
            return float(price_element.text[1:])
        return None
    except Exception as e:
        print(f"❌ Sandbox Error: {e}")
        return None


# --- THE ROUTER (Traffic Control) ---
def check_prices():
    # 1. Load History
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            price_history = json.load(f)
    else:
        price_history = {}

    # 2. The List of Targets
    my_items = [
        "http://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        "https://www.ebay.ca/itm/376654197486" # Put your eBay link here
    ]

    # 3. Process Each Item
    for url in my_items:
        current_price = None
        
        # ROUTING LOGIC
        if "ebay" in url:
            current_price = fetch_ebay(url)
        elif "toscrape" in url:
            current_price = fetch_toscrape(url)
        else:
            print(f"Unknown domain for {url}")
            continue

        # 4. Save & Alert Logic
        if current_price is not None:
            print(f"✅ Price found: {current_price}")
            
            # Use clean key for history
            history_key = url.split("?")[0]
            
            if history_key in price_history:
                old_price = price_history[history_key]
                if current_price != old_price:
                    msg = f"🚨 CHANGE: {old_price} -> {current_price} | {history_key}"
                    if WEBHOOK_URL:
                        requests.post(WEBHOOK_URL, json={"content": msg})
                        print("Alert sent.")
                    price_history[history_key] = current_price
            else:
                price_history[history_key] = current_price

    # 5. Save History
    with open(DB_FILE, 'w') as f:
        json.dump(price_history, f)

if __name__ == "__main__":
    check_prices()