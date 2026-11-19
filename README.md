# Scout v4 — free, evidence-first investment research

**Mobile app:** https://laytongreenland-byte.github.io/scout-market1/

Scout is a **research screener** for a small NZ investor, not a financial adviser, an autonomous AI investment analyst, a live exchange terminal, or a broker. **Nothing on this site is a buy/sell order or a demonstrated source of excess investment returns.** It never trades, holds login credentials, or requests bank access.

## What the live system actually does

- Approximately hourly, a **best-effort** GitHub Actions job collects 53 configured US share/ETF quotes (Finnhub free tier), public NZX announcements (third-party RSS), US Federal Reserve releases, and—**only when configured**—SEC issuer filings.
- Research for eight companies per run fetches provider-reported ratios, company profiles, and news. No longer attaches obviously unrelated headlines to the wrong company. The data feed may still be incomplete or delayed.
- Uses conservative, **explainable, rules-based** screening to make a shortlist, limiting concentration to at most two companies per known industry. **INVESTIGATE** is a research label, not a purchase recommendation or an estimate of intrinsic value.
- Saves one immutable weekly financial-feature observation per eligible company, together with a same-session SPY price, and one quote for each NY market session. Historical feature vectors are never backfilled using future information.
- On eligible 30-day outcomes, measures top-quintile **gross USD price** excess over SPY, by distinct week, **not** an invented portfolio return. The app shows sample size, source health, outstanding data gaps, and whether the evidence is still insufficient.
- Opens GitHub Issues for rare issuer-source catalysts and a Monday research shortlist (best effort, assuming GitHub Issues/notifications are enabled). Neither GitHub Issues nor ChatGPT notifications guarantee real-time alerts.
- Provides a **small-trade cost estimator** using editable NZD amount, brokerage fee percentage and FX conversion rate. Its default percentages are *illustrations*, not current broker pricing; dividends, spreads, FX market movements and taxes are not included in backtests.

## Machine learning: strict, not magical

The weekly learning engine is small **L2-regularised logistic regression**, using original frozen financial scores, valuation, growth, leverage, price context, and *explicit missing-data flags*. It is **not** an LLM and cannot conduct qualitative diligence on company strategy, governance or contracts.

- The target is price outperformance over SPY after about 30 days (a **1% illustrative round-trip friction penalty**, not actual execution costs). Free data are not guaranteed split/dividend-adjusted; extreme price discontinuities are excluded until a reliable corporate-action source can validate them.
- It requires **at least 52 matured weekly cohorts**, including six **separate walk-forward validation weeks** spaced five weeks apart. The preceding six weeks are purged from the training set, and each training example's 30-day result must have become knowable *before* the validation week.
- Each test week needs at least 20 companies. Earlier training needs at least 250 examples covering at least 20 symbols, and both positive and negative outcomes. Test performance must be positive in at least five of six weeks, exceed original financial rules by at least one percentage point on average, and clear the net-of-illustrative-friction SPY gate.
- A passing model can influence **at most 10% of research ranking**; it cannot override risk/quality gates, make buy decisions, or trade. Failed validation deactivates it. Even a passing result is **experimental, not proof of an edge**, because the selected companies are correlated and validating many models introduces selection bias.
- The learning system **will likely need over a year** of honest forward observations before any model influence can be considered. Historic financial data cannot safely be reconstructed from today's reported fundamentals.

## What is still not solved

1. **No full market coverage:** the 53 liquid US names are a curated universe. NZX announcements are monitored, **not NZ share prices, valuation, or reliable NZ-stock recommendations**.
2. **No issuer-specific fair value calculation or complete earnings model.** Accounting ratios can mean different things for banks, insurers, REITs and technology companies. Industry labels help concentration but do not fix sector scoring biases.
3. **No validated after-tax NZD profit history.** Free quote history is not guaranteed dividend/split adjusted. Results exclude realistic bid–ask spread, tax, financing and currency changes. A small trade may be uneconomic even when its headline price increases.
4. **No automatic intelligent qualitative analysis:** the user's scheduled ChatGPT research tasks remain separate from Scout and are not automatically written back to this static website. No free LLM API is silently assumed.
5. **No guaranteed instant notifications or zero downtime:** GitHub Actions may be delayed/skipped and free API limits may change. SEC EDGAR needs a descriptive `SEC_USER_AGENT` environment secret identifying a real contact; without it Scout explicitly reports unavailable.
6. **No guarantee of compliance with every provider's redistribution terms:** verify the free provider's applicable terms for public price displays. This is non-commercial research, not resale of live market data.

## Operational setup

GitHub repo: https://github.com/laytongreenland-byte/scout-market1

- GitHub Pages website and hourly GitHub Actions workflow use public repository free-tier services (subject to applicable limits).
- The free `FINNHUB_API_KEY` must be stored in **GitHub Actions Secrets**; do not put keys, private portfolios or personal details into public project files. User credentials are never required by Scout.
- Optional: store `SEC_USER_AGENT` as `Scout Research <reachable-contact-email>` in a private GitHub Actions secret if using official SEC submissions. Do not place your email in public code.
- To receive GitHub Issue notifications, watch the repository and enable the desired mobile/email notifications. The Issues are **not** purchase advice.
- To examine a failed job: **GitHub → Actions → Refresh Scout data and site → latest run → logs**. Every feed's success/error and last check time is also displayed in **Scout → Setup**.
- Budget and fee illustrations live in your *browser's local storage*, not in GitHub or the public dataset.

## Run tests locally

```sh
python -m unittest discover -s tests -v
SCOUT_OFFLINE=1 python scanner.py
```

The offline test intentionally reports missing sources and never fabricates market information. Files: `scanner.py` (collector), `research.py` (screening), `ml_engine.py` (purged forward validation), `learner.py` (weekly review), `scripts/post_reports.py` (optional Issues), `app.js` (mobile UI), and `tests/` (offline checks).
