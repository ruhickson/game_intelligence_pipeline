# Efficient Steam Price Tracker

This tool efficiently detects Steam price changes without scanning the entire 142,000+ game catalog. It leverages Steam's sale APIs and (optionally) third-party services to identify games with likely price changes, fetches their latest prices, and records any changes to your database.

## Features
- **Efficient Detection:** Uses Steam's featured sales and daily deals APIs to get a daily set of discounted/changed games.
- **Third-Party Integration:** Optionally integrates with IsThereAnyDeal for additional price change feeds.
- **Database Logging:** Records price changes and detection statistics in dedicated tables.
- **Email Notifications:** Optionally sends summary emails when price changes are detected.
- **Statistics:** Provides stats on detection efficiency and results.

## How It Works
1. **Sale APIs:** The script queries Steam's featured sales and daily deals APIs to get a list of app IDs with current discounts or price changes.
2. **(Optional) Third-Party Feeds:** If configured, it also checks IsThereAnyDeal for additional price change data.
3. **Price Fetching:** For each identified app ID, it fetches detailed price data from the Steam API.
4. **Change Detection:** Compares the new price data to your database's last known prices.
5. **Logging:** Records any detected price changes and logs detection run statistics.
6. **Notification:** Optionally sends a summary email if price changes are found.

## Setup
1. **Dependencies:**
   - Python 3.7+
   - `requests`, `psycopg2`, `python-dotenv`, `smtplib`
   - Install with: `pip install -r requirements.txt` (create if needed)
2. **Environment Variables:**
   - Create a `.Renv` file in the project root or set these in your environment:
     - `SUPABASE_CONNECTION_STRING` (Postgres connection string)
     - `EMAIL_ENABLED` (`true` or `false`)
     - `SMTP_SERVER`, `SMTP_PORT`, `EMAIL_USER`, `EMAIL_PASSWORD`, `NOTIFICATION_EMAIL` (for email notifications)
     - `ISTHEREANYDEAL_API_KEY` (optional, for IsThereAnyDeal integration)
3. **Database:**
   - The script will auto-create the following tables if they do not exist:
     - `steam_price_changes`
     - `steam_sale_detection_log`

## Usage
Run the script from the `game_intelligence_pipeline` directory:

```bash
python efficient_steam_price_tracker.py
```

- The script will log its progress to `efficient_price_tracker.log` and print summary statistics to the console.
- If email is enabled and price changes are detected, a summary will be sent to the configured address.

## Customization
- **Third-Party Feeds:** To use IsThereAnyDeal, set `ISTHEREANYDEAL_API_KEY` in your environment.
- **Email:** Set `EMAIL_ENABLED=true` and configure SMTP/email variables.
- **Database:** Ensure your `SUPABASE_CONNECTION_STRING` is correct and the target database is accessible.

## Output Tables
- `steam_price_changes`: Records each detected price change (app_id, old/new price, discount, etc.)
- `steam_sale_detection_log`: Logs each detection run (date, games checked, price changes found, processing time)

## Notes
- This approach checks only a few thousand games per day (those on sale or with detected changes), not the full catalog.
- For full-catalog price history, run a separate, less frequent full scan if needed.
- SteamDB and SteamSpy do not provide public APIs for bulk price change feeds; scraping is not implemented here.

## License
MIT 