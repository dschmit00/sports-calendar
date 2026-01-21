# generate_ics.py
import os
import json
import requests
from datetime import datetime, timedelta
from dateutil import parser
import pytz

API_KEY = os.environ.get("THE_SPORTSDB_KEY", "1")   # public key "1" works but may be rate-limited
API_BASE = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}"
OUT_DIR = "docs"
PRODID = "-//My Sports Calendar//EN"
UID_DOMAIN = os.environ.get("ICS_DOMAIN", "github.io")
DEFAULT_TZ = os.environ.get("DEFAULT_TZ", "UTC")  # used when API gives naive datetimes

def fetch_events(team_id):
    """Fetch upcoming events for a team from TheSportsDB."""
    url = f"{API_BASE}/eventsnext.php?id={team_id}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json().get("events") or []

def to_utc_rfc(dt):
    """Return UTC RFC-like string: 20260312T020000Z"""
    return dt.astimezone(pytz.utc).strftime("%Y%m%dT%H%M%SZ")

def uid_for(event):
    """Stable UID for an event using league + idEvent"""
    league = (event.get("strLeague") or "league").replace(" ", "_")
    eid = event.get("idEvent") or event.get("id")
    return f"{league}-{eid}@{UID_DOMAIN}"

def make_dt(event):
    """Parse API date/time into an aware datetime (prefer timezone if present)."""
    date_str = event.get("dateEvent")
    time_str = event.get("strTime")  # sometimes None
    if not date_str:
        raise ValueError("Event missing dateEvent")

    raw = date_str
    if time_str:
        raw = f"{date_str} {time_str}"

    dt = parser.parse(raw)

    if dt.tzinfo is None:
        # assume DEFAULT_TZ (set via env) if naive
        tz = pytz.timezone(DEFAULT_TZ)
        dt = tz.localize(dt)

    return dt

def build_vevent(event, team):
    dt = make_dt(event)
    duration = int(team.get("duration_minutes", 120))
    dtstart = to_utc_rfc(dt)
    dtend = to_utc_rfc(dt + timedelta(minutes=duration))
    dtstamp = datetime.utcnow().replace(tzinfo=pytz.utc).strftime("%Y%m%dT%H%M%SZ")

    uid = uid_for(event)
    summary = f"{team.get('sport_emoji','')} {event.get('strEvent') or (event.get('strHomeTeam')+' vs '+event.get('strAwayTeam'))}".strip()
    location = event.get("strVenue") or event.get("strVenueLocation") or ""
    description = event.get("strLeague") or ""

    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{summary}",
        f"LOCATION:{location}",
        f"DESCRIPTION:{description}",
        "END:VEVENT",
    ]
    return "\n".join(lines)

def generate_calendar(all_vevents):
    header = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
    ]
    footer = ["END:VCALENDAR"]
    return "\n".join(header + all_vevents + footer)

def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    with open("teams.json", "r", encoding="utf-8") as f:
        teams = json.load(f)

    seen_uids = set()
    vevents = []

    for team in teams:
        team_id = team["team_id"]
        print(f"Fetching team {team.get('name')} (id={team_id})...")
        try:
            events = fetch_events(team_id)
        except Exception as e:
            print(f"  Error fetching {team_id}: {e}")
            continue

        if not events:
            print("  No upcoming events returned.")
            continue

        for ev in events:
            try:
                uid = uid_for(ev)
                if uid in seen_uids:
                    continue
                seen_uids.add(uid)
                vevents.append(build_vevent(ev, team))
            except Exception as e:
                print(f"  Skipping event due to error: {e}")
                continue

    calendar_text = generate_calendar(vevents)
    out_path = os.path.join(OUT_DIR, "all.ics")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(calendar_text)
    print(f"Wrote {out_path} ({len(vevents)} events).")

if __name__ == "__main__":
    main()
