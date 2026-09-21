// tv_bridge.mjs — TradingView-API bridge untuk bot v15 unified.
// Ambil: (1) TA consensus multi-TF (5m/15m/1h) dari TradingView, (2) candles 1h utk regime.
// Dipanggil dari Python via subprocess: node tv_bridge.mjs BINANCE:BTCUSDT
const TradingView = require('/tmp/tvapi/main.js');

async function taFor(client, symbol, timeframe, range) {
  return new Promise((resolve, reject) => {
    const chart = new client.Session.Chart();
    const to = setTimeout(() => { try { chart.delete(); } catch {} ; resolve({ timeframe, periods: 0, ta: null }); }, 12000);
    chart.onError((...e) => { clearTimeout(to); resolve({ timeframe, periods: 0, ta: null }); });
    chart.setMarket(symbol, { timeframe, range });
    chart.onUpdate(() => {
      const p = chart.periods;
      clearTimeout(to);
      const out = { timeframe, periods: p.length, ta: null };
      if (p.length >= 60) {
        // EMA + RSI dihitung dari candles TradingView (nilai sama dgn TV studies)
        const closes = p.map(x => x.close).reverse();
        out.ta = {
          ema10: ema(closes, 10), ema20: ema(closes, 20), ema50: ema(closes, 50),
          rsi: rsi(closes, 14),
          last_close: closes[closes.length - 1],
        };
      }
      try { chart.delete(); } catch {}
      resolve(out);
    });
  });
}

function ema(arr, n) { const k = 2/(n+1); let e = arr[0]; for (let i=1;i<arr.length;i++) e = arr[i]*k + e*(1-k); return e; }
function rsi(arr, n) {
  let g=0,l=0; for (let i=1;i<=n;i++){const d=arr[i]-arr[i-1]; d>=0?g+=d:l-=d;}
  let ag=g/n, al=l/n;
  for (let i=n+1;i<arr.length;i++){const d=arr[i]-arr[i-1]; ag=(ag*(n-1)+Math.max(d,0))/n; al=(al*(n-1)+Math.max(-d,0))/n;}
  return al===0?100:100-100/(1+ag/al);
}

(async () => {
  const symbol = process.argv[2] || 'BINANCE:BTCUSDT';
  const client = new TradingView.Client();
  const [t5, t15, t60] = await Promise.all([
    taFor(client, symbol, '5', 300),
    taFor(client, symbol, '15', 300),
    taFor(client, symbol, '60', 300),
  ]);
  console.log(JSON.stringify({ symbol, tf5: t5, tf15: t15, tf60: t60 }));
  client.end();
  process.exit(0);
})().catch(e => { console.error(JSON.stringify({ error: e.message })); process.exit(1); });
