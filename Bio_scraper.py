import requests
import csv
import os
import time
from bs4 import BeautifulSoup
from datetime import date, timedelta # NEW: Added timedelta to calculate yesterday's date dynamically

API_TOKEN = os.getenv("SCRAPE_DO_TOKEN")

def main():
    print(">> Starting Scrape.do (Targeting Blog Page)...")

    # NEW: Calculate yesterday's date to dynamically build the URL
    yesterday = date.today() - timedelta(days=1)
    
    # NEW: Format the date to match NameBio's URL structure (e.g., "february-18th-2026")
    day = yesterday.day
    if 4 <= day <= 20 or 24 <= day <= 30:
        suffix = "th"
    else:
        suffix = ["st", "nd", "rd"][day % 10 - 1]
    
    formatted_date_string = f"{yesterday.strftime('%B').lower()}-{day}{suffix}-{yesterday.year}"
    
    # NEW UPDATE: We keep the old generated URL as a fallback, but we will dynamically fetch the REAL URL first.
    # Guessing URLs is dangerous because WordPress redirects 404 errors to the homepage if there's a typo.
    guessed_target_url = f"https://namebio.com/blog/daily-market-report-for-{formatted_date_string}/"
    
    api_url = "https://api.scrape.do/"

    # THE STRATEGY:
    # 1. mobile=true: Tells Cloudflare we are a phone (touchscreen, battery, etc.)
    # 2. render=true: Uses a real browser engine to solve the Javascript challenge
    params = {
        "token": API_TOKEN,
        "url": guessed_target_url, # NEW UPDATE: Default to guessed, will update dynamically below
        "render": "true",
        "mobile": "true"
    }

    # NEW UPDATE: Step 1 - Fetch the blog index to find the EXACT link to the newest report
    try:
        # blog_index_url = "https://namebio.com/blog/"
        # NEW UPDATE: Changed to the specific Daily Market Report category page
        blog_index_url = "https://namebio.com/blog/category/daily-market-report/"
        print(f">> Step 1: Visiting {blog_index_url} to find the exact latest report URL...")
        
        # Clone our Scrape.do settings for this quick index check
        index_params = params.copy()
        index_params["url"] = blog_index_url
        
        index_response = requests.get(api_url, params=index_params, timeout=120)
        
        if index_response.status_code == 200:
            index_soup = BeautifulSoup(index_response.text, 'html.parser')
            real_url = None
            
            # Find all links on the blog page and grab the first Daily Market Report
            for a_tag in index_soup.find_all('a', href=True):
                href = a_tag['href']
                # NEW UPDATE: Ensure it is a post URL and not a pagination link by excluding the word "category"
                if "daily-market-report" in href.lower() and "category" not in href.lower():
                    real_url = href
                    break
            
            if real_url:
                print(f">> Found exact latest URL: {real_url}")
                params["url"] = real_url # Update params with the real URL
            else:
                print(">> Warning: Could not find dynamic URL. Falling back to guessed URL.")
                print(f">> Target URL: {guessed_target_url}")
                
        else:
            print(">> Warning: Failed to load blog index. Falling back to guessed URL.")
            print(f">> Target URL: {guessed_target_url}")

    except Exception as e:
        print(f">> Error in Step 1: {e}. Falling back to guessed URL.")

    # --- Start Step 2: Actually Scrape the Found Page ---
    try:
        print(">> Step 2: Sending request to the Target URL via Scrape.do...")
        response = requests.get(api_url, params=params, timeout=120)

        if response.status_code == 200:
            # Check if we are still in the "Waiting Room"
            if "Just a moment" in response.text or "security check" in response.text:
                print(">> FAILED: Cloudflare detected us on the blog page as well.")
                exit(1)

            soup = BeautifulSoup(response.text, 'html.parser')
            
            # --- PARSING ---
            # NEW: We now specifically target the main "All Sales Results $500+" table by its exact ID
            table = soup.find('table', id='daily-results')
            
            if not table:
                print(">> CRITICAL: Cloudflare let us in, but I can't find the 'daily-results' table.")
                print(f">> Page Title: {soup.title.string if soup.title else 'No Title'}")
                exit(1)

            # Handle tables that might or might not have a <tbody> tag (common in blogs)
            rows = table.find('tbody').find_all('tr') if table.find('tbody') else table.find_all('tr')
            print(f">> SUCCESS! Found {len(rows)} rows in the main daily-results table.")

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

                # Automatically apply yesterday's exact date string to the records
                date_sold = yesterday.strftime("%Y-%m-%d")
                
                if len(cols) >= 4:
                    date_sold = cols[3].get_text(strip=True)

                # NEW UPDATE: Expanding the venue filter to capture GoDaddy, Afternic, and Sedo sales instead of just GoDaddy
                # target_venues = ["godaddy", "afternic", "sedo"] 
                # NEW UPDATE: Commented out target_venues as requested, since we now capture all venues.
                
                # NEW: Check if it is a .com and belongs to any of our target venues
                # if ".com" in domain.lower() and any(v in venue.lower() for v in target_venues):
                # NEW UPDATE: Replaced the specific filter to allow ALL extensions and ALL venues EXCEPT "DropCatch".
                if "dropcatch" not in venue.lower():
                    
                    # NEW UPDATE: Prepare new variables strictly for WordPress format compatibility
                    status = "SOLD"
                    bids = "0"
                    platform = venue

                    # NEW UPDATE: Changed appended list to strictly follow Domain,Price,Status,Date,Bids,Platform order.
                    filtered_sales.append([domain, price, status, date_sold, bids, platform])

            # Save to CSV
            filename = "daily_sales.csv"
            
            # NEW UPDATE: Changed the file mode from "a" (append) to "w" (overwrite). 
            # This ensures that old data doesn't mix with new data. It writes a fresh file every time.
            with open(filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                
                # NEW UPDATE: Since we overwrite every time, we ALWAYS write the exact headers first.
                writer.writerow(["Domain", "Price", "Status", "Date", "Bids", "Platform"])
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
