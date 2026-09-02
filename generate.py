from __future__ import annotations

import html
import json
import os
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OWNER = "G-Glitch404"
API = "https://api.github.com"
ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
TOKEN = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")

FEATURED = [
    ("RedditScraper", "Reddit extraction and analysis platform"),
    ("xActionsWrapper", "Containerized X scraping microservice"),
    ("TelegramCrawler", "Telegram crawling and data processing service"),
    ("investing.com-scraper", "Financial content extraction actor"),
    ("RedditCrawler", "FastAPI Reddit crawling service"),
    ("Seleniumbase-Template", "Reusable browser automation foundation"),
]

FOCUS = [
    ("Python Automation", 96),
    ("Web Data Extraction", 92),
    ("Backend Engineering", 84),
    ("Browser Automation", 78),
    ("Data Processing", 72),
    ("Security", 58),
    ("Reverse Engineering", 46),
    ("Low-Level Programming", 38),
]

PALETTE = {
    "bg": "#0d1117",
    "panel": "#161b22",
    "panel2": "#11161d",
    "border": "#30363d",
    "text": "#f0f6fc",
    "muted": "#8b949e",
    "accent": "#58a6ff",
    "accent2": "#2f81f7",
    "green": "#3fb950",
    "purple": "#bc8cff",
    "orange": "#f0883e",
    "cyan": "#39d0d8",
}

LANGUAGE_COLORS = {
    "Python": "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "SQL": "#e38c00",
    "Shell": "#89e051",
    "C": "#555555",
    "C++": "#f34b7d",
    "Assembly": "#6E4C13",
}


def request_json(url: str, params: dict | None = None) -> dict | list:
    """Fetch JSON from the GitHub API"""
    if params:
        url = f"{url}?{urlencode(params)}"

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
        "User-Agent": f"{OWNER}-profile-dashboard",
    }

    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    request = Request(url, headers=headers)

    for attempt in range(4):
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in {403, 429} and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise
        except URLError:
            if attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise

    raise RuntimeError("GitHub API request failed")


def fetch_user() -> dict:
    """Fetch public profile data"""
    return request_json(f"{API}/users/{OWNER}")


def fetch_repositories() -> list[dict]:
    """Fetch all public repositories owned by the profile"""
    repositories = []

    for page in range(1, 10):
        items = request_json(
            f"{API}/users/{OWNER}/repos",
            {
                "per_page": 100,
                "page": page,
                "type": "owner",
                "sort": "updated",
            },
        )

        if not items:
            break

        repositories.extend(items)

        if len(items) < 100:
            break

    return [
        repository
        for repository in repositories
        if not repository.get("fork")
    ]


def fetch_repository_commits(
    repository: dict,
    since: datetime,
    until: datetime | None = None,
) -> list[dict]:
    """Fetch commits authored by the profile for one repository"""
    commits = []
    page = 1

    while page <= 20:
        params = {
            "author": OWNER,
            "since": since.isoformat().replace("+00:00", "Z"),
            "per_page": 100,
            "page": page,
        }

        if until:
            params["until"] = until.isoformat().replace("+00:00", "Z")

        try:
            items = request_json(
                f"{API}/repos/{OWNER}/{repository['name']}/commits",
                params,
            )
        except Exception:
            break

        if not items:
            break

        commits.extend(items)

        if len(items) < 100:
            break

        page += 1

    return commits


def fetch_public_commit_activity(
    repositories: list[dict],
) -> tuple[int, Counter, Counter, list[dict]]:
    """Calculate yearly commits and repository activity"""
    since = datetime.now(timezone.utc) - timedelta(days=365)
    counts = Counter()
    monthly = Counter()
    repository_activity = []

    for repository in repositories:
        commits = fetch_repository_commits(repository, since)
        repository_count = 0

        for item in commits:
            commit = item.get("commit", {})
            author = commit.get("author") or {}
            date = author.get("date")

            if not date:
                continue

            stamp = datetime.fromisoformat(date.replace("Z", "+00:00"))

            if stamp < since:
                continue

            day = stamp.date().isoformat()
            month = stamp.strftime("%Y-%m")
            counts[day] += 1
            monthly[month] += 1
            repository_count += 1

        repository_activity.append(
            {
                "name": repository["name"],
                "commits_last_365_days": repository_count,
                "updated_at": repository.get("updated_at"),
                "created_at": repository.get("created_at"),
                "stars": repository.get("stargazers_count", 0),
                "forks": repository.get("forks_count", 0),
                "language": repository.get("language") or "Mixed",
            }
        )

    return sum(counts.values()), counts, monthly, repository_activity


def fetch_search_count(query: str) -> int:
    """Fetch a GitHub search result count"""
    result = request_json(
        f"{API}/search/issues",
        {
            "q": query,
            "per_page": 1,
        },
    )

    return int(result.get("total_count", 0))


def fetch_monthly_event_counts(
    kind: str,
    months: int = 12,
) -> Counter:
    """Fetch monthly pull request or issue counts"""
    now = datetime.now(timezone.utc)
    result = Counter()

    for offset in range(months - 1, -1, -1):
        first = (now.replace(day=1) - timedelta(days=offset * 31)).replace(day=1)
        next_month = (
            first.replace(day=28) + timedelta(days=4)
        ).replace(day=1)
        month_key = first.strftime("%Y-%m")

        if kind == "pr":
            query_type = "pr"
        else:
            query_type = "issue"

        query = (
            f"type:{query_type} author:{OWNER} is:public "
            f"created:{first.date().isoformat()}.."
            f"{(next_month - timedelta(days=1)).date().isoformat()}"
        )

        try:
            result[month_key] = fetch_search_count(query)
        except Exception:
            result[month_key] = 0

    return result


def build_languages(repositories: list[dict]) -> Counter:
    """Count primary repository languages"""
    languages = Counter()

    for repository in repositories:
        language = repository.get("language")

        if language:
            languages[language] += 1

    return languages


def normalize_featured(repositories: list[dict]) -> list[dict]:
    """Select the strongest public projects for the dashboard"""
    by_name = {
        repository["name"].lower(): repository
        for repository in repositories
    }

    selected = []

    for name, description in FEATURED:
        repository = by_name.get(name.lower())

        if repository:
            item = dict(repository)
            item["dashboard_description"] = description
            selected.append(item)

    if len(selected) < 6:
        used = {repository["name"] for repository in selected}

        extras = sorted(
            [
                repository
                for repository in repositories
                if repository["name"] not in used
            ],
            key=lambda repository: (
                repository.get("stargazers_count", 0),
                repository.get("forks_count", 0),
                repository.get("updated_at", ""),
            ),
            reverse=True,
        )

        for repository in extras:
            if len(selected) >= 6:
                break

            item = dict(repository)
            item["dashboard_description"] = (
                repository.get("description")
                or "Public engineering project"
            )
            selected.append(item)

    return selected[:6]


def esc(value: str) -> str:
    """Escape text for SVG"""
    return html.escape(str(value), quote=True)


def short_number(value: int) -> str:
    """Format large numbers compactly"""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"

    if value >= 1_000:
        return f"{value / 1_000:.1f}K"

    return str(value)


def truncate(value: str, length: int) -> str:
    """Trim text to a fixed display width"""
    value = value.strip()

    if len(value) <= length:
        return value

    return value[: max(0, length - 1)].rstrip() + "…"


def svg_text(
    x: int,
    y: int,
    value: str,
    size: int,
    color: str,
    weight: int = 400,
    anchor: str = "start",
) -> str:
    """Render SVG text"""
    return (
        f'<text x="{x}" y="{y}" fill="{color}" '
        f'font-family="Inter,Segoe UI,Arial,sans-serif" '
        f'font-size="{size}px" font-weight="{weight}" '
        f'text-anchor="{anchor}">{esc(value)}</text>'
    )


def rounded_card(
    x: int,
    y: int,
    width: int,
    height: int,
    fill: str | None = None,
) -> str:
    """Render a dashboard card"""
    fill = fill or PALETTE["panel"]

    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" '
        f'rx="18" fill="{fill}" stroke="{PALETTE["border"]}" '
        'stroke-width="1"/>'
    )


def build_heatmap(
    counts: Counter,
    x: int,
    y: int,
    cell: int = 8,
    gap: int = 3,
) -> str:
    """Render a one-year contribution heatmap"""
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=364)
    start -= timedelta(days=(start.weekday() + 1) % 7)

    output = []
    maximum = max(counts.values(), default=1)
    day = start

    while day <= today:
        week = (day - start).days // 7
        weekday = (day.weekday() + 1) % 7
        count = counts.get(day.isoformat(), 0)
        ratio = count / maximum if maximum else 0

        if count == 0:
            fill = "#21262d"
        elif ratio < 0.25:
            fill = "#0e4429"
        elif ratio < 0.5:
            fill = "#006d32"
        elif ratio < 0.75:
            fill = "#26a641"
        else:
            fill = "#39d353"

        px = x + week * (cell + gap)
        py = y + weekday * (cell + gap)

        output.append(
            f'<rect x="{px}" y="{py}" width="{cell}" height="{cell}" '
            f'rx="2" fill="{fill}"/>'
        )

        day += timedelta(days=1)

    return "".join(output)


def build_monthly_chart(
    commits: Counter,
    prs: Counter,
    issues: Counter,
    x: int,
    y: int,
    width: int,
    height: int,
) -> str:
    """Render monthly activity bars"""
    months = sorted(set(commits) | set(prs) | set(issues))[-12:]
    maximum = max(
        [
            *(commits.get(month, 0) for month in months),
            *(prs.get(month, 0) for month in months),
            *(issues.get(month, 0) for month in months),
            1,
        ]
    )
    chart_bottom = y + height - 34
    chart_top = y + 24
    chart_height = chart_bottom - chart_top
    group_width = width / max(len(months), 1)
    output = []

    for index, month in enumerate(months):
        base_x = x + index * group_width
        values = [
            commits.get(month, 0),
            prs.get(month, 0),
            issues.get(month, 0),
        ]
        bar_width = max(4, (group_width - 18) / 3)
        gap = 3

        for value_index, value in enumerate(values):
            bar_height = 4 if value == 0 else max(
                4,
                int(chart_height * value / maximum),
            )
            bar_x = base_x + 6 + value_index * (bar_width + gap)
            bar_y = chart_bottom - bar_height
            palette_index = [
                PALETTE["accent"],
                PALETTE["purple"],
                PALETTE["orange"],
            ][value_index]

            output.append(
                f'<rect x="{bar_x:.1f}" y="{bar_y}" '
                f'width="{bar_width:.1f}" height="{bar_height}" '
                f'rx="3" fill="{palette_index}"/>'
            )

        output.append(
            svg_text(
                int(base_x + group_width / 2),
                chart_bottom + 20,
                month[5:],
                10,
                PALETTE["muted"],
                500,
                "middle",
            )
        )

    output.extend(
        [
            svg_text(x, y + 18, "COMMITS", 11, PALETTE["accent"], 700),
            svg_text(x + 72, y + 18, "PULL REQUESTS", 11, PALETTE["purple"], 700),
            svg_text(x + 177, y + 18, "ISSUES", 11, PALETTE["orange"], 700),
        ]
    )

    return "".join(output)


def build_repository_performance(
    repositories: list[dict],
    repository_activity: list[dict],
    x: int,
    y: int,
) -> str:
    """Render repository performance cards"""
    by_name = {
        item["name"]: item
        for item in repository_activity
    }

    ranked = []

    for repository in repositories:
        activity = by_name.get(repository["name"], {})
        ranked.append(
            {
                **repository,
                "recent_commits": activity.get("commits_last_365_days", 0),
            }
        )

    ranked = sorted(
        ranked,
        key=lambda item: (
            item["recent_commits"],
            item.get("stargazers_count", 0),
            item.get("updated_at", ""),
        ),
        reverse=True,
    )[:6]

    output = []
    positions = [
        (x, y),
        (x + 362, y),
        (x + 724, y),
        (x, y + 158),
        (x + 362, y + 158),
        (x + 724, y + 158),
    ]

    for repository, (card_x, card_y) in zip(ranked, positions):
        language = repository.get("language") or "Mixed"
        language_color = LANGUAGE_COLORS.get(
            language,
            PALETTE["accent"],
        )

        output.extend(
            [
                f'<rect x="{card_x}" y="{card_y}" width="326" height="136" '
                f'rx="16" fill="{PALETTE["panel2"]}" '
                f'stroke="{PALETTE["border"]}"/>',
                svg_text(
                    card_x + 20,
                    card_y + 29,
                    truncate(repository["name"], 29),
                    16,
                    PALETTE["text"],
                    750,
                ),
                f'<circle cx="{card_x + 25}" cy="{card_y + 54}" r="5" fill="{language_color}"/>',
                svg_text(
                    card_x + 38,
                    card_y + 59,
                    truncate(language, 18),
                    12,
                    PALETTE["muted"],
                    500,
                ),
                svg_text(
                    card_x + 20,
                    card_y + 90,
                    f'★ {repository.get("stargazers_count", 0)}',
                    12,
                    PALETTE["orange"],
                    700,
                ),
                svg_text(
                    card_x + 100,
                    card_y + 90,
                    f'⑂ {repository.get("forks_count", 0)}',
                    12,
                    PALETTE["purple"],
                    700,
                ),
                svg_text(
                    card_x + 180,
                    card_y + 90,
                    f'● {repository["recent_commits"]}',
                    12,
                    PALETTE["green"],
                    700,
                ),
                svg_text(
                    card_x + 20,
                    card_y + 116,
                    "commits · last 365 days",
                    11,
                    PALETTE["muted"],
                    400,
                ),
            ]
        )

    return "".join(output)


def build_ranked_list(
    repositories: list[dict],
    repository_activity: list[dict],
    mode: str,
    x: int,
    y: int,
) -> str:
    """Render a compact repository ranking"""
    by_name = {item["name"]: item for item in repository_activity}
    rows = []

    for repository in repositories:
        activity = by_name.get(repository["name"], {})
        rows.append(
            {
                "name": repository["name"],
                "stars": repository.get("stargazers_count", 0),
                "activity": activity.get("commits_last_365_days", 0),
            }
        )

    if mode == "stars":
        rows.sort(key=lambda item: (item["stars"], item["activity"]), reverse=True)
        title = "MOST STARRED"
        value_key = "stars"
        value_prefix = "★ "
        value_color = PALETTE["orange"]
    else:
        rows.sort(key=lambda item: (item["activity"], item["stars"]), reverse=True)
        title = "MOST ACTIVE"
        value_key = "activity"
        value_prefix = "● "
        value_color = PALETTE["green"]

    output = [
        svg_text(x, y, title, 12, PALETTE["muted"], 700),
    ]

    for index, row in enumerate(rows[:3], start=1):
        row_y = y + 30 + (index - 1) * 30
        output.extend(
            [
                svg_text(x, row_y, f"{index:02d}", 10, PALETTE["muted"], 700),
                svg_text(x + 28, row_y, truncate(row["name"], 24), 12, PALETTE["text"], 600),
                svg_text(x + 300, row_y, f'{value_prefix}{row[value_key]}', 11, value_color, 700, "end"),
            ]
        )

    return "".join(output)


def build_timeline(
    repositories: list[dict],
    x: int,
    y: int,
    width: int,
    height: int,
) -> str:
    """Render repository creation timeline"""
    if not repositories:
        return ""

    repos = sorted(
        repositories,
        key=lambda repository: repository.get("created_at") or "",
    )

    dates = []

    for repository in repos:
        created_at = repository.get("created_at")
        if created_at:
            dates.append(
                datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            )

    if not dates:
        return ""

    start = min(dates)
    end = max(dates)
    span = max((end - start).total_seconds(), 1)
    line_y = y + height // 2
    output = [
        f'<line x1="{x}" y1="{line_y}" x2="{x + width}" '
        f'y2="{line_y}" stroke="{PALETTE["border"]}" stroke-width="2"/>'
    ]

    for index, repository in enumerate(repos):
        created_at = repository.get("created_at")
        if not created_at:
            continue

        created = datetime.fromisoformat(
            created_at.replace("Z", "+00:00")
        )
        ratio = (created - start).total_seconds() / span
        px = x + int(ratio * width)
        direction = -1 if index % 2 == 0 else 1
        dot_y = line_y + direction * 20

        output.extend(
            [
                f'<line x1="{px}" y1="{line_y}" x2="{px}" '
                f'y2="{dot_y}" stroke="{PALETTE["border"]}" stroke-width="1"/>',
                f'<circle cx="{px}" cy="{dot_y}" r="6" '
                f'fill="{PALETTE["accent"]}"/>',
                svg_text(
                    px,
                    dot_y + (28 if direction > 0 else -12),
                    truncate(repository["name"], 18),
                    10,
                    PALETTE["text"],
                    600,
                    "middle",
                ),
                svg_text(
                    px,
                    dot_y + (42 if direction > 0 else -26),
                    created.strftime("%Y-%m"),
                    9,
                    PALETTE["muted"],
                    400,
                    "middle",
                ),
            ]
        )

    output.extend(
        [
            svg_text(x, y + height - 4, start.strftime("%Y"), 10, PALETTE["muted"], 500),
            svg_text(x + width, y + height - 4, end.strftime("%Y"), 10, PALETTE["muted"], 500, "end"),
        ]
    )

    return "".join(output)


def build_dashboard(
    user: dict,
    repositories: list[dict],
    commits: int,
    commit_days: Counter,
    monthly_commits: Counter,
    monthly_prs: Counter,
    monthly_issues: Counter,
    repository_activity: list[dict],
) -> str:
    """Build the complete dashboard SVG"""
    stars = sum(
        repository.get("stargazers_count", 0)
        for repository in repositories
    )

    forks = sum(
        repository.get("forks_count", 0)
        for repository in repositories
    )

    languages = build_languages(repositories)
    language_total = sum(languages.values()) or 1
    top_languages = languages.most_common(5)
    featured = normalize_featured(repositories)

    created = user.get("created_at", "")[:10]
    account_year = created[:4] if created else "—"

    width = 1200
    height = 2780

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{PALETTE["bg"]}"/>',
        "<defs>",
        '<linearGradient id="hero" x1="0" x2="1" y1="0" y2="1">',
        f'<stop offset="0%" stop-color="{PALETTE["accent2"]}" stop-opacity="0.22"/>',
        f'<stop offset="55%" stop-color="{PALETTE["purple"]}" stop-opacity="0.13"/>',
        f'<stop offset="100%" stop-color="{PALETTE["cyan"]}" stop-opacity="0.08"/>',
        "</linearGradient>",
        "</defs>",
        f'<rect x="24" y="24" width="1152" height="300" rx="28" fill="url(#hero)" stroke="{PALETTE["border"]}"/>',
        svg_text(64, 94, "YOUSIF WAEL", 38, PALETTE["text"], 800),
        svg_text(64, 136, "G-GLITCH404", 18, PALETTE["accent"], 700),
        svg_text(64, 188, "SOFTWARE DEVELOPER", 20, PALETTE["muted"], 700),
        svg_text(64, 222, "Python automation · Web data · Backend systems", 30, PALETTE["text"], 600),
        svg_text(64, 270, "Building crawlers, services, extraction pipelines and automation infrastructure", 18, PALETTE["muted"], 400),
        rounded_card(876, 70, 238, 174, PALETTE["panel2"]),
        svg_text(995, 105, "ENGINEERING", 13, PALETTE["muted"], 700, "middle"),
        svg_text(995, 142, "AUTOMATION", 21, PALETTE["text"], 800, "middle"),
        svg_text(995, 174, "DATA", 21, PALETTE["text"], 800, "middle"),
        svg_text(995, 206, "BACKEND", 21, PALETTE["text"], 800, "middle"),
        svg_text(995, 238, "SECURITY", 21, PALETTE["text"], 800, "middle"),
    ]

    stat_cards = [
        ("PUBLIC REPOS", len(repositories), PALETTE["accent"]),
        ("STARS", stars, PALETTE["orange"]),
        ("FORKS", forks, PALETTE["purple"]),
        ("FOLLOWERS", user.get("followers", 0), PALETTE["green"]),
    ]

    x = 24

    for label, value, accent in stat_cards:
        parts.extend(
            [
                rounded_card(x, 350, 270, 150),
                f'<rect x="{x}" y="350" width="5" height="150" rx="2" fill="{accent}"/>',
                svg_text(x + 24, 388, label, 13, PALETTE["muted"], 700),
                svg_text(x + 24, 448, short_number(int(value)), 40, PALETTE["text"], 800),
            ]
        )
        x += 290

    parts.extend(
        [
            rounded_card(24, 526, 750, 300),
            svg_text(52, 564, "PUBLIC ACTIVITY · LAST 365 DAYS", 15, PALETTE["muted"], 700),
            svg_text(52, 606, short_number(commits), 34, PALETTE["text"], 800),
            svg_text(52, 633, "authored commits in public repositories", 14, PALETTE["muted"], 400),
            build_heatmap(commit_days, 52, 678, 8, 3),
            svg_text(52, 806, "less", 11, PALETTE["muted"], 400),
            '<rect x="82" y="797" width="12" height="12" rx="2" fill="#21262d"/>',
            '<rect x="100" y="797" width="12" height="12" rx="2" fill="#0e4429"/>',
            '<rect x="118" y="797" width="12" height="12" rx="2" fill="#006d32"/>',
            '<rect x="136" y="797" width="12" height="12" rx="2" fill="#26a641"/>',
            '<rect x="154" y="797" width="12" height="12" rx="2" fill="#39d353"/>',
            svg_text(174, 806, "more", 11, PALETTE["muted"], 400),
            rounded_card(798, 526, 378, 300),
            svg_text(826, 564, "PRIMARY LANGUAGES", 15, PALETTE["muted"], 700),
        ]
    )

    language_y = 604

    for language, count in top_languages:
        percentage = count / language_total
        bar_width = int(265 * percentage)
        color = LANGUAGE_COLORS.get(language, PALETTE["accent"])

        parts.extend(
            [
                svg_text(826, language_y, language, 15, PALETTE["text"], 600),
                svg_text(1140, language_y, f"{percentage * 100:.0f}%", 14, PALETTE["muted"], 600, "end"),
                f'<rect x="826" y="{language_y + 12}" width="265" height="8" rx="4" fill="#21262d"/>',
                f'<rect x="826" y="{language_y + 12}" width="{max(6, bar_width)}" height="8" rx="4" fill="{color}"/>',
            ]
        )
        language_y += 42

    parts.extend(
        [
            rounded_card(24, 852, 1152, 280),
            svg_text(52, 890, "ENGINEERING FOCUS", 15, PALETTE["muted"], 700),
        ]
    )

    focus_left = FOCUS[:4]
    focus_right = FOCUS[4:]

    for index, (label, score) in enumerate(focus_left):
        y = 938 + index * 42
        parts.extend(
            [
                svg_text(52, y, label, 14, PALETTE["text"], 600),
                f'<rect x="220" y="{y - 11}" width="280" height="10" rx="5" fill="#21262d"/>',
                f'<rect x="220" y="{y - 11}" width="{int(280 * score / 100)}" height="10" rx="5" fill="{PALETTE["accent"]}"/>',
                svg_text(516, y, str(score), 13, PALETTE["muted"], 600),
            ]
        )

    for index, (label, score) in enumerate(focus_right):
        y = 938 + index * 42
        parts.extend(
            [
                svg_text(608, y, label, 14, PALETTE["text"], 600),
                f'<rect x="776" y="{y - 11}" width="280" height="10" rx="5" fill="#21262d"/>',
                f'<rect x="776" y="{y - 11}" width="{int(280 * score / 100)}" height="10" rx="5" fill="{PALETTE["purple"]}"/>',
                svg_text(1072, y, str(score), 13, PALETTE["muted"], 600),
            ]
        )

    parts.append(
        svg_text(52, 1106, f"Public profile since {account_year}", 13, PALETTE["muted"], 400)
    )

    parts.extend(
        [
            rounded_card(24, 1158, 1152, 490),
            svg_text(52, 1198, "FEATURED WORK", 15, PALETTE["muted"], 700),
        ]
    )

    positions = [
        (52, 1232),
        (414, 1232),
        (776, 1232),
        (52, 1410),
        (414, 1410),
        (776, 1410),
    ]

    for repository, (card_x, card_y) in zip(featured, positions):
        parts.extend(
            [
                f'<rect x="{card_x}" y="{card_y}" width="326" height="146" rx="16" fill="{PALETTE["panel2"]}" stroke="{PALETTE["border"]}"/>',
                svg_text(card_x + 20, card_y + 31, truncate(repository["name"], 28), 17, PALETTE["text"], 750),
                svg_text(card_x + 20, card_y + 59, truncate(repository.get("dashboard_description", ""), 38), 12, PALETTE["muted"], 400),
                svg_text(card_x + 20, card_y + 92, f'★ {repository.get("stargazers_count", 0)}', 12, PALETTE["orange"], 700),
                svg_text(card_x + 102, card_y + 92, f'⑂ {repository.get("forks_count", 0)}', 12, PALETTE["purple"], 700),
                svg_text(card_x + 20, card_y + 122, truncate(repository.get("language") or "Mixed stack", 24), 12, PALETTE["accent"], 600),
            ]
        )

    parts.extend(
        [
            rounded_card(24, 1670, 1152, 390),
            svg_text(52, 1710, "REPOSITORY PERFORMANCE", 15, PALETTE["muted"], 700),
            svg_text(52, 1737, "Ranked by public activity, then stars and recent updates", 12, PALETTE["muted"], 400),
            build_repository_performance(repositories, repository_activity, 52, 1762),
        ]
    )

    parts.extend(
        [
            rounded_card(24, 2090, 1152, 600),
            svg_text(52, 2130, "ACTIVITY", 15, PALETTE["muted"], 700),
            svg_text(52, 2157, "Commits, pull requests and issues over the last 12 months", 12, PALETTE["muted"], 400),
            build_monthly_chart(monthly_commits, monthly_prs, monthly_issues, 52, 2180, 690, 240),
            build_ranked_list(repositories, repository_activity, "active", 790, 2190),
            build_ranked_list(repositories, repository_activity, "stars", 790, 2318),
            svg_text(52, 2470, "REPOSITORY CREATION TIMELINE", 13, PALETTE["muted"], 700),
            build_timeline(repositories, 52, 2490, 1070, 150),
        ]
    )

    parts.extend(
        [
            svg_text(600, 2742, "github.com/G-Glitch404", 13, PALETTE["muted"], 500, "middle"),
            "</svg>",
        ]
    )

    return "".join(parts)


def main() -> None:
    """Generate the profile dashboard asset"""
    ASSETS.mkdir(parents=True, exist_ok=True)

    user = fetch_user()
    repositories = fetch_repositories()
    commits, commit_days, monthly_commits, repository_activity = fetch_public_commit_activity(repositories)
    monthly_prs = fetch_monthly_event_counts("pr", 12)
    monthly_issues = fetch_monthly_event_counts("issue", 12)

    dashboard = build_dashboard(
        user,
        repositories,
        commits,
        commit_days,
        monthly_commits,
        monthly_prs,
        monthly_issues,
        repository_activity,
    )

    (ASSETS / "dashboard.svg").write_text(
        dashboard,
        encoding="utf-8",
    )

    stars = sum(repository.get("stargazers_count", 0) for repository in repositories)
    forks = sum(repository.get("forks_count", 0) for repository in repositories)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "owner": OWNER,
        "public_repositories": len(repositories),
        "stars": stars,
        "forks": forks,
        "followers": user.get("followers", 0),
        "public_commits_last_365_days": commits,
        "pull_requests_last_12_months": sum(monthly_prs.values()),
        "issues_last_12_months": sum(monthly_issues.values()),
        "monthly_commits": dict(monthly_commits),
        "monthly_pull_requests": dict(monthly_prs),
        "monthly_issues": dict(monthly_issues),
        "repository_activity": sorted(
            repository_activity,
            key=lambda item: item["commits_last_365_days"],
            reverse=True,
        ),
        "most_starred_repositories": [
            repository["name"]
            for repository in sorted(
                repositories,
                key=lambda item: item.get("stargazers_count", 0),
                reverse=True,
            )[:6]
        ],
    }

    (ASSETS / "stats.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
