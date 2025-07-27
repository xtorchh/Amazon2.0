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

# --- Helper function to send to Discord ---
def send_to_discord(deal_info, source_name="Deal Bot"):
    """Sends deal information to a Discord webhook."""
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
        response.raise_for_status()
        print(f"Successfully sent deal to Discord: {deal_info['title']} (Source: {source_name})")
    except requests.exceptions.RequestException as e:
        print(f"Error sending to Discord webhook from {source_name}: {e}")

# --- Helper function to try multiple selectors ---
def find_element_with_multiple_selectors(soup_or_element, selector_list):
    """
    Tries to find an element using a list of CSS selectors.
    Returns the first found element or None.
    """
    for selector in selector_list:
        found_element = soup_or_element.select_one(selector)
        if found_element:
            # print(f"  Found element with selector: {selector}") # Uncomment for verbose debugging
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
    """Scrapes hotukdeals.com for popular deals using basic Playwright with backup selectors."""
    base_url = "https://www.hotukdeals.com/"
    
    deals_found = []
    
    # --- Define lists of potential selectors ---
    # These are speculative and need live inspection for verification
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

        while page_num <= max_pages: 
            print(f"Scraping HotUKDeals page {page_num} from {current_url} using Playwright (Basic with backup selectors)...")
            try:
                page.goto(current_url, wait_until="networkidle", timeout=90000)
                
                # --- Update: Wait for ANY of the main deal container selectors ---
                try:
                    # Construct a CSS selector string that tries all main container selectors
                    combined_main_selector = ', '.join(MAIN_DEAL_CONTAINER_SELECTORS)
                    page.wait_for_selector(combined_main_selector, timeout=30000) 
                    print("HotUKDeals: Successfully waited for a deal card element (using backup selectors).")
                except Exception as e:
                    print(f"HotUKDeals: Did not find expected deal content after navigation (all backup selectors failed?). Error: {e}")
                    print(f"HotUKDeals: Current HTML content (first 1000 chars):\n{page.content()[:1000]}...")
                    # If even backup selectors for main container fail, likely total block or major redesign.
                    break 

                html_content = page.content()
                soup = BeautifulSoup(html_content, 'lxml')

                # --- Use the helper function for the main deal containers ---
                products = []
                for selector in MAIN_DEAL_CONTAINER_SELECTORS:
                    found_products = soup.select(selector) # Use select (find_all equivalent for CSS selectors)
                    if found_products:
                        products.extend(found_products)
                        # print(f"  Found products with main selector: {selector}") # Uncomment for verbose debugging
                        break # Stop after finding products with the first working selector

                if not products:
                    print("HotUKDeals: No products found with any of the current main selectors.")
                    print(f"HotUKDeals: HTML content received (first 2000 chars for debugging):\n{html_content[:2000]}...")
                    break

                for product in products:
                    # --- Use helper functions for nested elements ---
                    title = find_text_with_multiple_selectors(product, TITLE_SELECTORS)
                    link_element = find_element_with_multiple_selectors(product, TITLE_SELECTORS)
                    link = link_element.get('href').strip() if link_element else "N/A"
                    
                    price = find_text_with_multiple_selectors(product, PRICE_SELECTORS)
                    heat = find_text_with_multiple_selectors(product, HEAT_SELECTORS)
                    image_url = find_text_with_multiple_selectors(product, IMAGE_SELECTORS, attribute='src')
                    discount_info = "N/A" # HotUKDeals typically doesn't have a separate discount % field easily scrapeable

                    if title != "N/A" and link != "N/A" and price != "N/A":
                        deal_item = {
                            "title": title,
                            "price": price,
                            "link": link,
                            "image_url": image_url,
                            "metric_info": f"🔥 {heat} Heat",
                            "discount_info": discount_info
                        }
                        deals_found.append(deal_item)
                        send_to_discord(deal_item, source_name="HotUKDeals")
                    else:
                        print(f"HotUKDeals: Skipped incomplete deal (potential selector issue). Title: '{title}', Link: '{link}', Price: '{price}'")

                # --- HOTUKDEALS PAGINATION WITH PLAYWRIGHT ---
                # These selectors are for buttons/links, less likely to change drastically.
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

                time.sleep(random.uniform(2, 5)) 

            except Exception as e:
                print(f"Error during Playwright scraping for HotUKDeals: {e}")
                import traceback
                traceback.print_exc() 
                break
        
        browser.close()
    return deals_found

if __name__ == "__main__":
    print("Starting deal scraping from HotUKDeals using Playwright (Basic with backup selectors). This may still hit Cloudflare blocks or miss deals if selectors are very different.")
    
    print("\n--- Scraping HotUKDeals ---")
    hukd_deals = scrape_hotukdeals(max_pages=1) 

    total_deals_found = len(hukd_deals)
    if total_deals_found == 0:
        print("No new deals found from HotUKDeals in this run.")
    else:
        print(f"\nScraping complete. Found and attempted to send {len(hukd_deals)} deals from HotUKDeals.")
