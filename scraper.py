import requests
from bs4 import BeautifulSoup
import time
import random
import os
import json
# Import from playwright_extra instead of playwright.sync_api
from playwright_extra import sync_playwright
# Import the stealth plugin
from puppeteer_extra_plugin_stealth import stealth

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

# --- Scraper for HotUKDeals.com with Playwright-Extra (Stealth, User Agent, Viewport) ---
def scrape_hotukdeals(max_pages=1):
    """Scrapes hotukdeals.com for popular deals using Playwright with stealth plugin, user agent, and viewport."""
    base_url = "https://www.hotukdeals.com/"
    
    deals_found = []
    
    # Apply the stealth plugin to Playwright
    # This modifies Playwright to evade common bot detections
    sync_playwright.add_plugin(stealth)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # --- Configure Browser Context with User Agent and Viewport ---
        # Creating a new browser context allows you to set specific options
        # like user_agent and viewport, which apply to all pages opened within this context.
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080} # Common desktop resolution
        )
        page = context.new_page() # Use the context to create the page
        # --- End Context Configuration ---
        
        page_num = 1
        current_url = base_url

        while page_num <= max_pages: 
            print(f"Scraping HotUKDeals page {page_num} from {current_url} using Playwright (Stealth, UA, Viewport)...")
            try:
                # Navigate to the page.
                # Use 'networkidle' to wait for network activity to cease, which might help with JS challenges.
                # Increased timeout significantly as Cloudflare challenges can take time.
                page.goto(current_url, wait_until="networkidle", timeout=90000) # Increased timeout to 90 seconds
                
                # IMPORTANT: After goto, wait for a known element on the *actual* page.
                # This will give Cloudflare time to resolve if it can.
                # If this selector is not found within the timeout, it means Cloudflare blocked us.
                try:
                    page.wait_for_selector('article.thread--card', timeout=30000) # Wait up to 30s for a deal card
                    print("HotUKDeals: Successfully waited for deal card element.")
                except Exception as e:
                    print(f"HotUKDeals: Did not find expected deal content after navigation (Cloudflare bypass failed?). Error: {e}")
                    # Print the current page content to see if it's still Cloudflare
                    print(f"HotUKDeals: Current HTML content (first 1000 chars):\n{page.content()[:1000]}...")
                    break # Break if we can't find the content

                # Get the fully rendered HTML content
                html_content = page.content()
                soup = BeautifulSoup(html_content, 'lxml')

                # --- HOTUKDEALS MAIN DEAL CONTAINER SELECTOR ---
                products = soup.find_all('article', class_='thread--card') 

                if not products:
                    print("HotUKDeals: No products found with current selector AFTER Cloudflare check. HTML structure may have changed or content not loaded.")
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
        
        browser.close() # Ensure the browser is closed when done
    return deals_found

if __name__ == "__main__":
    print("Starting deal scraping from HotUKDeals using Playwright (with Stealth, UA, Viewport)...")
    
    print("\n--- Scraping HotUKDeals ---")
    hukd_deals = scrape_hotukdeals(max_pages=1) 

    total_deals_found = len(hukd_deals)
    if total_deals_found == 0:
        print("No new deals found from HotUKDeals in this run.")
    else:
        print(f"\nScraping complete. Found and attempted to send {len(hukd_deals)} deals from HotUKDeals.")
