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

Examples:
```bash
python main.py --dry-run              # Preview changes
python main.py --position bottom      # Add list at bottom of board
python main.py --week 10              # Create list for week 10
```

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

## Cron Setup

```bash
crontab -e
# Add: 1 0 * * 0 cd /path/to/recurring_kanban_cards && .venv/bin/python main.py >> logs/cron.log 2>&1
```

## Tests

```bash
pytest test_main.py -v
```
