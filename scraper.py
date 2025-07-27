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
        "avatar_url": "https://i.imgur.com/example.png" if source_name == "HotUKDeals" else "https://i.imgur.com/example2.png", # Placeholder, replace with actual favicons or logos
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
    # For hot deals, homepage is sufficient for first page. Pagination is different.
    
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

    while page_num <= max_pages: # Limiting pages for HotUKDeals as pagination is complex
        print(f"Scraping HotUKDeals page {page_num} from {current_url}...")
        try:
            response = requests.get(current_url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')

            # --- HotUKDeals Specific Selectors (verify these!) ---
            # Main deal container
            products = soup.find_all('div', {'data-deal-id': True, 'data-card-type': 'deal'})
            
            if not products:
                print("No more products found on HotUKDeals page or end of results.")
                break

            for product in products:
                title_tag = product.find('a', class_='cept-deal-title')
                title = title_tag.text.strip() if title_tag else "N/A"

                link = title_tag['href'] if title_tag and 'href' in title_tag.attrs else "N/A"
                if link and not link.startswith("http"): # Ensure full URL for relative links
                    link = "https://www.hotukdeals.com" + link

                price_tag = product.find('span', class_='thread-price')
                price = price_tag.text.strip() if price_tag else "N/A"

                heat_tag = product.find('span', class_='cept-vote-temp')
                heat = heat_tag.text.strip() if heat_tag else "N/A"

                image_tag = product.find('img', class_='cept-img-loaded')
                image_url = image_tag['src'] if image_tag and 'src' in image_tag.attrs else ""

                # HotUKDeals doesn't have a direct 'percentage off' element,
                # but it might be in the title or description (which we're not scraping fully here).
                # We'll just indicate it's from HotUKDeals for now.
                discount_info = "Check deal page for discount details"

                if title != "N/A" and link != "N/A" and price != "N/A":
                    deal_item = {
                        "title": title,
                        "price": price,
                        "link": link,
                        "image_url": image_url,
                        "metric_info": f"🔥 {heat} Heat",
                        "discount_info": discount_info # Placeholder
                    }
                    deals_found.append(deal_item)
                    send_to_discord(deal_item, source_name="HotUKDeals")

            # HotUKDeals pagination is usually done via "load more" button or different page numbering.
            # For simplicity, we'll limit to max_pages (default 1) for the main page.
            # Implementing robust pagination for HUKD requires deeper inspection of their JS.
            if page_num < max_pages: # Only try to go to next if max_pages > 1
                 next_page_link = soup.find('a', class_='pagination-next') # Check this if you want more pages
                 if next_page_link and 'href' in next_page_link.attrs:
                     current_url = "https://www.hotukdeals.com" + next_page_link['href']
                     page_num += 1
                 else:
                     print("HotUKDeals: No more pages or pagination button not found.")
                     break
            else:
                break # Reached max_pages limit

            time.sleep(random.uniform(3, 8))

        except requests.exceptions.RequestException as e:
            print(f"Error scraping HotUKDeals: {e}")
            break
        except Exception as e:
            print(f"An unexpected error occurred during parsing HotUKDeals: {e}")
            break
    return deals_found

# --- Scraper for LatestDeals.co.uk ---
def scrape_latestdeals(max_pages=1):
    """Scrapes latestdeals.co.uk for recent deals."""
    base_url = "https://www.latestdeals.co.uk/deals"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36", # Current User-Agent (July 2025)
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

            # --- LatestDeals Specific Selectors (verify these!) ---
            # Main deal container
            products = soup.find_all('div', class_='ld-card ld-card--deal')

            if not products:
                print("No more products found on LatestDeals page or end of results.")
                break

            for product in products:
                title_tag = product.find('h2', class_='ld-card__title').find('a', class_='ld-card__link')
                title = title_tag.text.strip() if title_tag else "N/A"

                link = title_tag['href'] if title_tag and 'href' in title_tag.attrs else "N/A"
                if link and not link.startswith("http"):
                    link = "https://www.latestdeals.co.uk" + link

                price_tag = product.find('span', class_='ld-card__price')
                price = price_tag.text.strip() if price_tag else "N/A"
                
                likes_tag = product.find('span', class_='js-likes-count')
                likes = likes_tag.text.strip() if likes_tag else "0"

                image_tag = product.find('img', class_='ld-card__image')
                image_url = image_tag['src'] if image_tag and 'src' in image_tag.attrs else ""

                # LatestDeals also doesn't have a direct 'percentage off' element consistently
                # You might find it in the title or description on their site.
                discount_info = "Check deal page for discount details"
                
                if title != "N/A" and link != "N/A" and price != "N/A":
                    deal_item = {
                        "title": title,
                        "price": price,
                        "link": link,
                        "image_url": image_url,
                        "metric_info": f"👍 {likes} Likes",
                        "discount_info": discount_info # Placeholder
                    }
                    deals_found.append(deal_item)
                    send_to_discord(deal_item, source_name="LatestDeals")

            # LatestDeals pagination
            next_page_link = soup.find('li', class_='pagination__item--next')
            if next_page_link:
                next_page_a_tag = next_page_link.find('a', class_='pagination__link')
                if next_page_a_tag and 'href' in next_page_a_tag.attrs:
                    current_url = next_page_a_tag['href'] # LatestDeals uses full URLs for pagination
                    page_num += 1
                else:
                    print("LatestDeals: No more pages or pagination button not found.")
                    break
            else:
                break # Reached max_pages limit

            time.sleep(random.uniform(3, 8))

        except requests.exceptions.RequestException as e:
            print(f"Error scraping LatestDeals: {e}")
            break
        except Exception as e:
            print(f"An unexpected error occurred during parsing LatestDeals: {e}")
            break
    return deals_found

if __name__ == "__main__":
    
    print("Starting deal scraping from HotUKDeals and LatestDeals...")
    
    # You can adjust max_pages for each site if you want to scrape more pages.
    # Be mindful of the sites' terms of service and server load.
    
    print("\n--- Scraping HotUKDeals ---")
    hukd_deals = scrape_hotukdeals(max_pages=2) # Scrape first 2 pages of HUKD

    print("\n--- Scraping LatestDeals ---")
    ld_deals = scrape_latestdeals(max_pages=2) # Scrape first 2 pages of LatestDeals

    total_deals_found = len(hukd_deals) + len(ld_deals)
    if total_deals_found == 0:
        print("No new deals found from either HotUKDeals or LatestDeals in this run.")
    else:
        print(f"\nScraping complete. Found and attempted to send {len(hukd_deals)} deals from HotUKDeals and {len(ld_deals)} deals from LatestDeals.")

