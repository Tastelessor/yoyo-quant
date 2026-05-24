# GTJA 191 Alpha Factors Reference

Source: Guotai Junan Securities 191 Alpha Factors (DolphinDB implementation)
Adapted from: https://github.com/dolphindb/DolphinDBModules/blob/master/gtja191Alpha/src/gtja191Alpha.dos

## Input Variables

| Variable | Description |
|----------|-------------|
| `open` | Daily open price |
| `high` | Daily high price |
| `low` | Daily low price |
| `close` | Daily close price |
| `vol` | Daily volume |
| `vwap` | Volume-weighted average price |
| `index_close` | Benchmark index close (e.g. CSI 300) |

## Notation

| Symbol | Meaning |
|--------|---------|
| `delta(x, n)` | x - delay(x, n), i.e. change over n periods |
| `delay(x, n)` | Value n periods ago |
| `ret` | Daily return = close / delay(close, 1) - 1 |
| `mean(x, n)` | Moving average over n periods |
| `std(x, n)` | Moving standard deviation over n periods |
| `sum(x, n)` | Moving sum over n periods |
| `rank(x)` | Cross-sectional rank (percentile within universe) |
| `corr(x, y, n)` | Moving correlation over n periods |
| `sma(x, n, m)` | Exponential moving average (alpha = m/n) |
| `tsrank(x, n)` | Time-series rank over n periods |
| `tsmax(x, n)` | Time-series max over n periods |
| `tsmin(x, n)` | Time-series min over n periods |
| `decaylinear(x, n)` | Linearly-weighted moving average over n periods |

---

## Category 1: Volume-Price Relationship

These factors explore how volume interacts with price movements.

| # | Formula | Description |
|---|---------|-------------|
| 1 | `-1 * corr(rank(delta(log(vol), 1)), rank((close - open) / open), 6)` | Correlation between volume change rank and intraday return rank over 6d |
| 5 | `-1 * tsmax(corr(tsrank(vol, 5), tsrank(high, 5), 5), 3)` | Max correlation between volume rank and high rank over 3d |
| 7 | `(rank(tsmax(vwap - close, 3)) + rank(tsmin(vwap - close, 3))) * rank(delta(vol, 3))` | VWAP-close deviation range × volume change rank |
| 11 | `sum(((close-low)-(high-close))/(high-low)*vol, 6)` | 6d sum of volume-weighted directional pressure (buy vs sell) |
| 16 | `-1 * tsmax(rank(corr(rank(vol), rank(vwap), 5)), 5)` | Max correlation between volume rank and VWAP rank |
| 29 | `(close - delay(close, 6)) / delay(close, 6) * vol` | 6d return × volume |
| 32 | `-1 * sum(rank(corr(rank(high), rank(vol), 3)), 3)` | 3d rolling sum of high-volume correlation rank |
| 36 | `rank(sum(corr(rank(vol), rank(vwap), 6), 2))` | 2d sum of volume-VWAP correlation rank |
| 40 | `sum(close>delay(close,1)?vol:0, 26) / sum(close<=delay(close,1)?vol:0, 26) * 100` | Up-volume / down-volume ratio over 26d |
| 42 | `-1 * rank(std(high, 10)) * corr(high, vol, 10)` | Volatility rank × high-volume correlation |
| 43 | `sum(close>delay(close,1)?vol:(close<delay(close,1)?-vol:0), 6)` | 6d OBV-like signed volume sum |
| 45 | `rank(delta(close*0.6+open*0.4, 1)) * rank(corr(vwap, mean(vol,150), 15))` | Price change rank × long-term volume correlation rank |
| 62 | `-1 * corr(high, rank(vol), 5)` | Negative correlation between high price and volume rank |
| 70 | `std(vol * vwap, 6)` | 6d std of dollar volume (trading amount) |
| 73 | `(tsrank(decaylinear(decaylinear(corr(close, vol, 10), 16), 4), 5) - rank(decaylinear(corr(vwap, mean(vol,30), 4), 3))) * -1` | Doubly smoothed close-volume correlation vs VWAP-volume correlation |
| 76 | `std(abs(close/delay(close,1)-1)/vol, 20) / mean(abs(close/delay(close,1)-1)/vol, 20)` | Coefficient of variation of return-per-volume over 20d |
| 80 | `(vol - delay(vol, 5)) / delay(vol, 5) * 100` | 5d volume change percentage |
| 83 | `-1 * rank(covariance(rank(high), rank(vol), 5))` | Negative covariance between high price rank and volume rank |
| 84 | `sum(close>delay(close,1)?vol:(close<delay(close,1)?-vol:0), 20)` | 20d OBV-like signed volume |
| 90 | `-1 * rank(corr(rank(vwap), rank(vol), 5))` | Negative correlation between VWAP rank and volume rank |
| 94 | `sum(close>delay(close,1)?vol:(close<delay(close,1)?-vol:0), 30)` | 30d OBV-like signed volume |
| 95 | `std(vol * vwap, 20)` | 20d std of dollar volume |
| 97 | `std(vol, 10)` | 10d volume volatility |
| 99 | `-1 * rank(covariance(rank(close), rank(vol), 5))` | Negative covariance between close rank and volume rank |
| 100 | `std(vol, 20)` | 20d volume volatility |
| 102 | `sma(max(vol-delay(vol,1),0), 6, 1) / sma(abs(vol-delay(vol,1)), 6, 1) * 100` | Volume RSI-like: up-volume intensity over 6d |
| 105 | `-1 * corr(rank(open), rank(vol), 10)` | Negative correlation between open rank and volume rank |
| 111 | `sma(vol*((close-low)-(high-close))/(high-low), 11, 2) - sma(vol*((close-low)-(high-close))/(high-low), 4, 2)` | Short-term minus long-term money flow |
| 113 | `-1 * rank(sum(delay(close,5), 20)/20) * corr(close, vol, 2) * rank(corr(sum(close,5), sum(close,20), 2))` | Delayed price level × volume correlation × price trend consistency |
| 114 | `(rank(delay((high-low)/(sum(close,5)/5), 2)) * rank(rank(vol))) / ((high-low)/(sum(close,5)/5) / (vwap-close))` | Lagged volatility rank × volume rank, normalized by current volatility and VWAP discount |
| 117 | `tsrank(vol, 32) * (1 - tsrank(close+high-low, 16)) * (1 - tsrank(ret, 32))` | Volume rank × inverse price strength × inverse return rank |
| 132 | `mean(vol * vwap, 20)` | 20d average dollar volume |
| 134 | `(close - delay(close, 12)) / delay(close, 12) * vol` | 12d return × volume |
| 139 | `-1 * corr(open, vol, 10)` | Negative open-volume correlation |
| 141 | `-1 * rank(corr(rank(high), rank(mean(vol,15)), 9))` | Negative correlation between high rank and volume average rank |
| 145 | `(mean(vol, 9) - mean(vol, 26)) / mean(vol, 12) * 100` | Volume MACD-like indicator |
| 155 | `sma(vol, 13, 2) - sma(vol, 27, 2) - sma(sma(vol, 13, 2) - sma(vol, 27, 2), 10, 2)` | Volume MACD (13, 27, 10) |
| 168 | `-1 * vol / mean(vol, 20)` | Negative volume ratio |
| 178 | `(close - delay(close, 1)) / delay(close, 1) * vol` | Daily return × volume |
| 180 | `(mean(vol,20) < vol) ? (-1 * tsrank(abs(delta(close,7)), 60) * sign(delta(close,7))) : (-1 * vol)` | If volume is above average: negative rank of |7d price change|, else: negative volume |

---

## Category 2: Price Momentum / Trend

Factors measuring price direction, momentum, and trend strength.

| # | Formula | Description |
|---|---------|-------------|
| 6 | `-1 * rank(delta(open*0.85 + high*0.15, 4))` | Negative rank of 4d change in open/high blend |
| 14 | `close - delay(close, 5)` | 5d price change (simple momentum) |
| 15 | `open / delay(close, 1) - 1` | Overnight gap (open vs yesterday's close) |
| 18 | `close / delay(close, 5)` | 5d price ratio |
| 19 | `close < delay(close,5) ? (close-delay(close,5))/delay(close,5) : (close=delay(close,5) ? 0 : (close-delay(close,5))/close)` | Asymmetric 5d return (down uses base, up uses current) |
| 20 | `(close - delay(close, 6)) / delay(close, 6) * 100` | 6d return percentage |
| 21 | `reghbeta(mean(close,6), sequence(6))` | Slope of 6d moving average (trend strength) |
| 24 | `sma(close - delay(close, 5), 5, 1)` | Smoothed 5d momentum |
| 25 | `-1 * rank(delta(close,7) * (1 - rank(decaylinear(vol/mean(vol,20), 9)))) * (1 + rank(sum(ret, 250)))` | 7d momentum × inverse decay-weighted volume ratio × long-term return rank |
| 31 | `(close - mean(close, 12)) / mean(close, 12) * 100` | 12d price vs MA deviation % |
| 33 | `(-1*tsmin(low,5) + delay(tsmin(low,5),5)) * rank((sum(ret,240)-sum(ret,20))/220) * tsrank(vol,5)` | Low bounce × long-term minus short-term momentum × volume rank |
| 34 | `mean(close, 12) / close` | Inverse of 12d MA/price ratio (mean reversion signal) |
| 37 | `-1 * rank(sum(open,5)*sum(ret,5) - delay(sum(open,5)*sum(ret,5), 10))` | Negative rank of 10d change in (5d avg open × 5d return) |
| 38 | `(mean(high,20) < high) ? -1*delta(high,2) : 0` | Negative 2d high change when above 20d MA high |
| 46 | `(mean(close,3)+mean(close,6)+mean(close,12)+mean(close,24)) / (4*close)` | Multi-period MA ratio (3/6/12/24d vs price) |
| 58 | `count(close>delay(close,1), 20) / 20 * 100` | % of up-days in 20d (advance rate) |
| 65 | `mean(close, 6) / close` | 6d MA / price ratio |
| 66 | `(close - mean(close, 6)) / mean(close, 6) * 100` | 6d MA deviation % |
| 88 | `(close - delay(close, 20)) / delay(close, 20) * 100` | 20d return percentage |
| 98 | `(delta(mean(close,100),100)/delay(close,100) <= 0.05) ? -1*(close-tsmin(close,100)) : -1*delta(close,3)` | If 100d trend flat: negative drawdown from high; else: negative 3d change |
| 106 | `close - delay(close, 20)` | 20d price change (simple 20d momentum) |
| 116 | `reghbeta(close, sequence, 20)` | 20d linear regression slope (trend) |
| 127 | `mean((100*(close-max(close,12))/max(close,12))^2, 12)^(1/2)` | 12d RMS drawdown from 12d high |
| 133 | `((20-highday(high,20))/20)*100 - ((20-lowday(low,20))/20)*100` | Days since 20d high vs days since 20d low |
| 147 | `reghbeta(mean(close,12), sequence(12))` | Slope of 12d MA (trend direction) |
| 153 | `(mean(close,3)+mean(close,6)+mean(close,12)+mean(close,24))/4` | Multi-period MA average |
| 177 | `((20-highday(high,20))/20)*100` | Days since 20d high as % |
| 184 | `rank(corr(delay(open-close,1), close, 200)) + rank(open-close)` | Lagged gap correlation + current gap rank |

---

## Category 3: Mean Reversion / Overbought-Oversold

Factors that capture mean reversion and overbought/oversold conditions.

| # | Formula | Description |
|---|---------|-------------|
| 2 | `-1 * delta(((close-low)-(high-close))/(high-low), 1)` | Negative 1d change in (close-low)/(high-low), i.e. 1d change in internal bar position |
| 3 | `sum(close==delay(close,1) ? 0 : close-(close>delay(close,1) ? min(low,delay(close,1)) : max(high,delay(close,1))), 6)` | 6d sum of directional offset from prior bar range |
| 22 | `smean(((close-mean(close,6))/mean(close,6) - delay((close-mean(close,6))/mean(close,6), 3)), 12, 1)` | Smoothed acceleration of 6d MA deviation |
| 23 | `sma(close>delay(close,1)?std(close,20):0, 20, 1) / (sma(...)+sma(close<=delay(close,1)?std(close,20):0,20,1)) * 100` | RSI-like: % of upward volatility in total volatility |
| 26 | `mean(close,7)/7 - close + corr(vwap, delay(close,5), 230)` | 7d MA deviation + long-term VWAP-close correlation |
| 39 | `(rank(decaylinear(delta(close,2),8)) - rank(decaylinear(corr(vwap*0.3+open*0.7, sum(mean(vol,180),37), 14), 12))) * -1` | Decay-weighted 2d price change vs long-term volume correlation |
| 47 | `sma((tsmax(high,6)-close)/(tsmax(high,6)-tsmin(low,6))*100, 9, 1)` | Williams %R-like smoothed over 9d |
| 53 | `count(close>delay(close,1), 12)/12*100` | % of up-days in 12d |
| 57 | `sma((close-tsmin(low,9))/(tsmax(high,9)-tsmin(low,9))*100, 3, 1)` | Stochastic %K-like smoothed 3d |
| 63 | `sma(max(close-delay(close,1),0), 6, 1) / sma(abs(close-delay(close,1)), 6, 1) * 100` | 6d RSI |
| 67 | `sma(max(close-delay(close,1),0), 24, 1) / sma(abs(close-delay(close,1)), 24, 1) * 100` | 24d RSI |
| 71 | `(close - mean(close, 24)) / mean(close, 24) * 100` | 24d MA deviation % |
| 72 | `sma((tsmax(high,6)-close)/(tsmax(high,6)-tsmin(low,6))*100, 15, 1)` | Williams %R-like smoothed 15d |
| 79 | `sma(max(close-delay(close,1),0), 12, 1) / sma(abs(close-delay(close,1)), 12, 1) * 100` | 12d RSI |
| 82 | `sma((tsmax(high,6)-close)/(tsmax(high,6)-tsmin(low,6))*100, 20, 1)` | Williams %R-like smoothed 20d |
| 89 | `2*(sma(close,13,2)-sma(close,27,2)-sma(sma(close,13,2)-sma(close,27,2),10,2))` | MACD-like indicator (13, 27, 10) |
| 96 | `sma(sma((close-tsmin(low,9))/(tsmax(high,9)-tsmin(low,9))*100, 3, 1), 3, 1)` | Double-smoothed stochastic |
| 103 | `((20-lowday(low,20))/20)*100` | Days since 20d low as % |
| 112 | `(sum(close>delay(close,1)?close-delay(close,1):0,12)-sum(close<delay(close,1)?abs(close-delay(close,1)):0,12))/(sum(...)+sum(...))*100` | 12d RSI-type (advance-decline balance) |
| 118 | `sum(high-open, 20) / sum(open-low, 20) * 100` | 20d upper shadow / lower shadow ratio |
| 120 | `rank(vwap - close) / rank(vwap + close)` | VWAP vs close rank ratio (discount/premium) |
| 122 | `(sma(sma(sma(log(close),13,2),13,2),13,2) - delay(...)) / delay(...)` | Triple-smoothed log-price momentum |
| 124 | `(close - vwap) / decaylinear(rank(tsmax(close,30)), 2)` | Close vs VWAP, decay-weighted by 30d high rank |
| 128 | `100 - 100/(1+sum(up_amount,14)/sum(down_amount,14))` | Money flow index-like (14d) |
| 129 | `sum(close<delay(close,1) ? abs(close-delay(close,1)) : 0, 12)` | 12d sum of down-moves (absolute) |
| 151 | `sma(close - delay(close, 20), 20, 1)` | Smoothed 20d momentum |
| 160 | `sma(close<=delay(close,1)?std(close,20):0, 20, 1)` | Smoothed downside volatility |
| 162 | `(sma(max(close-delay(close,1),0),12,1)/sma(abs(close-delay(close,1)),12,1)*100 - min(...,12)) / (max(...,12)-min(...,12))` | 12d RSI normalized to 0-1 range (stochastic RSI) |
| 167 | `sum(close>delay(close,1) ? close-delay(close,1) : 0, 12)` | 12d sum of up-moves |
| 174 | `sma(close>delay(close,1)?std(close,20):0, 20, 1)` | Smoothed upside volatility |
| 185 | `rank(-1 * (1 - open/close)^2)` | Negative squared overnight gap (small gaps ranked high) |
| 189 | `mean(abs(close - mean(close, 6)), 6)` | 6d average absolute deviation from 6d MA |

---

## Category 4: Volatility / Risk

Factors measuring price dispersion, volatility, and risk.

| # | Formula | Description |
|---|---------|-------------|
| 10 | `rank(tsmax((ret<0 ? std(ret,20) : close)^2, 5))` | Max of squared downside vol or price over 5d |
| 48 | `-1 * rank(sign(delta(close,1))+sign(delay(delta(close,1),1))+sign(delay(delta(close,1),2))) * sum(vol,5)/sum(vol,20)` | 3d signed momentum × volume concentration |
| 54 | `-1 * rank(std(abs(close-open),10) + close-open + corr(close,open,10))` | Negative rank of candle body std + gap + correlation |
| 78 | `((high+low+close)/3 - ma((high+low+close)/3,12)) / (0.015*mean(abs(close-mean((high+low+close)/3,12)),12))` | CCI (Commodity Channel Index) over 12d |
| 97 | `std(vol, 10)` | 10d volume volatility |
| 100 | `std(vol, 20)` | 20d volume volatility |
| 109 | `sma(high-low, 10, 2) / sma(sma(high-low, 10, 2), 10, 2)` | ATR ratio: short-term / smoothed ATR |
| 126 | `(close + high + low) / 3` | Typical price (stateless) |
| 130 | `rank(decaylinear(corr((high+low)/2, mean(vol,40), 9), 10)) / rank(decaylinear(corr(rank(vwap), rank(vol), 7), 3))` | Decay-weighted price-volume correlation vs VWAP-volume correlation |
| 140 | `min(rank(decaylinear((rank(open)+rank(low))-(rank(high)+rank(close)),8)), tsrank(decaylinear(corr(tsrank(close,8),tsrank(mean(vol,60),20),8),7),3))` | Min of rank imbalance and volume-adjusted correlation |
| 158 | `(high - sma(close,15,2)) - (low - sma(close,15,2))) / close` | Normalized distance of high/low from smoothed close |
| 161 | `mean(max(max(high-low, abs(delay(close,1)-high)), abs(delay(close,1)-low)), 12)` | 12d average true range (ATR) |
| 165 | `max(sumac(close-mean(close,48))) - min(sumac(close-mean(close,48))) / std(close,48)` | Cumulative deviation range / volatility |
| 175 | `mean(max(max(high-low, abs(delay(close,1)-high)), abs(delay(close,1)-low)), 6)` | 6d average true range (ATR) |
| 183 | `max(sumac(close-mean(close,24))) - min(sumac(close-mean(close,24))) / std(close,24)` | Cumulative deviation range / volatility (24d) |
| 188 | `((high-low) - sma(high-low,11,2)) / sma(high-low,11,2) * 100` | ATR deviation % |

---

## Category 5: VWAP-Based

Factors centered on VWAP as a reference point.

| # | Formula | Description |
|---|---------|-------------|
| 8 | `-1 * rank(delta((high+low)/2*0.2 + vwap*0.8, 4))` | Negative rank of 4d change in VWAP-weighted typical price |
| 12 | `rank(open - sum(vwap,10)/10) * -1 * rank(abs(close-vwap))` | Open vs 10d VWAP deviation × close-VWAP distance |
| 13 | `sqrt(high * low) - vwap` | Geometric mean of H/L minus VWAP (stateless) |
| 17 | `rank(vwap - max(vwap, 15))^delta(close, 5)` | Rank of VWAP drawdown from 15d high, raised to 5d return power |
| 41 | `-1 * rank(tsmax(delta(vwap,3), 5))` | Negative rank of max 3d VWAP change over 5d |
| 44 | `tsrank(decaylinear(corr(low, mean(vol,10), 7), 6), 4) + tsrank(decaylinear(delta(vwap,3), 10), 15)` | Low-volume correlation rank + VWAP change rank |
| 92 | `-1 * max(rank(decaylinear(delta(close*0.35+vwap*0.65,2),3)), tsrank(decaylinear(abs(corr(mean(vol,180),close,13)),5),15))` | Max of price change rank and volume correlation rank |
| 108 | `-1 * rank(high-min(high,2))^rank(corr(vwap, mean(vol,120), 6))` | High drawdown rank raised to VWAP-volume correlation rank |
| 121 | `-1 * rank(vwap-min(vwap,12))^tsrank(corr(tsrank(vwap,20),tsrank(mean(vol,60),2),18),3)` | VWAP drawdown rank raised to correlation rank |
| 125 | `rank(decaylinear(corr(vwap, mean(vol,80), 17), 20)) / rank(decaylinear(delta(close*0.5+vwap*0.5, 3), 16))` | VWAP-volume correlation / price change |
| 131 | `rank(delta(vwap,1))^tsrank(corr(close, mean(vol,50), 18), 18)` | 1d VWAP change rank raised to close-volume correlation |
| 156 | `-1 * max(rank(decaylinear(delta(vwap,5),3)), rank(decaylinear(delta(open*0.15+low*0.85,2)/(open*0.15+low*0.85)*-1,3)))` | Max of VWAP change rank and price decline rank |
| 170 | `rank(1/close)*vol/mean(vol,20) * high*rank(high-close)/(sum(high,5)/5) - rank(vwap-delay(vwap,5))` | Composite: inverse price rank × volume ratio × high-close rank − VWAP change rank |
| 191 | `corr(mean(vol,20), low, 5) + (high+low)/2 - close` | Volume-low correlation + typical price vs close |

---

## Category 6: VWAP / Close Cross-Sectional

| # | Formula | Description |
|---|---------|-------------|
| 28 | `3*sma((close-tsmin(low,9))/(tsmax(high,9)-tsmin(low,9))*100,3,1) - 2*sma(sma((close-tsmin(low,9))/(tsmax(high,9)-tsmin(low,9))*100,3,1),3,1)` | Double-smoothed stochastic oscillator |
| 52 | `sum(max(0,high-delay((high+low+close)/3,1)),26) / sum(max(0,delay((high+low+close)/3,1)-low),26) * 100` | Upward RSI variant using typical price |
| 85 | `tsrank(vol/mean(vol,20), 20) * tsrank(-1*delta(close,7), 8)` | Volume ratio rank × negative 7d momentum rank |
| 86 | Complex conditional: compares 10d trend slope thresholds | Trend acceleration filter |
| 91 | `-1 * rank(close-max(close,5)) * rank(corr(mean(vol,40), low, 5))` | Close drawdown × low-volume correlation |
| 101 | `(rank(corr(close, sum(mean(vol,30),37), 15)) < rank(corr(rank(high*0.1+vwap*0.9), rank(vol), 11))) * -1` | Close-volume correlation vs high/VWAP-volume correlation |
| 110 | `sum(max(0,high-delay(close,1)),20) / sum(max(0,delay(close,1)-low),20) * 100` | 20d upward RSI variant |
| 115 | `rank(corr(high*0.9+close*0.1, mean(vol,30), 10))^rank(corr(tsrank((high+low)/2,4), tsrank(vol,10), 7))` | High-close-volume correlation raised to typical price-volume correlation |
| 136 | `-1 * rank(delta(ret,3)) * corr(open, vol, 10)` | Negative 3d return change rank × open-volume correlation |
| 142 | `-1 * rank(tsrank(close,10)) * rank(delta(delta(close,1),1)) * rank(tsrank(vol/mean(vol,20),5))` | Close rank × acceleration × volume ratio rank |
| 148 | `(rank(corr(open, sum(mean(vol,60),9), 6)) < rank(open-tsmin(open,14))) * -1` | Open-volume correlation vs open drawdown |
| 154 | `(vwap-min(vwap,16)) < corr(vwap, mean(vol,180), 18)` | Boolean: VWAP drawdown vs long-term VWAP-volume correlation |
| 163 | `rank(-1 * ret * mean(vol,20) * vwap * (high-close))` | Negative return × volume × VWAP × high-close gap |

---

## Category 7: Open / Gap / Intraday

Factors based on open price and intraday patterns.

| # | Formula | Description |
|---|---------|-------------|
| 35 | `-1 * min(rank(decaylinear(delta(open,1),15)), rank(decaylinear(corr(vol, open, 17),7)))` | Min of open change rank and open-volume correlation rank |
| 54 | `-1 * rank(std(abs(close-open),10) + close-open + corr(close,open,10))` | Negative candle body volatility + gap + correlation |
| 87 | `-1 * (rank(decaylinear(delta(vwap,4),7)) + tsrank(decaylinear((low-vwap)/(open-(high+low)/2),11),7))` | VWAP change + price position in bar |
| 107 | `-1 * rank(open-delay(high,1)) * rank(open-delay(close,1)) * rank(open-delay(low,1))` | Triple product of open gaps vs yesterday's H/C/L |
| 137 | Complex: 16×(close-delay+intraday)/normalized_range×max_range | Directional movement with intraday bias (single bar factor) |
| 150 | `(close+high+low)/3 * vol` | Typical price × volume (stateless) |
| 187 | `sum(open<=delay(open,1) ? 0 : max(high-open, open-delay(open,1)), 20)` | 20d sum of upward opening gaps |
| 171 | `-1 * (low-close)*(open^5) / ((close-high)*(close^5))` | Intraday position ratio with 5th power scaling |

---

## Category 8: DMI / Directional Movement

Factors based on directional movement index concepts.

| # | Formula | Description |
|---|---------|-------------|
| 49 | `sum(down_direction,12) / (sum(down_direction,12) + sum(up_direction,12))` | Down-direction / total direction ratio over 12d |
| 50 | `sum(up_direction,12)/(sum+sum) - sum(down_direction,12)/(sum+sum)` | Net directional ratio (up - down) |
| 51 | `sum(up_direction,12) / (sum + sum)` | Up-direction / total direction ratio over 12d |
| 69 | `(sum(DTM,20)>sum(DBM,20)) ? (DTM-DBM)/DTM : (DTM==DBM) ? 0 : (DTM-DBM)/DBM` | DMI-like: directional movement balance over 20d |
| 172 | `mean(abs(up_di-down_di)/(up_di+down_di)*100, 6)` | 6d average of absolute DMI imbalance |
| 186 | `(mean(abs(DMI_imbalance),6) + delay(mean(abs(DMI_imbalance),6),6)) / 2` | 6d DMI imbalance smoothed with 6d lag |

---

## Category 9: Beta / Market Sensitivity

Factors requiring benchmark index data.

| # | Formula | Description |
|---|---------|-------------|
| 30 | `wma((regresi(close/delay(close)-1, MKT, SMB, HML, 60))^2, 20)` | Fama-French 3-factor residual variance (60d regression, 20d WMA) |
| 75 | `count(close>open & index_close<index_open, 50) / count(index_close<index_open, 50)` | Stock up when market down ratio (50d) |
| 149 | `reghbeta(filtered_ret, filtered_index_ret, 252)` | 252d beta in down-market days only |
| 181 | Complex: covariance-like term / cube term | Skewness-adjusted beta (20d) |
| 182 | `count((close>open & index>index_open) or (close<open & index<index_open), 20) / 20` | 20d stock-market direction agreement rate |

---

## Category 10: Decay Linear / Time-Weighted

Factors heavily using decaylinear (linearly-weighted moving average).

| # | Formula | Description |
|---|---------|-------------|
| 9 | `sma(((high+low)/2-(delay(high,1)+delay(low,1))/2)*(high-low)/vol, 7, 2)` | Money flow weighted by price change and bar range |
| 27 | `wma((close-delay(close,3))/delay(close,3)*100 + (close-delay(close,6))/delay(close,6)*100, 12)` | WMA of 3d and 6d return percentages |
| 56 | `rank(open-tsmin(open,12)) < rank(rank(corr(sum((high+low)/2,19), sum(mean(vol,40),19), 13))^5)` | Boolean: open drawdown vs quintupled price-volume correlation |
| 61 | `-1 * max(rank(decaylinear(delta(vwap,1),12)), rank(decaylinear(rank(corr(low,mean(vol,80),8)),17)))` | Max of VWAP change and low-volume correlation, both decay-weighted |
| 64 | `-1 * max(rank(decaylinear(corr(rank(vwap),rank(vol),4),4)), rank(decaylinear(max(corr(rank(close),rank(mean(vol,60)),4),13),14)))` | Max of two decay-weighted correlations |
| 77 | `min(rank(decaylinear((high+low)/2+high-(vwap+high),20)), rank(decaylinear(corr((high+low)/2,mean(vol,40),3),6)))` | Min of price position and price-volume correlation |
| 119 | `rank(decaylinear(corr(vwap,sum(mean(vol,5),26),5),7)) - rank(decaylinear(tsrank(min(corr(rank(open),rank(mean(vol,15)),21),9),7),8))` | Two decay-weighted VWAP correlation components |
| 138 | `(rank(decaylinear(delta(low*0.7+vwap*0.3,3),20)) - tsrank(decaylinear(tsrank(corr(tsrank(low,8),tsrank(mean(vol,60),17),5),19),16),7)) * -1` | Low/VWAP change vs nested volume correlation |

---

## Category 11: Complex / Multi-Component

Highly composite factors mixing multiple signals.

| # | Formula | Description |
|---|---------|-------------|
| 4 | Conditional: checks if 8d MA ± std vs 2d MA, then volume ratio | Price trend + volume confirmation filter |
| 30 | Fama-French 3-factor residual | Residual variance from Fama-French model (needs MKT, SMB, HML) |
| 49 | Down-direction / total-direction ratio (12d) | RSI-like directional balance |
| 50 | Net directional ratio (up - down, 12d) | Net buying/selling pressure |
| 51 | Up-direction / total-direction ratio (12d) | Upward directional dominance |
| 55 | Complex: 16×(directional_move)/normalized_range × max_range | Directional movement with intraday bias (20d sum) |
| 86 | Trend acceleration filter with 0.25 threshold | Detects trend inflection points |
| 143 | `close>delay(close,1) ? (close-delay)/delay*SELF : SELF` | Compounding return if up, else carry forward |
| 144 | `sumif(|return|/amount, 20, close<delay) / count(close<delay, 20)` | Average |return|/dollar-volume on down days |
| 146 | Smoothed return deviation / squared smoothed return | Information-ratio-like signal |
| 152 | Triple-smoothed return momentum (MACD-like) | Multi-period return smoothing |
| 157 | `min(rank(rank(log(tsmin(rank(rank(-1*rank(delta(close-1,5)))),2)))),5) + tsrank(delay(-1*ret,6),5)` | Nested ranks + log transform of 5d minimum + delayed return rank |
| 159 | Multi-period weighted RSI-like using close, low, high | 6/12/24d weighted directional balance |
| 164 | Smoothed (1/return) normalized by bar range | Inverse return intensity |
| 166 | `-20*(20-1)^1.5*sum(deviation,20)/((20-1)*(20-2)*sum(avg_ret^2,20)^1.5)` | Skewness of returns over 20d |
| 169 | Multi-period smoothed momentum (MACD variant) | MACD-like using 9d/12d/26d/10d smoothing |
| 173 | `3*sma(close,13,2)-2*sma(sma(close,13,2),13,2)+sma(sma(sma(log(close),13,2),13,2),13,2)` | Triple-smoothed close momentum (T3-like) |
| 176 | `corr(rank((close-tsmin(low,12))/(tsmax(high,12)-tsmin(low,12))), rank(vol), 6)` | Stochastic rank vs volume correlation |
| 180 | Volume-conditional: if above avg vol → momentum signal, else → negative vol | Volume-triggered momentum |
| 190 | `log(((count_above-1)*sum_sq_below) / (count_below*sum_sq_above))` | Log-ratio of above/below trend squared deviations |

---

## Summary by Category Count

| Category | Count | Key Examples |
|----------|-------|-------------|
| Volume-Price Relationship | 39 | #1, #11, #43, #84, #94 |
| Price Momentum / Trend | 23 | #14, #18, #20, #88, #106 |
| Mean Reversion / OB-OS | 28 | #23, #63, #79, #112, #162 |
| Volatility / Risk | 16 | #54, #78, #97, #100, #161 |
| VWAP-Based | 15 | #8, #13, #120, #124, #191 |
| Beta / Market Sensitivity | 5 | #30, #75, #149 |
| Decay Linear / Time-Weighted | 8 | #9, #27, #61, #119 |
| DMI / Directional Movement | 6 | #49, #69, #172 |
| Open / Gap / Intraday | 8 | #35, #107, #171, #187 |
| Complex / Multi-Component | 18 | #4, #143, #159, #166, #190 |

## Priority Picks for Our Strategy

Based on our current needs (pair trading, trend+multifactor), highest-signal factors to explore first:

1. **Momentum**: #14 (5d change), #18 (5d ratio), #20 (6d return), #88 (20d return), #106 (20d change)
2. **Mean Reversion**: #63 (6d RSI), #79 (12d RSI), #112 (12d directional balance), #128 (MFI-like)
3. **Volume-Price**: #11 (6d money flow), #43/#84 (OBV variants), #40 (up/down volume ratio)
4. **Volatility**: #78 (CCI), #97/#100 (volume volatility), #161/#175 (ATR)
5. **VWAP**: #120 (VWAP/close ratio), #124 (VWAP deviation)
6. **Trend**: #21/#116 (regression slope), #89 (MACD-like)
