from curl_cffi import requests # <--- The Magic Library
from bs4 import BeautifulSoup
import csv
import time

def main():
    print(">> Starting NameBio Scrape (The 'Impostor' Method)...")
    target_url = "https://namebio.com"

    # We use 'impersonate="chrome120"' to mimic a real Chrome browser's handshake.
    # This often bypasses the "Checking your browser" screen completely.
    try:
        print(">> Sending request as Chrome 120...")
        
        # Notice we use requests.get from curl_cffi, not standard requests
        response = requests.get(
            target_url, 
            impersonate="chrome120", 
            timeout=30
        )

        if response.status_code == 200:
            # Check if we still got the captcha redirect
            if "window.location" in response.text and "captcha" in response.text:
                print(">> Failed: Still got sent to Captcha Jail.")
                # We can't solve it, but we know why it failed.
                exit(1)

            soup = BeautifulSoup(response.text, 'html.parser')
            
            # --- PARSING LOGIC (Same as before) ---
            table = soup.find('table', id='sales-table')
            if not table:
                # Backup search
                for t in soup.find_all('table'):
                    th = t.find('th')
                    if th and "Domain" in th.get_text():
                        table = t
                        break
            
            if not table:
                print(">> CRITICAL: Table not found. NameBio layout might have changed.")
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
            exit(1)

    except Exception as e:
        print(f">> ERROR: {e}")
        exit(1)

if __name__ == "__main__":
    main()
