import email
import imaplib
from datetime import UTC, datetime
from email.header import decode_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime


def decode_mime_header(value: str | None) -> str:
    if not value:
        return ""
    parts: list[str] = []
    for chunk, encoding in decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(str(chunk))
    return "".join(parts).strip()


def message_datetime(message: Message) -> datetime | None:
    date_header = message.get("Date")
    if not date_header:
        return None
    try:
        parsed = parsedate_to_datetime(date_header)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def extract_body_and_attachments(
    message: Message,
) -> tuple[str | None, list[dict[str, str | None]]]:
    attachments: list[dict[str, str | None]] = []
    if message.is_multipart():
        text_parts: list[str] = []
        for part in message.walk():
            content_disposition = part.get_content_disposition()
            filename = part.get_filename()
            if filename:
                attachments.append(
                    {
                        "original_filename": decode_mime_header(filename),
                        "attachment_mime": part.get_content_type(),
                    }
                )
                continue
            if content_disposition == "attachment":
                continue
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    text_parts.append(payload.decode(charset, errors="replace"))
        body = "\n".join(text_parts).strip() or None
        return body, attachments
    payload = message.get_payload(decode=True)
    if payload is None:
        return None, attachments
    charset = message.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace").strip() or None, attachments


def parse_raw_email(raw_bytes: bytes) -> dict[str, object]:
    message = email.message_from_bytes(raw_bytes)
    message_id = (message.get("Message-ID") or "").strip()
    sender_name, sender_email = parseaddr(decode_mime_header(message.get("From")))
    subject = decode_mime_header(message.get("Subject"))
    body, attachments = extract_body_and_attachments(message)
    return {
        "message_id": message_id or None,
        "sender_name": sender_name or sender_email,
        "sender_email": sender_email.casefold() if sender_email else None,
        "subject": subject,
        "body": body,
        "occurred_at": message_datetime(message),
        "attachments": attachments,
        "raw_headers": dict(message.items()),
    }


def fetch_messages_since(
    *,
    host: str,
    username: str,
    password: str,
    since: datetime,
) -> list[dict[str, object]]:
    since_label = since.strftime("%d-%b-%Y")
    connection = imaplib.IMAP4_SSL(host)
    connection.login(username, password)
    connection.select("INBOX", readonly=True)
    status, data = connection.search(None, f"(SINCE {since_label})")
    if status != "OK" or not data or not data[0]:
        connection.logout()
        return []
    parsed_messages: list[dict[str, object]] = []
    for num in data[0].split():
        fetch_status, fetched = connection.fetch(num, "(BODY.PEEK[])")
        if fetch_status != "OK" or not fetched:
            continue
        raw_bytes = b""
        for item in fetched:
            if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
                raw_bytes = item[1]
                break
        if not raw_bytes:
            continue
        parsed = parse_raw_email(raw_bytes)
        parsed_messages.append(parsed)
    connection.logout()
    return parsed_messages
