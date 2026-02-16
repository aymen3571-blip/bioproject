import requests
import csv
import os
import time
from bs4 import BeautifulSoup
from datetime import date

# Get token from GitHub Secrets
API_TOKEN = os.getenv("SCRAPE_DO_TOKEN")

def main():
    print(">> Starting Homepage Scrape via Scrape.do...")

    # 1. Target the HOMEPAGE (GET request), not the Search API (POST)
    target_url = "https://namebio.com"
    
    # 2. Scrape.do Parameters
    # 'render=true' spins up a real browser to solve the JS Challenge/Captcha
    # 'wait=5000' gives the table 5 seconds to load
    api_url = "https://api.scrape.do/"
    params = {
        "token": API_TOKEN,
        "url": target_url,
        "render": "true",
        "wait": "5000" 
    }

    try:
        # 3. GET Request (This looks like a human opening the site)
        response = requests.get(api_url, params=params, timeout=120)

        if response.status_code == 200:
            # 4. Parse the HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the main sales table
            # (NameBio's table usually has an ID or class, but we look for the main data structure)
            table = soup.find('table', id='sales-table')
            
            if not table:
                print(">> Warning: Main 'sales-table' not found. Dumping HTML for debug...")
                print(response.text[:500]) # Print first 500 chars to see if we got blocked
                exit(1)

            # Get all rows from the table body
            rows = table.find('tbody').find_all('tr')
            print(f">> Found {len(rows)} sales on homepage. Filtering...")

            filtered_sales = []
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 4: continue # Skip empty/header rows
                
                # Extract Data (Columns: Domain, Price, Date, Venue)
                domain = cols[0].get_text(strip=True)
                price = cols[1].get_text(strip=True)
                date_sold = cols[2].get_text(strip=True)
                venue = cols[3].get_text(strip=True)

                # 5. PYTHON FILTERING
                # We only keep rows that are .com AND GoDaddy
                if ".com" in domain.lower() and "godaddy" in venue.lower():
                    filtered_sales.append([domain, price, date_sold, venue])

            # 6. Save to CSV
            filename = "daily_sales.csv"
            with open(filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Domain", "Price", "Date", "Venue"])
                writer.writerows(filtered_sales)
                
            print(f">> SUCCESS! Saved {len(filtered_sales)} GoDaddy .com sales to {filename}")

        else:
            print(f">> FAILED. Status: {response.status_code}")
            print(f">> Error Message: {response.text}")
            exit(1)

    except Exception as e:
        print(f">> CRITICAL ERROR: {e}")
        exit(1)

if __name__ == "__main__":
    main()
