import requests
import csv
import os
import time
from bs4 import BeautifulSoup

# 1. SAFER KEY LOADING: We use .strip() to remove invisible spaces/newlines
API_KEY = os.getenv("SCRAPE_DO_TOKEN", "").strip()

def main():
    print(">> Starting NameBio Scrape via ScrapingAnt...")
    
    if not API_KEY:
        print(">> CRITICAL ERROR: API Key is missing or empty.")
        exit(1)

    target_url = "https://namebio.com"
    api_url = "https://api.scrapingant.com/v2/general"

    # 2. SIMPLIFIED PARAMETERS
    # We removed 'wait_for_selector' because it was causing empty responses.
    # We added 'return_page_source' to ensure we get the HTML.
    params = {
        "x-api-key": API_KEY,
        "url": target_url,
        "browser": "true",
        "proxy_type": "residential", 
        "return_page_source": "true" 
    }

    try:
        print(">> Sending request...")
        response = requests.get(api_url, params=params, timeout=120)

        # 3. DEBUGGING THE RESPONSE
        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError:
                print(">> ERROR: The API returned 200 OK but the body was not JSON.")
                print(f">> Raw Response: {response.text[:500]}") # Print what we actually got
                exit(1)

            html_content = data.get("content", "")
            
            if not html_content:
                print(">> Error: ScrapingAnt returned empty HTML content.")
                print(f">> Full API Response: {data}")
                exit(1)

            soup = BeautifulSoup(html_content, 'html.parser')
            
            # --- PARSING ---
            table = soup.find('table', id='sales-table')
            
            if not table:
                # Backup search
                for t in soup.find_all('table'):
                    th = t.find('th')
                    if th and "Domain" in th.get_text():
                        table = t
                        break
            
            if not table:
                print(">> CRITICAL: Table not found. We might be blocked.")
                print(">> Page Title:", soup.title.string if soup.title else "No Title")
                exit(1)

            rows = table.find('tbody').find_all('tr')
            print(f">> Found {len(rows)} sales. Filtering...")

            filtered_sales = []
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 4: continue
                
                domain = cols[0].get_text(strip=True)
                price = cols[1].get_text(strip=True)
                date_sold = cols[2].get_text(strip=True)
                venue = cols[3].get_text(strip=True)

                if ".com" in domain.lower() and "godaddy" in venue.lower():
                    filtered_sales.append([domain, price, date_sold, venue])

            # Save to CSV
            filename = "daily_sales.csv"
            with open(filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Domain", "Price", "Date", "Venue"])
                writer.writerows(filtered_sales)
                
            print(f">> SUCCESS! Saved {len(filtered_sales)} GoDaddy .com sales.")

        else:
            print(f">> FAILED. Status: {response.status_code}")
            print(f">> Error: {response.text}")
            exit(1)

    except Exception as e:
        print(f">> ERROR: {e}")
        exit(1)

if __name__ == "__main__":
    main()
