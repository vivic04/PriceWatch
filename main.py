from curl_cffi import requests
from bs4 import BeautifulSoup
import json
import os
import re

# --- CONFIG ---
WEBHOOK_URL = os.environ.get("DISCORD_URL") 
DB_FILE = "price_history.json"
TRACKING_FILE = "tracking_list.json"

# --- 1. ZARA (The "SEO" Strategy) ---
def fetch_zara(url):
    print(f"👗 Zara Detected: Checking public SEO data...")
    try:
        # 1. Clean URL and Fetch
        response = requests.get(url, impersonate="chrome110", timeout=30)
        soup = BeautifulSoup(response.text, "html.parser")

        # 2. Look for the "Product" tag that Google reads
        # This is usually a script called "application/ld+json"
        schema_tags = soup.find_all("script", type="application/ld+json")
        
        for tag in schema_tags:
            try:
                data = json.loads(tag.string)
                
                # Sometimes the data is a list, sometimes a dict
                if isinstance(data, list):
                    data = data[0]
                
                # Check if this valid Product data
                if data.get("@type") == "Product":
                    # Grab the price from the "offers" section
                    offers = data.get("offers", {})
                    
                    # Sometimes offers is a list (multiple sizes)
                    if isinstance(offers, list):
                        price = offers[0].get("price")
                    else:
                        price = offers.get("price")
                        
                    if price:
                        print(f"   Found SEO Price: {price}")
                        return float(price)
            except:
                continue
                
        # 3. Fallback: Try the "Raw Meta Data" if SEO fails
        meta_price = soup.find("meta", property="product:price:amount")
        if meta_price:
             return float(meta_price["content"])

        print("❌ Zara SEO data missing. They might be blocking cloud IPs.")
        return None

    except Exception as e:
        print(f"❌ Zara Error: {e}")
        return None

# --- 2. AMAZON (Clean URL Strategy) ---
def fetch_amazon(url):
    # CLEAN THE URL: Strip all the tracking junk
    # Converts: https://amazon.ca/dp/B016XTADG2/?stuff... -> https://amazon.ca/dp/B016XTADG2
    clean_url = url.split("?")[0]
    print(f"📦 Amazon Detected: {clean_url}")
    
    try:
        response = requests.get(clean_url, impersonate="chrome110", timeout=30)
        
        # Check for the "Dog Page" (CAPTCHA)
        if "api-services-support@amazon.com" in response.text or "Enter the characters" in response.text:
            print("🛑 AMAZON BLOCKED YOU (CAPTCHA Page).")
            print("   (This is normal for GitHub IPs. You need a Proxy to fix this reliably.)")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        
        # Try finding the price
        selectors = [".a-price .a-offscreen", "#priceblock_ourprice", ".a-price-whole"]
        for sel in selectors:
            element = soup.select_one(sel)
            if element:
                # Clean "$24.99" -> 24.99
                clean = element.text.strip().replace("$", "").replace(",", "").replace(".", "")
                
                # Regex to find the first real number (e.g. "24.99")
                match = re.search(r"(\d+\.\d+)", element.text.replace("$", "").replace(",", ""))
                if match:
                    return float(match.group(1))
                    
        print("❌ Page loaded, but price not found (Layout mismatch)")
        return None

    except Exception as e:
        print(f"❌ Amazon Error: {e}")
        return None

# --- 3. EBAY (Keep this, it works) ---
def fetch_ebay(url):
    # ... (Paste your working eBay function here) ...
    # (I'm skipping pasting it to save space, but DO NOT DELETE IT from your file!)
    print(f"🕵️  eBay Detected: {url}")
    # ... use the exact code you had before ...
    # Quick fix for now:
    try:
        clean_url = url.split("?")[0]
        response = requests.get(clean_url, impersonate="chrome110", timeout=30)
        soup = BeautifulSoup(response.text, "html.parser")
        price_element = soup.find('div', class_='x-price-primary')
        if not price_element: price_element = soup.find('span', id='prcIsum')
        if price_element:
            text = price_element.text.strip().replace("C", "").replace("US", "").replace("$", "").replace(",", "")
            if "Approx" in text: text = text.split("Approx")[1]
            return float(text.strip())
    except:
        return None
    return None

# --- ROUTER ---
def get_price(url):
    if "zara" in url: return fetch_zara(url)
    elif "amazon" in url: return fetch_amazon(url)
    elif "ebay" in url: return fetch_ebay(url)
    else: return None

# ... (Rest of main loop logic)