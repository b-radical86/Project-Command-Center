import re
import json
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from app.db import get_connection

# Common English stop words for idea deduplication
STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
    "by", "could", "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him",
    "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me",
    "more", "most", "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "she", "should",
    "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves", "then",
    "there", "these", "they", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom", "why",
    "with", "would", "you", "your", "yours", "yourself", "yourselves",
    # Domain generic terms
    "tool", "app", "system", "platform", "service", "project", "framework", "library"
}


def stem_word(w: str) -> str:
    """Basic domain-aware suffix stripper and root normalizer."""
    w = w.lower()
    if w.startswith("crypto"):
        return "crypto"
    for suffix in ["analyzer", "calculator", "tracking", "tracker", "ing", "tion", "tions", "ers", "er", "ies", "ied", "ed", "es", "s", "ment", "ments"]:
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[:-len(suffix)]
    return w


def tokenize_text(text: str) -> set:
    """Normalize text into clean stemmed word token set."""
    if not text:
        return set()
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    tokens = {stem_word(word) for word in cleaned.split() if len(word) > 2 and word not in STOP_WORDS}
    return tokens


def calculate_jaccard_similarity(tokens1: set, tokens2: set) -> float:
    """Compute Jaccard token overlap between two token sets."""
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union)


def calculate_levenshtein_ratio(s1: str, s2: str) -> float:
    """Calculate normalized character similarity ratio between two strings."""
    s1, s2 = s1.lower().strip(), s2.lower().strip()
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    # Fast path: substring match
    if s1 in s2 or s2 in s1:
        return min(len(s1), len(s2)) / max(len(s1), len(s2))
    
    # Simple dynamic programming Levenshtein distance
    len1, len2 = len(s1), len(s2)
    if abs(len1 - len2) > max(len1, len2) * 0.7:
        return 0.0
        
    dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]
    for i in range(len1 + 1):
        dp[i][0] = i
    for j in range(len2 + 1):
        dp[0][j] = j

    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)

    distance = dp[len1][len2]
    max_len = max(len1, len2)
    return 1.0 - (distance / max_len)


def calculate_idea_similarity(title1: str, desc1: str, title2: str, desc2: str) -> Tuple[float, Dict[str, float]]:
    """
    Calculate composite similarity score between two project ideas (0.0 to 1.0).
    Combines title token overlap, shared domain keywords, and description overlap.
    """
    t_tokens1, t_tokens2 = tokenize_text(title1), tokenize_text(title2)
    d_tokens1, d_tokens2 = tokenize_text(desc1), tokenize_text(desc2)

    shared_title_words = len(t_tokens1.intersection(t_tokens2))
    title_jaccard = calculate_jaccard_similarity(t_tokens1, t_tokens2)
    title_char_sim = calculate_levenshtein_ratio(title1, title2)
    desc_jaccard = calculate_jaccard_similarity(d_tokens1, d_tokens2)

    effective_title_sim = max(title_jaccard, title_char_sim)

    # Significant boost when multiple root concepts in the title match
    boost = 0.30 if shared_title_words >= 3 else (0.20 if shared_title_words >= 2 else 0.0)
    composite_score = min(1.0, (effective_title_sim * 0.55) + (desc_jaccard * 0.35) + boost)

    return round(composite_score, 3), {
        "title_similarity": round(effective_title_sim, 3),
        "desc_similarity": round(desc_jaccard, 3),
        "shared_title_roots": shared_title_words,
    }


def find_duplicate_ideas(title: str, description: str, threshold: float = 0.55) -> List[Dict[str, Any]]:
    """
    Search historical project ideas in SQLite and return any existing ideas with
    similarity scores exceeding the threshold.
    """
    conn = get_connection()
    duplicates = []
    try:
        rows = conn.execute("SELECT id, title, description, domain_tag, source, status, notes, created_at FROM project_ideas").fetchall()
        for r in rows:
            existing = dict(r)
            score, metrics = calculate_idea_similarity(title, description, existing["title"], existing["description"])
            if score >= threshold:
                duplicates.append({
                    "existing_idea": existing,
                    "similarity_score": score,
                    "metrics": metrics,
                    "is_exact_match": score >= 0.85,
                    "is_strong_duplicate": score >= 0.60,
                })
        
        # Sort by highest similarity score first
        duplicates.sort(key=lambda x: x["similarity_score"], reverse=True)
        return duplicates
    finally:
        conn.close()


def save_project_idea(
    title: str,
    description: str,
    domain_tag: str = "General",
    source: str = "user",
    status: str = "parked",
    notes: Optional[str] = None,
    tags: Optional[List[str]] = None,
    force: bool = False
) -> Dict[str, Any]:
    """
    Save a new project idea with automated duplicate checking.
    If force is False and a duplicate is found with score >= 0.55, prevents creation
    and returns the conflicting historical idea.
    """
    title = title.strip()
    description = description.strip()
    if not title:
        raise ValueError("Idea title cannot be empty")

    duplicates = find_duplicate_ideas(title, description, threshold=0.55)

    if duplicates and not force and duplicates[0]["similarity_score"] >= 0.55:
        return {
            "created": False,
            "reason": "duplicate_found",
            "message": f"Similar historical idea already exists: '{duplicates[0]['existing_idea']['title']}' (Match: {int(duplicates[0]['similarity_score'] * 100)}%)",
            "duplicate_match": duplicates[0],
            "all_matches": duplicates,
        }

    token_str = " ".join(sorted(tokenize_text(f"{title} {description}")))
    tags_json = json.dumps(tags or [])

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO project_ideas (title, description, domain_tag, source, status, tags, similarity_keywords, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (title, description, domain_tag, source, status, tags_json, token_str, notes or ""))
        idea_id = cursor.lastrowid
        conn.commit()

        row = conn.execute("SELECT * FROM project_ideas WHERE id = ?", (idea_id,)).fetchone()
        return {
            "created": True,
            "idea": dict(row),
            "similar_past_ideas": duplicates,
        }
    finally:
        conn.close()


def list_project_ideas(
    status: Optional[str] = None,
    domain: Optional[str] = None,
    search: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve historical project ideas with optional filtering and keyword search."""
    conn = get_connection()
    try:
        query = "SELECT * FROM project_ideas WHERE 1=1"
        params: List[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if domain:
            query += " AND domain_tag = ?"
            params.append(domain)
        if search:
            query += " AND (title LIKE ? OR description LIKE ? OR notes LIKE ?)"
            term = f"%{search}%"
            params.extend([term, term, term])

        query += " ORDER BY updated_at DESC, id DESC"
        rows = conn.execute(query, params).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            try:
                d["tags"] = json.loads(d["tags"] or "[]")
            except Exception:
                d["tags"] = []
            results.append(d)
        return results
    finally:
        conn.close()


def update_project_idea(
    idea_id: int,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    domain_tag: Optional[str] = None,
    graduated_repo_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Update status, notes, or graduation link for an existing historical idea."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM project_ideas WHERE id = ?", (idea_id,)).fetchone()
        if not row:
            return None

        updates = []
        params = []
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        if domain_tag is not None:
            updates.append("domain_tag = ?")
            params.append(domain_tag)
        if graduated_repo_id is not None:
            updates.append("graduated_repo_id = ?")
            params.append(graduated_repo_id)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            sql = f"UPDATE project_ideas SET {', '.join(updates)} WHERE id = ?"
            params.append(idea_id)
            conn.execute(sql, params)
            conn.commit()

        updated_row = conn.execute("SELECT * FROM project_ideas WHERE id = ?", (idea_id,)).fetchone()
        res = dict(updated_row)
        try:
            res["tags"] = json.loads(res["tags"] or "[]")
        except Exception:
            res["tags"] = []
        return res
    finally:
        conn.close()
