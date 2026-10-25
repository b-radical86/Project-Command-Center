import re
from typing import List, Dict, Any, Tuple

# Regex patterns for secret scrubbing
SECRET_PATTERNS = [
    # GitHub Tokens
    (re.compile(r'ghp_[A-Za-z0-9_]{36,}', re.IGNORECASE), '[REDACTED_GH_PAT]'),
    (re.compile(r'gho_[A-Za-z0-9_]{36,}', re.IGNORECASE), '[REDACTED_GH_OAUTH]'),
    (re.compile(r'github_pat_[A-Za-z0-9_]{50,}', re.IGNORECASE), '[REDACTED_GH_FINE_PAT]'),
    (re.compile(r'ghs_[A-Za-z0-9_]{36,}', re.IGNORECASE), '[REDACTED_GH_APP_TOKEN]'),
    
    # Google AI / GCP API keys
    (re.compile(r'AIza[0-9A-Za-z\-_]{35}', re.IGNORECASE), '[REDACTED_GEMINI_KEY]'),
    (re.compile(r'AQ\.[A-Za-z0-9\-_]{40,}', re.IGNORECASE), '[REDACTED_GEMINI_KEY]'),
    
    # OpenAI & other keys
    (re.compile(r'sk-[A-Za-z0-9\-_]{32,}', re.IGNORECASE), '[REDACTED_API_KEY]'),
    (re.compile(r're_[A-Za-z0-9_]{24,}', re.IGNORECASE), '[REDACTED_RESEND_KEY]'),
    
    # Private Keys
    (re.compile(r'-----BEGIN[ A-Z_-]*PRIVATE KEY-----[\s\S]*?-----END[ A-Z_-]*PRIVATE KEY-----'), '[REDACTED_PRIVATE_KEY]'),
    
    # Basic Authorization / Bearer tokens
    (re.compile(r'(?i)(bearer\s+)[a-zA-Z0-9_\-\.]{20,}'), r'\1[REDACTED_BEARER_TOKEN]'),
    
    # Sensitive URL credentials (e.g. postgres://user:password@host)
    (re.compile(r'://([^:]+):([^@]+)@'), r'://\1:[REDACTED_PWD]@'),
    
    # Email addresses
    (re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'), '[REDACTED_EMAIL]'),
]

CHECKBOX_PATTERN = re.compile(r'^\s*[-*+]\s+\[([ xX])\]\s*(.*)$', re.MULTILINE)
TODO_FIXME_PATTERN = re.compile(r'(?i)\b(TODO|FIXME|BUG|BLOCKER)\b:?\s*(.*)')

def scrub_secrets(text: str) -> str:
    """Scrub sensitive credentials, tokens, and personal identifiers from text."""
    if not text:
        return ""
    sanitized = text
    for pattern, replacement in SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized

def truncate_text(text: str, max_chars: int = 10000) -> str:
    """
    Enforce ceiling on file content:
    If > max_chars, retain first 8,000 + last 2,000 characters.
    """
    if not text or len(text) <= max_chars:
        return text
    first_chunk = text[:8000]
    last_chunk = text[-2000:]
    return f"{first_chunk}\n\n... [TRUNCATED {len(text) - 10000} CHARACTERS FOR EFFICIENCY] ...\n\n{last_chunk}"

def parse_markdown_content(content: str, file_path: str = "") -> Dict[str, Any]:
    """
    Extract checkboxes, TODOs, and calculate completion stats deterministically.
    """
    completed_items: List[Dict[str, Any]] = []
    pending_items: List[Dict[str, Any]] = []
    todo_items: List[Dict[str, Any]] = []
    
    lines = content.splitlines()
    for idx, line in enumerate(lines, start=1):
        # Match markdown checkbox
        cb_match = CHECKBOX_PATTERN.match(line)
        if cb_match:
            mark, title = cb_match.groups()
            title = title.strip()
            if not title:
                continue
            item = {
                "title": title,
                "file_path": file_path,
                "line_number": idx,
                "is_completed": mark.lower() == 'x',
            }
            if item["is_completed"]:
                completed_items.append(item)
            else:
                pending_items.append(item)
        else:
            # Check for TODO / FIXME
            todo_match = TODO_FIXME_PATTERN.search(line)
            if todo_match:
                tag, detail = todo_match.groups()
                clean_detail = detail.strip() or line.strip()
                todo_items.append({
                    "title": f"[{tag.upper()}] {clean_detail}",
                    "file_path": file_path,
                    "line_number": idx,
                    "is_completed": False
                })
                
    total_checks = len(completed_items) + len(pending_items)
    completion_pct = (len(completed_items) / total_checks * 100.0) if total_checks > 0 else 0.0

    return {
        "file_path": file_path,
        "completed_count": len(completed_items),
        "pending_count": len(pending_items),
        "total_checkboxes": total_checks,
        "completion_pct": round(completion_pct, 1),
        "completed_items": completed_items,
        "pending_items": pending_items,
        "todo_items": todo_items,
    }

def process_harvested_docs(docs: Dict[str, str]) -> Dict[str, Any]:
    """
    Process multiple harvested markdown documents for a repository.
    Returns sanitized texts, aggregate completion percentage, and combined action items.
    """
    sanitized_docs: Dict[str, str] = {}
    all_action_items: List[Dict[str, Any]] = []
    total_completed = 0
    total_pending = 0
    
    for file_path, raw_text in docs.items():
        # 1. Scrub secrets
        cleaned = scrub_secrets(raw_text)
        # 2. Parse checkboxes and TODOs
        parsed = parse_markdown_content(cleaned, file_path=file_path)
        all_action_items.extend(parsed["pending_items"])
        all_action_items.extend(parsed["todo_items"])
        total_completed += parsed["completed_count"]
        total_pending += parsed["pending_count"]
        # 3. Truncate for token efficiency
        sanitized_docs[file_path] = truncate_text(cleaned)
        
    total_boxes = total_completed + total_pending
    aggregate_pct = (total_completed / total_boxes * 100.0) if total_boxes > 0 else 0.0
    
    return {
        "sanitized_docs": sanitized_docs,
        "all_action_items": all_action_items,
        "total_completed": total_completed,
        "total_pending": total_pending,
        "completion_pct": round(aggregate_pct, 1),
    }
