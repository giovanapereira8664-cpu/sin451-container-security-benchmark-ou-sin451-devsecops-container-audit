import os

print("uid do processo:", os.getuid())
print("DB_PASSWORD definida:", bool(os.environ.get("DB_PASSWORD")))
