"""Team accounts generated for one contest from a roster.

A team account belongs to exactly one contest, is registered for it on
creation and signs in with a password, never through SSO. It is not an OJ
account in its own right: user lists and rankings leave it out.
"""
import secrets
import string

from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.db.models.functions import Lower

from account.models import User, UserProfile
from utils.api import APIError
from utils.constants import ContestRuleType
from utils.shortcuts import datetime2str
from .models import ACMContestRank, ContestParticipation, ContestTeam, OIContestRank

# Usernames are team- plus four letters; passwords are read off paper, so
# characters that look alike are left out.
PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
# Generated passwords carry about 46 random bits, so a light hash keeps a
# roster of hundreds fast; Django rehashes with its default cost on first login.
PASSWORD_ITERATIONS = 20000


def team_password():
    while True:
        password = "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(8))
        if any(char.isdigit() for char in password) and any(char.isalpha() for char in password):
            return password


def hash_team_password(password):
    hasher = PBKDF2PasswordHasher()
    return hasher.encode(password, hasher.salt(), iterations=PASSWORD_ITERATIONS)


def team_usernames(count):
    names = set()
    while len(names) < count:
        batch = {"team-" + "".join(secrets.choice(string.ascii_lowercase) for _ in range(4))
                 for _ in range(count - len(names))} - names
        taken = set(User.objects.annotate(lower=Lower("username")).filter(lower__in=batch)
                    .values_list("lower", flat=True))
        names |= batch - taken
    return sorted(names)


def team_real_name(name, members):
    """A team account's real name is its member list, so 实名 views show the people."""
    return ",".join(members) or name


def team_data(team):
    return {"id": team.id, "name": team.name, "members": team.members, "username": team.user.username,
            "user_id": team.user_id, "create_time": datetime2str(team.create_time)}


def create_teams(contest, roster):
    """Create and register one account per roster row; returns them with their plaintext passwords.

    Call inside a transaction. Plaintext passwords exist only in this result.
    """
    roster = [{"name": item["name"].strip(),
               "members": [member.strip() for member in item["members"] if member.strip()]}
              for item in roster]
    names = [item["name"] for item in roster]
    if not all(names):
        raise APIError("Every team needs a name")
    duplicated = sorted({name for name in names if names.count(name) > 1} |
                        set(ContestTeam.objects.filter(contest=contest, name__in=names)
                            .values_list("name", flat=True)))
    if duplicated:
        raise APIError(f"Duplicate team names: {', '.join(duplicated[:5])}")

    created = []
    for item, username in zip(roster, team_usernames(len(roster))):
        password = team_password()
        user = User.objects.create(username=username, password=hash_team_password(password))
        UserProfile.objects.create(user=user, real_name=team_real_name(item["name"], item["members"]))
        team = ContestTeam.objects.create(contest=contest, user=user, **item)
        ContestParticipation.objects.create(contest=contest, user=user)
        if contest.rule_type == ContestRuleType.ACM:
            ACMContestRank.objects.create(contest=contest, user=user)
        elif contest.rule_type == ContestRuleType.OI:
            OIContestRank.objects.create(contest=contest, user=user)
        created.append(dict(team_data(team), password=password))
    return created
