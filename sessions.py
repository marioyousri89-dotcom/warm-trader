"""The three trading sessions that move markets (all times UTC; Melbourne is UTC+10/+11).

  ASIA    Tokyo/Sydney/Hong Kong   00:00-07:00 UTC   usually quieter, ranges form
  LONDON  Europe opens             07:00-13:00 UTC   volume and direction arrive, Asia's range often breaks
  NY      US opens (overlaps London 13:00-16:00 UTC = most liquid) 13:00-21:00 UTC, trends continue or reverse, then fade
  LATE    21:00-24:00 UTC          thin, spreads widen
Crypto trades 24/7, but the same human rhythm shows in its volume and volatility. Whether it shows up as a TRADABLE edge
is something the agents have to measure (see the session_analyst improver), not something we assume.
"""
SESSIONS = ("asia", "london", "overlap", "ny", "late")


def session_of_hour(h):
    if h < 7:
        return "asia"
    if h < 13:
        return "london"
    if h < 16:
        return "overlap"
    if h < 21:
        return "ny"
    return "late"


def session_at(ts):
    return session_of_hour(int(ts // 3600) % 24)


def hour_of(ts):
    return (ts % 86400) / 3600.0


SIM_VOL = {"asia": 0.75, "london": 1.1, "overlap": 1.35, "ny": 1.05, "late": 0.8}   # synthetic market only
