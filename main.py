from curl_cffi import requests
from bs4 import BeautifulSoup
import json
import os
import re # We need Regex to find hidden JSON data

# --- CONFIG ---
WEBHOOK_URL = os.environ.get("DISCORD_URL") 
DB_FILE = "price_history.json"
TRACKING_FILE = "tracking_list.json"

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

# --- 1. ZARA / ARITZIA (The "Hidden JSON" Strategy) ---
def fetch_zara(url):
    print(f"👗 Zara Detected: Hunting for hidden JSON data...")
    try:
        response = requests.get(url, impersonate="chrome", timeout=30)
        
        # 1. Regex Search: Look for the specific pattern Zara uses to store data
        # They often store it in a variable called "product" or inside "viewPayload"
        # We look for the price section directly to be safe
        
        # Strategy: Look for "price":1234 (Zara stores prices as integers, e.g., 4599 for $45.99)
        # This is a bit "hacky" but works when the JSON structure changes
        matches = re.findall(r'"price":\s*(\d+)', response.text)
        
        if matches:
            # Zara usually lists the main price first or multiple times.
            # We take the largest number found (to avoid finding "0" or discount placeholders)
            prices = [int(p) for p in matches]
            max_price = max(prices)
            
            # Convert 4599 -> 45.99
            final_price = max_price / 100
            print(f"   Found hidden price in script: {final_price}")
            return float(final_price)
            
        print("❌ Zara JSON not found. They might have changed their code.")
        return None

    except Exception as e:
        print(f"❌ Zara Error: {e}")
        return None
# --- 2. AMAZON (The "Fort Knox" Strategy) ---
def fetch_amazon(url):
    print(f"📦 Amazon Detected: {url}")
    try:
        # Amazon requires the newest Chrome impersonation
        response = requests.get(url, impersonate="chrome110", timeout=30)
        
        # 1. THE BLOCK CHECK
        if "api-services-support@amazon.com" in response.text or "Enter the characters you see below" in response.text:
            print("🛑 AMAZON BLOCKED YOU (CAPTCHA Page).")
            print("   Solution: You need a Residential Proxy to fix this.")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        
        # 2. SELECTOR ROULETTE (Try everything)
        selectors = [
            ".a-price .a-offscreen",           # Most common
            "#priceblock_ourprice",            # Older items
            "#priceblock_dealprice",           # On sale
            "span.a-color-price",              # Books
            ".a-price-whole"                   # Just the main number
        ]
        
        for sel in selectors:
            element = soup.select_one(sel)
            if element:
                clean = element.text.strip().replace("$", "").replace(",", "").replace(".", "")
                # Amazon might return "24" and "99" separately.
                # If we get a whole number, assume it's the dollars.
                # For safety, let's just grab the first valid float we see.
                try:
                    # Quick fix for currency formatting issues
                    import re
                    # Extract just the numbers and dot (e.g. "24.99")
                    found_price = re.search(r'\d+\.\d+', element.text)
                    if found_price:
                        return float(found_price.group())
                except:
                    continue

        print("❌ Page loaded, but no price found (Amazon might have changed layout)")
        return None

    except Exception as e:
        print(f"❌ Amazon Error: {e}")
        return None
# --- ROUTER (The "Brain") ---
def get_price(url):
    domain = url
    if "zara" in domain:
        return fetch_zara(url)
    elif "amazon" in domain:
        return fetch_amazon(url)
    elif "ebay" in domain:
        # Put your existing eBay function here!
        return fetch_ebay(url) 
    else:
        print("Unknown Domain")
        return None

# ... (Keep your load_tracking_list and main loop the same)
# --- MAIN LOGIC ---
TRACKING_FILE = "tracking_list.json"

def load_tracking_list():
    """Reads the list of URLs from an external file"""
    if os.path.exists(TRACKING_FILE):
        with open(TRACKING_FILE, 'r') as f:
            return json.load(f)
    else:
        print(f"⚠️ Warning: {TRACKING_FILE} not found. Creating a template.")
        # Create a dummy file so the user sees where to put links
        dummy_data = [{"url": "PUT_URL_HERE", "note": "Example Item"}]
        with open(TRACKING_FILE, 'w') as f:
            json.dump(dummy_data, f, indent=4)
        return []
    

def check_prices():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            price_history = json.load(f)
    else:
        price_history = {}
    tracking_data = load_tracking_list()
    load_list = [item['url'] for item in tracking_data]
    for url in load_list:
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