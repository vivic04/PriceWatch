import requests
from bs4 import BeautifulSoup
import json
import os
import time

def send_discord_alert(message):
    webhook_url = "https://discord.com/api/webhooks/1449920563106812026/4W5R_WklStpv2W9lWt5r91kbix09SUB5txwJymX6Aexzvb8dendOD52ITO632nfeAaGn"
    data = {
        "content": message
    }
    # This acts like a browser submitting a form
    try:
        requests.post(webhook_url, json=data)
        print("Sent alert to Discord!")
    except Exception as e:
        print(f"Failed to send alert: {e}")

def get_book_price(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    
    # The logic you just fixed:
    price_element = soup.find('p', class_='price_color')
    
    if price_element:
        price_text = price_element.text  # "£51.77"
        clean_price = price_text[2:]     # "51.77"
        return float(clean_price)        # 51.77 (The Number)
    else:
        return None

DB_FILE = "price_history.json"
CHECK_INTERVAL = 60  # Check every 60 seconds

print(f"Monitor started. I will check prices every {CHECK_INTERVAL} seconds.")
print("Press Ctrl+C to stop me.")
my_books = [
    "http://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
    "http://books.toscrape.com/catalogue/tipping-the-velvet_999/index.html",
    "http://books.toscrape.com/catalogue/soumission_998/index.html"
]
while True:
    # --- LOAD DATABASE ---
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            price_history = json.load(f)
    else:
        price_history = {}

    print(f"Checking prices at {time.ctime()}...")

    # --- CHECK PRICES ---
    for book_url in my_books:
        current_price = get_book_price(book_url)
        
        if current_price is None:
            print(f"Error fetching {book_url}")
            continue

        if book_url in price_history:
            old_price = price_history[book_url]
            
            if current_price != old_price:
                # THIS IS WHERE YOU WOULD EMAIL THE CUSTOMER
                send_discord_alert(f"🚨 ALERT! PRICE CHANGE: {old_price} -> {current_price}")
                
                # Update the database immediately so we don't alert twice
                price_history[book_url] = current_price
        else:
            print(f"First time seeing this book.")
            price_history[book_url] = current_price

    # --- SAVE DATABASE ---
    with open(DB_FILE, 'w') as f:
        json.dump(price_history, f)
    
    print("Sleeping...")
    # This pauses the code so your computer doesn't overheat
    time.sleep(CHECK_INTERVAL)