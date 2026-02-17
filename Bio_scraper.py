import requests
import csv
import os
from bs4 import BeautifulSoup

API_TOKEN = os.getenv("SCRAPE_DO_TOKEN")

def main():
    print(">> Starting Scrape.do (Mobile Mode)...")

    target_url = "https://namebio.com"
    api_url = "https://api.scrape.do/"

    # 1. THE MOBILE CONFIGURATION
    params = {
        "token": API_TOKEN,
        "url": target_url,
        # We use render=true to handle the Javascript
        "render": "true",
        # We turn OFF 'super' to rely on their data center solvers (often faster)
        "super": "false",
        # We wait 20 SECONDS to ensure the Cloudflare redirect finishes
        "wait": "20000",
        # We tell Scrape.do to emulate a Mobile device (often easier to bypass)
        "mobile": "true" 
    }

    try:
        print(">> Sending request (iPhone Emulation + 20s Wait)...")
        response = requests.get(api_url, params=params, timeout=60)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # --- Check if we are still stuck ---
            if "captcha" in response.text.lower() or "prove you're not a robot" in response.text.lower():
                print(">> FAILED: Still stuck on Cloudflare Challenge page.")
                print(f">> Title: {soup.title.string}")
                exit(1)

            # --- PARSE THE TABLE ---
            # On mobile view, tables sometimes change structure, so we look for ANY table
            table = None
            for t in soup.find_all('table'):
                if "Domain" in t.get_text():
                    table = t
                    break
            
            if not table:
                print(">> CRITICAL: No data table found. Layout might be different on mobile.")
                exit(1)

            rows = table.find_all('tr')
            print(f">> Found {len(rows)} rows. Filtering...")

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
                
            print(f">> SUCCESS! Saved {len(filtered_sales)} rows.")

        else:
            print(f">> FAILED. Status: {response.status_code}")
            print(f">> Error: {response.text}")
            exit(1)

    except Exception as e:
        print(f">> ERROR: {e}")
        exit(1)

if __name__ == "__main__":
    main()
