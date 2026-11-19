# Scout — $0-extra-cost market research app (v2)

**Live dashboard:** https://laytongreenland-byte.github.io/scout-market1/

Scout is now a mobile-first, automated *research screener* — still **not** a stock-trading engine, fiduciary adviser or predictive AI model. It does not place trades or forecast reliable price targets.

## What is automatic

- **Hourly:** best-effort GitHub Actions checks public NZX announcements and Federal Reserve updates; Finnhub quotes for a configured **53-symbol** US large-cap stock/ETF universe, with each quote timestamp shown. This is a curated universe, **not all listed securities**.
- **Rotating fundamentals/news:** up to eight companies per run receive Finnhub metrics, company-related news, and issuer website identification; when all 48 equities have been visited the rotation repeats. The app shows how many have adequate current financial data. Cache updates are persisted in GitHub.
- **Research screen:** rule-based 0–100 ranking from trailing profit margin, return on equity, growth, trailing valuations, 52-week context and daily price moves. **INVESTIGATE means verify independently; not BUY.** Missing essential fields or stale quotes produce *INSUFFICIENT DATA*.
- **Weekly shortlist:** up to five investigated/watchlist candidates, refreshed at the beginning of the NZ research week. Strong cases can be absent. Each item includes recorded risks, prices/as-of and external source references. Diversified ETFs are presented separately as long-term instruments to research.
- **Paper-only record:** reference prices for flagged companies and subsequent 7-/30-day price changes when observed. This is NOT executable profit or a validated backtest; fees, FX, spreads, dividends and taxes are excluded.
- **Very selective alerts:** an issuer-originated fresh announcement containing a specific positive catalyst, plus strong screened financial metrics and a recent quote, may create a GitHub Issue labelled *urgent research*. It is **not** a buy instruction. A Monday-evening NZ-time GitHub Issue contains the weekly shortlist. The script deduplicates issue titles. Automated Issues are best effort and can fail if Issues or permissions are unavailable.

## Get notifications on your phone (no subscription)

In your public GitHub repository select **Watch → All Activity**. Enable GitHub mobile push notifications or email notification preferences on your device. GitHub does not guarantee instant notification delivery; the scanner runs at most hourly and GitHub scheduled jobs can be delayed or skipped. Urgent alerts only appear when the strict evidence conditions are met, and many weeks can legitimately have none.

GitHub Issues: https://github.com/laytongreenland-byte/scout-market1/issues

## Free integrations

**Already configured:** GitHub Pages, GitHub Actions and the free `FINNHUB_API_KEY` stored as a private repository Actions secret.

**Optional for SEC EDGAR direct filings:** add private GitHub Actions secret `SEC_USER_AGENT` with an application name and **real, reachable contact email**. SEC official APIs require a descriptive user-agent. No reason to publish your contact email in code. Without it, Scout explicitly marks the SEC feed unavailable and still uses NZX/Fed/Finnhub sources.

All API secrets are read server-side by GitHub Actions and are never placed in the website, committed JSON or JavaScript. Your app's budget settings are stored only in your browser.

## AI integration & limitations

Scout's automated scores are an **explainable rules-based screen**, not an LLM. No paid AI service or cloud model API is used. The separately scheduled **ChatGPT** daily, weekly, and hourly research automations can use its published data to perform deeper qualitative analysis and notify you in ChatGPT, but their answers are **not automatically written back into this public site**. This is deliberate, so there's no invented AI judgment inside an unattended app.

The price feed and free API access have provider limits, latency and usage rights. This app is for non-commercial personal research, not redistribution or real-time order routing. Some securities may have missing quotes or metrics; this is visible in the dashboard. All links and timestamps should be verified independently before any investment decision. New Zealand overseas-investment taxes, broker fees, exchange rates and your cash-reserve needs still matter even for small balances.

## Source/test files

- `scanner.py`: RSS, issuer filings, quote retrieval, source integrity
- `research.py`: financial screener, weekly shortlist, possible urgent catalyst checks and paper observations
- `scripts/post_reports.py`: best-effort GitHub Issue notifications, with title deduplication
- `config/watchlist.json`: set the tracked instruments (limit 65)
- `.github/workflows/scan.yml`: scheduled collector, snapshot saving, optional alert issue creation, GitHub Pages publishing
- `data/latest.json`, `data/research_cache.json`, `data/history.json`, `data/weekly.json`: public evidence-derived output (not user financial data)
- `tests/`: stdlib offline tests (`python -m unittest discover -s tests -v`)

Change tracked symbols only via `config/watchlist.json`. For an independent offline sanity check, run `SCOUT_OFFLINE=1 python scanner.py`; the application will mark unavailable sources rather than fabricating prices or recommendations.

## Weekly evidence-based machine learning (v3)

- `learner.py` checks for a new research week after **Monday 19:00 NZ time**, using the existing hourly GitHub Actions job (best effort, not guaranteed to run on time). All code and training run with the Python standard library, so there are no added hosting, paid API, or model fees.
- The hourly scanner archives one actual provider-reported USD quote per NY trading session and **freezes** up to one financial feature snapshot per stock each NZ week, including the matching SPY benchmark quote. It never uses current company fundamentals to invent past predictions.
- After **30 calendar days**, Scout looks for a dated, same-session stock and SPY quote within the next 10 days. If either is missing, it marks the outcome pending rather than guessing. Label: did the stock outperform SPY by more than one percentage point, gross, over the measured period? **No single-week result is a training set.**
- The model is a small, deterministic, L2-regularised **logistic regression** trained on those frozen observations; no paid AI service, GPU or API token is required. Before enabling it, Scout requires at least **six matured training weeks, two later held-out weeks, 120 training observations, 40 holdout observations and 20 unique stocks**. It must improve the top 20% average excess return versus the original rules by at least **0.5 percentage points** and outperform SPY during the chronological holdout.
- If evidence is weak or deteriorates, it falls back to the transparent original financial rules. A model that does pass can only supply **20% of a research ranking**, never change company risk gates, create buy signals, or trigger trades.
- The Research screen shows how many signals and matured observations exist, whether the model is validated, and the *actual held-out results*. This is hypothesis testing with a very small, correlated sample, **not proof of outperformance**; fees, FX, spreads, taxes, dividends and data gaps are not included. Expect learning to remain disabled for several months while the dataset builds.
- Training output (`data/ml_report.json`, `data/ml_model.json`) and frozen research observations (`data/history.json`) are public because the repository is public. They do not contain portfolio holdings, bank details or account credentials. API keys remain GitHub Secrets.
