# Scout v4 — free, evidence-first investment research

## Integrated NZX market research (23 November 2026)

The **main Scout UI now includes New Zealand** in its Overview, Research, Weekly Watch,
Market Coverage, Signals and Results views. NZX data is **NZD end-of-day**, never USD.
The original Finnhub US scanner, SPY benchmark, US entry levels, US paper journal and
disabled US ML model remain unchanged. New NZX modules are isolated:
`nzx_research.py`, `nzx.js`, `data/nzx_research.json`, and
`data/nzx_history.json`.

- **Discovery:** 128 NZX companies from an authenticated NZXplorer company directory,
  plus 33 Smart NZX-listed ETFs from a separately dated issuer-supported catalogue.
  Neither directory proves a particular security is tradeable in Sharesies.
- **Pricing:** NZXplorer accepts verified NZD closing prices for both a company (AIR)
  and an ETF (FNZ). `apac_data.py` checks up to 40 symbols per local NZ trading day,
  within the provider's account rate limit. Prices are retained only while fresh,
  with dated 1-day / 5-session movements when comparable provider observations exist.
- **Research:** NZX companies and ETF funds are searchable in the main Research and
  Watchlist views, with source links and explicit data-quality labels. The weekly NZX
  watch notes and a short NZX core ETF research list are *not* ranked US buy picks.
  Funds are never assessed with a single-company P/E model.
- **Alerts:** a verified unusually large daily NZD close movement can create a
  research-only NZX alert, not a trade instruction. A deduplicated NZX weekly
  watch notification can be posted to GitHub Issues, with delivery depending on
  the repository's Watch/notification settings.
- **Forward-only accountability:** a separate NZD watch journal freezes dated
  original observations; after sufficient *subsequent* exchange-session observations
  it can show 7/30-day price-only changes. It never backfills buying decisions,
  invents realised profits, or compares NZD movements to the USD SPY benchmark.
- **Restricted financial features:** the current NZX finance screen is explicitly
  **not scored** (zero issuer valuations), with no automated NZD buy/sell targets
  until dependable, appropriately licensed financial inputs and a validated
  sector-aware methodology are available. NZXplorer terms expressly prohibit
  training machine learning on its data without written authorisation. The
  existing US model is unaffected. Do not mislabel price discovery as a
  fundamental investment recommendation.

Provider and market-data permission matters: NZXplorer's terms include
restrictions on caching, redistribution, derivative use and model training.
See https://nzxplorer.co.nz/terms . Before publicly redistributing more
provider data or using it for ML, obtain the necessary written rights.
The current repository is public, so avoid committing private API keys,
personal portfolios or any data not permitted for redistribution.



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

## Scenario entry / exit research (v5)

Scout calculates **illustrative USD price zones** from fresh Finnhub quotes, published trailing P/E and growth ratios, profitability, industry and observed 52-week range. This is **not** an analyst consensus price target, an intrinsically valued company, a trading recommendation, a stop-loss, or machine-learned return forecast.

The method uses a capped, discounted past-growth assumption for a hypothetical next-12-month earnings proxy; an explicit scenario P/E from revenue-growth brackets (12–23×); a 22% valuation haircut; and an entry ceiling capped at the lower half of the observed 52-week trading range. It shows a base-case **exit review** and higher bull-case **profit-taking review** level, plus a bear-case downside reference. This model is heuristic; it is **not fitted or shown to be profitable** and can miss major changes to business outlook, stock splits, and accounting restatements.

- **ENTRY CANDIDATE** is shown only if the company's original status is INVESTIGATE, financial score ≥80, the quote is below the illustrative entry ceiling, and price is not below the bear-case warning band. You still must independently verify company filings, valuation, liquidity, portfolio suitability, fees, tax and news.
- **WAIT FOR ENTRY**, **ABOVE BASE CASE**, **POSSIBLE VALUE TRAP**, and **NO RELIABLE PRICE RANGE** explicitly mean no purchase trigger. Financial firms, insurers, banks, REITs, utilities, energy and biotech are excluded from simplistic P/E-based target levels; their valuation methods differ.
- Entry and exit levels refresh from each research scan, not just the frozen weekly shortlist. The weekly list refreshes live pricing but retains its original weekly research thesis. Missing/stale quotes and missing metrics suppress scenario price levels rather than inventing numbers.
- These scenarios are intentionally not integrated with automated buying, and they do not train the ML algorithm or count as investment-return evidence. Trading costs (including FX, fees, spreads, NZ tax and dividends) are not reflected in the calculated targets.


## Scout Compass (November 2026)

**Distinctive purpose:** a decision-first dashboard for a small New Zealand investor, not a Bloomberg clone, brokerage account or high-frequency trading service. The first screen explains whether any candidate passes the *financial quality* AND *illustrative price* gates, including a genuinely useful **no entry** result. An NZD small-trade estimate exposes hypothetical round-trip brokerage and FX fee drag. Filters let users find a symbol, see the company's plain-language verdict, valuation assumptions and primary evidence.

**Coverage:** Curated 225 US-listed equities (including some global company ADRs) and 64 diversified/sector ETFs, 289 unique symbol identifiers, across multiple sectors. These are **not** the whole US stock market, the whole global market or an NZX price feed. Valid price quotes are retrieved by Finnhub per symbol; about 12 company financial metrics/news records are refreshed by rotation per hourly scan. First-time financial coverage therefore takes multiple runs (and any provider refusal slows it). ETF quotes are **not** scored as company stocks with P/E/ROE rules. Frontend counts clearly distinguish configured tickers, successfully fetched quotes and companies with sufficient current financial evidence. If a ticker becomes invalid or unavailable, no fake price or score should appear.

**Interpretation:** Scout displays transparent research classifications and conditional price *scenarios*, not real analyst targets or calibrated investment predictions. It does not calculate NZD share costs without a live USD/NZD conversion rate, connect to a broker, buy/sell automatically, know investor holdings, or claim measured excess returns before outcomes mature.

## Scout Simple Answer + wider S&P 500 discovery

**Default experience:** The overview now starts with one clear view: whether a company is an `ENTRY CANDIDATE` (research only), why it is attractive, the latest quote, an indicative maximum entry price, an illustrative exit-review price and a downside reference. If nothing passes, Scout says WAIT. Older research panels are hidden in an expandable section. All detailed market data and evidence remain in the Research tab.

**Avoid false buy/sell certainty:** These prices are *illustrative scenario outputs* from the original rules. They are not a trained model prediction, professional financial advice, or evidence of a winning trade system. No candidate is promoted without the original quality gate and a recent quote. Broad-market ETF alternatives, trading costs and FX must still be considered.

**Larger discovery:** In addition to 289 curated US-listed assets, the hourly scanner tries to fetch a third-party, community-maintained S&P 500 constituent list from `datasets/s-and-p-500-companies`. This adds several hundred large US stocks without requiring manual ticker entry. It verifies the CSV schema and size, excludes known obsolete symbols, deduplicates tickers and caps total monitored symbols at 720 to avoid unbounded external API requests. If the constituent list is unavailable, the 289 curated symbols remain the fallback. A *successful quote* is not a financially screened company. Finnhub request limits, quote staleness, and the 22-minute GitHub Actions job time cap constrain how wide each hourly scan can be. Avoid asserting that all US, NZ or global equities are covered. The constituent dataset is not an official index license and may lag changes.

**Local-server option, not installed:** The older Xeon/GTX 1060 PC can later run Python collectors, a market-history database, CPU-based backtesting and a small local explanation model while the GitHub Pages app stays accessible on mobile. Check licence terms before republishing third-party market data, and do not expose an unauthenticated home server to the internet or put private model prompts/positions into the public repository. Local compute does not bypass market-data subscription limits or establish predictive ability.

## Results tab: forward-only accountability (paper trading)

Scout now freezes new weekly ticker/verdict opinions in `data/history.json` as `decisions`, recording original signal, dated quote, business reasons, main risk, financial score, USD buy ceiling and sell-review level. A different verdict during the same week makes a separate record; unchanged verdicts do not retroactively overwrite original levels. Original unpriced research flags remain intact and are **never backfilled** with today's pricing estimates. This journaling is independent of the existing ML weekly `episodes` and 7/30-day `calls` datasets.

A paper position can only open on a **subsequent NY market-session closing observation** at or below the frozen buy ceiling, within 14 calendar days, with same-session SPY information. No inferred intraday fills or purchases at earlier quotes. If the sell-review level is seen at a subsequent daily close before the 30-day holding horizon, the position closes then; otherwise it closes at the first observed daily close >=30 days after entry (within a 10-day data window). Results are sealed once verifiable; closed gains and **losses** both count, separately from skipped opinions and entry prices never reached. A 1% illustrative round-trip friction deduction is applied to paper trade returns and compared with the same-session SPY buy-and-hold price return. This **excludes real trading costs, bid–ask spreads, dividends, split adjustments, FX and NZ tax**. Abnormal unadjusted price changes remain unverified.

Scout shows wins, losses and original predictions in the Results tab. A skipped company that later rose is visibly reported as an observation, not silently scored as a successful non-purchase. Unverifiable cases and zero mature outcomes remain explicit, not invented successes. The public dashboard shows recent records and summary totals; the git-tracked `data/history.json` preserves frozen long-term records. This is a **hypothetical back-office accountability log, not actual order execution or a validated profit-making strategy**.

## Exchange-wide Sharesies-targeted discovery — safe Phase 1

The app now has a **separate exchange listing catalogue** under Market Coverage. It uses two official NasdaqTrader downloadable symbol directories (Nasdaq and other US exchanges) to discover thousands of US-exchange-listed securities. A bounded, standalone `market_catalog.py` validates entire directory schemas and rejects truncated/malformed feeds. It runs at most once a week on normal scans, and if refresh fails it preserves the last fully valid snapshot; **the quote scanner and learning/Results history remain unchanged**. The catalogue is saved as `data/market_catalog.json`, independently of `data/latest.json` and the immutable paper-trade journal.

**Important: This is not the full Sharesies catalogue.** Neither a public documented Sharesies export API nor a provider-authorised live stock list has been verified. A listed security may not be tradeable in the user's Sharesies account. Australian and NZ exchanges are explicitly marked **NOT CONNECTED** until reliable permitted directory and market data sources are available. Likewise a discovered US listing is NOT a freshly quoted, financially screened or recommended stock. Stock prices and ratios are still limited by Finnhub's data and API quotas. We do not crawl private or undocumented Sharesies endpoints, use account credentials, submit orders, or infer prices from symbol names. International access, market-data licences, timestamp guarantees, foreign-exchange fees and any resale/republication limitations still apply.

The UX keeps a simple Scout buy/wait decision; under Market Coverage users can search the independently discovered US listing metadata and see the actual counts of discovered securities versus successful price quotes and financially screened companies. **Additional market coverage will be staged and validated before it is allowed to affect Scout recommendations.**

Testing: `python -m unittest discover -s tests -v`. To refresh the catalogue separately: `python market_catalog.py`, or `SCOUT_DISCOVERY_FORCE=1 python market_catalog.py` to force; `SCOUT_OFFLINE=1` prevents network traffic. No changes are needed to broker credentials, historical signal records or existing trading rules.


## ASX / NZX exchange directory integration (November 2026)

- **ASX directory**: public ASX listed-companies CSV (`https://www.asx.com.au/asx/research/ASXListedCompanies.csv`), validated for expected columns and roughly 900–4,000 company rows. No key required. Source availability and reuse permissions must be respected; this is a discovery catalogue, **not** an approved market-data redistribution licence.
- **NZX directory**: optional NZXplorer v1 `GET /api/v1/companies`. NZXplorer documents a free API tier (10 requests/minute, 250/day). Create a personal API key at `https://nzxplorer.co.nz/settings`, then store it ONLY in **GitHub → Settings → Secrets and variables → Actions → New repository secret** under the exact name `NZXPLORER_API_KEY`. The source must return a validated, sufficiently complete company list; partial/changed responses are rejected rather than presented as complete. Do not paste the secret into this public repository.
- **Refresh**: The separate `market_catalog.py` step is run within the existing GitHub Actions scanner; catalogue refresh is at most weekly unless `SCOUT_DISCOVERY_FORCE=1` is set. A failed APAC directory fetch retains the previously validated regional list and marks it stale. The US scanner continues regardless.
- **Scope**: This adds searchable ASX/NZX *company names and tickers* only where the source succeeds. It **does not** connect APAC prices, valuations, earnings, buy/sell recommendations, broker eligibility or paper-trade labels. A separate licensed/authorised EOD or delayed-price source and robust historical adjustments are still required for those features.
- **Provider alternatives investigated**: SeaBee Market Data documents an authenticated ASX company directory and OHLCV endpoint; EODHD publishes ASX/NZX market APIs and a free **20 calls/day** testing tier, insufficient for complete daily exchange-wide coverage. Review each provider's terms and data rights before adding automated published prices.


## APAC end-of-day research (read-only)

`apac_data.py` runs after directory discovery, separately from the US recommendation scanner. A bounded daily rotation requests up to 10 NZX historical closing-price responses via NZXplorer (`NZXPLORER_API_KEY`) and up to 10 ASX responses from SeaBee (`SEABEE_API_KEY`, optional). Valid closes must be NZD or AUD, have a parseable date within the past seven calendar days, and pass conservative numeric bounds. Unusable data remains missing. The research quotes are stored in `data/apac.json`, are marked EOD, and are displayed alongside matching directory tickers. They do not affect buy/wait decisions, Results, ML validation or history. A full ASX price feed requires the user's own SeaBee key and terms-compliant permitted usage. Public access to the repository means any provider's redistribution restrictions must be checked before enabling public quote publication.

The first run may expose provider-response incompatibilities that require a separate patch; never treat the existence of the data collector as proof of current, complete APAC market coverage. Company financial-statement integration and NZD cross-market paper trading remain outstanding.


## Reliability and failure isolation (November 2026)

- GitHub Pages is published by the repository's existing **branch-based Pages build and deployment** workflow. The hourly research scanner **does not upload or deploy a second Pages artifact**. This prevents competing deployments and the observed intermittent missing-artifact failure. The site lives at the repository root, with `.nojekyll`.
- The scanner commits validated JSON snapshots only. Existing `history.json`, `ml_model.json` and paper-trading results are not reset by provider additions; a failed optional feed cannot produce fabricated recommendations.
- Research runs are not automatically cancelled by newly queued research jobs. Scheduled Github Actions may still be delayed or skipped by GitHub; there is no real-time execution guarantee.
- NZXplorer is account-limited to 10 requests per minute and 250 per day. Directory and price code intentionally pace authenticated requests and retry unavailable directory discovery at most daily. Failed provider authorization is reported as an HTTP status, never bypassed. A failed connection is **not** evidence that the key or subscription permits the requested data.
- StocksDeepDive has returned HTTP 401 on its ASX scan endpoints. Scout records `ACCESS_DENIED`, stops that day's further ASX endpoint probes, continues independent US research when available, and never converts third-party scores to buy/sell signals.
- When troubleshooting, check GitHub Actions **Refresh Scout data and site** for collection, **pages build and deployment** for publication, and the source-status fields of `data/market_catalog.json`, `data/apac.json`, and `data/stocksdeepdive.json`. A green job step does not imply a provider returned valid records.


## Sharesies-aligned market coverage — operational notes (23 November 2026)

- Sharesies itself advertises **5,000+ US, 1,700+ Australian and 120+ NZ company shares**, and **4,500+ ETFs** across the regions. References: https://www.sharesies.nz/investments/shares and https://www.sharesies.nz/investments/exchange-traded-funds . These are estimates published by Sharesies, **not an export of its tradable instruments**.
- The independent catalogue contained **13,237 US and 2,058 ASX-listed securities** in the 22 Nov snapshot; that catalogue intentionally includes securities outside Sharesies and does **not** establish actual broker eligibility.
- The original US quote scanner, financial screening, history journal, model and tests remain separate from `market_catalog.py`, `apac_data.py`, and `market.js`. Regional prices are research-only and never become US buy/wait or paper-trading records.
- An NZX directory provider returned HTTP 500 on paginated calls. The independent directory collector now tries the documented single list endpoint first, then bounded pagination, validating **80–350 unique symbols**. Previously validated market lists are preserved if the provider fails. Its next scheduled scan will attempt the new strategy.
- NZX end-of-day research samples up to **25 ticker histories daily** by default (hard upper limit 25), with explicit market-local trading dates, 7-calendar-day freshness checks and an error stop on authorization/rate-limit responses. The limit may be adjusted via `SCOUT_NZX_PRICE_DAILY_LIMIT` (1–25) within the provider's actual entitlements. It does not change the US scanner.
- ASX company discovery is functioning from the official directory, but **ASX price research still requires an authorised SeaBee provider key**, stored privately as GitHub Actions secret `SEABEE_API_KEY`. SeaBee describes an API-key-only service at https://marketdata.seabee.me/ ; there is **no implied public or free right to bulk redistribute its prices**. The separate ASX EOD collector stays inactive without a key. Its default price requests are 10/day (configurable up to 30 via `SCOUT_ASX_PRICE_DAILY_LIMIT`, subject to the account's actual quota).
- Market prices require source permissions. NZX expressly requires a distribution licence for redistribution to end users, see https://www.nzx.com/services/products-tools/data-connectivity/nzx-market-data/data-licensing . Do not publish NZX/ASX bulk prices from a non-redistribution subscription. Confirm permitted personal and public display use with providers before enabling regional publication.
- The unpriced directory, market-news feeds, US scanner and paper trading should **never** report APAC data as a validated price, company valuation, confirmed Sharesies availability, or a verified winning trade.


## Live NZX paper-trade research — 23 November 2026

NZX is now a parallel regional research and **educational forward-only paper-trade** module, distinct from the pre-existing US/SPY scanner, machine learning and USD paper journal. Main UI panels show NZX company financial screens, NZX-linked announcements, a weekly shortlist, validated NZD end-of-day prices, monitored large price movements, and an independent results ledger.

- `nzx_fundamentals.py`: bounded sample of issuer-reported accounting ratios and period labels from the existing authenticated NZXplorer account; by default only four company metric lookups per day and never part of US model training. A retrieved timestamp does not prove the associated financial period is current. Financial metrics can be imperfect, and issuer reports should be checked directly via the linked NZX issuer page.
- `nzx_paper.py`: an explicit, versioned, explainable **hypothetical exercise**. Candidate screening checks the reported financial year, profit margin, ROE, P/E, growth and debt together with issuer-linked disclosure evidence. Banks, insurers, REITs, biotechnology and funds are excluded from the basic generic P/E screen. No missing metrics or loss-making company is automatically praised.
- Freeze up to **four new NZX experimental trade ideas per calendar week** only if the financial and evidence gates pass. Paper entry is allowed only at a **later observed** closing price up to 101% of the frozen reference price, within 14 calendar days. No intraday or historically inferred fills. Cap a paper trade at an illustrative NZ$100, using whole units; observe a +12% profit-review level or close on a later verified closing price around 30 days after the paper entry.
- Record **open, closed, missed, unverified, gain and loss** outcomes with illustrative 1%-each-way fees, alongside original dated explanations and unchanged entry thresholds. Exclude dividends, NZ tax, spread, market liquidity, corporate-action adjustments and current Sharesies transaction pricing. We cannot assume that every NZX listing can actually be purchased on Sharesies. No NZD-vs-SPY performance comparisons or fictitious after-tax return measurements.
- **Paper-trading success is not machine learning.** The ML engine remains limited to its original, separate USD history because NZXplorer terms prohibit ML training on their data without written permission. Existing USD paper decisions and historical records remain unchanged.
- The first frozen NZX paper proposal may persist even if a later, more conservative version of the scoring method rejects that company. That's intentional: original predictions, good or bad, must remain auditable rather than being quietly rewritten.
- Read `data/nzx_research.json`, `data/nzx_history.json`, and the latest `data/regional_integrity.json` for coverage, original experiments and automated test status. Nothing in the NZX ledger places a real order.
- **Important provider licensing:** A public GitHub Pages site is different from personal private analysis. NZX and NZXplorer restrict redistribution and some uses of financial datasets. The account owner should obtain appropriate public-display/derived-data permission before treating the current prototype as a production investment publication, greatly expanding the stored provider dataset, or opening it to third-party users. Documentation: https://nzxplorer.co.nz/terms and https://www.nzx.com/services/products-tools/data-connectivity/nzx-market-data/data-licensing .
