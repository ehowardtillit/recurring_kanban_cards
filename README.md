# Recurring Kanban Cards

Creates weekly Trello lists with predefined cards. Runs every Sunday at 00:01.

## Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
cp config/cards.yaml.example config/cards.yaml
# Edit .env with your Trello credentials
# Edit config/cards.yaml with your recurring tasks
```

## Get Trello Credentials

1. **API Key**: https://trello.com/app-key
2. **Token**: Click "Token" link on the API key page
3. **Board ID**: 
   ```bash
   curl "https://api.trello.com/1/members/me/boards?key=YOUR_KEY&token=YOUR_TOKEN" | jq '.[] | {name, id}'
   ```

## Run

```bash
source .venv/bin/activate
python main.py
```

### Options

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview what would be created without making API calls |
| `--position top\|bottom` | Where to place the new list (default: top) |
| `--week N` | Create list for week N (1-53). Defaults to current week. |
| `--start-day saturday\|sunday\|monday` | First day of the week (default: monday). Set `WEEK_START_DAY` env var to change the default. |
| `--timezone TZ` | IANA timezone for card due dates (default: UTC). Set `TIMEZONE` env var to change the default. |

Examples:
```bash
python main.py --dry-run                         # Preview changes
python main.py --position bottom                 # Add list at bottom of board
python main.py --week 10                         # Create list for week 10
python main.py --start-day sunday                # Use Sunday as first day of week (US)
python main.py --start-day saturday              # Use Saturday as first day of week (Islamic/Middle East)
python main.py --timezone Europe/Paris           # Due dates in CET/CEST
python main.py --timezone America/New_York       # Due dates in ET
```

## Timezone

By default due dates are stored in UTC. Set the timezone so Trello shows the correct local time in the card UI.

```bash
# In .env
TIMEZONE=Europe/Paris
```

Or pass it directly:

```bash
python main.py --timezone Europe/Paris
```

The value must be a valid [IANA timezone name](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) (e.g. `Europe/Paris`, `America/New_York`, `Asia/Tokyo`). An invalid name raises an error at startup.

**DST safety**: due dates are constructed by combining the target calendar date with the requested wall-clock time in the configured timezone. This means a card set for `10:00` on a spring-forward day stays at `10:00` — it never drifts by one hour. If a card's `hour`/`minute` falls inside a DST gap (a time that does not exist on that date, e.g. `02:30` on the night clocks spring forward), the script raises a clear error instead of silently sending an ambiguous timestamp to Trello.

## Card Configuration

Cards are defined in `config/cards.yaml`. Each card supports:

```yaml
cards:
  - title: "Weekly planning"
    day_of_week: "monday"
    hour: 9
    minute: 0
    labels:
      - "Work"
    description: "Optional card description"
    checklists:
      - name: "Tasks"
        items:
          - "Review last week"
          - "Set goals"
          - "Prioritize"
```

Card titles, descriptions, checklist names, and checklist items all support UTF-8 (accented characters, CJK, etc.).

## Cron Setup

```bash
crontab -e
# Add: 1 0 * * 0 cd /path/to/recurring_kanban_cards && .venv/bin/python main.py >> logs/cron.log 2>&1
```

Set `TIMEZONE` in your `.env` file so that cron jobs (which often run under UTC) produce correctly-localised due dates.

## Adding a Different Backend (WeKan)

The card-creation logic is decoupled from Trello through a `KanbanClient` protocol. Any object that implements the six methods of that protocol (`list_exists`, `create_list`, `get_board_labels`, `create_card`, `create_checklist`, `add_checklist_item`) can be passed to `WeeklyListCreator` without modifying any other code.

See [`docs/WEKAN.md`](docs/WEKAN.md) for the WeKan REST API surface to implement and a wiring example.

## Tests

```bash
pytest test_main.py -v
```

## License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
See the full license text in the [`LICENSE`](LICENSE) file or at https://www.gnu.org/licenses/agpl-3.0.html.

For commercial licensing inquiries or special agreements, contact the project owner.
