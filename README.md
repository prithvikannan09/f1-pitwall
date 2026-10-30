# F1 Race Engineering Command Centre

A working build of Loriane Arielle Larevoir's three F1 portfolio projects plus her Mexico GP dashboard, in one Python project:

| Blueprint project | What you get here |
|---|---|
| 1. Strategy & Telemetry Engine (Python + SQL) | FastF1 → SQL database loader, 8 example SQL queries, tyre-wear model with fuel correction, pit-window optimiser |
| 2. Pit-Window Risk Simulator | Monte Carlo undercut simulator: Safety Car / VSC odds, pit-stop spread, slow stops, traffic on rejoin, track grip |
| 3. Command Centre (Streamlit) | One dashboard with 8 tabs: Speed Trap, Telemetry, Tyre Degradation, Undercut Calculator, Strategy Simulator, Weather, Race Pace, Database |
| Mexico GP dashboard | Its 4 tabs are inside the Command Centre, for any season and Grand Prix (Mexico 2024 is the default) |

## Run it (3 commands)

```bash
pip install -r requirements.txt
python -m f1analytics setup
streamlit run app.py
```

`setup` creates `data/f1.duckdb` and loads 2024 Mexico Practice 2, Qualifying and Race. Your browser opens the dashboard at http://localhost:8501.

On a Mac, do it inside a virtual environment (a private folder of Python packages) first:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
```

The first time you open a real session it takes up to a minute or two (the free data service limits how fast we can ask). After that it is saved in `fastf1_cache/` and opens in about a second.

## Live pit wall (Ferrari by default)

A second page, **Pit Wall**, follows a live race from F1's own free live-timing feed (the one the official app uses; no login needed for timing, gaps, tyres, race control and weather). For each car of the chosen team it shows:

- **Box / stay-out call** with the pit window, the tyre to fit, Plan A and Plan B, and where the car would rejoin (and who it would be stuck behind) if it boxed now.
- **Undercut threats:** live chance (from 3,000 simulated stops) of undercutting the car ahead, and of the car behind undercutting us. Teammates are not treated as threats.
- **Safety Car plan:** "box now under SC / VSC?" with the cheaper stop worked out, plus a double-stack warning when both cars would queue.
- **Tyre wear:** this stint's wear rate against the field on the same compound.
- **Team radio:** the clips F1 makes public, playable on the page, Ferrari first (toggle for everyone).
- **Track (from gaps):** every car placed around a circle by its time gap to the leader. An estimate: real GPS car positions are F1TV-only data since the 2025 Dutch GP.

### Race night (all times IST)

The Mexico City GP starts **01:30 IST Monday 2 Nov** (qualifying 02:30 IST Sunday 1 Nov).

1. **Before 01:15**, in Terminal 1: `cd ~/code/f1-analytics && source .venv/bin/activate && python -m f1analytics live record`
   You want: `feed status: {'connected': True}` and a `snapshot:` line naming the Mexico City Grand Prix.
2. In Terminal 2: `cd ~/code/f1-analytics && source .venv/bin/activate && streamlit run app.py`, then click **Pit Wall** in the left menu. Leave Mode on **Live**.
3. Keep Terminal 1 running for the whole race. If the Mac sleeps or Wi-Fi drops, the recorder reconnects by itself; lap history before the drop is kept.

Start the recorder **before** lights out: tyre-wear fits need the lap history from the start of the race.

### Test it any time

- `python -m f1analytics live check`: confirms the live feed answers.
- `python -m f1analytics live demo --seconds 3`: replays last Sunday's US GP into the Live pit wall, one lap every 3 s.
- Or switch the page to **Replay** and scrub through any 2023+ race lap by lap.

Checked against real races. 2025 Mexico: box calls for Leclerc (window laps 26–32, stopped lap 31, then no more stops) and Hamilton (laps 21–29 → stopped 23; laps 41–47 → stopped 47). 2026 US GP: Leclerc box call at lap 12–14, stopped lap 15.

**Limits:** pit loss starts as a track estimate and switches to the measured value after 4+ green-flag stops. Tyre wear is a straight-line model blended with defaults until enough laps are in. Car positions on track, DRS and pit-stop durations are paid F1TV data and not used. The live feed is unofficial and for personal use; if this becomes a paid product it needs a data licence.

### On your phone (hosted, Mac can be off)

The repo has a hosted entry point, `pitwall_app.py`, that runs the live recorder inside the app, so nothing needs to run on your laptop.

1. On your phone open **share.streamlit.io** → *Continue with GitHub* → sign in as `prithvikannan09` and allow access to private repos.
2. *Create app* → *Deploy from GitHub*: repository `prithvikannan09/f1-pitwall`, branch `main`, main file `pitwall_app.py`, pick an app URL (e.g. `hamilton-pitwall`). Under *Advanced settings* choose Python 3.12. Deploy (first build takes about 5 minutes).
3. In the app press *Share* (top right) and switch on **This app is public**, so anyone with the link can open it.
4. You want: "Ferrari Pit Wall" with "Live feed connected". Between sessions it shows the last session; during a session it switches by itself (practice view in FP1–FP3 and qualifying, race calls in the race).

Open the link **10–15 minutes before each session** so the app is awake and starts recording laps from the beginning (free hosted apps sleep after hours without visitors). Add `?driver=LEC` or `?team=McLaren` to the link to change the default focus.

**Wing and mode estimates:** real wing angles and engine/energy modes are private to the teams. The pit wall estimates the wing level from top speed against the field, and flags laps where straight-line speed jumps (tow or extra battery deployment) or drops (harvesting or lifting). Treat these as hints, not facts.

## Where the data comes from

Since 2025 the official F1 timing archive that FastF1 reads asks for an F1 account login (it answers "401 unauthorised" without one). So the app has four data modes:

- **Auto** (default): FastF1 if you have set an F1 login (see below), otherwise the free **OpenF1** API, otherwise sample data.
- **OpenF1** (free, no login, 2023 season onwards): laps, sectors, speed trap, tyres, pit stops, Safety Cars, weather and car telemetry. Checked against 2024 Mexico: Sainz pole 1:15.946 and Leclerc fastest race lap 1:18.336 match the official results.
- **FastF1** (2018 onwards, richer telemetry): needs your F1 account. Put it in your own terminal, never in a file you share: `export F1_USERNAME=you@example.com` and `export F1_PASSWORD=...`
- **Sample data**: a built-in generator with the same columns (20 drivers, 2024 calendar, tyre wear, fuel burn, pit stops, Safety Cars, telemetry). Every screen marks sample data with a ⚠️ line.

## Command line

```bash
python -m f1analytics load --year 2024 --gp Monza --sessions Q R     # store sessions
python -m f1analytics list                                             # what's stored
python -m f1analytics query                                            # list example queries
python -m f1analytics query 04_degradation_slope --show-sql            # run one on the latest session
python -m f1analytics refresh --year 2026                              # load every finished session not yet stored (OpenF1)
```

`refresh` is the after-race automation. It only uses real data (OpenF1 by default, `--source fastf1` if you have a login), logs to `logs/refresh.log`, and exits with an error code if any session failed. To run it every Monday at 9:30 IST on a Mac or Linux machine, add this with `crontab -e` (change the path):

```
CRON_TZ=Asia/Kolkata
30 9 * * 1 cd /path/to/f1-analytics && .venv/bin/python scripts/refresh_after_race.py >> logs/cron.log 2>&1
```

## The maths (all estimates are editable in the app)

| Item | Formula | Default |
|---|---|---|
| Fuel correction (race only) | corrected = lap time − k·F₀·(1 − (lap−1)/N) | F₀ = 105 kg (est., low/base/high 95/105/110), k = 0.033 s/kg (est., 0.030/0.033/0.037) |
| Tyre wear | per stint: corrected lap = α + β·tyre age, least squares, outliers beyond 3 robust σ dropped once | stints need 5+ clean laps |
| Stint cost | L·α + β·(L·a₀ + L(L−1)/2) | every 1- and 2-stop plan, 2+ compounds, stints ≥ 8 laps |
| Best one-stop lap | L₁ = (α₂ − α₁ + (β₂ − β₁)(a₀ − ½) + β₂·N) / (β₁ + β₂) | checked against brute force |
| Undercut | final gap = gap + (your pit loss − rival's) + your warm-up − Σ fresh-tyre gain − (rival warm-up − your tyre wear·k) + traffic | doc defaults give +1.85 s (fails) |
| Safety Car per lap | 1 − (1 − race chance)^(1/laps) | SC 50%, VSC 30% (est.); replaced by stored real history for that track when available |

## Fixes to the original blueprint code

1. `laps.groupby('Driver').pick_fastest()` does not exist; replaced with a proper per-driver maximum.
2. `pick_driver` is deprecated in FastF1 3.x; uses `pick_drivers`.
3. The undercut calculator ignored pit loss and the rival's own stop; now it counts both stops, both out-laps, extra laps and traffic.
4. Speed trap used only the fastest lap; now each driver's highest reading.
5. FastF1 sessions cannot be cached with `st.cache_data`; uses `st.cache_resource`.
6. `SERIAL`/`FLOAT` in the SQL replaced with sequences and `DOUBLE PRECISION`, so the same schema runs in DuckDB and PostgreSQL.

## Tests

```bash
pytest
```

80 tests, all offline, including a headless run of every dashboard tab.

## Credits

Project blueprints and Mexico GP dashboard design: Loriane Arielle Larevoir (IG @ariellelarevoir). Data: [OpenF1](https://openf1.org/) and [FastF1](https://docs.fastf1.dev/). Not affiliated with Formula 1.
