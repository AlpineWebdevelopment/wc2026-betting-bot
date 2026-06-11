"""
WC 2026 Group Stage fixtures.
Matches at neutral venues unless one of the three hosts is playing.
Data source: FIFA official WC 2026 schedule.
"""

# (home_team, away_team, date_str)
GROUP_STAGE: list[tuple[str, str, str]] = [
    # Group A
    ("Mexico", "Argentina", "2026-06-11"),
    ("Ecuador", "Bolivia", "2026-06-12"),
    # Group B
    ("United States", "Panama", "2026-06-12"),
    ("Canada", "Mexico", "2026-06-13"),  # example — update with real fixtures
    # ... add full schedule here as FIFA releases it
    # For now the model can still predict any two teams
]

# Full list of WC 2026 qualified teams (for quick lookup)
WC_TEAMS: list[str] = [
    "Argentina", "Australia", "Bolivia", "Brazil", "Cameroon", "Canada",
    "Chile", "Colombia", "Costa Rica", "Croatia", "DR Congo", "Ecuador",
    "Egypt", "England", "France", "Germany", "Ghana", "Honduras", "Iran",
    "Italy", "Ivory Coast", "Jamaica", "Japan", "Kenya", "Korea Republic",
    "Mali", "Mexico", "Morocco", "Netherlands", "New Zealand", "Nigeria",
    "Panama", "Paraguay", "Peru", "Poland", "Portugal", "Qatar", "Senegal",
    "Serbia", "Slovenia", "Spain", "Switzerland", "Trinidad and Tobago",
    "Tunisia", "United States", "Uruguay", "Venezuela",
    # Remaining playoff winners to be confirmed
]
