"""
Trello Weekly List Creator
Creates weekly Trello lists with predefined cards.
"""
import argparse
import os
import sys
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from pathlib import Path
import yaml
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load .env file from script directory
load_dotenv(Path(__file__).parent / ".env")

# Module-level logger
logger = logging.getLogger(__name__)


@dataclass
class TrelloConfig:
    """Configuration for Trello API credentials."""
    api_key: str
    api_token: str
    board_id: str
    base_url: str = "https://api.trello.com/1"

    @classmethod
    def from_env(cls) -> "TrelloConfig":
        """Load configuration from environment variables."""
        api_key = os.getenv("TRELLO_API_KEY")
        api_token = os.getenv("TRELLO_API_TOKEN")
        board_id = os.getenv("TRELLO_BOARD_ID")
        
        if not all([api_key, api_token, board_id]):
            raise ValueError(
                "Missing required environment variables: "
                "TRELLO_API_KEY, TRELLO_API_TOKEN, TRELLO_BOARD_ID"
            )
        
        return cls(api_key=api_key, api_token=api_token, board_id=board_id)


@dataclass
class CardTemplate:
    """Template for creating a Trello card."""
    title: str
    day_of_week: str
    hour: int
    minute: int = 0
    labels: List[str] = field(default_factory=list)
    description: str = ""

    def __post_init__(self):
        """Validate card template data."""
        valid_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        if self.day_of_week.lower() not in valid_days:
            raise ValueError(f"Invalid day_of_week: {self.day_of_week}. Must be one of {valid_days}")
        
        if not 0 <= self.hour <= 23:
            raise ValueError(f"Invalid hour: {self.hour}. Must be between 0 and 23")
        
        if not 0 <= self.minute <= 59:
            raise ValueError(f"Invalid minute: {self.minute}. Must be between 0 and 59")


class TrelloAPIClient:
    """Client for interacting with Trello API."""

    def __init__(self, config: TrelloConfig):
        """Initialize the Trello API client with retry logic."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Setup session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)

    def _get_auth_params(self) -> Dict[str, str]:
        """Get authentication parameters for API requests."""
        return {
            "key": self.config.api_key,
            "token": self.config.api_token
        }

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make an authenticated request to the Trello API."""
        url = f"{self.config.base_url}/{endpoint}"
        request_params = self._get_auth_params()
        
        if params:
            request_params.update(params)

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=request_params,
                json=json_data,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API request failed: {e}")
            raise

    def get_board_lists(self) -> List[Dict[str, Any]]:
        """Get all lists from the board."""
        return self._make_request(
            method="GET",
            endpoint=f"boards/{self.config.board_id}/lists"
        )

    def list_exists(self, name: str) -> bool:
        """Check if a list with the given name already exists."""
        lists = self.get_board_lists()
        return any(lst["name"] == name for lst in lists)

    def create_list(self, name: str, position: str = "top") -> str:
        """Create a new list on the board."""
        self.logger.info(f"Creating list: {name}")
        data = self._make_request(
            method="POST",
            endpoint="lists",
            params={
                "name": name,
                "idBoard": self.config.board_id,
                "pos": position
            }
        )
        return data["id"]

    def get_board_labels(self) -> Dict[str, str]:
        """Get all labels from the board, returning a map of name to ID."""
        self.logger.info("Fetching board labels")
        labels = self._make_request(
            method="GET",
            endpoint=f"boards/{self.config.board_id}/labels"
        )
        return {label["name"]: label["id"] for label in labels}

    def create_card(
        self,
        list_id: str,
        name: str,
        due_date: datetime,
        label_ids: List[str],
        description: str = ""
    ) -> str:
        """Create a card in the specified list."""
        self.logger.info(f"Creating card: {name}")
        
        params = {
            "idList": list_id,
            "name": name,
            "due": due_date.isoformat(),
            "pos": "bottom"
        }
        
        if label_ids:
            params["idLabels"] = ",".join(label_ids)
        
        if description:
            params["desc"] = description

        data = self._make_request(method="POST", endpoint="cards", params=params)
        return data["id"]


class WeeklyListCreator:
    """Creates weekly Trello lists with predefined cards."""

    DAYS_OF_WEEK = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6
    }

    def __init__(self, client: TrelloAPIClient, dry_run: bool = False, position: str = "top", week_number: Optional[int] = None):
        """Initialize the weekly list creator."""
        self.client = client
        self.dry_run = dry_run
        self.position = position
        self.week_number = week_number
        self.logger = logging.getLogger(__name__)

    def get_current_week_number(self) -> int:
        """Get the ISO week number for the current week."""
        return datetime.now().isocalendar()[1]

    def get_week_start(self, week_number: Optional[int] = None) -> datetime:
        """Get the datetime for the start of the specified week (Monday at 00:00).
        
        If week_number is None, returns the start of the current week.
        """
        today = datetime.now()
        current_week = today.isocalendar()[1]
        current_year = today.isocalendar()[0]
        
        if week_number is None:
            week_number = current_week
        
        # Calculate the Monday of the target week
        # ISO week 1 is the week containing January 4th
        jan4 = datetime(current_year, 1, 4)
        jan4_weekday = jan4.weekday()  # Monday = 0
        week1_monday = jan4 - timedelta(days=jan4_weekday)
        target_monday = week1_monday + timedelta(weeks=week_number - 1)
        
        return target_monday.replace(hour=0, minute=0, second=0, microsecond=0)

    def calculate_due_date(self, day_of_week: str, hour: int, minute: int = 0) -> datetime:
        """Calculate the due date for a card based on day of week, hour, and minute."""
        week_start = self.get_week_start(self.week_number)
        day_offset = self.DAYS_OF_WEEK[day_of_week.lower()]
        due_date = week_start + timedelta(days=day_offset, hours=hour, minutes=minute)
        return due_date

    def resolve_label_ids(
        self,
        label_names: List[str],
        board_labels: Dict[str, str]
    ) -> List[str]:
        """Resolve label names to label IDs."""
        label_ids = []
        for name in label_names:
            if name in board_labels:
                label_ids.append(board_labels[name])
            else:
                self.logger.warning(f"Label '{name}' not found on board, skipping")
        return label_ids

    def create_weekly_list(self, cards: List[CardTemplate]) -> None:
        """Create a weekly list with predefined cards."""
        week_number = self.week_number if self.week_number else self.get_current_week_number()
        list_name = f"Todo w{week_number:02d}"
        
        self.logger.info(f"Starting weekly list creation: {list_name}")
        
        # Check for duplicate list
        if not self.dry_run and self.client.list_exists(list_name):
            self.logger.warning(f"List '{list_name}' already exists, skipping creation")
            return
        
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create list: {list_name} at position: {self.position}")
            for card in cards:
                due_date = self.calculate_due_date(card.day_of_week, card.hour, card.minute)
                self.logger.info(f"[DRY-RUN] Would create card: {card.title} (due: {due_date})")
            self.logger.info(f"[DRY-RUN] Would create {len(cards)} cards total")
            return
        
        # Create the list
        list_id = self.client.create_list(list_name, self.position)
        self.logger.info(f"List created with ID: {list_id}")
        
        # Get board labels
        board_labels = self.client.get_board_labels()
        
        # Create cards
        for card in cards:
            due_date = self.calculate_due_date(card.day_of_week, card.hour, card.minute)
            label_ids = self.resolve_label_ids(card.labels, board_labels)
            
            self.client.create_card(
                list_id=list_id,
                name=card.title,
                due_date=due_date,
                label_ids=label_ids,
                description=card.description
            )
        
        self.logger.info(f"Successfully created {len(cards)} cards in list {list_name}")


def load_card_templates(yaml_path: Path) -> List[CardTemplate]:
    """Load card templates from YAML file."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"Cards configuration not found: {yaml_path}")
    
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    cards = []
    for item in data.get("cards", []):
        cards.append(CardTemplate(
            title=item["title"],
            day_of_week=item["day_of_week"],
            hour=item["hour"],
            minute=item.get("minute", 0),
            labels=item.get("labels", []),
            description=item.get("description", "")
        ))
    
    return cards


def setup_logging(log_dir: Path) -> None:
    """Setup logging configuration with file and console handlers."""
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"trello_automation_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Create weekly Trello lists with predefined cards")
    parser.add_argument(
        "--dry-run", 
        action="store_true",
        help="Preview what would be created without making API calls"
    )
    parser.add_argument(
        "--position",
        choices=["top", "bottom"],
        default="top",
        help="Position for the new list (default: top)"
    )
    parser.add_argument(
        "--week",
        type=int,
        metavar="N",
        help="Week number to create (1-53). Defaults to current week."
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point for the script."""
    args = parse_args()
    script_dir = Path(__file__).parent
    
    # Setup logging first
    log_dir = Path(os.getenv("LOG_DIR", script_dir / "logs"))
    setup_logging(log_dir)
    
    try:
        logger.info("Starting Trello Weekly List Creator")
        if args.dry_run:
            logger.info("Running in DRY-RUN mode - no changes will be made")
        
        # Load configuration
        config = TrelloConfig.from_env()
        
        # Load card templates
        yaml_path = Path(os.getenv("CARDS_YAML_PATH", script_dir / "config" / "cards.yaml"))
        cards = load_card_templates(yaml_path)
        logger.info(f"Loaded {len(cards)} card templates")
        
        # Create weekly list
        client = TrelloAPIClient(config)
        creator = WeeklyListCreator(client, dry_run=args.dry_run, position=args.position, week_number=args.week)
        creator.create_weekly_list(cards)
        
        logger.info("Weekly list creation completed successfully")
        return 0
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
