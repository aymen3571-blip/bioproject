import requests
import csv
import os
import time
from bs4 import BeautifulSoup
from datetime import date, timedelta # NEW: Added timedelta to calculate yesterday's date dynamically

API_TOKEN = os.getenv("SCRAPE_DO_TOKEN")

# NEW UPDATE: Exceptional override variables for manual backup runs or historical data retrieval.
# Leave MANUAL_URL empty ("") for normal automated daily runs.
# If you enter a URL here, the script will skip the category search and scrape this exact link instead.
MANUAL_URL = "" # Example: "https://namebio.com/blog/daily-market-report-for-february-10th-2026/"

# NEW UPDATE: If using MANUAL_URL for an old post, enter the exact date here (Format: "YYYY-MM-DD").
# This ensures the CSV records the correct past date instead of "yesterday's" date.
# If left empty, the script will default to "yesterday".
MANUAL_DATE = "" # Example: "2026-02-10"

def main():
    print(">> Starting Scrape.do (Targeting Blog Page)...")

    # NEW: Calculate yesterday's date to dynamically build the URL (and use for the CSV data)
    yesterday = date.today() - timedelta(days=1)
    
    # NEW UPDATE: Determine which date to inject into the CSV based on the manual override
    if MANUAL_DATE:
        target_date_string = MANUAL_DATE
        print(f">> [LOG] MANUAL_DATE override active. Using date: {target_date_string}")
    else:
        target_date_string = yesterday.strftime("%Y-%m-%d")
        print(f">> [LOG] Calculated target date for data injection: {target_date_string}")
    
    api_url = "https://api.scrape.do/"

    # THE STRATEGY:
    # 1. mobile=true: Tells Cloudflare we are a phone (touchscreen, battery, etc.)
    # 2. render=true: Uses a real browser engine to solve the Javascript challenge
    params = {
        "token": API_TOKEN,
        "render": "true",
        
    }

    # NEW UPDATE: Defined MAX_RETRIES globally so both Step 1 and Step 2 can use it for the proxy roulette.
    MAX_RETRIES = 3

    # NEW UPDATE: Check if we are doing a manual backup run or an automated run
    if MANUAL_URL:
        print(f">> [LOG] MANUAL_URL override active! Skipping Step 1 (Index Search).")
        print(f">> [LOG] Directing scraper exactly to: {MANUAL_URL}")
        params["url"] = MANUAL_URL
    else:
        # --- Start Step 1: Fetch the blog index to find the EXACT link to the newest report ---
        # NEW UPDATE: Added a retry loop to combat the "Phantom 200" Cloudflare WAF block on the index page.
        index_successful = False
        
        for index_attempt in range(1, MAX_RETRIES + 1):
            try:
                # NEW UPDATE: Changed to the specific Daily Market Report category page
                blog_index_url = "https://namebio.com/blog/category/daily-market-report/"
                # NEW UPDATE: Added the attempt counter to the log
                print(f">> [LOG] Step 1 Initiated (Attempt {index_attempt}/{MAX_RETRIES}): Requesting category index page at {blog_index_url}")
                
                # Clone our Scrape.do settings for this quick index check
                index_params = params.copy()
                index_params["url"] = blog_index_url
                
                print(">> [LOG] Waiting for Scrape.do to bypass Cloudflare on the index page...")
                index_response = requests.get(api_url, params=index_params, timeout=120)
                
                if index_response.status_code == 200:
                    # NEW UPDATE: Check for Cloudflare's invisible waiting room (Phantom 200 OK)
                    if "Just a moment" in index_response.text or "security check" in index_response.text:
                        print(">> WARNING: Cloudflare detected us on the index page (Phantom 200).")
                        print(">> [LOG] Spinning the proxy roulette wheel again in 3 seconds...")
                        time.sleep(3)
                        continue

                    print(">> [LOG] Index page loaded successfully without WAF blocks. Parsing HTML to locate the newest post link...")
                    index_soup = BeautifulSoup(index_response.text, 'html.parser')
                    real_url = None
                    
                    # Find all links on the blog page and grab the first Daily Market Report
                    for a_tag in index_soup.find_all('a', href=True):
                        href = a_tag['href']
                        # NEW UPDATE: Ensure it is a post URL and not a pagination link by excluding the word "category"
                        if "daily-market-report" in href.lower() and "category" not in href.lower():
                            real_url = href
                            print(f">> [LOG] Valid post link successfully extracted: {real_url}")
                            break
                    
                    if real_url:
                        print(f">> Found exact latest URL: {real_url}")
                        params["url"] = real_url # Update params with the real URL
                        # NEW UPDATE: Mark Step 1 as successful and break out of the retry loop
                        index_successful = True
                        break 
                    else:
                        # NEW: Hard exit if the URL cannot be found, since we removed the guessing fallback
                        # NEW UPDATE: Instead of a hard crash, we warn and trigger a proxy retry. 
                        # Cloudflare Captchas hide all legitimate links.
                        print(">> WARNING: [LOG] CRITICAL: Could not find any valid report link on the index page. Possible Captcha page masking.")
                        print(">> [LOG] Spinning the proxy roulette wheel again in 3 seconds...")
                        time.sleep(3)
                        continue
                        
                else:
                    # NEW UPDATE: If we get a real error code (like 403 or 500), we retry.
                    print(f">> WARNING: [LOG] CRITICAL: Failed to load blog index. Status Code: {index_response.status_code}")
                    print(">> [LOG] Spinning the proxy roulette wheel again in 3 seconds...")
                    time.sleep(3)
                    continue

            except Exception as e:
                # NEW UPDATE: Catch connection timeouts and trigger a retry instead of crashing.
                print(f">> WARNING: [LOG] CRITICAL ERROR in Step 1 (Attempt {index_attempt}): {e}")
                print(">> [LOG] Spinning the proxy roulette wheel again in 3 seconds...")
                time.sleep(3)
                continue
                
        # NEW UPDATE: If all 3 attempts fail for Step 1, we finally let the script crash safely.
        if not index_successful:
            print(">> [LOG] CRITICAL: All 3 attempts failed to locate the index link due to WAF blocks or errors. Exiting.")
            exit(1)

    # --- Start Step 2: Actually Scrape the Found Page ---
    # NEW UPDATE: Added a retry loop to combat the "Proxy Roulette".
    # We will try up to 3 times to get a clean IP from Scrape.do.
    scrape_successful = False

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # NEW UPDATE: Added the attempt counter to the log
            print(f">> [LOG] Step 2 Initiated (Attempt {attempt}/{MAX_RETRIES}): Requesting the exact post URL: {params['url']}")
            response = requests.get(api_url, params=params, timeout=120)

            if response.status_code == 200:
                print(">> [LOG] Post page loaded successfully. Checking for Cloudflare interference...")
                # Check if we are still in the "Waiting Room"
                if "Just a moment" in response.text or "security check" in response.text:
                    # NEW UPDATE: Instead of crashing, we warn and trigger a retry
                    print(">> WARNING: Cloudflare detected us on the blog page.")
                    print(">> [LOG] Spinning the proxy roulette wheel again in 3 seconds...")
                    time.sleep(3)
                    continue

                print(">> [LOG] No Cloudflare blocks detected. Proceeding to parse tables...")
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # --- PARSING ---
                # NEW: We now specifically target the main "All Sales Results $500+" table by its exact ID
                table = soup.find('table', id='daily-results')
                
                if not table:
                    # NEW UPDATE: Silent redirects to the homepage hide the table. We warn and retry.
                    print(">> WARNING: Cloudflare let us in, but I can't find the 'daily-results' table. Likely a silent redirect.")
                    print(f">> Page Title: {soup.title.string if soup.title else 'No Title'}")
                    print(">> [LOG] Spinning the proxy roulette wheel again in 3 seconds...")
                    time.sleep(3)
                    continue

                # Handle tables that might or might not have a <tbody> tag (common in blogs)
                rows = table.find('tbody').find_all('tr') if table.find('tbody') else table.find_all('tr')
                print(f">> SUCCESS! Found {len(rows)} rows in the main daily-results table. Beginning data extraction...")

                filtered_sales = []
                for row in rows:
                    # Blog tables sometimes use <th> for the first column instead of <td>, so we find both
                    cols = row.find_all(['td', 'th']) 
                    if len(cols) < 3: continue 
                    
                    domain = cols[0].get_text(strip=True)
                    price = cols[1].get_text(strip=True)
                    venue = cols[2].get_text(strip=True) 
                    
                    # NEW UPDATE: Clean the price by removing the dollar sign and commas so it matches WordPress format.
                    price = price.replace("$", "").replace(",", "")

                    # NEW UPDATE: Automatically apply the target date string to the records
                    date_sold = target_date_string
                    
                    if len(cols) >= 4:
                        date_sold = cols[3].get_text(strip=True)

                    # NEW UPDATE: Replaced the specific filter to allow ALL extensions and ALL venues EXCEPT "DropCatch".
                    if "dropcatch" not in venue.lower():
                        
                        # NEW UPDATE: Prepare new variables strictly for WordPress format compatibility
                        status = "SOLD"
                        bids = "0"
                        platform = venue

                        # NEW UPDATE: Changed appended list to strictly follow Domain,Price,Status,Date,Bids,Platform order.
                        filtered_sales.append([domain, price, status, date_sold, bids, platform])

                print(f">> [LOG] Data extraction complete. Total valid records prepared for export: {len(filtered_sales)}")

                # Save to CSV
                filename = "daily_sales.csv"
                print(f">> [LOG] Opening file {filename} in overwrite mode to ensure clean data...")
                
                # NEW UPDATE: Changed the file mode from "a" (append) to "w" (overwrite). 
                # This ensures that old data doesn't mix with new data. It writes a fresh file every time.
                with open(filename, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    
                    # NEW UPDATE: Since we overwrite every time, we ALWAYS write the exact headers first.
                    writer.writerow(["Domain", "Price", "Status", "Date", "Bids", "Platform"])
                    writer.writerows(filtered_sales)
                    
                print(f">> SAVED {len(filtered_sales)} rows to {filename}")
                print(">> [LOG] Data successfully written to disk. Run completed successfully.")
                
                # NEW UPDATE: Mark the run as successful and break out of the retry loop
                scrape_successful = True
                break

            else:
                print(f">> API FAILED. Status: {response.status_code}")
                print(f">> Error: {response.text}")
                print(">> [LOG] Spinning the proxy roulette wheel again in 3 seconds...")
                time.sleep(3)
                continue

        except Exception as e:
            print(f">> ERROR on attempt {attempt}: {e}")
            print(">> [LOG] Spinning the proxy roulette wheel again in 3 seconds...")
            time.sleep(3)
            continue

    # NEW UPDATE: If all 3 attempts fail, we finally let the script crash.
    if not scrape_successful:
        print(">> [LOG] CRITICAL: All 3 attempts failed due to Cloudflare blocks or API errors. Exiting.")
        exit(1)

if __name__ == "__main__":
    main()
