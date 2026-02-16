import re
import requests
from datetime import datetime
import textwrap
from typing import Dict, Any

ALERTS_URL = "https://s3.amazonaws.com/st-service-alerts-prod/alerts_pb.json"

def _color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"

SEVERITY_BG = {
    "WARNING": "1;43",  # bold yellow bg
    "INFO": "1;42",     # bold green bg
    "SEVERE": "1;41",   # bold red bg
}
EFFECT_FG = {
    "ACCESSIBILITY_ISSUE": "1;35",  # magenta
    "NO_SERVICE": "1;31",           # red
    "OTHER_EFFECT": "1;33",         # yellow
    "ADDITIONAL_SERVICE": "1;32",   # green
}

def _safe_translation(obj: Dict[str, Any], key: str) -> str:
    # return first translation text if present
    try:
        trans = obj.get(key, {}).get("translation", [])
        if trans and isinstance(trans, list):
            return trans[0].get("text", "").strip()
    except Exception:
        pass
    return ""

def _fmt_time(ts):
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)

def summarize_alert(entity: Dict[str, Any]) -> str:
    aid = entity.get("id", "")
    alert = entity.get("alert", {})
    effect = alert.get("effect", "UNKNOWN")
    severity = alert.get("severity_level", "UNKNOWN")
    header = _safe_translation(alert, "header_text") or _safe_translation(alert, "description_text") or "(no header)"
    description = _safe_translation(alert, "description_text")
    if description:
        description = " ".join(description.splitlines())
    # Active period - use first period
    active = alert.get("active_period", [])
    start = active[0].get("start") if active else None
    end = active[0].get("end") if active and active[0].get("end") else None

    # informed entities summary
    informed = alert.get("informed_entity", [])
    ie_parts = []
    for ie in informed[:6]:  # limit to first few entries
        parts = []
        if "agency_id" in ie:
            parts.append(f"agency={ie.get('agency_id')}")
        if "route_id" in ie:
            parts.append(f"route={ie.get('route_id')}")
        if "stop_id" in ie:
            parts.append(f"stop={ie.get('stop_id')}")
        if "trip" in ie:
            trip = ie["trip"]
            parts.append(f"trip={trip.get('trip_id','?')}")
        if parts:
            ie_parts.append("/".join(parts))
    ie_text = ", ".join(ie_parts) if ie_parts else "all entities"

    # colors
    sev_code = SEVERITY_BG.get(severity, "1;44")  # default bold blue bg
    eff_code = EFFECT_FG.get(effect, "1;36")      # default cyan
    header_line = f"{_color(severity, sev_code)} {_color(effect, eff_code)} ID:{aid}"
    header_text = _color(header, "1;37")  # bold white for header text
    time_text = f"{_fmt_time(start)}{(' — ' + _fmt_time(end)) if end else ''}"

    wrapped_header_line = textwrap.fill(header_line, width=78)
    wrapped_time_text = textwrap.fill(time_text, width=78)
    wrapped_header_text = textwrap.fill(header_text, width=78)
    wrapped_ie_text = textwrap.fill(ie_text, width=78)
    # description truncated
    # desc_clean = (description[:240] + "...") if description and len(description) > 240 else (description or "")
    wrapped_desc = description # textwrap.fill(description, width=78)

    out_lines = [
        f"{wrapped_header_line} {wrapped_time_text}",
        f"  {wrapped_header_text}",
        f"  Entities: {wrapped_ie_text}",
    ]
    if wrapped_desc:
        # print(f"{wrapped_desc=}")
        wrapped_desc = "\n" + wrapped_desc
        wrapped_desc = wrapped_desc.replace(" " * 4, "\n")
        wrapped_desc = wrapped_desc.replace(" " * 2, "\n")
        wrapped_desc = wrapped_desc.replace("•", "\n•")
        wrapped_desc = re.sub(r"\. (\d+)\.", r".\n\1.", wrapped_desc)
        out_lines.append(f"{wrapped_desc}")
    return "\n".join(out_lines)

def fetch_and_print(url: str = ALERTS_URL):
    try:
        resp = requests.get(url, timeout=10)
    except Exception as e:
        print(_color("Network error fetching alerts:", "1;31"), str(e))
        return
    if resp.status_code != 200:
        print(_color("Failed to fetch alerts:", "1;31"), resp.status_code)
        return
    try:
        data = resp.json()
    except Exception as e:
        print(_color("Failed to parse JSON:", "1;31"), str(e))
        return

    entities = data.get("entity", [])
    if not entities:
        print(_color("No alerts found.", "1;33"))
        return

    # sort alerts by active start time descending (most recent first)
    def _start_of(e):
        try:
            ap = e.get("alert", {}).get("active_period", [])
            return ap[0].get("start", 0) if ap else 0
        except Exception:
            return 0
    for ent in sorted(entities, key=_start_of, reverse=True):
        print(summarize_alert(ent))
        print("-" * 80)

if __name__ == "__main__":
    fetch_and_print()