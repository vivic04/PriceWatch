import requests
from bs4 import BeautifulSoup
import json
import os
from urllib.parse import urlparse

# --- CONFIG ---
WEBHOOK_URL = os.environ.get("DISCORD_URL") 
DB_FILE = "price_history.json"

# REAL WORLD HEADER: This makes us look like a Chrome Browser on Windows
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# --- PARSERS (The Tools) ---

def parse_toscrape(soup):
    """Logic specifically for books.toscrape.com"""
    price_element = soup.find('p', class_='price_color')
    if price_element:
        # Returns "£51.77" -> 51.77
        return float(price_element.text[2:])
    return None

def parse_ebay(soup):
    """Logic specifically for eBay"""
    # eBay usually keeps price in 'x-price-primary' or 'prcIsum'
    # We try one, if it fails, try the other
    price_element = soup.find('div', class_='x-price-primary')
    if not price_element:
        price_element = soup.find('span', id='ux-textspans')
        
    if price_element:
        # eBay often has "US $20.00", we need to split the text to find the number
        text = price_element.text.strip()
        # Remove '$', 'US', and commas
        clean_text = text.replace("US", "").replace("$", "").replace(",", "").strip()
        try:
            return float(clean_text)
        except:
            return None
    return None

# --- THE ROUTER (The Brain) ---

def get_price(url):
    try:
        print(f"Fetching: {url}")
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"⚠️ Blocked or Error ({response.status_code})")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        domain = urlparse(url).netloc # Extracts "www.ebay.com" or "books.toscrape.com"

        # This is the "Switchboard"
        if "toscrape.com" in domain:
            return parse_toscrape(soup)
        elif "ebay.com" in domain:
            return parse_ebay(soup)
        # elif "amazon.com" in domain:  <-- We will add this later
        #    return parse_amazon(soup)
        else:
            print(f"❌ Error: No parser built for {domain} yet!")
            return None

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        return None

# --- MAIN LOGIC ---
# Now we can mix and match websites!
my_items = [
    "https://www.ebay.ca/itm/376654197486"
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
            
            # Logic to check vs history
            if url in price_history:
                old_price = price_history[url]
                if price != old_price:
                    msg = f"🚨 CHANGE: {old_price} -> {price} | {url}"
                    if WEBHOOK_URL:
                        requests.post(WEBHOOK_URL, json={"content": msg})
                    price_history[url] = price
            else:
                price_history[url] = price
        else:
            print(f"Failed to extract price for {url}")

    with open(DB_FILE, 'w') as f:
        json.dump(price_history, f)

if __name__ == "__main__":
    check_prices()