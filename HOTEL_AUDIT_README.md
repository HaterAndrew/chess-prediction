# Hotel Room-Block Audit List

Builds the name list you hand a hotel when you demand a room-block audit.
The hotel matches each name against its reservation folios; every match is
a room-night that comes off the shortfall bill.

The tool pulls the event's public entry list from chessaction.com, removes
duplicate players (multi-event entries, re-entries), and, when you give it
the registration export, adds every person who paid for someone else's
entry. A parent who paid the entry fee usually booked the room in their own
name, so those names are the ones the hotel's list misses.

## Setup (once)

```
pip install -r requirements-optional.txt
```

## Commands

```
# Preliminary list, any time (scrapes the public entry list):
python3 hotel_audit.py "southern open"

# Final list, after entries close (add the registration export):
python3 hotel_audit.py "southern open" --payers export.csv

# From the export alone, no scrape:
python3 hotel_audit.py --payers export.csv

# Pick the output file name:
python3 hotel_audit.py "world open" --payers export.csv -o worldopen_audit.xlsx
```

Event names are free text ("southern open", "2026 World Open"). Use
`--year` for a past or future edition; it defaults to the current year.

The export CSV needs these columns, with PayerName as "Last, First":

```
LastName, FirstName, City, State, ZipCode, PayerName
```

## What comes out

One .xlsx with two sheets:

- **Audit List**: LastName, FirstName, City, State, Zip. Clean, deduped,
  alphabetical. This is the sheet for the hotel.
- **Reference**: for you. Marks each person as Player or Payer, shows which
  source they came from, who each payer paid for, and flags anything worth
  a second look: withdrawn players, blank names in the source data, one
  name appearing in several states, and bulk payers (a person who paid for
  more than three entries is registration staff, not a parent booking a
  room).

Nobody gets dropped silently. A data problem becomes a flag on the
Reference sheet, and the row stays in.

## Workflow for an event

1. Any time before the event: run the scrape-only command for a
   preliminary list and a head count.
2. After entries close: pull the registration export, rerun with
   `--payers`, and send the hotel the Audit List sheet.
3. Rooms are usually under the parent's name for junior players. The
   Reference sheet's "Paid for" column tells the hotel whose reservation
   credits which player if they ask.

## Notes

- The public entry list has no addresses and no payer data. Those only
  exist in the registration export, so the final list needs both sources.
- The scrape covers the event's main entry-list page. Side events with
  separate pages (World Open weekend has several) reach the list through
  the export, so a multi-event weekend without the export undercounts.
- World Open 2026 check: all 1,108 entry-list players matched the
  registration export; the export added 320 side-event players and 492
  payers for a final list of 1,923 names from 2,036 raw rows.
