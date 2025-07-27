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

            # --- HOTUKDEALS SELECTOR TO VERIFY/UPDATE ---
            # IMPORTANT: Right-click on a deal on hotukdeals.com -> Inspect.
            # Find the main HTML tag (e.g., <article>, <div>, <li>) that contains ALL info for one deal.
            # Example: <article class="thread--card">
            products = soup.find_all('article', class_='thread--card') # Current best guess

            if not products:
                print("HotUKDeals: No products found with current selector. HTML structure may have changed.")
                print(f"HotUKDeals: HTML content received (first 500 chars):\n{response.text[:500]}...") # Print beginning of HTML for debugging
                # If you see a lot of JS or very little content, the page might be rendered via JavaScript
                break

            for product in products:
                # Title & Link: Right-click deal title -> Inspect. Find <a> tag with title text.
                # Example: <h2 class="thread-title"><a class="cept-deal-title" href="...">Deal Title</a></h2>
                title_link_tag = product.find('h2', class_='thread-title').find('a', class_='cept-deal-title') # Current best guess
                title = title_link_tag.text.strip() if title_link_tag else "N/A"
                link = title_link_tag['href'] if title_link_tag and 'href' in title_link_tag.attrs else "N/A"
                
                # Price: Right-click deal price -> Inspect. Find <span> or <div> with price text.
                # Example: <span class="thread-price">£12.99</span>
                price_tag = product.find('span', class_='thread-price') # Current best guess
                price = price_tag.text.strip() if price_tag else "N/A"

                # Heat Score: Right-click heat score (e.g., +100) -> Inspect.
                # Example: <span class="cept-vote-temp"></span> inside <span class="vote-box__score">
                heat_tag = product.find('span', class_='cept-vote-temp') # Current best guess
                heat = heat_tag.text.strip() if heat_tag else "N/A"

                # Image: Right-click deal image -> Inspect. Find <img> tag.
                # Example: <img class="thread-image" src="...">
                image_tag = product.find('img', class_='thread-image') # Current best guess
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
                else:
                    print(f"HotUKDeals: Skipped incomplete deal. Title: {title}, Link: {link}, Price: {price}")


            # HotUKDeals pagination (still challenging, often JS loaded)
            # Find the 'next' button for pagination. Example: <li class="pagination-next"><a>Next</a></li>
            next_page_li = soup.find('li', class_='pagination-next') # Current best guess
            if next_page_li:
                next_page_a_tag = next_page_li.find('a')
                if next_page_a_tag and 'href' in next_page_a_tag.attrs:
                    current_url = next_page_a_tag['href']
                    page_num += 1
                else:
                    print("HotUKDeals: Next page link found, but href attribute missing.")
                    break
            else:
                # Check for "Load More" button if standard pagination not found
                load_more_button = soup.find('a', class_='cept-load-more') # Common for more deals
                if load_more_button and 'href' in load_more_button.attrs:
                     current_url = load_more_button['href']
                     page_num += 1
                     print(f"HotUKDeals: Found 'Load More' button. Moving to {current_url}")
                else:
                    print("HotUKDeals: No more pages or pagination button not found.")
                    break


            time.sleep(random.uniform(3, 8))

        except requests.exceptions.RequestException as e:
            print(f"Error scraping HotUKDeals: {e}")
            break
        except Exception as e:
            print(f"An unexpected error occurred during parsing HotUKDeals: {e}. This might mean a selector is finding an element, but not in the expected structure for subsequent operations. Check the full HTML content if necessary.")
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

            # --- LATESTDEALS SELECTOR TO VERIFY/UPDATE ---
            # IMPORTANT: Right-click on a deal on latestdeals.co.uk/deals -> Inspect.
            # Find the main HTML tag (e.g., <div>, <article>, <li>) that contains ALL info for one deal.
            # Example: <div class="ld-card ld-card--deal">
            products = soup.find_all('div', class_='ld-card ld-card--deal') # Current best guess

            if not products:
                print("LatestDeals: No products found with current selector. HTML structure may have changed.")
                print(f"LatestDeals: HTML content received (first 500 chars):\n{response.text[:500]}...") # Print beginning of HTML for debugging
                break

            for product in products:
                # Title & Link: Right-click deal title -> Inspect. Find <a> tag with title text.
                # Example: <h2 class="ld-card__title"><a class="ld-card__link" href="...">Deal Title</a></h2>
                title_link_tag = product.find('h2', class_='ld-card__title').find('a', class_='ld-card__link') # Current best guess
                title = title_link_tag.text.strip() if title_link_tag else "N/A"
                link = title_link_tag['href'] if title_link_tag and 'href' in title_link_tag.attrs else "N/A"

                # Price: Right-click deal price -> Inspect. Find <span> or <div> with price text.
                # Example: <span class="ld-card__price">£10.00</span>
                price_tag = product.find('span', class_='ld-card__price') # Current best guess
                price = price_tag.text.strip() if price_tag else "N/A"
                
                # Likes: Right-click likes count (e.g., 100 Likes) -> Inspect.
                # Example: <span class="js-likes-count">100</span>
                likes_tag = product.find('span', class_='js-likes-count') # Current best guess
                likes = likes_tag.text.strip() if likes_tag else "0"

                # Image: Right-click deal image -> Inspect. Find <img> tag.
                # Example: <img class="ld-card__image" src="...">
                image_tag = product.find('img', class_='ld-card__image') # Current best guess
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
                else:
                    print(f"LatestDeals: Skipped incomplete deal. Title: {title}, Link: {link}, Price: {price}")

            # LatestDeals pagination (UPDATED)
            # Find the 'next' button for pagination. Example: <li class="pagination__item--next"><a class="pagination__link" href="...">Next</a></li>
            next_page_li = soup.find('li', class_='pagination__item--next') # Current best guess
            if next_page_li:
                next_page_a_tag = next_page_li.find('a', class_='pagination__link')
                if next_page_a_tag and 'href' in next_page_a_tag.attrs:
                    current_url = next_page_a_tag['href'] # LatestDeals usually uses full URLs for pagination
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
            print(f"An unexpected error occurred during parsing LatestDeals: {e}. This might mean a selector is finding an element, but not in the expected structure for subsequent operations. Check the full HTML content if necessary.")
            break
    return deals_found

if __name__ == "__main__":
    
    print("Starting deal scraping from HotUKDeals and LatestDeals...")
    
    # Start with 1 page for each to quickly test the new selectors.
    # If successful, increase max_pages for more coverage (e.g., 2 or 3).
    
    print("\n--- Scraping HotUKDeals ---")
    hukd_deals = scrape_hotukdeals(max_pages=1)

    print("\n--- Scraping LatestDeals ---")
    ld_deals = scrape_latestdeals(max_pages=1)

    total_deals_found = len(hukd_deals) + len(ld_deals)
    if total_deals_found == 0:
        print("No new deals found from either HotUKDeals or LatestDeals in this run.")
    else:
        print(f"\nScraping complete. Found and attempted to send {len(hukd_deals)} deals from HotUKDeals and {len(ld_deals)} deals from LatestDeals.")

