"""
Notification System

Handles sending notifications about identified opportunities through
various channels: console, file, email, Slack.
"""

import json
import logging
import smtplib
from abc import ABC, abstractmethod
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Any, Dict, List, Optional

from analyzers.base import Opportunity


logger = logging.getLogger(__name__)


class Notifier(ABC):
    """Abstract base class for notification backends."""

    @abstractmethod
    def send(self, opportunities: List[Opportunity]) -> None:
        """
        Send notifications for a list of opportunities.

        Args:
            opportunities: List of opportunities to notify about
        """
        pass

    def format_opportunity(self, opp: Opportunity) -> str:
        """
        Format an opportunity as a string.

        Args:
            opp: Opportunity to format

        Returns:
            Formatted string
        """
        lines = [
            f"=== {opp.opportunity_type.value.upper()} OPPORTUNITY ===",
            f"Confidence: {opp.confidence.value}",
            f"Time: {opp.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"Markets: {', '.join(opp.market_tickers)}",
        ]

        for ticker, title, url in zip(opp.market_tickers, opp.market_titles, opp.market_urls):
            lines.append(f"  - {title}")
            lines.append(f"    {url}")

        lines.extend([
            "",
            f"Current Prices:",
        ])
        for ticker, price in opp.current_prices.items():
            lines.append(f"  {ticker}: {price:.1f}¢")

        lines.extend([
            "",
            f"Estimated Edge: {opp.estimated_edge_cents:.1f}¢ ({opp.estimated_edge_percent:.1f}%)",
            "",
            f"Reasoning: {opp.reasoning}",
            "",
        ])

        return "\n".join(lines)


class ConsoleNotifier(Notifier):
    """Prints opportunities to the console."""

    def __init__(self, min_confidence: Optional[str] = None):
        """
        Initialize console notifier.

        Args:
            min_confidence: Minimum confidence level to notify (low/medium/high)
        """
        self.min_confidence = min_confidence

    def send(self, opportunities: List[Opportunity]) -> None:
        """Print opportunities to console."""
        filtered_opps = self._filter_by_confidence(opportunities)

        if not filtered_opps:
            logger.info("No opportunities to notify about")
            return

        print("\n" + "=" * 80)
        print(f"FOUND {len(filtered_opps)} OPPORTUNITY(IES)")
        print("=" * 80 + "\n")

        for opp in filtered_opps:
            print(self.format_opportunity(opp))
            print("-" * 80 + "\n")

    def _filter_by_confidence(self, opportunities: List[Opportunity]) -> List[Opportunity]:
        """Filter opportunities by minimum confidence level."""
        if not self.min_confidence:
            return opportunities

        confidence_order = {"low": 0, "medium": 1, "high": 2}
        min_level = confidence_order.get(self.min_confidence.lower(), 0)

        return [
            opp for opp in opportunities
            if confidence_order.get(opp.confidence.value, 0) >= min_level
        ]


class FileNotifier(Notifier):
    """Writes opportunities to a file (JSON or text)."""

    def __init__(self, file_path: str, format: str = "json"):
        """
        Initialize file notifier.

        Args:
            file_path: Path to output file
            format: Output format ('json' or 'text')
        """
        self.file_path = Path(file_path)
        self.format = format

    def send(self, opportunities: List[Opportunity]) -> None:
        """Write opportunities to file."""
        if not opportunities:
            return

        try:
            if self.format == "json":
                self._write_json(opportunities)
            else:
                self._write_text(opportunities)

            logger.info(f"Wrote {len(opportunities)} opportunities to {self.file_path}")

        except Exception as e:
            logger.error(f"Failed to write to file {self.file_path}: {e}")

    def _write_json(self, opportunities: List[Opportunity]) -> None:
        """Write opportunities as JSON."""
        data = {
            "timestamp": datetime.now().isoformat(),
            "count": len(opportunities),
            "opportunities": [opp.to_dict() for opp in opportunities],
        }

        # Append to existing file if it exists
        if self.file_path.exists():
            with open(self.file_path, "r") as f:
                try:
                    existing = json.load(f)
                    if isinstance(existing, list):
                        existing.append(data)
                        data = existing
                    else:
                        data = [existing, data]
                except json.JSONDecodeError:
                    pass  # Overwrite invalid JSON

        with open(self.file_path, "w") as f:
            json.dump(data, f, indent=2)

    def _write_text(self, opportunities: List[Opportunity]) -> None:
        """Write opportunities as text."""
        with open(self.file_path, "a") as f:
            f.write(f"\n{'=' * 80}\n")
            f.write(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Opportunities found: {len(opportunities)}\n")
            f.write(f"{'=' * 80}\n\n")

            for opp in opportunities:
                f.write(self.format_opportunity(opp))
                f.write(f"\n{'-' * 80}\n\n")


class EmailNotifier(Notifier):
    """Sends opportunities via email."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        sender: str,
        recipients: List[str],
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_tls: bool = True,
    ):
        """
        Initialize email notifier.

        Args:
            smtp_host: SMTP server hostname
            smtp_port: SMTP server port
            sender: Sender email address
            recipients: List of recipient email addresses
            username: SMTP username (optional)
            password: SMTP password (optional)
            use_tls: Whether to use TLS (default: True)
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.sender = sender
        self.recipients = recipients
        self.username = username or sender
        self.password = password
        self.use_tls = use_tls

    def send(self, opportunities: List[Opportunity]) -> None:
        """Send opportunities via email."""
        if not opportunities:
            return

        try:
            msg = self._create_message(opportunities)

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()

                if self.password:
                    server.login(self.username, self.password)

                server.send_message(msg)

            logger.info(f"Sent email with {len(opportunities)} opportunities")

        except Exception as e:
            logger.error(f"Failed to send email: {e}")

    def _create_message(self, opportunities: List[Opportunity]) -> MIMEMultipart:
        """Create email message."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Kalshi Opportunities: {len(opportunities)} found"
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)

        # Text version
        text_body = "\n\n".join(self.format_opportunity(opp) for opp in opportunities)
        msg.attach(MIMEText(text_body, "plain"))

        # HTML version
        html_body = self._create_html(opportunities)
        msg.attach(MIMEText(html_body, "html"))

        return msg

    def _create_html(self, opportunities: List[Opportunity]) -> str:
        """Create HTML version of notification."""
        html_parts = [
            "<html><body>",
            f"<h2>Kalshi Market Opportunities ({len(opportunities)})</h2>",
        ]

        for opp in opportunities:
            html_parts.append("<div style='margin-bottom: 20px; border: 1px solid #ccc; padding: 10px;'>")
            html_parts.append(f"<h3>{opp.opportunity_type.value.upper()}</h3>")
            html_parts.append(f"<p><strong>Confidence:</strong> {opp.confidence.value}</p>")

            html_parts.append("<ul>")
            for ticker, title, url in zip(opp.market_tickers, opp.market_titles, opp.market_urls):
                html_parts.append(f"<li><a href='{url}'>{title}</a></li>")
            html_parts.append("</ul>")

            html_parts.append(
                f"<p><strong>Edge:</strong> {opp.estimated_edge_cents:.1f}¢ "
                f"({opp.estimated_edge_percent:.1f}%)</p>"
            )
            html_parts.append(f"<p>{opp.reasoning}</p>")
            html_parts.append("</div>")

        html_parts.append("</body></html>")
        return "\n".join(html_parts)


class SlackNotifier(Notifier):
    """Sends opportunities to Slack via webhook."""

    def __init__(self, webhook_url: str, channel: Optional[str] = None):
        """
        Initialize Slack notifier.

        Args:
            webhook_url: Slack webhook URL
            channel: Optional channel override
        """
        self.webhook_url = webhook_url
        self.channel = channel

        try:
            import requests
            self.requests = requests
        except ImportError:
            logger.error("requests library required for SlackNotifier")
            self.requests = None

    def send(self, opportunities: List[Opportunity]) -> None:
        """Send opportunities to Slack."""
        if not self.requests:
            logger.error("Cannot send Slack notification: requests not available")
            return

        if not opportunities:
            return

        try:
            payload = self._create_payload(opportunities)

            response = self.requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            response.raise_for_status()
            logger.info(f"Sent Slack notification with {len(opportunities)} opportunities")

        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")

    def _create_payload(self, opportunities: List[Opportunity]) -> Dict[str, Any]:
        """Create Slack message payload."""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Kalshi Opportunities: {len(opportunities)} found",
                },
            }
        ]

        for opp in opportunities:
            # Opportunity header
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{opp.opportunity_type.value.upper()}* "
                        f"({opp.confidence.value} confidence)\n"
                        f"{opp.reasoning}"
                    ),
                },
            })

            # Market links
            market_links = []
            for ticker, title, url in zip(opp.market_tickers, opp.market_titles, opp.market_urls):
                market_links.append(f"• <{url}|{title}>")

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n".join(market_links),
                },
            })

            # Edge info
            blocks.append({
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Edge:* {opp.estimated_edge_cents:.1f}¢",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Return:* {opp.estimated_edge_percent:.1f}%",
                    },
                ],
            })

            blocks.append({"type": "divider"})

        payload = {"blocks": blocks}

        if self.channel:
            payload["channel"] = self.channel

        return payload


if __name__ == "__main__":
    # Simple test
    logging.basicConfig(level=logging.INFO)

    from analyzers.base import OpportunityType, ConfidenceLevel

    # Create test opportunity
    test_opp = Opportunity(
        opportunity_type=OpportunityType.WIDE_SPREAD,
        confidence=ConfidenceLevel.MEDIUM,
        timestamp=datetime.now(),
        market_tickers=["TEST-2025-01-01"],
        market_titles=["Test Market"],
        market_urls=["https://kalshi.com/markets/TEST"],
        current_prices={"TEST-2025-01-01": 50.0},
        estimated_edge_cents=5.0,
        estimated_edge_percent=10.0,
        reasoning="Test opportunity for demonstration",
        additional_data={},
    )

    # Test console notifier
    print("\n=== Testing Console Notifier ===")
    console = ConsoleNotifier()
    console.send([test_opp])

    # Test file notifier
    print("\n=== Testing File Notifier ===")
    file_notifier = FileNotifier("/tmp/kalshi_opportunities.txt", format="text")
    file_notifier.send([test_opp])
    print("Wrote to /tmp/kalshi_opportunities.txt")
