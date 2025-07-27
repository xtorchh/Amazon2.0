import requests
from bs4 import BeautifulSoup
import time
import random
import os
import json # For formatting webhook payload

# --- Configuration ---
# Get Discord Webhook URL from environment variables for security
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
if not DISCORD_WEBHOOK_URL:
    print("Warning: DISCORD_WEBHOOK_URL environment variable not set. Deals will not be sent to Discord.")

# --- Helper function to send to Discord ---
def send_to_discord(deal_info):
    """Sends deal information to a Discord webhook."""
    if not DISCORD_WEBHOOK_URL:
        return

    # Create a Discord embed for better formatting and visual appeal
    embed = {
        "title": deal_info["title"],
        "url": deal_info["link"],
        "color": 0x00FF00, # Green color for deals
        "fields": [
            {"name": "Price", "value": deal_info["price"], "inline": True},
            {"name": "Discount", "value": deal_info["discount_text"], "inline": True}
        ],
        "thumbnail": {"url": deal_info.get("image_url", "")} # Add image if scraped
    }

    payload = {
        "username": "Amazon UK Deal Bot",
        "avatar_url": "https://www.amazon.co.uk/favicon.ico", # Amazon's favicon as bot avatar
        "embeds": [embed]
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10) # Added timeout
        response.raise_for_status() # Raise an exception for HTTP errors (e.g., 400, 500)
        print(f"Successfully sent deal to Discord: {deal_info['title']}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending to Discord webhook: {e}")

# --- Amazon Scraper Function ---
def get_amazon_deals(min_discount=70, max_pages=3):
    """
    Scrapes Amazon UK for general deals with a specified minimum discount across multiple pages.
    """
    # Base URL for Amazon UK Deals page.
    # We append the percentage-off filter directly to this.
    initial_url = f"https://www.amazon.co.uk/deals?pct-off={min_discount}-"

    # Mimic a real browser's headers to avoid being easily blocked
    # Updated User-Agent for July 2025
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    }

    deals_found = []
    page_num = 1
    current_url = initial_url

    while page_num <= max_pages:
        print(f"Scraping page {page_num} for general deals with {min_discount}% off from {current_url}...")
        try:
            response = requests.get(current_url, headers=headers, timeout=15) # Increased timeout
            response.raise_for_status() # Raise an exception for bad status codes

            soup = BeautifulSoup(response.text, 'lxml')

            # --- IMPORTANT: Amazon HTML Structure can change! ---
            # You MUST inspect Amazon.co.uk page source to find the current correct selectors.
            # Use your browser's "Inspect Element" (F12) tool on an Amazon Deals page filtered by 70% off.
            #
            # Common selectors for product items, these may need adjustment.
            products = soup.find_all('div', {'data-component-type': 's-search-result'})
            # On the /deals page, product containers might also be in different structures,
            # e.g., 'div[data-card-type="deal"]' or specific deal-grid classes.
            # Inspect the actual deals page (e.g., https://www.amazon.co.uk/deals?pct-off=70-)
            # to confirm the correct product container selector. If 's-search-result' doesn't work,
            # look for a different overarching div/article for each deal item.
            # For the deals page, often deals are within structures like:
            # <div data-deal-id="..." class="deal-card-container"> or similar.
            # If the above 's-search-result' doesn't yield results, you'll need to adapt.

            if not products:
                print("No more products found on this page or end of results.")
                break # Exit loop if no products are found

            for product in products:
                # Extract product title
                # Check for common title classes on deal pages.
                title_tag = product.find('span', class_='a-size-medium a-color-base a-text-normal') # Search result titles
                if not title_tag: # Fallback for deals page specific titles
                    title_tag = product.find('div', class_='a-section a-spacing-small a-text-left deal-title-and-discount')
                    if title_tag:
                        title_tag = title_tag.find('span') # Look for the actual title text within this div
                title = title_tag.text.strip() if title_tag else "N/A"

                # Extract product link
                link_tag = product.find('a', class_='a-link-normal s-underline-text s-underline-link-text s-link-style a-text-normal')
                if not link_tag: # Fallback for deals page specific links
                    link_tag = product.find('a', class_='a-link-normal deal-card-link') # Common on deals page
                link = "https://www.amazon.co.uk" + link_tag['href'] if link_tag and 'href' in link_tag.attrs else "N/A"
                
                # Extract price. Amazon prices can be split (whole/fraction) or in a hidden span.
                price_whole_tag = product.find('span', class_='a-price-whole')
                price_fraction_tag = product.find('span', class_='a-price-fraction')
                price_symbol_tag = product.find('span', class_='a-price-symbol')

                price_text = "N/A"
                if price_whole_tag and price_fraction_tag and price_symbol_tag:
                    price_text = f"{price_symbol_tag.text}{price_whole_tag.text}.{price_fraction_tag.text}"
                else: # Fallback for hidden price (e.g., for "a-offscreen" span)
                    hidden_price_tag = product.find('span', class_='a-offscreen')
                    if hidden_price_tag:
                        price_text = hidden_price_tag.text.strip()
                
                # Discount information: Primarily filtered by URL.
                discount_text = "N/A (filtered by URL)"
                # Look for explicit discount percentage if present on the page (e.g., "70% off")
                # This often appears in a badge or specific text. Inspect carefully!
                discount_span = product.find('span', class_='a-badge-text') # Common class for badges on search results
                if discount_span and "% off" in discount_span.text:
                    discount_text = discount_span.text.strip()
                elif product.find('div', class_='deal-savings-and-price'): # Common on deals page
                    discount_span_deal_page = product.find('span', class_='a-color-price') # Often contains e.g., "-70%"
                    if discount_span_deal_page and "%" in discount_span_deal_page.text:
                        discount_text = discount_span_deal_page.text.strip()
                elif product.find('span', class_='s-label-popover-default'): # Another common pattern on search results
                     discount_text = product.find('span', class_='s-label-popover-default').text.strip()


                # Optional: Scrape image URL for Discord embed thumbnail
                image_tag = product.find('img', class_='s-image')
                if not image_tag: # Fallback for deals page specific images
                    image_tag = product.find('img', class_='_fluid_ext_grid_image_view_image__image__3qN_4') # Example for deal grid images
                image_url = image_tag['src'] if image_tag and 'src' in image_tag.attrs else ""

                # Only add if we have basic valid info
                if title != "N/A" and link != "N/A" and price_text != "N/A":
                    deal_item = {
                        "title": title,
                        "price": price_text,
                        "link": link,
                        "discount_text": discount_text,
                        "image_url": image_url
                    }
                    deals_found.append(deal_item)
                    send_to_discord(deal_item) # Send each deal to Discord as it's found

            # Find the "Next Page" button/link to continue pagination
            next_page_link = soup.find('a', class_='s-pagination-next') # This class is common, but check it!
            # On the /deals page, pagination might also be different.
            # Look for elements like <a class="a-last" href="...">Next</a> or similar.
            if not next_page_link:
                next_page_link = soup.find('li', class_='a-last') # Sometimes the 'Next' button is in an <li>
                if next_page_link:
                    next_page_link = next_page_link.find('a') # Get the <a> tag inside the <li>

            if next_page_link and 'href' in next_page_link.attrs:
                # Amazon's 'next' link is usually a relative URL, so append it to the base.
                current_url = "https://www.amazon.co.uk" + next_page_link['href']
                page_num += 1
            else:
                print("No more pages found (or pagination structure changed). Stopping.")
                break # Exit loop if no next page link

            # Be polite to Amazon's servers and avoid IP blocking
            time.sleep(random.uniform(3, 8)) # Random delay between requests

        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error {e.response.status_code} for {current_url}: {e.response.text}")
            if e.response.status_code == 404: # Page not found
                print("Page not found, stopping pagination.")
            elif e.response.status_code == 429: # Too Many Requests
                print("Received a 429 (Too Many Requests). Pausing for a longer duration.")
                time.sleep(random.uniform(60, 120)) # Longer pause for 429
            break
        except requests.exceptions.ConnectionError as e:
            print(f"Connection Error: {e}. Retrying in 10 seconds...")
            time.sleep(10)
        except requests.exceptions.Timeout as e:
            print(f"Request timed out: {e}. Retrying in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            print(f"An unexpected error occurred during parsing or request: {e}")
            break

    return deals_found

if __name__ == "__main__":
    
    print("Starting Amazon UK 70% off general deal scraper...")
    # No search_term needed, as we're hitting the general deals page.
    # Limiting to 3 pages for a balance between speed and coverage for automated runs.
    found_deals = get_amazon_deals(min_discount=70, max_pages=3)

    if not found_deals:
        print("No new general deals found with at least 70% off in this run.")
    else:
        print(f"\nScraping complete. Found and attempted to send {len(found_deals)} general deals.")

