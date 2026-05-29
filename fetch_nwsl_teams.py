#!/usr/bin/env python3
"""
HerFixtures — NWSL individual team feed generator
Fetches per-team ICS from fixtur.es and re-serves with HerFixtures branding.
No API key required.
"""

import requests
from icalendar import Calendar
import uuid

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; HerFixtures/1.0)'}

# fixtur.es slug → (display name, output slug)
NWSL_TEAMS = {
    'angel-city':          ('Angel City FC',          'angel_city'),
    'bay-fc':              ('Bay FC',                  'bay_fc'),
    'boston-legacy':       ('Boston Legacy FC',        'boston_legacy'),
    'chicago-red-stars':   ('Chicago Red Stars',       'chicago_red_stars'),
    'denver-summit':       ('Denver Summit FC',        'denver_summit'),
    'sky-blue':            ('Gotham FC',               'gotham_fc'),
    'houston-dash':        ('Houston Dash',            'houston_dash'),
    'kansas-city':         ('Kansas City Current',     'kansas_city'),
    'north-carolina-courage': ('North Carolina Courage', 'north_carolina_courage'),
    'orlando-pride':       ('Orlando Pride',           'orlando_pride'),
    'portland-thorns':     ('Portland Thorns FC',      'portland_thorns'),
    'racing-louisville':   ('Racing Louisville FC',    'racing_louisville'),
    'san-diego-wave':      ('San Diego Wave FC',       'san_diego_wave'),
    'seattle-reign':       ('Seattle Reign FC',        'seattle_reign'),
    'utah-royals':         ('Utah Royals FC',          'utah_royals'),
    'washington-spirit':   ('Washington Spirit',       'washington_spirit'),
}

def fetch_team(fixtures_slug, display_name, output_slug):
    url = f'https://ics.fixtur.es/v2/{fixtures_slug}.ics'
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()

    source_cal = Calendar.from_ical(r.content)

    cal = Calendar()
    cal.add('prodid',   f'-//HerFixtures//NWSL 2026 {display_name}//EN')
    cal.add('version',  '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method',   'PUBLISH')
    cal.add('x-wr-calname',  f'{display_name} 2026 — HerFixtures')
    cal.add('x-wr-caldesc',  f'{display_name} 2026 fixtures. Updated automatically by HerFixtures.com')
    cal.add('x-wr-timezone', 'UTC')
    cal.add('refresh-interval;value=duration', 'PT12H')
    cal.add('x-published-ttl', 'PT12H')

    count = 0
    for component in source_cal.walk():
        if component.name == 'VEVENT':
            existing_desc = str(component.get('description', ''))
            if 'description' in component:
                del component['description']
            component.add('description',
                existing_desc.strip() + '\n\nFixtures by HerFixtures.com — Women\'s Sports on Your Calendar'
            )
            if 'uid' not in component:
                component.add('uid', str(uuid.uuid4()))
            cal.add_component(component)
            count += 1

    output_file = f'nwsl_{output_slug}.ics'
    with open(output_file, 'wb') as f:
        f.write(cal.to_ical())

    return count, output_file

def main():
    print(f"Generating NWSL 2026 team feeds from fixtur.es...")
    print()

    success = 0
    for fixtures_slug, (display_name, output_slug) in NWSL_TEAMS.items():
        try:
            count, output_file = fetch_team(fixtures_slug, display_name, output_slug)
            print(f"  ✓ {output_file:45} ({count} events)")
            success += 1
        except Exception as e:
            print(f"  ✗ {display_name}: {e}")

    print()
    print(f"Done — {success}/{len(NWSL_TEAMS)} team feeds written.")

if __name__ == '__main__':
    main()
