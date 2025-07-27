import requests
from bs4 import BeautifulSoup
import time
import random
import os
import json

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
        "color": 0xFFA500 if source_name == "HotUKDeals" else 0x1E90FF, # Orange for HUKD, DodgerBlue for LD
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
        # Replace these with actual favicons if you want them to show up
        "avatar_url": "https://www.hotukdeals.com/favicon.ico" if source_name == "HotUKDeals" else "https://www.latestdeals.co.uk/favicon.ico",
        "embeds": [embed]
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        print(f"Successfully sent deal to Discord: {deal_info['title']} (Source: {source_name})")
    except requests.exceptions.RequestException as e:
        print(f"Error sending to Discord webhook from {source_name}: {e}")

# --- Scraper for HotUKDeals.com ---
def scrape_hotukdeals(max_pages=1):
    """Scrapes hotukdeals.com for popular deals."""
    base_url = "https://www.hotukdeals.com/"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    }

    deals_found = []
    page_num = 1
    current_url = base_url

    while page_num <= max_pages: 
        print(f"Scraping HotUKDeals page {page_num} from {current_url}...")
        try:
            response = requests.get(current_url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')

            # --- HotUKDeals Specific Selectors (UPDATED - Verify these if issues persist!) ---
            # Main deal container - Look for an <article> tag with class 'thread--card'
            products = soup.find_all('article', class_='thread--card')
            
            if not products:
                print("HotUKDeals: No products found with current selector. HTML structure may have changed.")
                break

            for product in products:
                # Title & Link: Usually within h2.thread-title > a.cept-deal-title
                title_link_tag = product.find('h2', class_='thread-title').find('a', class_='cept-deal-title')
                title = title_link_tag.text.strip() if title_link_tag else "N/A"
                link = title_link_tag['href'] if title_link_tag and 'href' in title_link_tag.attrs else "N/A"
                
                # Price
                price_tag = product.find('span', class_='thread-price')
                price = price_tag.text.strip() if price_tag else "N/A"

                # Heat Score
                heat_tag = product.find('span', class_='cept-vote-temp') # Example: span.cept-vote-temp or span.vote-box__score
                heat = heat_tag.text.strip() if heat_tag else "N/A"

                # Image
                image_tag = product.find('img', class_='thread-image') # Example: img.thread-image
                image_url = image_tag['src'] if image_tag and 'src' in image_tag.attrs else ""

                discount_info = "N/A" # HotUKDeals doesn't have a standard discount percentage element

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

            # HotUKDeals pagination (UPDATED - still challenging, often JS loaded)
            # This looks for a simple 'next page' link, might not always work for deep pagination.
            next_page_link_container = soup.find('li', class_='pagination-next')
            if next_page_link_container:
                next_page_a_tag = next_page_link_container.find('a')
                if next_page_a_tag and 'href' in next_page_a_tag.attrs:
                    current_url = next_page_a_tag['href']
                    page_num += 1
                else:
                    print("HotUKDeals: Next page link found, but href attribute missing.")
                    break
            else:
                print("HotUKDeals: No more pages or pagination button not found.")
                break

            time.sleep(random.uniform(3, 8))

        except requests.exceptions.RequestException as e:
            print(f"Error scraping HotUKDeals: {e}")
            break
        except Exception as e:
            print(f"An unexpected error occurred during parsing HotUKDeals: {e}. This might mean a selector is finding an element, but not in the expected structure for subsequent operations.")
            break
    return deals_found

# --- Scraper for LatestDeals.co.uk ---
def scrape_latestdeals(max_pages=1):
    """Scrapes latestdeals.co.uk for recent deals."""
    base_url = "https://www.latestdeals.co.uk/deals"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    }

    deals_found = []
    page_num = 1
    current_url = base_url

    while page_num <= max_pages:
        print(f"Scraping LatestDeals page {page_num} from {current_url}...")
        try:
            response = requests.get(current_url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')

            # --- LatestDeals Specific Selectors (UPDATED - Verify these if issues persist!) ---
            # Main deal container - This class still appears correct.
            products = soup.find_all('div', class_='ld-card ld-card--deal')

            if not products:
                print("LatestDeals: No products found with current selector. HTML structure may have changed.")
                break

            for product in products:
                # Title & Link: Usually within h2.ld-card__title > a.ld-card__link
                title_link_tag = product.find('h2', class_='ld-card__title').find('a', class_='ld-card__link')
                title = title_link_tag.text.strip() if title_link_tag else "N/A"
                link = title_link_tag['href'] if title_link_tag and 'href' in title_link_tag.attrs else "N/A"

                # Price
                price_tag = product.find('span', class_='ld-card__price')
                price = price_tag.text.strip() if price_tag else "N/A"
                
                # Likes
                likes_tag = product.find('span', class_='js-likes-count')
                likes = likes_tag.text.strip() if likes_tag else "0"

                # Image
                image_tag = product.find('img', class_='ld-card__image')
                image_url = image_tag['src'] if image_tag and 'src' in image_tag.attrs else ""

                discount_info = "N/A" # LatestDeals doesn't have a standard discount percentage element
                
                if title != "N/A" and link != "N/A" and price != "N/A":
                    deal_item = {
                        "title": title,
                        "price": price,
                        "link": link,
                        "image_url": image_url,
                        "metric_info": f"👍 {likes} Likes",
                        "discount_info": discount_info
                    }
                    deals_found.append(deal_item)
                    send_to_discord(deal_item, source_name="LatestDeals")

            # LatestDeals pagination (UPDATED)
            # Looks for the li with class 'pagination__item--next' and then the 'a' tag inside it
            next_page_li = soup.find('li', class_='pagination__item--next')
            if next_page_li:
                next_page_a_tag = next_page_li.find('a', class_='pagination__link')
                if next_page_a_tag and 'href' in next_page_a_tag.attrs:
                    current_url = next_page_a_tag['href'] # LatestDeals uses full URLs for pagination
                    page_num += 1
                else:
                    print("LatestDeals: Next page link container found, but 'a' tag or href missing.")
                    break
            else:
                print("LatestDeals: No more pages or pagination button not found.")
                break

            time.sleep(random.uniform(3, 8))

        except requests.exceptions.RequestException as e:
            print(f"Error scraping LatestDeals: {e}")
            break
        except Exception as e:
            print(f"An unexpected error occurred during parsing LatestDeals: {e}. This might mean a selector is finding an element, but not in the expected structure for subsequent operations.")
            break
    return deals_found

if __name__ == "__main__":
    
    print("Starting deal scraping from HotUKDeals and LatestDeals...")
    
    # You can adjust max_pages for each site if you want to scrape more pages.
    # Be mindful of the sites' terms of service and server load.
    
    print("\n--- Scraping HotUKDeals ---")
    hukd_deals = scrape_hotukdeals(max_pages=1) # Start with 1 page to test, increase to 2-3 if working

    print("\n--- Scraping LatestDeals ---")
    ld_deals = scrape_latestdeals(max_pages=1) # Start with 1 page to test, increase to 2-3 if working

    total_deals_found = len(hukd_deals) + len(ld_deals)
    if total_deals_found == 0:
        print("No new deals found from either HotUKDeals or LatestDeals in this run.")
    else:
        print(f"\nScraping complete. Found and attempted to send {len(hukd_deals)} deals from HotUKDeals and {len(ld_deals)} deals from LatestDeals.")

