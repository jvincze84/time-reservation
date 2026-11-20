"""Generate a password hash for config/users.json (so passwords are not stored in plain text).

Usage:  docker compose run --rm reservation python hashpw.py
"""
import getpass

from werkzeug.security import generate_password_hash

pw = getpass.getpass("Password: ")
if pw != getpass.getpass("Repeat password: "):
    raise SystemExit("Passwords do not match.")
print(generate_password_hash(pw))
