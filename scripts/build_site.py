#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
build_site.py

Fetches NFL scores from ESPN, computes each owner's combined team record,
and writes a static, interactive site into docs/ (GitHub Pages source).

Run manually:
    python3 scripts/build_site.py

Edit MATCHUPS below whenever rosters change (new draft, trade, etc).
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode

import requests

# --------------------------
# Config: season + matchups (edit this every draft)
# --------------------------

SEASON = 2026

MATCHUPS = [
    {
        "slug": "owen-vs-jamie",
        "owner_left": "Owen",
        "owner_right": "Jamie",
        "teams_left": ["SEA", "BAL", "PHI", "LAC", "NE", "CIN", "SF"],
        "teams_right": ["LAR", "BUF", "DET", "HOU", "DEN", "DAL", "JAX"],
    },
    {
        "slug": "harry-vs-jamie",
        "owner_left": "Harry",
        "owner_right": "Jamie",
        "teams_left": ["DET", "DEN", "SEA", "HOU", "DAL", "JAX", "SF"],
        "teams_right": ["LAR", "BUF", "BAL", "LAC", "NE", "KC", "PHI"],
    },
]

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# --------------------------
# Team aliases & normalization
# --------------------------

ALIASES: Dict[str, Iterable[str]] = {
    "ARI": ["ARI", "Arizona", "Arizona Cardinals", "Cardinals"],
    "LAR": ["LAR", "LA Rams", "Los Angeles Rams", "Rams", "STL", "St. Louis Rams", "St Louis Rams"],
    "SEA": ["SEA", "Seattle", "Seattle Seahawks", "Seahawks"],
    "SF":  ["SF", "SFO", "San Francisco", "San Francisco 49ers", "49ers", "Niners"],
    "ATL": ["ATL", "Atlanta", "Atlanta Falcons", "Falcons"],
    "CAR": ["CAR", "Carolina", "Carolina Panthers", "Panthers"],
    "NO":  ["NO", "NOS", "New Orleans", "New Orleans Saints", "Saints"],
    "TB":  ["TB", "TBB", "Tampa Bay", "Tampa Bay Buccaneers", "Buccaneers", "Bucs"],
    "CHI": ["CHI", "Chicago", "Chicago Bears", "Bears"],
    "DET": ["DET", "Detroit Lions", "Lions"],
    "GB":  ["GB", "Green Bay", "Green Bay Packers", "Packers"],
    "MIN": ["MIN", "Minnesota", "Minnesota Vikings", "Vikings"],
    "DAL": ["DAL", "Dallas", "Dallas Cowboys", "Cowboys"],
    "NYG": ["NYG", "New York Giants", "Giants"],
    "PHI": ["PHI", "Philadelphia", "Philadelphia Eagles", "Eagles"],
    "WAS": ["WAS", "WSH", "Washington", "Washington Commanders", "Commanders", "WFT", "Washington Football Team"],
    "DEN": ["DEN", "Denver", "Denver Broncos", "Broncos"],
    "KC":  ["KC", "KAN", "Kansas City", "Kansas City Chiefs", "Chiefs"],
    "LAC": ["LAC", "LA Chargers", "Los Angeles Chargers", "Chargers", "SD", "SDG", "San Diego Chargers"],
    "LV":  ["LV", "Las Vegas", "Las Vegas Raiders", "Raiders", "OAK", "Oakland Raiders", "LA Raiders", "Los Angeles Raiders"],
    "HOU": ["HOU", "Houston", "Houston Texans", "Texans"],
    "IND": ["IND", "Indianapolis", "Indianapolis Colts", "Colts"],
    "JAX": ["JAX", "JAC", "Jacksonville", "Jacksonville Jaguars", "Jaguars"],
    "TEN": ["TEN", "Tennessee", "Tennessee Titans", "Titans", "Houston Oilers", "Oilers"],
    "BAL": ["BAL", "Baltimore", "Baltimore Ravens", "Ravens"],
    "CIN": ["CIN", "Cincinnati", "Cincinnati Bengals", "Bengals"],
    "CLE": ["CLE", "Cleveland", "Cleveland Browns", "Browns"],
    "PIT": ["PIT", "Pittsburgh", "Pittsburgh Steelers", "Steelers"],
    "BUF": ["BUF", "Buffalo", "Buffalo Bills", "Bills"],
    "MIA": ["MIA", "Miami", "Miami Dolphins", "Dolphins"],
    "NE":  ["NE", "NWE", "New England", "New England Patriots", "Patriots"],
    "NYJ": ["NYJ", "New York Jets", "Jets"],
}
NORMALIZE: Dict[str, str] = {v.strip().lower(): k for k, vs in ALIASES.items() for v in vs}


def normalize_team(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    return NORMALIZE.get(name.strip().lower())


def normalize_group(raw_list: Iterable[str]) -> List[str]:
    out = []
    for t in raw_list:
        canon = normalize_team(t)
        if canon:
            out.append(canon)
    return out


# --------------------------
# ESPN fetching (cached)
# --------------------------

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"


@dataclass
class Game:
    week: int
    seasontype: int  # 2=regular, 3=postseason
    home: str
    away: str
    home_score: int
    away_score: int
    status: str


class EspnFetchError(RuntimeError):
    """Raised when ESPN's scoreboard API can't be reached/parsed after
    retries -- distinct from a week legitimately having no games yet, so
    callers can tell "the fetch failed" from "nothing happened this week"
    and refuse to publish a page built from a failed fetch."""


def http_get_json(url: str) -> dict:
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    return r.json()


def _fetch_week(season: int, week: int, seasontype: int, logo_map: Dict[str, str],
                 retries: int = 3) -> List[Game]:
    params = {"year": season, "week": week, "seasontype": seasontype}
    url = f"{ESPN_SCOREBOARD}?{urlencode(params)}"
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        if attempt:
            time.sleep(2 ** attempt)  # 2s, 4s, ...
        try:
            data = http_get_json(url)
            break
        except requests.RequestException as e:
            last_err = e
    else:
        # A network/HTTP failure (e.g. ESPN/Akamai returning 403) must not
        # be silently treated as "no games this week" -- that previously
        # let a blocked request wipe real results down to 0-0-0 records,
        # which then got committed as if it were current data. Surface it
        # instead so the caller can abort the whole build.
        raise EspnFetchError(f"Failed to fetch {season} week {week} (seasontype {seasontype}) after {retries} attempts: {last_err}") from last_err
    events = data.get("events") or []
    out: List[Game] = []
    for ev in events:
        comps = (ev.get("competitions") or [])
        if not comps:
            continue
        comp = comps[0]
        status = (comp.get("status") or {}).get("type", {}).get("name", "") or ""
        wk = int((ev.get("week") or {}).get("number") or week)

        home_abbr = away_abbr = None
        home_score = away_score = 0

        for c in comp.get("competitors") or []:
            team = c.get("team") or {}
            abbr = team.get("abbreviation") or ""
            canon = normalize_team(abbr) or abbr.upper()

            logo_url = None
            if isinstance(team.get("logos"), list) and team["logos"]:
                logo_url = team["logos"][0].get("href")
            elif team.get("logo"):
                logo_url = team.get("logo")
            if canon in ALIASES and logo_url:
                logo_map.setdefault(canon, logo_url)

            score = int(c.get("score") or 0)
            if c.get("homeAway") == "home":
                home_abbr, home_score = canon, score
            else:
                away_abbr, away_score = canon, score

        if home_abbr and away_abbr:
            out.append(Game(
                week=wk,
                seasontype=seasontype,
                home=home_abbr,
                away=away_abbr,
                home_score=home_score,
                away_score=away_score,
                status=status
            ))
    return out


@lru_cache(maxsize=64)
def fetch_season_cached(season: int,
                        weeks: Optional[Tuple[int, int]],
                        include_postseason: bool) -> Tuple[Tuple[Game, ...], Tuple[Tuple[str, str], ...]]:
    games: List[Game] = []
    logos: Dict[str, str] = {}

    lo, hi = (1, 18)
    if weeks:
        lo, hi = max(1, weeks[0]), min(18, weeks[1])
    for wk in range(lo, hi + 1):
        games.extend(_fetch_week(season, wk, 2, logos))
        time.sleep(0.2)  # be gentle on ESPN's unofficial API
    if include_postseason:
        for wk in range(1, 6):
            games.extend(_fetch_week(season, wk, 3, logos))
            time.sleep(0.2)
    return tuple(games), tuple(sorted(logos.items()))


@lru_cache(maxsize=32)
def detect_last_completed_week_cached(season: int) -> Optional[int]:
    games_t, _ = fetch_season_cached(season, None, False)
    finals = [g.week for g in games_t if g.seasontype == 2 and str(g.status).upper().endswith("FINAL")]
    return max(finals) if finals else None


# --------------------------
# Records & weekly helpers
# --------------------------

@dataclass
class Record:
    wins: int = 0
    losses: int = 0
    ties: int = 0

    def add_outcome(self, o: int) -> None:
        if o > 0: self.wins += 1
        elif o < 0: self.losses += 1
        else: self.ties += 1

    @property
    def games(self) -> int: return self.wins + self.losses + self.ties

    @property
    def pct(self) -> float:
        return (self.wins + 0.5 * self.ties) / self.games if self.games else 0.0

    def to_dict(self) -> dict:
        return {"wins": self.wins, "losses": self.losses, "ties": self.ties, "pct": round(self.pct, 3)}


def outcome_for(team: str, g: Game) -> Optional[int]:
    if team == g.home:
        if g.home_score > g.away_score: return 1
        if g.home_score < g.away_score: return -1
        return 0
    if team == g.away:
        if g.away_score > g.home_score: return 1
        if g.away_score < g.home_score: return -1
        return 0
    return None


def team_records(group: List[str], games: List[Game]) -> Dict[str, Record]:
    s = set(group)
    recs: Dict[str, Record] = {t: Record() for t in group}
    for g in games:
        for t in s:
            o = outcome_for(t, g)
            if o is not None:
                recs[t].add_outcome(o)
    return recs


def combined_record(recs: Dict[str, Record]) -> Record:
    tot = Record()
    for r in recs.values():
        tot.wins += r.wins
        tot.losses += r.losses
        tot.ties += r.ties
    return tot


def weekly_wins_counts(group: List[str], games: List[Game]) -> Dict[int, int]:
    s = set(group)
    by_week: Dict[int, int] = {}
    for g in games:
        if g.seasontype != 2:
            continue
        wins = 0
        if g.home in s and g.home_score > g.away_score:
            wins += 1
        if g.away in s and g.away_score > g.home_score:
            wins += 1
        by_week[g.week] = by_week.get(g.week, 0) + wins
        by_week.setdefault(g.week, 0)
    return by_week


def cumulative_from_weekly(weekly_counts: Dict[int, int], last_week: int) -> List[int]:
    cum = []
    running = 0
    for w in range(1, max(1, last_week) + 1):
        running += weekly_counts.get(w, 0)
        cum.append(running)
    return cum


def team_week_result(team: str, games: List[Game], week: Optional[int]) -> Optional[int]:
    if week is None:
        return None
    for g in games:
        if g.seasontype != 2 or g.week != week:
            continue
        if team != g.home and team != g.away:
            continue
        if g.home == team:
            if g.home_score > g.away_score: return +1
            if g.home_score < g.away_score: return -1
            return 0
        else:
            if g.away_score > g.home_score: return +1
            if g.away_score < g.home_score: return -1
            return 0
    return None


def team_game_log(team: str, games: List[Game]) -> List[dict]:
    """Regular-season, FINAL game-by-game log for one team, for the hover detail panel."""
    log = []
    for g in sorted(games, key=lambda g: g.week):
        if g.seasontype != 2 or team not in (g.home, g.away):
            continue
        is_home = team == g.home
        opp = g.away if is_home else g.home
        team_score = g.home_score if is_home else g.away_score
        opp_score = g.away_score if is_home else g.home_score
        if team_score > opp_score:
            result = "W"
        elif team_score < opp_score:
            result = "L"
        else:
            result = "T"
        log.append({
            "week": g.week,
            "opponent": opp,
            "home": is_home,
            "team_score": team_score,
            "opp_score": opp_score,
            "result": result,
        })
    return log


# --------------------------
# Build JSON payload for one matchup
# --------------------------

def build_matchup_data(owner_left: str, owner_right: str, teams_left: List[str], teams_right: List[str],
                        season: int) -> dict:
    left = normalize_group(teams_left)
    right = normalize_group(teams_right)
    if not left or not right:
        raise ValueError(f"Unrecognized teams for {owner_left} vs {owner_right}")

    last_week = detect_last_completed_week_cached(season)
    if last_week is not None:
        week_span = (1, last_week)
        games_t, logos_t = fetch_season_cached(season, week_span, False)
        display_week = last_week
    else:
        games_t, logos_t = fetch_season_cached(season, None, False)
        display_week = None

    games = list(games_t)
    logos = dict(logos_t)
    finals = [g for g in games if str(g.status).upper().endswith("FINAL")]

    recs_left = team_records(left, finals)
    recs_right = team_records(right, finals)
    tot_left = combined_record(recs_left)
    tot_right = combined_record(recs_right)

    this_week_left = {t: team_week_result(t, finals, display_week) for t in left}
    this_week_right = {t: team_week_result(t, finals, display_week) for t in right}

    def rows_for(group: List[str], recs: Dict[str, Record], this_week: Dict[str, Optional[int]]) -> List[dict]:
        rows = [{
            "team": t,
            "logo": logos.get(t),
            "record": recs[t].to_dict(),
            "this_week_delta": this_week.get(t),
            "game_log": team_game_log(t, finals),
        } for t in group]
        rows.sort(key=lambda r: (-r["record"]["pct"], -r["record"]["wins"], r["record"]["losses"], r["team"]))
        return rows

    wl_counts = weekly_wins_counts(left, finals)
    wr_counts = weekly_wins_counts(right, finals)
    last_wk = last_week or max(list(wl_counts.keys()) + list(wr_counts.keys()) + [1])
    weeks = list(range(1, max(1, last_wk) + 1))

    return {
        "season": season,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "display_week": display_week,
        "owner_left": owner_left,
        "owner_right": owner_right,
        "totals_left": tot_left.to_dict(),
        "totals_right": tot_right.to_dict(),
        "rows_left": rows_for(left, recs_left, this_week_left),
        "rows_right": rows_for(right, recs_right, this_week_right),
        "weeks": weeks,
        "weekly_counts_left": [wl_counts.get(w, 0) for w in weeks],
        "weekly_counts_right": [wr_counts.get(w, 0) for w in weeks],
        "cumulative_left": cumulative_from_weekly(wl_counts, last_wk),
        "cumulative_right": cumulative_from_weekly(wr_counts, last_wk),
    }


# --------------------------
# Site assembly
# --------------------------

PAGE_TEMPLATE = """<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title>
<link rel="stylesheet" href="../assets/style.css" />
</head>
<body>
<div id="app" data-src="./data.json"></div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<script src="../assets/app.js"></script>
</body>
</html>
"""


def write_matchup_page(slug: str, owner_left: str, owner_right: str, data: dict) -> None:
    page_dir = DOCS / slug
    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / "data.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    title = f"{owner_left} vs {owner_right} — {data['season']} Team Comparison"
    (page_dir / "index.html").write_text(PAGE_TEMPLATE.format(title=title), encoding="utf-8")


def write_landing_page(matchup_meta: List[dict]) -> None:
    links = "\n".join(
        f'      <li><a href="./{m["slug"]}/">{m["owner_left"]} vs {m["owner_right"]}</a></li>'
        for m in matchup_meta
    )
    html = f"""<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Fantasy Team Comparisons</title>
<link rel="stylesheet" href="./assets/style.css" />
</head>
<body>
  <div class="landing">
    <h1>Fantasy Team Comparisons</h1>
    <ul class="landing-links">
{links}
    </ul>
  </div>
</body>
</html>
"""
    (DOCS / "index.html").write_text(html, encoding="utf-8")


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "assets").mkdir(parents=True, exist_ok=True)

    # Compute every matchup's data before writing anything -- a fetch
    # failure partway through must not leave some pages updated and others
    # stale/inconsistent, and must never overwrite docs/ with data built
    # from a failed (rather than merely empty) ESPN response.
    built = []
    for m in MATCHUPS:
        print(f"Fetching {m['owner_left']} vs {m['owner_right']}...")
        data = build_matchup_data(m["owner_left"], m["owner_right"], m["teams_left"], m["teams_right"], SEASON)
        built.append((m, data))

    for m, data in built:
        write_matchup_page(m["slug"], m["owner_left"], m["owner_right"], data)

    write_landing_page(MATCHUPS)
    print(f"Done. Site written to {DOCS}")


if __name__ == "__main__":
    try:
        main()
    except EspnFetchError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print("Aborting without writing docs/ -- a failed fetch must not overwrite good data with empty results.", file=sys.stderr)
        sys.exit(1)
    main()
