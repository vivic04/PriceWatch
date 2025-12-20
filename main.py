import requests
from bs4 import BeautifulSoup
import json
import os
from urllib.parse import urlparse

# --- CONFIG ---
WEBHOOK_URL = os.environ.get("DISCORD_URL") 
DB_FILE = "price_history.json"

# REAL WORLD HEADERS: Updated to look more like a standard browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# --- PARSERS (The Tools) ---

def parse_toscrape(soup):
    """Logic specifically for books.toscrape.com"""
    price_element = soup.find('p', class_='price_color')
    if price_element:
        return float(price_element.text[2:])
    return None

def parse_ebay(soup):
    """Logic specifically for eBay (Works for .com, .ca, .co.uk, etc)"""
    # eBay tries to hide prices in different places. We check the most common ones.
    
    # 1. Try the standard 'main price' div
    price_element = soup.find('div', class_='x-price-primary')
    
    # 2. If that fails, try the older ID style
    if not price_element:
        price_element = soup.find('span', id='prcIsum')
    
    # 3. If that fails, try the 'shipping included' style
    if not price_element:
        price_element = soup.find('div', class_='main-price-with-shipping')

    if price_element:
        text = price_element.text.strip()
        # Clean up currency symbols (CAD, US, $, etc.)
        # We remove letters and $ signs, keeping only numbers and dots
        clean_text = text.replace("C", "").replace("US", "").replace("$", "").replace(",", "").strip()
        
        # Sometimes eBay puts "Approx" in front. Remove that.
        if "Approx" in clean_text:
            clean_text = clean_text.split("Approx")[1]
            
        try:
            return float(clean_text)
        except:
            print(f"Could not convert '{text}' to number")
            return None
    
    print("Debug: eBay price element not found in HTML.")
    return None

# --- THE ROUTER (The Brain) ---

def get_price(url):
    try:
        # CLEAN THE URL: Remove everything after the '?'
        clean_url = url.split("?")[0]
        
        print(f"Fetching: {clean_url}")
        
        # INCREASED TIMEOUT: From 10 -> 30 seconds
        response = requests.get(clean_url, headers=HEADERS, timeout=30)
        
        if response.status_code != 200:
            print(f"⚠️ Blocked or Error ({response.status_code})")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        domain = urlparse(clean_url).netloc 

        # UPDATED SWITCHBOARD: Checks for 'ebay.' anywhere in the domain name
        if "toscrape.com" in domain:
            return parse_toscrape(soup)
        elif "ebay." in domain: 
            return parse_ebay(soup)
        else:
            print(f"❌ Error: No parser built for {domain} yet!")
            return None

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        return None

# --- MAIN LOGIC ---
my_items = [
    "http://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
    "https://www.ebay.ca/itm/376654197486",
    "https://www.ebay.ca/itm/177323518317"
]

def check_prices():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            price_history = json.load(f)
    else:
        price_history = {}

    for url in my_items:
        price = get_price(url)
        
        if price:
            print(f"✅ Price found: {price}")
            
            clean_url = url.split("?")[0] # Use clean URL for history key
            
            if clean_url in price_history:
                old_price = price_history[clean_url]
                if price != old_price:
                    msg = f"🚨 CHANGE: {old_price} -> {price} | {clean_url}"
                    if WEBHOOK_URL:
                        requests.post(WEBHOOK_URL, json={"content": msg})
                        print("Alert sent to Discord.")
                    price_history[clean_url] = price
            else:
                price_history[clean_url] = price
        else:
            print(f"Failed to extract price for {url}")

    with open(DB_FILE, 'w') as f:
        json.dump(price_history, f)

if __name__ == "__main__":
    check_prices()