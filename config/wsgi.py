import os
import logging

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
application = get_wsgi_application()

logger = logging.getLogger("rate_limiter")

# Warm the Lua script cache at startup for the fast path. This is
# best-effort only — if Redis is unreachable at boot time, we must NOT
# crash the whole application. The repository already loads the script
# lazily on first real use (see redis_repository.py's _get_sha), so a
# failure here just means the first request pays a slightly higher
# latency cost instead of the app refusing to start entirely.
try:
    from rate_limiter.repositories.redis_repository import redis_rate_limit_repository
    redis_rate_limit_repository.load_script()
except Exception:
    logger.warning(
        "Could not warm Lua script cache at startup (Redis may be unavailable) — "
        "will load lazily on first request instead.",
        exc_info=True,
    )