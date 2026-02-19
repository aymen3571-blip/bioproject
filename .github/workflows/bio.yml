name: Daily NameBio Blog Scrape

on:
  schedule:
    - cron: '0 9 * * *'
  workflow_dispatch:

# We explicitly give the bot permission to push the CSV file back to the repo
permissions:
  contents: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          pip install requests beautifulsoup4

      - name: Run Scraper
        # NEW: Removed the SCRAPE_DO_TOKEN environment variable entirely since we are going direct
        run: python Bio_scraper.py

      - name: Commit and Push CSV
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add daily_sales.csv
          # Only push if there is new data
          git diff-index --quiet HEAD || git commit -m "Update daily sales from blog"
          git push
