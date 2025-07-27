import requests # Keeping requests just in case, though not used for HUKD anymore
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
    
    # Add discount if available
    if deal_info.get("discount_info") and deal_info["discount_info"] != "N/A":
        embed["fields"].append({"name": "Discount Info", "value": deal_info["discount_info"], "inline": False})
    
    # Add Heat/Likes if available
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

# --- Scraper for HotUKDeals.com with Playwright ---
def scrape_hotukdeals(max_pages=1):
    """Scrapes hotukdeals.com for popular deals using Playwright."""
    base_url = "https://www.hotukdeals.com/"
    
    deals_found = []
    
    with sync_playwright() as p:
        # Launch a Chromium browser in headless mode (no visible UI)
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        page_num = 1
        current_url = base_url

        while page_num <= max_pages: 
            print(f"Scraping HotUKDeals page {page_num} from {current_url} using Playwright...")
            try:
                # Navigate to the page and wait for the DOM to be ready
                # 'domcontentloaded' waits for HTML parsing, 'networkidle' waits for network activity to cease
                page.goto(current_url, wait_until="domcontentloaded", timeout=60000) 
                
                # OPTIONAL: Wait for the main deal elements to be visible/loaded
                # This can help if content is lazy-loaded or takes time to appear.
                # page.wait_for_selector('article.thread--card', timeout=30000) 

                # Get the fully rendered HTML content
                html_content = page.content()
                soup = BeautifulSoup(html_content, 'lxml')

                # --- HOTUKDEALS MAIN DEAL CONTAINER SELECTOR ---
                # This should still be accurate. Playwright ensures JS rendering.
                products = soup.find_all('article', class_='thread--card') 

                if not products:
                    print("HotUKDeals: No products found with current selector. HTML structure may have changed or content not loaded.")
                    print(f"HotUKDeals: HTML content received (first 2000 chars for debugging):\n{html_content[:2000]}...")
                    break

                for product in products:
                    title = "N/A"
                    link = "N/A"
                    price = "N/A"
                    heat = "N/A"
                    image_url = ""
                    discount_info = "N/A"

                    # --- HOTUKDEALS NESTED SELECTORS ---
                    # These should be robust enough with Playwright
                    title_link_tag = product.find('a', class_='cept-deal-title')
                    if title_link_tag:
                        title = title_link_tag.text.strip()
                        if 'href' in title_link_tag.attrs:
                            link = title_link_tag['href']
                    
                    price_tag = product.find('span', class_='thread-price')
                    if price_tag:
                        price = price_tag.text.strip()

                    heat_tag = product.find('span', class_='cept-vote-temp')
                    if heat_tag:
                        heat = heat_tag.text.strip()

                    image_tag = product.find('img', class_='thread-image')
                    if image_tag and 'src' in image_tag.attrs:
                        image_url = image_tag['src']

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
                # Playwright allows clicking buttons, which is more reliable than parsing URLs
                next_button_selector = 'li.pagination-next a' # For standard 'next page' links
                load_more_selector = 'a.cept-load-more' # For "Load More" buttons

                if page_num < max_pages:
                    # Prefer clicking 'Load More' if it exists, as HUKD often uses it.
                    if page.is_visible(load_more_selector, timeout=5000): 
                        print("HotUKDeals: Clicking 'Load More' button...")
                        page.click(load_more_selector)
                        # Wait for network activity to settle after clicking, indicating new content loaded
                        page.wait_for_load_state('networkidle', timeout=30000) 
                        current_url = page.url # URL might change, or content is appended. Update to current URL.
                        page_num += 1
                    elif page.is_visible(next_button_selector, timeout=5000): # Fallback to standard next page link
                        print("HotUKDeals: Clicking next page link...")
                        page.click(next_button_selector)
                        page.wait_for_load_state('domcontentloaded', timeout=30000)
                        current_url = page.url # Update URL for the next iteration
                        page_num += 1
                    else:
                        print("HotUKDeals: No more pages or load more button found. Stopping pagination.")
                        break
                else:
                    print("HotUKDeals: Max pages reached. Stopping pagination.")
                    break

                time.sleep(random.uniform(2, 5)) # Shorter, more realistic delay for browser automation

            except Exception as e:
                print(f"Error during Playwright scraping for HotUKDeals: {e}")
                # Log full traceback for better debugging on Railway
                import traceback
                traceback.print_exc() 
                break
        
        browser.close() # Ensure browser is closed
    return deals_found

if __name__ == "__main__":
    print("Starting deal scraping from HotUKDeals using Playwright...")
    
    print("\n--- Scraping HotUKDeals ---")
    # Start with 1 page to quickly test Playwright setup.
    # If successful, increase max_pages for more coverage (e.g., 2 or 3).
    hukd_deals = scrape_hotukdeals(max_pages=1) 

    total_deals_found = len(hukd_deals)
    if total_deals_found == 0:
        print("No new deals found from HotUKDeals in this run.")
    else:
        print(f"\nScraping complete. Found and attempted to send {len(hukd_deals)} deals from HotUKDeals.")

