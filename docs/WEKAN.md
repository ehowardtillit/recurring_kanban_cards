# Adding WeKan support

The `WeeklyListCreator` class is decoupled from Trello via the `KanbanClient`
protocol defined in `main.py`. Any object that implements the six methods of
that protocol can be passed as the `client` argument.

## What to implement

```python
class WeKanAPIClient:
    """WeKan REST API client implementing KanbanClient."""

    def list_exists(self, name: str) -> bool:
        """Return True if a list with this name already exists on the board."""
        ...

    def create_list(self, name: str, position: str = "top") -> str:
        """Create a new list and return its ID."""
        ...

    def get_board_labels(self) -> dict[str, str]:
        """Return a mapping of label name → label ID for the board."""
        ...

    def create_card(
        self,
        list_id: str,
        name: str,
        due_date,          # timezone-aware datetime
        label_ids: list[str],
        description: str = "",
    ) -> str:
        """Create a card and return its ID."""
        ...

    def create_checklist(self, card_id: str, name: str) -> str:
        """Create a checklist on a card and return its ID."""
        ...

    def add_checklist_item(self, checklist_id: str, name: str) -> str:
        """Add an item to a checklist and return its ID."""
        ...
```

## WeKan REST API reference

- Base URL: typically `http://<host>/api/v1`
- Auth: username/password or LDAP via `POST /users/login` → JWT bearer token
- Board lists: `GET /boards/{boardId}/lists`
- Create list: `POST /boards/{boardId}/lists`
- Cards: `GET/POST /boards/{boardId}/lists/{listId}/cards`
- Card labels: WeKan uses swimlane-level labels; map them via
  `GET /boards/{boardId}/swimlanes` and look up label objects
- Checklists: `GET/POST /boards/{boardId}/cards/{cardId}/checklists`
- Checklist items: `POST /boards/{boardId}/cards/{cardId}/checklists/{checklistId}/items`

## Wiring it in

Once `WeKanAPIClient` is implemented, pass it to `WeeklyListCreator`:

```python
client = WeKanAPIClient(base_url="http://wekan.local", username="...", password="...")
# Pass start_day and any other WeeklyListCreator options as needed.
# The timezone parameter becomes available after feat/timezone-aware-dates is merged;
# without it, due dates default to UTC.
creator = WeeklyListCreator(client, start_day="monday")
creator.create_weekly_list(cards)
```

No changes to `WeeklyListCreator` or the rest of the codebase are needed.

## Configuration

Add a `KANBAN_BACKEND=wekan` env var and a `WeKanConfig` dataclass (mirroring
`TrelloConfig`) when you want `main()` to choose the backend at runtime.
