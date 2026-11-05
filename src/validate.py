def clean_list(value, max_items, max_len):
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip()[:max_len])
        if len(out) == max_items:
            break
    return out

def clean_result(raw):
    if not isinstance(raw, dict):
        raw = {}

    try:
        score = int(raw.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))

    return {
        "score": score,
        "matched_skills": clean_list(raw.get("matched_skills"), 30, 60),
        "missing_skills": clean_list(raw.get("missing_skills"), 30, 60),
        "suggestions": clean_list(raw.get("suggestions"), 5, 300),
    }