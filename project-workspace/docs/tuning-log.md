# Prompt Tuning Log

Experiment results and conclusions from `scripts/tune_prompt.py` runs.
Raw data: `data/tuning-results.jsonl`

## Experiment 1: Market Context Bias on Non-Index Comments

**Date:** 2026-02-12
**Hypothesis:** Market context injection (SPY/QQQ/IWM data) biases sentiment on comments about specific tickers that aren't related to broad market moves.

**Test:** Compare temp=0.3 with vs without market context on SLV comment (o50n9bi)
```
python scripts/tune_prompt.py o50n9bi --compare "temp=0.3" "temp=0.3,no-market-context"
```

**Comment:** "He gave himself some time (2/20). He was betting that the lack of volume due to the Chinese market being closed would provide higher volatility. I'm sure he is straddled with calls at this point."
**Post:** "16K gain on SLV puts in 30 minutes"

**Result:**
- With market context (SPY -1.54%, QQQ -2.03%, IWM -2.04%): **bearish** @ 0.7, SLV(bearish)
- Without market context: **bullish** @ 0.7, SLV(bullish)

**Analysis:** Market context alone flips the sentiment. The comment is observational — explaining someone else's SLV volatility play — and should probably be neutral regardless. The system prompt's MARKET CONTEXT section uses prescriptive language ("These are NOT predictive and should be classified as neutral") that creates a blanket bias on volatile days, even for comments discussing unrelated ticker-specific trades.

**Conclusion:** The market context guidance is too directive. It should provide market data as informational context and let the model judge per-comment relevance, rather than instructing a global shift toward neutral.

**Next:** Draft softened prompt language and test on:
1. This SLV comment (should stop flipping)
2. Comments that correctly moved to neutral (should stay neutral with softer language)
