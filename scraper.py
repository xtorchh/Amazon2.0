import requests
from bs4 import BeautifulSoup
import time
import random
import os
import json
from playwright.sync_api import sync_playwright

# --- Configuration ---
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
if not DISCORD_WEBHOOK_URL:
    print("Warning: DISCORD_WEBHOOK_URL environment variable not set. Deals will not be sent to Discord.")

# Define the path for the file that stores sent deals.
# This path should ideally be within a persistent volume on Railway.
SENT_DEALS_FILE = "/app/data/sent_deals.json"

# --- Helper functions for managing sent deals ---
def load_sent_deals(file_path):
    """Loads previously sent deal links from a JSON file."""
    if not os.path.exists(file_path):
        print(f"No existing sent deals file found at {file_path}. Starting fresh.")
        return set() # Use a set for efficient lookup
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # Load as list, convert to set for lookup efficiency
            sent_deals = set(json.load(f))
            print(f"Loaded {len(sent_deals)} previously sent deals.")
            return sent_deals
    except (json.JSONDecodeError, FileNotFoundError, IOError) as e:
        print(f"Error loading sent deals from {file_path}: {e}. Starting fresh.")
        return set()

def save_sent_deals(file_path, sent_deals):
    """Saves the current list of sent deal links to a JSON file."""
    # Ensure the directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            # Convert set back to list for JSON serialization
            json.dump(list(sent_deals), f, indent=4)
            print(f"Saved {len(sent_deals)} sent deals to {file_path}.")
    except IOError as e:
        print(f"Error saving sent deals to {file_path}: {e}")

# --- Helper function to send to Discord ---
def send_to_discord(deal_info, source_name="Deal Bot"):
    """Sends deal information to a Discord webhook, with rate limit handling."""
    if not DISCORD_WEBHOOK_URL:
        return

    embed = {
        "title": deal_info["title"],
        "url": deal_info["link"],
        "color": 0xFFA500, # Orange for HUKD
        "fields": [
            {"name": "Price", "value": deal_info["price"], "inline": True},
            {"name": "Source", "value": source_name, "inline": True},
        ],
        "thumbnail": {"url": deal_info.get("image_url", "")}
    }
    
    if deal_info.get("discount_info") and deal_info["discount_info"] != "N/A":
        embed["fields"].append({"name": "Discount Info", "value": deal_info["discount_info"], "inline": False})
    
    if deal_info.get("metric_info"):
        embed["fields"].append({"name": "Popularity", "value": deal_info["metric_info"], "inline": True})


    payload = {
        "username": f"{source_name} Deal Bot",
        "avatar_url": "https://www.hotukdeals.com/favicon.ico",
        "embeds": [embed]
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 1)) / 1000 # Retry-After is in milliseconds
            print(f"Discord rate limited. Retrying after {retry_after:.2f} seconds...")
            time.sleep(retry_after + 0.1) 
            response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10) 

        response.raise_for_status()
        print(f"Successfully sent deal to Discord: {deal_info['title']} (Source: {source_name})")
    except requests.exceptions.RequestException as e:
        print(f"Error sending to Discord webhook from {source_name}: {e}")
    
    time.sleep(1)

# --- Helper function to try multiple selectors ---
def find_element_with_multiple_selectors(soup_or_element, selector_list):
    """
    Tries to find an element using a list of CSS selectors.
    Returns the first found element or None.
    """
    for selector in selector_list:
        found_element = soup_or_element.select_one(selector)
        if found_element:
            return found_element
    return None

def find_text_with_multiple_selectors(soup_or_element, selector_list, attribute=None):
    """
    Tries to find text or an attribute from an element using a list of CSS selectors.
    Returns the text/attribute or "N/A".
    """
    element = find_element_with_multiple_selectors(soup_or_element, selector_list)
    if element:
        if attribute:
            return element.get(attribute, "N/A").strip()
        return element.text.strip()
    return "N/A"

# --- Scraper for HotUKDeals.com with basic Playwright and backup selectors ---
def scrape_hotukdeals(max_pages=1):
    """Scrapes hotukdeals.com for popular deals using basic Playwright with backup selectors and scrolling."""
    base_url = "https://www.hotukdeals.com/"
    
    new_deals_sent = []
    
    # --- Deduplication: Load previously sent deals ---
    sent_deal_links = load_sent_deals(SENT_DEALS_FILE)

    # --- Define lists of potential selectors ---
    MAIN_DEAL_CONTAINER_SELECTORS = [
        'article.thread--card',                  # Original
        'div.thread--card',                      # Common: div instead of article
        'div[class*="deal-item"]',               # Generic "deal-item" in class
        'section[class*="product-card"]',        # Generic "product-card" in class
        'div[data-thread-id]',                   # If they use data attributes for threads
        'article[id*="thread"]',                 # If thread is in ID
        'div.x-threadCard',                      # Example of potential new, arbitrary class name
        'div.offer-card',                        # Another common naming convention
    ]

    TITLE_SELECTORS = [
        '.cept-deal-title',                      # Original
        '.deal-title-link',                      # Common alternative
        'h2.thread-title a',                     # Title inside H2, linked
        'h3.deal-item__title a',                 # Title inside H3
        'a[class*="title"]',                     # Link with "title" in class
    ]

    PRICE_SELECTORS = [
        '.thread-price',                         # Original
        '.deal-price',                           # Common alternative
        '.price-text',                           # Another common naming
        'span[class*="price"]',                  # Span with "price" in class
        '.current-price',                        # If they differentiate current/old price
        'div[class*="price"]',                   # Try a div for price
        '[itemprop="price"]',                    # Microdata price
        '.price',                                # Very generic price class
    ]

    HEAT_SELECTORS = [
        '.cept-vote-temp',                       # Original
        '.vote-temp',                            # Common alternative
        '.deal-heat',                            # Another common naming
        'span[class*="heat-count"]',             # Span with "heat-count" in class
        '.vote-score',                           # Generic score
    ]

    IMAGE_SELECTORS = [
        '.thread-image',                         # Original
        '.deal-image img',                       # Common structure: img inside a container
        'img[class*="product-image"]',           # Image with "product-image" in class
        'img[class*="deal-thumbnail"]',          # Image with "deal-thumbnail" in class
    ]
    # --- End selector lists ---

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()
        
        page_num = 1
        current_url = base_url

        SCROLL_ATTEMPTS_PER_PAGE = 3 
        
        while page_num <= max_pages: 
            print(f"Scraping HotUKDeals page {page_num} from {current_url} using Playwright (Basic with backup selectors and scrolling)...")
            try:
                page.goto(current_url, wait_until="networkidle", timeout=90000)
                
                combined_main_selector = ', '.join(MAIN_DEAL_CONTAINER_SELECTORS)
                try:
                    page.wait_for_selector(combined_main_selector, timeout=30000) 
                    print("HotUKDeals: Successfully waited for a deal card element (using backup selectors).")
                except Exception as e:
                    print(f"HotUKDeals: Did not find expected deal content after navigation (all backup selectors failed?). Error: {e}")
                    print(f"HotUKDeals: Current HTML content (first 1000 chars):\n{page.content()[:1000]}...")
                    break 

                # --- Scrolling Logic ---
                print(f"HotUKDeals: Attempting to scroll down {SCROLL_ATTEMPTS_PER_PAGE} times to load more deals.")
                for i in range(SCROLL_ATTEMPTS_PER_PAGE):
                    print(f"  Scrolling attempt {i+1} of {SCROLL_ATTEMPTS_PER_PAGE}...")
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(random.uniform(2, 4))
                    page.wait_for_load_state('networkidle', timeout=10000) 
                print("HotUKDeals: Finished scrolling attempts.")
                # --- End Scrolling Logic ---

                html_content = page.content()
                soup = BeautifulSoup(html_content, 'lxml')

                products = []
                for selector in MAIN_DEAL_CONTAINER_SELECTORS:
                    found_products = soup.select(selector)
                    if found_products:
                        products.extend(found_products)
                        break

                if not products:
                    print("HotUKDeals: No products found with any of the current main selectors (even after scrolling).")
                    print(f"HotUKDeals: HTML content received (first 2000 chars for debugging):\n{html_content[:2000]}...")
                    break

                for product in products:
                    title = find_text_with_multiple_selectors(product, TITLE_SELECTORS)
                    link_element = find_element_with_multiple_selectors(product, TITLE_SELECTORS)
                    link = link_element.get('href').strip() if link_element else "N/A"
                    
                    price = find_text_with_multiple_selectors(product, PRICE_SELECTORS)
                    heat = find_text_with_multiple_selectors(product, HEAT_SELECTORS)
                    image_url = find_text_with_multiple_selectors(product, IMAGE_SELECTORS, attribute='src')
                    discount_info = "N/A"

                    if title != "N/A" and link != "N/A" and price != "N/A":
                        deal_item = {
                            "title": title,
                            "price": price,
                            "link": link,
                            "image_url": image_url,
                            "metric_info": f"🔥 {heat} Heat",
                            "discount_info": discount_info
                        }
                        
                        # --- Deduplication: Check if deal has already been sent ---
                        if deal_item['link'] not in sent_deal_links:
                            send_to_discord(deal_item, source_name="HotUKDeals")
                            sent_deal_links.add(deal_item['link']) # Add to set of sent deals
                            new_deals_sent.append(deal_item) # Keep track of new deals for logging
                        else:
                            print(f"Skipped already sent deal: {deal_item['title']}")
                    else:
                        print(f"HotUKDeals: Skipped incomplete deal (potential selector issue). Title: '{title}', Link: '{link}', Price: '{price}'")

                # --- Pagination Logic ---
                next_button_selector = 'li.pagination-next a'
                load_more_selector = 'a.cept-load-more'

                if page_num < max_pages:
                    if page.is_visible(load_more_selector, timeout=5000): 
                        print("HotUKDeals: Clicking 'Load More' button...")
                        page.click(load_more_selector)
                        page.wait_for_load_state('networkidle', timeout=30000) 
                        current_url = page.url 
                        page_num += 1
                    elif page.is_visible(next_button_selector, timeout=5000): 
                        print("HotUKDeals: Clicking next page link...")
                        page.click(next_button_selector)
                        page.wait_for_load_state('domcontentloaded', timeout=30000)
                        current_url = page.url 
                        page_num += 1
                    else:
                        print("HotUKDeals: No more pages or load more button found. Stopping pagination.")
                        break
                else:
                    print("HotUKDeals: Max pages reached. Stopping pagination.")
                    break

            except Exception as e:
                print(f"Error during Playwright scraping for HotUKDeals: {e}")
                import traceback
                traceback.print_exc() 
                break
        
        browser.close()
    
    # --- Deduplication: Save updated list of sent deals ---
    save_sent_deals(SENT_DEALS_FILE, sent_deal_links)

    return new_deals_sent # Return only newly sent deals for clearer count

if __name__ == "__main__":
    print("Starting deal scraping from HotUKDeals...")
    
    print("\n--- Scraping HotUKDeals ---")
    newly_sent_deals = scrape_hotukdeals(max_pages=1) 

    total_new_deals_sent = len(newly_sent_deals)
    if total_new_deals_sent == 0:
        print("No new deals found and sent to Discord in this run.")
    else:
        print(f"\nScraping complete. Found and sent {total_new_deals_sent} NEW deals from HotUKDeals.")

