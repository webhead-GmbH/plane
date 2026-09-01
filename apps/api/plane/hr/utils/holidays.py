# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Austria's public holidays.

An empty calendar is not a neutral starting point. Every statutory holiday would
be read as an ordinary working day, so each one would show as a full day's
shortfall against somebody who was not entitled to work it — thirteen days a
year, on the record, against people who were legally off.

The dates are computed rather than listed, because four of them move with Easter
and a hand-written table silently stops being true the year it runs out. The
fixed ones are named in one place; the moveable ones are offsets from Easter,
which is what they actually are.

Nine are fixed to a date and four follow Easter. Good Friday is deliberately not
among them: it stopped being a holiday for members of certain churches after the
2019 ruling, and is not a general public holiday in Austria.

Sources are the Arbeitsruhegesetz. Days granted by agreement rather than statute
— 24 and 31 December are the usual ones — are marked as such, because only a
statutory holiday carries the pay entitlement that goes with it.
"""

# Python imports
from datetime import date, timedelta
from decimal import Decimal

# (month, day, German name, English name)
FIXED = (
    (1, 1, "Neujahr", "New Year's Day"),
    (1, 6, "Heilige Drei Könige", "Epiphany"),
    (5, 1, "Staatsfeiertag", "State Holiday"),
    (8, 15, "Mariä Himmelfahrt", "Assumption of Mary"),
    (10, 26, "Nationalfeiertag", "National Day"),
    (11, 1, "Allerheiligen", "All Saints' Day"),
    (12, 8, "Mariä Empfängnis", "Immaculate Conception"),
    (12, 25, "Christtag", "Christmas Day"),
    (12, 26, "Stefanitag", "St Stephen's Day"),
)

# (days after Easter Sunday, German name, English name)
AFTER_EASTER = (
    (1, "Ostermontag", "Easter Monday"),
    (39, "Christi Himmelfahrt", "Ascension Day"),
    (50, "Pfingstmontag", "Whit Monday"),
    (60, "Fronleichnam", "Corpus Christi"),
)

# Not statutory, and so not automatic — but so commonly agreed that leaving them
# out means every company enters the same two rows by hand every year.
CUSTOMARY_HALF_DAYS = (
    (12, 24, "Heiliger Abend", "Christmas Eve"),
    (12, 31, "Silvester", "New Year's Eve"),
)


def easter_sunday(year):
    """Easter Sunday in the Gregorian calendar.

    The anonymous Gregorian computus. It is written out rather than taken from a
    library because the whole holiday calendar hangs off it, and a dependency for
    nine lines of arithmetic is a dependency to keep working for as long as the
    payroll records have to be readable.

    Undefined before the Gregorian reform, and it says so rather than returning a
    plausible date for a calendar that was not yet in use.
    """
    if year < 1583:
        raise ValueError("Gregorian Easter is undefined before the 1582 reform.")

    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    lunar = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lunar) // 451
    month, day = divmod(h + lunar - 7 * m + 114, 31)
    return date(year, month, day + 1)


def austrian_holidays(year, include_customary_half_days=True):
    """Every public holiday in one year, in date order.

    Returns ``(date, name_de, name_en, fraction, is_statutory)`` rows. The fraction
    exists for the customary half days; a statutory holiday is always whole.

    The fraction is a Decimal because it is stored as one. A float survives the
    round trip through that column intact, but it does not survive arithmetic: a
    row read back from the database multiplies as a Decimal while one still in
    memory multiplies as a float, and mixing the two raises. Matching the column's
    type at the source keeps both paths identical.
    """
    whole = Decimal("1")
    half = Decimal("0.5")
    days = [(date(year, month, day), de, en, whole, True) for month, day, de, en in FIXED]

    easter = easter_sunday(year)
    days += [(easter + timedelta(days=offset), de, en, whole, True) for offset, de, en in AFTER_EASTER]

    if include_customary_half_days:
        days += [(date(year, month, day), de, en, half, False) for month, day, de, en in CUSTOMARY_HALF_DAYS]

    return _merge_coincident(sorted(days, key=lambda row: row[0]))


def _merge_coincident(days):
    """Fold two holidays that fall on the same date into one day off.

    Ascension lands on the Staatsfeiertag whenever Easter is 23 March — 2008 was
    the last time, 2160 the next. Two holidays on one date is still one day away
    from work, and the calendar stores at most one row per date, so leaving them
    separate would abort the whole year's seeding on a unique-constraint error
    rather than produce anything visibly wrong.
    """
    merged = []
    for row in days:
        if merged and merged[-1][0] == row[0]:
            day, name_de, name_en, fraction, is_statutory = merged[-1]
            merged[-1] = (
                day,
                f"{name_de} / {row[1]}",
                f"{name_en} / {row[2]}",
                # A whole day owed under one name is not halved by the other.
                max(fraction, row[3]),
                is_statutory or row[4],
            )
            continue
        merged.append(row)
    return merged
