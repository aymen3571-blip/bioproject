import requests
import csv
import os
import time
from bs4 import BeautifulSoup
from datetime import date

API_TOKEN = os.getenv("SCRAPE_DO_TOKEN")

def main():
    print(">> Starting Scrape.do (Targeting Blog Page)...")

    # NEW: We target the specific blog post URL instead of the main search database page
    target_url = "https://namebio.com/blog/daily-market-report-for-february-17th-2026/"
    api_url = "https://api.scrape.do/"

    # THE STRATEGY:
    # 1. mobile=true: Tells Cloudflare we are a phone (touchscreen, battery, etc.)
    # 2. render=true: Uses a real browser engine to solve the Javascript challenge
    # NEW: We removed the extreme 25-second wait to see if the blog loads instantly without a challenge.
    params = {
        "token": API_TOKEN,
        "url": target_url,
        "render": "true",
        "mobile": "true"
    }

    try:
        print(">> Sending request to Blog URL...")
        response = requests.get(api_url, params=params, timeout=120)

        if response.status_code == 200:
            # Check if we are still in the "Waiting Room"
            if "Just a moment" in response.text or "security check" in response.text:
                print(">> FAILED: Cloudflare detected us on the blog page as well.")
                exit(1)

            soup = BeautifulSoup(response.text, 'html.parser')
            
            # --- PARSING ---
            # NEW: Blog posts often use standard WordPress HTML tables, so we look for any table with "Domain" or "Price"
            table = None
            for t in soup.find_all('table'):
                if "Domain" in t.get_text() or "Price" in t.get_text():
                    table = t
                    break
            
            if not table:
                print(">> CRITICAL: Cloudflare let us in, but I can't find the table.")
                print(f">> Page Title: {soup.title.string if soup.title else 'No Title'}")
                exit(1)

            # NEW: Handle tables that might or might not have a <tbody> tag (common in blogs)
            rows = table.find('tbody').find_all('tr') if table.find('tbody') else table.find_all('tr')
            print(f">> SUCCESS! Cloudflare bypassed. Found {len(rows)} rows in the blog table.")

            filtered_sales = []
            for row in rows:
                # NEW: Blog tables sometimes use <th> for the first column instead of <td>, so we find both
                cols = row.find_all(['td', 'th']) 
                if len(cols) < 3: continue # NEW: Blog tables might only have 3 columns (Domain, Price, Venue)
                
                domain = cols[0].get_text(strip=True)
                price = cols[1].get_text(strip=True)
                
                # NEW: Extract venue. If Date is missing in the blog table, we handle it gracefully.
                venue = cols[2].get_text(strip=True) 
                date_sold = "2026-02-17" # NEW: Hardcoded date based on the URL for this specific test
                
                if len(cols) >= 4:
                    date_sold = cols[3].get_text(strip=True)

                if ".com" in domain.lower() and "godaddy" in venue.lower():
                    filtered_sales.append([domain, price, date_sold, venue])

            # Save to CSV
            filename = "daily_sales.csv"
            
            # Logic to append or create new
            file_exists = os.path.isfile(filename)
            with open(filename, "a" if file_exists else "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Domain", "Price", "Date", "Venue"])
                writer.writerows(filtered_sales)
                
            print(f">> SAVED {len(filtered_sales)} rows to {filename}")

        else:
            print(f">> API FAILED. Status: {response.status_code}")
            print(f">> Error: {response.text}")
            exit(1)

    except Exception as e:
        print(f">> ERROR: {e}")
        exit(1)

if __name__ == "__main__":
    main()
