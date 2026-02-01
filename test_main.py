"""Unit tests for Trello Weekly List Creator."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import os

from main import (
    TrelloConfig,
    CardTemplate,
    ChecklistTemplate,
    TrelloAPIClient,
    WeeklyListCreator,
    load_card_templates,
    parse_args,
)


class TestTrelloConfig:
    """Tests for TrelloConfig."""

    def test_from_env_success(self):
        """Load config from environment variables."""
        with patch.dict(os.environ, {
            'TRELLO_API_KEY': 'test_key',
            'TRELLO_API_TOKEN': 'test_token',
            'TRELLO_BOARD_ID': 'test_board'
        }):
            config = TrelloConfig.from_env()
            assert config.api_key == 'test_key'
            assert config.api_token == 'test_token'
            assert config.board_id == 'test_board'

    def test_from_env_missing_variables(self):
        """Raise ValueError when env vars are missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Missing required"):
                TrelloConfig.from_env()


class TestCardTemplate:
    """Tests for CardTemplate."""

    def test_valid_card(self):
        """Create a valid card template."""
        card = CardTemplate(
            title="Test",
            day_of_week="monday",
            hour=10,
            minute=30,
            labels=["Work"]
        )
        assert card.title == "Test"
        assert card.minute == 30

    def test_invalid_day(self):
        """Reject invalid day of week."""
        with pytest.raises(ValueError, match="Invalid day_of_week"):
            CardTemplate(title="Test", day_of_week="notaday", hour=10)

    def test_invalid_hour(self):
        """Reject invalid hour."""
        with pytest.raises(ValueError, match="Invalid hour"):
            CardTemplate(title="Test", day_of_week="monday", hour=25)

    def test_invalid_minute(self):
        """Reject invalid minute."""
        with pytest.raises(ValueError, match="Invalid minute"):
            CardTemplate(title="Test", day_of_week="monday", hour=10, minute=60)

    def test_default_values(self):
        """Check default values."""
        card = CardTemplate(title="Test", day_of_week="monday", hour=10)
        assert card.minute == 0
        assert card.labels == []
        assert card.description == ""
        assert card.checklists == []

    def test_with_description(self):
        """Card with description."""
        card = CardTemplate(
            title="Test",
            day_of_week="monday",
            hour=10,
            description="Some details"
        )
        assert card.description == "Some details"

    def test_with_checklists(self):
        """Card with checklists."""
        checklist = ChecklistTemplate(name="Tasks", items=["Item 1", "Item 2"])
        card = CardTemplate(
            title="Test",
            day_of_week="monday",
            hour=10,
            checklists=[checklist]
        )
        assert len(card.checklists) == 1
        assert card.checklists[0].name == "Tasks"
        assert card.checklists[0].items == ["Item 1", "Item 2"]


class TestChecklistTemplate:
    """Tests for ChecklistTemplate."""

    def test_create_checklist(self):
        """Create a valid checklist."""
        checklist = ChecklistTemplate(name="My List", items=["A", "B", "C"])
        assert checklist.name == "My List"
        assert checklist.items == ["A", "B", "C"]

    def test_default_items(self):
        """Checklist with no items defaults to empty list."""
        checklist = ChecklistTemplate(name="Empty")
        assert checklist.items == []


class TestTrelloAPIClient:
    """Tests for TrelloAPIClient."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        config = TrelloConfig(
            api_key="key",
            api_token="token",
            board_id="board123"
        )
        return TrelloAPIClient(config)

    def test_auth_params(self, client):
        """Check auth params are correct."""
        params = client._get_auth_params()
        assert params == {"key": "key", "token": "token"}

    @patch.object(TrelloAPIClient, '_make_request')
    def test_list_exists_true(self, mock_request, client):
        """list_exists returns True when list exists."""
        mock_request.return_value = [{"name": "Todo w05"}, {"name": "Other"}]
        assert client.list_exists("Todo w05") is True

    @patch.object(TrelloAPIClient, '_make_request')
    def test_list_exists_false(self, mock_request, client):
        """list_exists returns False when list doesn't exist."""
        mock_request.return_value = [{"name": "Other"}]
        assert client.list_exists("Todo w05") is False

    @patch.object(TrelloAPIClient, '_make_request')
    def test_create_list(self, mock_request, client):
        """create_list returns the new list ID."""
        mock_request.return_value = {"id": "list123"}
        result = client.create_list("Test List", "top")
        assert result == "list123"
        mock_request.assert_called_once()

    @patch.object(TrelloAPIClient, '_make_request')
    def test_create_card_with_description(self, mock_request, client):
        """create_card includes description when provided."""
        mock_request.return_value = {"id": "card123"}
        result = client.create_card(
            list_id="list1",
            name="Card",
            due_date=datetime(2026, 2, 2, 10, 0),
            label_ids=["label1"],
            description="Details here"
        )
        assert result == "card123"
        call_args = mock_request.call_args
        assert call_args[1]["params"]["desc"] == "Details here"

    @patch.object(TrelloAPIClient, '_make_request')
    def test_create_checklist(self, mock_request, client):
        """create_checklist returns checklist ID."""
        mock_request.return_value = {"id": "checklist123"}
        result = client.create_checklist("card123", "My Checklist")
        assert result == "checklist123"
        call_args = mock_request.call_args
        assert call_args[1]["params"]["idCard"] == "card123"
        assert call_args[1]["params"]["name"] == "My Checklist"

    @patch.object(TrelloAPIClient, '_make_request')
    def test_add_checklist_item(self, mock_request, client):
        """add_checklist_item returns item ID."""
        mock_request.return_value = {"id": "item123"}
        result = client.add_checklist_item("checklist123", "Task item")
        assert result == "item123"


class TestWeeklyListCreator:
    """Tests for WeeklyListCreator."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock client."""
        client = Mock(spec=TrelloAPIClient)
        client.list_exists.return_value = False
        client.create_list.return_value = "list123"
        client.get_board_labels.return_value = {"Work": "label1"}
        client.create_card.return_value = "card123"
        client.create_checklist.return_value = "checklist123"
        client.add_checklist_item.return_value = "item123"
        return client

    def test_get_current_week_number(self, mock_client):
        """get_current_week_number returns correct week."""
        creator = WeeklyListCreator(mock_client)
        week_num = creator.get_current_week_number()
        expected = datetime.now().isocalendar()[1]
        assert week_num == expected

    def test_calculate_due_date_current_week(self, mock_client):
        """calculate_due_date returns correct datetime for current week."""
        creator = WeeklyListCreator(mock_client)
        due = creator.calculate_due_date("monday", 10, 30)
        assert due.weekday() == 0  # Monday
        assert due.hour == 10
        assert due.minute == 30

    def test_calculate_due_date_specific_week(self, mock_client):
        """calculate_due_date respects specified week number."""
        creator = WeeklyListCreator(mock_client, week_number=10)
        due = creator.calculate_due_date("monday", 9, 0)
        assert due.weekday() == 0  # Monday
        assert due.isocalendar()[1] == 10  # Week 10

    def test_get_week_start_specific_week(self, mock_client):
        """get_week_start returns Monday of specified week."""
        creator = WeeklyListCreator(mock_client)
        week_start = creator.get_week_start(5)
        assert week_start.weekday() == 0  # Monday
        assert week_start.isocalendar()[1] == 5

    def test_resolve_label_ids(self, mock_client):
        """resolve_label_ids maps names to IDs."""
        creator = WeeklyListCreator(mock_client)
        labels = {"Work": "id1", "Home": "id2"}
        result = creator.resolve_label_ids(["Work", "Missing"], labels)
        assert result == ["id1"]

    def test_create_weekly_list_skips_duplicate(self, mock_client):
        """Skips creation if list already exists."""
        mock_client.list_exists.return_value = True
        creator = WeeklyListCreator(mock_client)
        cards = [CardTemplate(title="Test", day_of_week="monday", hour=10)]
        
        creator.create_weekly_list(cards)
        
        mock_client.create_list.assert_not_called()
        mock_client.create_card.assert_not_called()

    def test_create_weekly_list_creates_cards(self, mock_client):
        """Creates list and cards when list doesn't exist."""
        creator = WeeklyListCreator(mock_client)
        cards = [
            CardTemplate(title="Card1", day_of_week="monday", hour=10, labels=["Work"]),
            CardTemplate(title="Card2", day_of_week="tuesday", hour=14),
        ]
        
        creator.create_weekly_list(cards)
        
        mock_client.create_list.assert_called_once()
        assert mock_client.create_card.call_count == 2

    def test_create_weekly_list_with_checklists(self, mock_client):
        """Creates cards with checklists."""
        creator = WeeklyListCreator(mock_client)
        checklist = ChecklistTemplate(name="Tasks", items=["Item 1", "Item 2"])
        cards = [
            CardTemplate(title="Card1", day_of_week="monday", hour=10, checklists=[checklist]),
        ]
        
        creator.create_weekly_list(cards)
        
        mock_client.create_card.assert_called_once()
        mock_client.create_checklist.assert_called_once_with("card123", "Tasks")
        assert mock_client.add_checklist_item.call_count == 2

    def test_dry_run_no_api_calls(self, mock_client):
        """Dry run doesn't make API calls."""
        creator = WeeklyListCreator(mock_client, dry_run=True)
        cards = [CardTemplate(title="Test", day_of_week="monday", hour=10)]
        
        creator.create_weekly_list(cards)
        
        mock_client.create_list.assert_not_called()
        mock_client.create_card.assert_not_called()

    def test_position_passed_to_create_list(self, mock_client):
        """Position is passed to create_list."""
        creator = WeeklyListCreator(mock_client, position="bottom")
        cards = [CardTemplate(title="Test", day_of_week="monday", hour=10)]
        
        creator.create_weekly_list(cards)
        
        mock_client.create_list.assert_called_once()
        call_args = mock_client.create_list.call_args
        assert call_args[0][1] == "bottom"


class TestLoadCardTemplates:
    """Tests for load_card_templates."""

    def test_load_valid_yaml(self):
        """Load cards from valid YAML."""
        yaml_content = """
cards:
  - title: "Test Card"
    day_of_week: "monday"
    hour: 9
    minute: 30
    labels:
      - "Work"
    description: "Details"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(yaml_content)
            f.flush()
            
            cards = load_card_templates(Path(f.name))
            
            assert len(cards) == 1
            assert cards[0].title == "Test Card"
            assert cards[0].description == "Details"
            
            os.unlink(f.name)

    def test_load_yaml_with_checklists(self):
        """Load cards with checklists from YAML."""
        yaml_content = """
cards:
  - title: "Task with checklist"
    day_of_week: "monday"
    hour: 9
    checklists:
      - name: "Subtasks"
        items:
          - "Step 1"
          - "Step 2"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(yaml_content)
            f.flush()
            
            cards = load_card_templates(Path(f.name))
            
            assert len(cards) == 1
            assert len(cards[0].checklists) == 1
            assert cards[0].checklists[0].name == "Subtasks"
            assert cards[0].checklists[0].items == ["Step 1", "Step 2"]
            
            os.unlink(f.name)

    def test_file_not_found(self):
        """Raise error for missing file."""
        with pytest.raises(FileNotFoundError, match="not found"):
            load_card_templates(Path("/nonexistent/cards.yaml"))

    def test_utf8_content(self):
        """Handle UTF-8 content correctly."""
        yaml_content = """
cards:
  - title: "Réunion équipe"
    day_of_week: "monday"
    hour: 10
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(yaml_content)
            f.flush()
            
            cards = load_card_templates(Path(f.name))
            
            assert cards[0].title == "Réunion équipe"
            
            os.unlink(f.name)


class TestParseArgs:
    """Tests for parse_args."""

    def test_default_args(self):
        """Default arguments."""
        with patch('sys.argv', ['main.py']):
            args = parse_args()
            assert args.dry_run is False
            assert args.position == "top"
            assert args.week is None

    def test_dry_run_flag(self):
        """--dry-run flag."""
        with patch('sys.argv', ['main.py', '--dry-run']):
            args = parse_args()
            assert args.dry_run is True

    def test_position_bottom(self):
        """--position bottom."""
        with patch('sys.argv', ['main.py', '--position', 'bottom']):
            args = parse_args()
            assert args.position == "bottom"

    def test_week_number(self):
        """--week option."""
        with patch('sys.argv', ['main.py', '--week', '10']):
            args = parse_args()
            assert args.week == 10

    def test_start_day_default(self):
        """Default start_day from env or 'monday'."""
        with patch('sys.argv', ['main.py']):
            with patch.dict(os.environ, {}, clear=True):
                args = parse_args()
                assert args.start_day == "monday"

    def test_start_day_from_env(self):
        """--start-day defaults to WEEK_START_DAY env var."""
        with patch('sys.argv', ['main.py']):
            with patch.dict(os.environ, {'WEEK_START_DAY': 'monday'}):
                args = parse_args()
                assert args.start_day == "monday"

    def test_start_day_cli_overrides_env(self):
        """--start-day CLI overrides env var."""
        with patch('sys.argv', ['main.py', '--start-day', 'monday']):
            with patch.dict(os.environ, {'WEEK_START_DAY': 'sunday'}):
                args = parse_args()
                assert args.start_day == "monday"


class TestWeekStartDay:
    """Tests for week start day functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock client."""
        client = Mock(spec=TrelloAPIClient)
        client.list_exists.return_value = False
        client.create_list.return_value = "list123"
        client.get_board_labels.return_value = {}
        client.create_card.return_value = "card123"
        return client

    def test_monday_start_week_number(self, mock_client):
        """Monday start uses ISO week number."""
        with patch('main.datetime') as mock_dt:
            # Sunday 2025-01-26 - ISO week 4 (Monday-based)
            mock_dt.now.return_value = datetime(2025, 1, 26, 12, 0)
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            creator = WeeklyListCreator(mock_client, start_day="monday")
            week_num = creator.get_current_week_number()
            
            # ISO week: Sunday Jan 26 is in week 4 (week starts Mon Jan 20)
            assert week_num == 4

    def test_sunday_start_week_number(self, mock_client):
        """Sunday start calculates week from Sunday."""
        with patch('main.datetime') as mock_dt:
            # Sunday 2025-01-26 - Sunday-based week 5 (week starts Jan 26)
            mock_dt.now.return_value = datetime(2025, 1, 26, 12, 0)
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            creator = WeeklyListCreator(mock_client, start_day="sunday")
            week_num = creator.get_current_week_number()
            
            # Sunday-based: Jan 26 is first day of week 5
            assert week_num == 5

    def test_get_week_start_monday(self, mock_client):
        """get_week_start with Monday start returns Monday."""
        creator = WeeklyListCreator(mock_client, start_day="monday")
        week_start = creator.get_week_start(5)
        assert week_start.weekday() == 0  # Monday

    def test_get_week_start_sunday(self, mock_client):
        """get_week_start with Sunday start returns Sunday."""
        creator = WeeklyListCreator(mock_client, start_day="sunday")
        week_start = creator.get_week_start(5)
        assert week_start.weekday() == 6  # Sunday

    def test_invalid_start_day_raises(self, mock_client):
        """Invalid start_day raises ValueError."""
        with pytest.raises(ValueError, match="Invalid start_day"):
            WeeklyListCreator(mock_client, start_day="wednesday")

    def test_calculate_due_date_sunday_start(self, mock_client):
        """calculate_due_date works correctly with Sunday start."""
        creator = WeeklyListCreator(mock_client, start_day="sunday", week_number=5)
        
        # Sunday should be day 0 of the week
        due = creator.calculate_due_date("sunday", 10, 0)
        assert due.weekday() == 6  # Sunday
        
        # Monday should be day 1 of the week
        due = creator.calculate_due_date("monday", 10, 0)
        assert due.weekday() == 0  # Monday

    def test_saturday_start_week_number(self, mock_client):
        """Saturday start calculates week from Saturday."""
        with patch('main.datetime') as mock_dt:
            # Saturday 2025-01-25 - Saturday-based week 5 (week starts Jan 25)
            mock_dt.now.return_value = datetime(2025, 1, 25, 12, 0)
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            creator = WeeklyListCreator(mock_client, start_day="saturday")
            week_num = creator.get_current_week_number()
            
            # Saturday-based: Jan 25 is first day of week 5
            assert week_num == 5

    def test_get_week_start_saturday(self, mock_client):
        """get_week_start with Saturday start returns Saturday."""
        creator = WeeklyListCreator(mock_client, start_day="saturday")
        week_start = creator.get_week_start(5)
        assert week_start.weekday() == 5  # Saturday

    def test_calculate_due_date_saturday_start(self, mock_client):
        """calculate_due_date works correctly with Saturday start."""
        creator = WeeklyListCreator(mock_client, start_day="saturday", week_number=5)
        
        # Saturday should be day 0 of the week
        due = creator.calculate_due_date("saturday", 10, 0)
        assert due.weekday() == 5  # Saturday
        
        # Sunday should be day 1 of the week
        due = creator.calculate_due_date("sunday", 10, 0)
        assert due.weekday() == 6  # Sunday
        
        # Friday should be day 6 of the week
        due = creator.calculate_due_date("friday", 10, 0)
        assert due.weekday() == 4  # Friday
