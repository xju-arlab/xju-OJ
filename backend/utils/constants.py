class Choices:
    @classmethod
    def choices(cls):
        d = cls.__dict__
        return [d[item] for item in d.keys() if not item.startswith("__")]


class ContestType:
    PUBLIC_CONTEST = "Public"
    PASSWORD_PROTECTED_CONTEST = "Password Protected"


class ContestStatus:
    CONTEST_NOT_START = "1"
    CONTEST_ENDED = "-1"
    CONTEST_UNDERWAY = "0"


class ContestRuleType(Choices):
    ACM = "ACM"
    OI = "OI"
    AI = "AI"


class ContestPrepState(Choices):
    """Marks a private contest preparation workspace; null means a normal contest.

    Problems are set in the workspace at any time; review rounds run beside it.
    """
    PREPARATION = "Preparation"


class ContestPrepRole(Choices):
    CREATOR = "Creator"
    # Sets, selects and tests problems; everything but roles, review rounds and publishing.
    ORGANIZER = "Organizer"


# A preparation invite link works once and only within this many days.
PREP_INVITE_DAYS = 7
# A preparation workspace has no contest window before it is published, so its
# row keeps a placeholder far enough that it never looks like a finished
# contest. Reviews have no time limit: a round runs until its creator ends it.
PREP_PLACEHOLDER_DAYS = 3650
# The suggested length of the real contest a preparation contest is published
# as, used when the publish call leaves the window out.
PUBLISH_DEFAULT_HOURS = 5


class CacheKey:
    waiting_queue = "waiting_queue"
    contest_rank_cache = "contest_rank_cache"
    prep_invite_failures = "prep_invite_failures"
    website_config = "website_config"


class Difficulty(Choices):
    LOW = "Low"
    MID = "Mid"
    HIGH = "High"


CONTEST_PASSWORD_SESSION_KEY = "contest_password"
