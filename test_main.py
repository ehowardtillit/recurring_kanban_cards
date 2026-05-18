# SPDX-FileCopyrightText: 2026 ehowardtillit
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for Trello Weekly List Creator."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
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

    def test_close_session(self, client):
        """close() shuts down the underlying HTTP session."""
        client.session = Mock()
        client.close()
        client.session.close.assert_called_once()

    @patch.object(TrelloAPIClient, '_make_request')
    def test_get_board_labels_filters_unnamed(self, mock_request, client):
        """get_board_labels excludes labels with no name."""
        mock_request.return_value = [
            {"name": "Work", "id": "id1"},
            {"name": None, "id": "id2"},
            {"name": "", "id": "id3"},
            {"name": "Home", "id": "id4"},
        ]
        result = client.get_board_labels()
        assert result == {"Work": "id1", "Home": "id4"}


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
        """get_current_week_number returns correct week (UTC default)."""
        creator = WeeklyListCreator(mock_client)
        week_num = creator.get_current_week_number()
        expected = datetime.now(ZoneInfo("UTC")).isocalendar()[1]
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
        creator = WeeklyListCreator(mock_client, start_day="monday")
        # Sunday 2025-01-26 is ISO week 4 (Monday-based, week starts Jan 20)
        fixed = datetime(2025, 1, 26, 12, 0, tzinfo=ZoneInfo("UTC"))
        with patch.object(creator, '_now', return_value=fixed):
            week_num = creator.get_current_week_number()
        assert week_num == 4

    def test_sunday_start_week_number(self, mock_client):
        """Sunday start calculates week from Sunday."""
        creator = WeeklyListCreator(mock_client, start_day="sunday")
        # Sunday 2025-01-26 is the first day of Sunday-based week 5
        fixed = datetime(2025, 1, 26, 12, 0, tzinfo=ZoneInfo("UTC"))
        with patch.object(creator, '_now', return_value=fixed):
            week_num = creator.get_current_week_number()
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
        creator = WeeklyListCreator(mock_client, start_day="saturday")
        # Saturday 2025-01-25 is the first day of Saturday-based week 5
        fixed = datetime(2025, 1, 25, 12, 0, tzinfo=ZoneInfo("UTC"))
        with patch.object(creator, '_now', return_value=fixed):
            week_num = creator.get_current_week_number()
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


class TestSetupLogging:
    """Tests for setup_logging."""

    def test_no_duplicate_handlers(self, tmp_path):
        """setup_logging is a no-op when the root logger already has handlers."""
        import logging as _logging
        root = _logging.getLogger()
        original_handlers = root.handlers[:]
        original_level = root.level
        try:
            sentinel = _logging.NullHandler()
            root.addHandler(sentinel)
            handler_count_before = len(root.handlers)

            from main import setup_logging
            setup_logging(tmp_path)

            assert len(root.handlers) == handler_count_before
        finally:
            root.handlers[:] = original_handlers
            root.level = original_level


class TestMainSessionCleanup:
    """Tests that main() always closes the API client."""

    def _run_main(self, mock_client, create_weekly_list_side_effect=None):
        """Helper: run main() with all dependencies mocked."""
        from main import main

        mock_creator = Mock()
        if create_weekly_list_side_effect:
            mock_creator.create_weekly_list.side_effect = create_weekly_list_side_effect

        with patch('sys.argv', ['main.py', '--dry-run']), \
             patch.dict(os.environ, {
                 'TRELLO_API_KEY': 'k', 'TRELLO_API_TOKEN': 't', 'TRELLO_BOARD_ID': 'b'
             }), \
             patch('main.setup_logging'), \
             patch('main.load_card_templates', return_value=[
                 CardTemplate(title="T", day_of_week="monday", hour=9)
             ]), \
             patch('main.TrelloAPIClient', return_value=mock_client), \
             patch('main.WeeklyListCreator', return_value=mock_creator):
            return main()

    def test_close_called_on_success(self):
        """main() calls client.close() when create_weekly_list succeeds."""
        mock_client = Mock()
        self._run_main(mock_client)
        mock_client.close.assert_called_once()

    def test_close_called_on_exception(self):
        """main() calls client.close() even when create_weekly_list raises."""
        mock_client = Mock()
        self._run_main(mock_client, create_weekly_list_side_effect=RuntimeError("boom"))
        mock_client.close.assert_called_once()


class TestTimezone:
    """Tests for timezone-aware due date handling."""

    @pytest.fixture
    def mock_client(self):
        client = Mock(spec=TrelloAPIClient)
        client.list_exists.return_value = False
        client.create_list.return_value = "list123"
        client.get_board_labels.return_value = {}
        client.create_card.return_value = "card123"
        return client

    def test_invalid_timezone_raises(self, mock_client):
        """Invalid IANA timezone name raises ValueError."""
        with pytest.raises(ValueError, match="Invalid timezone"):
            WeeklyListCreator(mock_client, timezone="Not/ATimezone")

    def test_due_date_is_timezone_aware(self, mock_client):
        """calculate_due_date returns a timezone-aware datetime."""
        creator = WeeklyListCreator(mock_client, week_number=5, timezone="Europe/Paris")
        due = creator.calculate_due_date("monday", 10, 0)
        assert due.tzinfo is not None

    def test_due_date_utc_offset_included(self, mock_client):
        """Due date isoformat includes UTC offset (Trello needs explicit TZ)."""
        creator = WeeklyListCreator(mock_client, week_number=5, timezone="Europe/Paris")
        due = creator.calculate_due_date("monday", 10, 0)
        iso = due.isoformat()
        assert "+" in iso or iso.endswith("Z"), "ISO string must carry a UTC offset"

    def test_due_date_wall_clock_matches_requested_time(self, mock_client):
        """Due date wall-clock time matches the requested hour and minute."""
        creator = WeeklyListCreator(mock_client, week_number=5, timezone="America/New_York")
        due = creator.calculate_due_date("wednesday", 14, 30)
        assert due.hour == 14
        assert due.minute == 30

    def test_dst_spring_forward_does_not_shift_hour(self, mock_client):
        """Due date on a DST-transition week still shows the requested wall-clock time.

        Europe/Paris springs forward from CET→CEST in late March. A card set for
        10:00 on any day of that week must still appear as 10:00, not 11:00.
        Week 13 of 2025 contains the spring-forward (30 Mar 2025).
        """
        creator = WeeklyListCreator(mock_client, week_number=13, timezone="Europe/Paris")
        due = creator.calculate_due_date("sunday", 10, 0)
        assert due.hour == 10
        assert due.minute == 0

    def test_default_timezone_is_utc(self, mock_client):
        """Default timezone is UTC."""
        creator = WeeklyListCreator(mock_client, week_number=1)
        assert str(creator.timezone) == "UTC"

    def test_timezone_from_env(self, mock_client):
        """--timezone CLI argument and TIMEZONE env var are wired in parse_args."""
        with patch('sys.argv', ['main.py', '--timezone', 'Asia/Tokyo']):
            with patch.dict(os.environ, {}, clear=True):
                args = parse_args()
                assert args.timezone == "Asia/Tokyo"

    def test_timezone_env_var_default(self, mock_client):
        """TIMEZONE env var sets the default when no CLI flag given."""
        with patch('sys.argv', ['main.py']):
            with patch.dict(os.environ, {'TIMEZONE': 'America/Chicago'}):
                args = parse_args()
                assert args.timezone == "America/Chicago"

    def test_dst_gap_raises_value_error(self, mock_client):
        """calculate_due_date raises ValueError for a time inside a DST spring-forward gap.

        Europe/Paris springs forward on 30 March 2025: clocks jump 02:00 → 03:00,
        so 02:30 does not exist. The card config should be rejected at calculation
        time rather than silently sending an ambiguous UTC instant to Trello.
        """
        creator = WeeklyListCreator(mock_client, week_number=13, timezone="Europe/Paris")
        # Week 13 of 2025 contains Sunday 30 March (the spring-forward day)
        with pytest.raises(ValueError, match="DST spring-forward gap"):
            creator.calculate_due_date("sunday", 2, 30)

    def test_normal_time_on_dst_week_is_accepted(self, mock_client):
        """Times outside the gap on a DST-transition week are accepted normally."""
        creator = WeeklyListCreator(mock_client, week_number=13, timezone="Europe/Paris")
        due = creator.calculate_due_date("sunday", 4, 0)
        assert due.hour == 4


class TestUTF8Support:
    """Regression tests for UTF-8 in all user-visible string fields."""

    def _yaml_file(self, content: str) -> Path:
        """Write UTF-8 YAML to a temp file and return its path."""
        import tempfile
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8')
        f.write(content)
        f.flush()
        f.close()
        return Path(f.name)

    def test_utf8_description(self):
        """Description with accented characters round-trips correctly."""
        path = self._yaml_file("""
cards:
  - title: "Task"
    day_of_week: "monday"
    hour: 9
    description: "Réunion de l'équipe — résumé"
""")
        try:
            cards = load_card_templates(path)
            assert cards[0].description == "Réunion de l'équipe — résumé"
        finally:
            path.unlink()

    def test_utf8_checklist_name(self):
        """Checklist name with non-ASCII characters round-trips correctly."""
        path = self._yaml_file("""
cards:
  - title: "Task"
    day_of_week: "monday"
    hour: 9
    checklists:
      - name: "Étapes à suivre"
        items: []
""")
        try:
            cards = load_card_templates(path)
            assert cards[0].checklists[0].name == "Étapes à suivre"
        finally:
            path.unlink()

    def test_utf8_checklist_items(self):
        """Checklist items with non-ASCII characters round-trip correctly."""
        path = self._yaml_file("""
cards:
  - title: "Task"
    day_of_week: "monday"
    hour: 9
    checklists:
      - name: "Steps"
        items:
          - "Vérifier les données"
          - "Créer le résumé"
          - "日本語テスト"
""")
        try:
            cards = load_card_templates(path)
            items = cards[0].checklists[0].items
            assert items == ["Vérifier les données", "Créer le résumé", "日本語テスト"]
        finally:
            path.unlink()

    def test_utf8_label_names(self):
        """Label names with non-ASCII characters round-trip correctly."""
        path = self._yaml_file("""
cards:
  - title: "Task"
    day_of_week: "monday"
    hour: 9
    labels:
      - "Müsli & Käse"
      - "Fiançailles"
""")
        try:
            cards = load_card_templates(path)
            assert cards[0].labels == ["Müsli & Käse", "Fiançailles"]
        finally:
            path.unlink()

    @patch.object(TrelloAPIClient, '_make_request')
    def test_utf8_card_name_reaches_api(self, mock_request):
        """create_card passes a UTF-8 title to the API unchanged."""
        config = TrelloConfig(api_key="k", api_token="t", board_id="b")
        client = TrelloAPIClient(config)
        mock_request.return_value = {"id": "card1"}

        client.create_card(
            list_id="list1",
            name="Réunion d'équipe 会議",
            due_date=datetime(2026, 3, 2, 10, 0),
            label_ids=[],
        )

        call_params = mock_request.call_args[1]["params"]
        assert call_params["name"] == "Réunion d'équipe 会議"

    @patch.object(TrelloAPIClient, '_make_request')
    def test_utf8_checklist_name_reaches_api(self, mock_request):
        """create_checklist passes a UTF-8 name to the API unchanged."""
        config = TrelloConfig(api_key="k", api_token="t", board_id="b")
        client = TrelloAPIClient(config)
        mock_request.return_value = {"id": "cl1"}

        client.create_checklist("card1", "Étapes à suivre")

        call_params = mock_request.call_args[1]["params"]
        assert call_params["name"] == "Étapes à suivre"

    @patch.object(TrelloAPIClient, '_make_request')
    def test_utf8_checklist_item_reaches_api(self, mock_request):
        """add_checklist_item passes a UTF-8 item name to the API unchanged."""
        config = TrelloConfig(api_key="k", api_token="t", board_id="b")
        client = TrelloAPIClient(config)
        mock_request.return_value = {"id": "item1"}

        client.add_checklist_item("cl1", "Vérifier les données 検証")

        call_params = mock_request.call_args[1]["params"]
        assert call_params["name"] == "Vérifier les données 検証"
