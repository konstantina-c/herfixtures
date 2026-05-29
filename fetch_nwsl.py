#!/usr/bin/env python3
"""
HerFixtures — NWSL feed generator
Fetches fixtur.es NWSL ICS and re-serves as nwsl.ics with HerFixtures branding.
No API key required.
"""

import requests
from icalendar import Calendar
from datetime import datetime, timezone
import uuid

SOURCE_URL  = 'https://ics.fixtur.es/v2/league/nwsl-national-womens-soccer-league.ics'
OUTPUT_FILE = 'nwsl.ics'

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; HerFixtures/1.0)'}

def fetch_and_rebrand():
    print(f"Fetching NWSL 2026 fixtures from fixtur.es...")
    r = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()

    source_cal = Calendar.from_ical(r.content)

    cal = Calendar()
    cal.add('prodid',                    '-//HerFixtures//NWSL 2026//EN')
    cal.add('version',                   '2.0')
    cal.add('calscale',                  'GREGORIAN')
    cal.add('method',                    'PUBLISH')
    cal.add('x-wr-calname',              'NWSL 2026 — HerFixtures')
    cal.add('x-wr-caldesc',              'NWSL 2026 fixtures. Updated automatically by HerFixtures.com')
    cal.add('x-wr-timezone',             'UTC')
    cal.add('refresh-interval;value=duration', 'PT12H')
    cal.add('x-published-ttl',           'PT12H')

    count = 0
    for component in source_cal.walk():
        if component.name == 'VEVENT':
            # Append HerFixtures attribution to description
            existing_desc = str(component.get('description', ''))
            if 'description' in component:
                del component['description']
            component.add('description',
                existing_desc.strip() + '\n\nFixtures by HerFixtures.com — Women\'s Sports on Your Calendar'
            )
            # Ensure stable UID
            if 'uid' not in component:
                component.add('uid', str(uuid.uuid4()))
            cal.add_component(component)
            count += 1

    with open(OUTPUT_FILE, 'wb') as f:
        f.write(cal.to_ical())

    print(f"  → {count} events written to {OUTPUT_FILE}")

if __name__ == '__main__':
    fetch_and_rebrand()
