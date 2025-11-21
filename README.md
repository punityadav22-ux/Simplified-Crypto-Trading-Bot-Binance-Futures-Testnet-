
# Simplified Trading Bot (Binance Futures Testnet)

This repository contains the assignment solution for the Junior Python Developer – Crypto Trading Bot position.

## How to Run
1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Set environment variables:
   ```
   export BINANCE_API_KEY="your_key"
   export BINANCE_API_SECRET="your_secret"
   ```

3. Run a market order test:
   ```
   python basic_bot.py market --symbol BTCUSDT --side BUY --quantity 0.001
   ```

## Files
- `basic_bot.py` : Main bot implementation
- `requirements.txt`
- `README.md`
