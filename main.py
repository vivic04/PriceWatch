from curl_cffi import requests 
from bs4 import BeautifulSoup
import json
import os
from urllib.parse import urlparse

# --- CONFIG ---
WEBHOOK_URL = os.environ.get("DISCORD_URL") 
DB_FILE = "price_history.json"

# --- FETCHERS ---

def fetch_ebay(url):
    print(f"🕵️  eBay Detected: Using Browser Impersonation for {url}")
    
    try:
        # CLEAN THE URL
        clean_url = url.split("?")[0]
        
        # THE MAGIC LINE: 'impersonate="chrome"'
        # This spoofs the TLS Handshake (The "Secret Handshake")
        response = requests.get(
            clean_url, 
            impersonate="chrome", 
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"⚠️ eBay Blocked: Status {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        
        # eBay Parsing Logic
        price_element = soup.find('div', class_='x-price-primary')
        if not price_element:
            price_element = soup.find('span', id='prcIsum')
        if not price_element:
             price_element = soup.find('div', class_='main-price-with-shipping')

        if price_element:
            text = price_element.text.strip()
            print(f"   Raw Text Found: {text}") # Debug print
            clean_text = text.replace("C", "").replace("US", "").replace("$", "").replace(",", "").strip()
            if "Approx" in clean_text:
                clean_text = clean_text.split("Approx")[1]
            return float(clean_text)
        else:
            print("❌ Price tag not found (Check HTML structure)")
            return None

    except Exception as e:
        print(f"❌ eBay Error: {e}")
        return None

def fetch_toscrape(url):
    print(f"👶 Sandbox Detected: {url}")
    try:
        # We also use curl_cffi here just to keep it simple, 
        # but we don't strictly need impersonation for the sandbox.
        response = requests.get(url, impersonate="chrome", timeout=30)
        soup = BeautifulSoup(response.text, "html.parser")
        
        price_element = soup.find('p', class_='price_color')
        if price_element:
            return float(price_element.text[1:])
        return None
    except Exception as e:
        print(f"❌ Sandbox Error: {e}")
        return None

# --- ROUTER ---

def check_prices():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            price_history = json.load(f)
    else:
        price_history = {}

    my_items = [
        "http://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        "https://www.ebay.ca/itm/376654197486" 
    ]

    for url in my_items:
        current_price = None
        
        if "ebay" in url:
            current_price = fetch_ebay(url)
        elif "toscrape" in url:
            current_price = fetch_toscrape(url)
        
        if current_price is not None:
            print(f"✅ Price found: {current_price}")
            
            clean_key = url.split("?")[0]
            
            if clean_key in price_history:
                old_price = price_history[clean_key]
                if current_price != old_price:
                    msg = f"🚨 CHANGE: {old_price} -> {current_price} | {clean_key}"
                    if WEBHOOK_URL:
                        requests.post(WEBHOOK_URL, json={"content": msg}, impersonate="chrome")
                    price_history[clean_key] = current_price
            else:
                price_history[clean_key] = current_price

    with open(DB_FILE, 'w') as f:
        json.dump(price_history, f)

if __name__ == "__main__":
    check_prices()