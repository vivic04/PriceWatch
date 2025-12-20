import requests
from bs4 import BeautifulSoup
import json
import os

# --- 1. SETUP ---
# We get the URL from the "Safe" box (Environment Variable)
# If it's not found, we warn you but don't crash
WEBHOOK_URL = os.environ.get("DISCORD_URL") 
DB_FILE = "price_history.json"

my_books = [
    "http://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
    "http://books.toscrape.com/catalogue/tipping-the-velvet_999/index.html",
    "http://books.toscrape.com/catalogue/soumission_998/index.html"
]

def send_discord_alert(message):
    if not WEBHOOK_URL:
        print(f"NO DISCORD URL FOUND. Mock Alert: {message}")
        return

    data = {"content": message}
    try:
        requests.post(WEBHOOK_URL, json=data)
        print("Sent alert to Discord!")
    except Exception as e:
        print(f"Failed to send alert: {e}")

def get_book_price(url):
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        price_element = soup.find('p', class_='price_color')
        
        if price_element:
            price_text = price_element.text  # "£51.77"
            # If you are unsure, print(price_text) to check!
            clean_price = price_text[2:]     
            return float(clean_price)
        else:
            return None
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

def check_prices():
    # --- LOAD DATABASE ---
    # On GitHub Actions, we will restore this file before running
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            price_history = json.load(f)
    else:
        price_history = {}
        print("No history found. Starting fresh.")

    # --- CHECK PRICES ---
    for book_url in my_books:
        current_price = get_book_price(book_url)
        
        if current_price is None:
            continue

        if book_url in price_history:
            old_price = price_history[book_url]
            # Check for difference
            if current_price != old_price:
                msg = f"🚨 PRICE CHANGE! {old_price} -> {current_price} | {book_url}"
                send_discord_alert(msg)
                price_history[book_url] = current_price
            else:
                print(f"No change for {book_url} ({current_price})")
        else:
            print(f"First time tracking: {book_url}")
            price_history[book_url] = current_price

    # --- SAVE DATABASE ---
    with open(DB_FILE, 'w') as f:
        json.dump(price_history, f)
    print("Database updated.")

if __name__ == "__main__":
    check_prices()