"""OSV.dev API wrapper for vulnerability data."""

from __future__ import annotations

import httpx

OSV_API = "https://api.osv.dev/v1"


async def query_vulnerabilities(package_name: str, ecosystem: str = "npm") -> dict:
    """Query OSV.dev for known vulnerabilities of a package."""
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {
            "package": {
                "name": package_name,
                "ecosystem": ecosystem,
            }
        }
        resp = await client.post(f"{OSV_API}/query", json=payload)
        resp.raise_for_status()
        data = resp.json()

        vulns = data.get("vulns", [])

        # Categorize by severity
        critical = high = medium = low = 0
        parsed_vulns = []

        for v in vulns:
            severity = _extract_severity(v)
            if severity == "CRITICAL":
                critical += 1
            elif severity == "HIGH":
                high += 1
            elif severity == "MEDIUM":
                medium += 1
            else:
                low += 1

            affected_versions = []
            for affected in v.get("affected", []):
                for r in affected.get("ranges", []):
                    for event in r.get("events", []):
                        if "introduced" in event:
                            affected_versions.append(f">={event['introduced']}")
                        if "fixed" in event:
                            affected_versions.append(f"<{event['fixed']}")

            parsed_vulns.append({
                "id": v.get("id", ""),
                "summary": v.get("summary", v.get("details", "")[:200]),
                "severity": severity,
                "published": v.get("published", ""),
                "modified": v.get("modified", ""),
                "affected_versions": affected_versions,
            })

        return {
            "package_name": package_name,
            "ecosystem": ecosystem,
            "total_vulnerabilities": len(vulns),
            "critical": critical,
            "high": high,
            "medium": medium,
            "low": low,
            "vulnerabilities": parsed_vulns,
        }


def _extract_severity(vuln: dict) -> str:
    """Extract severity from a vulnerability entry."""
    # Check database_specific severity
    db_specific = vuln.get("database_specific", {})
    if "severity" in db_specific:
        return db_specific["severity"].upper()

    # Check CVSS from severity array
    for sev in vuln.get("severity", []):
        score_str = sev.get("score", "")
        if "CVSS" in sev.get("type", ""):
            # Parse CVSS vector for score
            try:
                # Extract base score from CVSS vector or direct score
                if score_str.replace(".", "").replace("-", "").isdigit():
                    score = float(score_str)
                    if score >= 9.0:
                        return "CRITICAL"
                    elif score >= 7.0:
                        return "HIGH"
                    elif score >= 4.0:
                        return "MEDIUM"
                    else:
                        return "LOW"
            except (ValueError, IndexError):
                pass

    # Check ecosystem-specific severity
    for affected in vuln.get("affected", []):
        eco_specific = affected.get("ecosystem_specific", {})
        if "severity" in eco_specific:
            return eco_specific["severity"].upper()

    return "UNKNOWN"
