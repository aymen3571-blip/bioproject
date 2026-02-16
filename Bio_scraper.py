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

    # 1. Target the HOMEPAGE (GET request)
    # The homepage automatically lists the latest sales, so we don't need to POST anything.
    target_url = "https://namebio.com"
    
    # 2. Scrape.do Parameters (The "Hybrid" Bypass)
    # 'render=true': Spins up a real Headless Browser (Chrome) to run JavaScript/Captchas.
    # 'super=true': Uses a RESIDENTIAL IP (Real home connection) so NameBio doesn't block us as a "Robot".
    # 'wait=10000': We wait 10 seconds to ensure the table loads fully after any redirects.
    api_url = "https://api.scrape.do/"
    params = {
        "token": API_TOKEN,
        "url": target_url,
        "render": "true",
        "super": "true", 
        "wait": "10000" 
    }

    try:
        print(f">> Sending request to Scrape.do (Render + Residential IP)...")
        response = requests.get(api_url, params=params, timeout=120)

        if response.status_code == 200:
            # 3. Parse the HTML Result
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 4. ROBUST TABLE SEARCH
            # First, try to find the table by its specific ID
            table = soup.find('table', id='sales-table')
            
            # Backup: If ID not found, look for ANY table that contains "Domain" in the header
            if not table:
                print(">> Warning: 'sales-table' ID not found. Searching for any valid data table...")
                for t in soup.find_all('table'):
                    # Check if the table has a header row with "Domain"
                    header = t.find('th')
                    if header and "Domain" in header.get_text():
                        table = t
                        print(">> Found a matching table structure.")
                        break
            
            # If we STILL can't find a table, we are likely blocked or the page is empty
            if not table:
                print(">> CRITICAL: Could not find any sales table. We might be blocked.")
                print(">> Page Title:", soup.title.string if soup.title else "No Title")
                # Debug: Print first 500 chars to see what happened
                print(f">> HTML Dump: {response.text[:500]}")
                exit(1)

            # 5. Extract Rows
            rows = table.find('tbody').find_all('tr')
            print(f">> Found {len(rows)} raw sales on homepage. Filtering...")

            filtered_sales = []
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 4: continue # Skip empty/header rows
                
                # Extract Data (Columns: Domain, Price, Date, Venue)
                # NameBio sometimes puts links inside the cells, so we use .get_text(strip=True)
                domain = cols[0].get_text(strip=True)
                price = cols[1].get_text(strip=True)
                date_sold = cols[2].get_text(strip=True)
                venue = cols[3].get_text(strip=True)

                # 6. PYTHON FILTERING
                # We only keep rows that are '.com' AND 'GoDaddy'
                if ".com" in domain.lower() and "godaddy" in venue.lower():
                    filtered_sales.append([domain, price, date_sold, venue])

            # 7. Save to CSV
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
