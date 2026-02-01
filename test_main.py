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

    def test_with_description(self):
        """Card with description."""
        card = CardTemplate(
            title="Test",
            day_of_week="monday",
            hour=10,
            description="Some details"
        )
        assert card.description == "Some details"


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
        return client

    def test_get_next_week_number(self, mock_client):
        """get_next_week_number returns correct week."""
        creator = WeeklyListCreator(mock_client)
        week_num = creator.get_next_week_number()
        expected = (datetime.now() + timedelta(weeks=1)).isocalendar()[1]
        assert week_num == expected

    def test_calculate_due_date(self, mock_client):
        """calculate_due_date returns correct datetime."""
        creator = WeeklyListCreator(mock_client)
        due = creator.calculate_due_date("monday", 10, 30)
        assert due.weekday() == 0  # Monday
        assert due.hour == 10
        assert due.minute == 30

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
