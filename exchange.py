import ccxt
import math
from typing import Dict, Optional, Any


# MEXC API Configuration
MEXC_API_KEY = "moloEwgk5VGozASOA608BuxnKcnbE5u81NT0dzcZ5XuF6yWuMMMs1ggpnziRmvFR"
MEXC_SECRET_KEY = "Yt01Ypt8ITpgnJCQ9ao7LBGH2MUVCEcOorxS0y8iYuh3mLa3ajA4jFHxf7Zv9VcT" 

# ⚙️ Trading Settings
TRADE_AMOUNT_USDT = 10000  # Amount in USDT to trade
LEVERAGE = 50          # Leverage

# 🔗 Initialize Exchange
exchange = ccxt.binanceusdm({
    'apiKey': MEXC_API_KEY,
    'secret': MEXC_SECRET_KEY
})


# ✅ Get Futures Balance
def get_futures_balance() -> float:
    balance = exchange.fetch_balance({'type': 'swap'})
    usdt_balance = balance['total'].get('USDT', 0)
    print(f"💰 Futures USDT Balance: {usdt_balance}")
    return usdt_balance


# 🚀 Main Trading Function
def mexc_futures_trade(token: str, side: str) -> bool:
    if not MEXC_API_KEY or not MEXC_SECRET_KEY:
        print("❌ API keys are not set.")
        return False

    symbol = f"{token.upper()}/USDT:USDT"
    ccxt_side = 'buy' if side.lower() == 'long' else 'sell'

    print(f"\n📢 Attempting {side.upper()} trade on {symbol} with {LEVERAGE}x leverage...")

    try:
        markets = exchange.load_markets()

        if symbol not in markets:
            print(f"❌ Symbol {symbol} is not available on MEXC Futures.")
            return False

        market = markets[symbol]
        print(f"📊 Market info: {market}")

        # Check balance first
        balance = get_futures_balance()
        if balance < TRADE_AMOUNT_USDT / LEVERAGE:
            print("❌ Insufficient balance in futures wallet.")
            return False

        # Set leverage
        try:
            position_type = 1 if ccxt_side == 'buy' else 2
            exchange.set_leverage(LEVERAGE, symbol, params={
                'openType': 2,  # cross margin
                'positionType': position_type
            })
            print(f"✅ Leverage set to {LEVERAGE}x")
        except Exception as e:
            print(f"⚠️ Leverage setting failed: {e}. Continuing...")

        # Fetch ticker price
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        print(f"💰 Current price for {symbol}: {current_price}")

        # Calculate position size
        raw_position_size = TRADE_AMOUNT_USDT / current_price

        # ✅ Fix precision handling
        precision = int(market['precision']['amount'] or 6)
        min_amount = market['limits']['amount']['min'] or 0

        step_size = 10 ** -precision

        position_size = math.floor(raw_position_size / step_size) * step_size
        position_size = round(position_size, precision)

        print(f"📐 Calculated position size: {position_size}")
        print(f"🔢 Precision: {precision} | Min amount: {min_amount}")

        if position_size <= 0 or position_size < min_amount:
            print("❌ Position size too small for this symbol.")
            return False

        # Place order
        order = exchange.create_market_order(
            symbol=symbol,
            side=ccxt_side,
            amount=position_size,
            params={
                'openType': 2,  # cross margin
                'positionType': 1 if ccxt_side == 'buy' else 2
            }
        )

        print("✅ Trade executed successfully!")
        print(f"📝 Order Info: {order}")

        # Place TP order (2%)
        # Calculate the target price first
        target_price = current_price * (1.015 if ccxt_side == 'buy' else 0.985)
        # Use exchange's built-in precision formatting
        tp_price = float(exchange.price_to_precision(symbol, target_price))

        tp_order = exchange.create_order(
            symbol=symbol,
            type='limit',
            side='sell' if ccxt_side == 'buy' else 'buy',
            amount=position_size,
            price=tp_price,
            params={
                'openType': 2,  # cross margin
                'positionType': 1 if ccxt_side == 'buy' else 2,
                'reduceOnly': True  # ✅ To close the position, not open a new one
            }
        )

        print(f"🎯 Take Profit order placed at {tp_price}")
        print(f"📝 TP Order Info: {tp_order}")


        return True

    except Exception as e:
        print(e)
        print(f"❌ Error during trade execution: {str(e)}")
        if hasattr(e, 'response'):
            print(f"🔍 Response: {e.response}")
        return False


# 🧠 Process Grok Signal
def process_grok_signal(grok_response: Dict[str, Any]) -> None:
    if not isinstance(grok_response, dict):
        print("❌ Invalid Grok response format.")
        return

    token = grok_response.get('token')
    side = grok_response.get('side')

    if token and side:
        # valid_tokens = ['BTC', 'ETH', 'ADA', 'SOL', 'DOGE', 'XRP']
        # if token.upper() not in valid_tokens:
        #     print(f"❌ Invalid token: {token}. Allowed tokens: {valid_tokens}")
        #     return

        print(f"📥 Signal received: {side.upper()} {token.upper()}")
        success = mexc_futures_trade(token, side)

        if success:
            print(f"🚀 Trade executed for {token.upper()}")
        else:
            print(f"⚠️ Failed to execute trade for {token.upper()}")
    elif 'result' in grok_response and grok_response['result'] is False:
        print("📝 No trading signal found.")
    else:
        print("❌ Missing 'token' or 'side' in Grok response.")

