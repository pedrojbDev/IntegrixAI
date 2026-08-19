import unittest
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.core.security.ops import (
    OPS_CSRF_COOKIE_NAME,
    OPS_SESSION_COOKIE_NAME,
    OpsPrincipal,
    authenticate_user,
    authorize_tenant_scope,
    create_ops_session,
    enforce_login_rate_limit,
    hash_password,
    require_csrf,
    require_ops_principal,
    revoke_session,
    verify_password,
)
from app.db import Base
from app.models.ops_auth import OpsSession, OpsUser, OpsUserTenant


def request_with(*, cookies: dict[str, str] | None = None, headers: dict[str, str] | None = None):
    header_items = [
        (key.lower().encode(), value.encode())
        for key, value in (headers or {}).items()
    ]
    if cookies:
        header_items.append(
            (b"cookie", "; ".join(f"{key}={value}" for key, value in cookies.items()).encode())
        )
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "server": ("testserver", 443),
            "path": "/ops/session",
            "query_string": b"",
            "headers": header_items,
            "client": ("127.0.0.1", 12345),
        }
    )


class OpsAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        self.session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        self.settings = Settings(
            _env_file=None,
            database_url="sqlite://",
            ops_login_max_attempts=3,
        )

    def _user(self, session, *, role="tenant_user", tenants=("tenant_a",)):
        user = OpsUser(
            email="user@example.com",
            password_hash=hash_password("correct-password-123"),
            role=role,
            is_active=True,
            must_change_password=False,
        )
        session.add(user)
        session.flush()
        session.add_all(
            OpsUserTenant(user_id=user.id, tenant_id=tenant_id)
            for tenant_id in tenants
        )
        session.commit()
        session.refresh(user)
        return user

    def test_passwords_use_argon2id_and_verify(self) -> None:
        encoded = hash_password("correct-password-123")

        self.assertTrue(encoded.startswith("$argon2id$"))
        self.assertTrue(verify_password(encoded, "correct-password-123"))
        self.assertFalse(verify_password(encoded, "wrong-password"))

    def test_session_stores_only_hash_and_requires_csrf_for_mutation(self) -> None:
        with self.session_local() as session:
            user = self._user(session)
            response = Response()
            principal = create_ops_session(session, response, user, self.settings)
            session_cookie = next(
                value.split(";", 1)[0].split("=", 1)[1]
                for value in response.headers.getlist("set-cookie")
                if value.startswith(f"{OPS_SESSION_COOKIE_NAME}=")
            )
            csrf_cookie = next(
                value.split(";", 1)[0].split("=", 1)[1]
                for value in response.headers.getlist("set-cookie")
                if value.startswith(f"{OPS_CSRF_COOKIE_NAME}=")
            )
            stored = session.execute(select(OpsSession)).scalar_one()

            self.assertNotEqual(session_cookie, stored.token_hash)
            self.assertNotIn(session_cookie, stored.token_hash)
            loaded = require_ops_principal(
                request_with(cookies={OPS_SESSION_COOKIE_NAME: session_cookie}),
                self.settings,
                session,
            )
            accepted = require_csrf(
                request_with(
                    cookies={OPS_SESSION_COOKIE_NAME: session_cookie},
                    headers={"x-csrf-token": csrf_cookie, "origin": "https://testserver"},
                ),
                loaded,
            )
            self.assertEqual(principal.id, accepted.id)
            with self.assertRaises(HTTPException) as rejected:
                require_csrf(request_with(), loaded)
            self.assertEqual(403, rejected.exception.status_code)

            revoke_session(session, loaded)
            session.commit()
            with self.assertRaises(HTTPException) as revoked:
                require_ops_principal(
                    request_with(cookies={OPS_SESSION_COOKIE_NAME: session_cookie}),
                    self.settings,
                    session,
                )
            self.assertEqual(401, revoked.exception.status_code)

    def test_rate_limit_counts_failures_shared_in_database(self) -> None:
        with self.session_local() as session:
            self._user(session)
            request = request_with()
            for _ in range(3):
                with self.assertRaises(HTTPException) as invalid:
                    authenticate_user(
                        session,
                        request,
                        "user@example.com",
                        "incorrect-password",
                        self.settings,
                    )
                self.assertEqual(401, invalid.exception.status_code)

            with self.assertRaises(HTTPException) as blocked:
                enforce_login_rate_limit(
                    session,
                    request,
                    "user@example.com",
                    self.settings,
                )
            self.assertEqual(429, blocked.exception.status_code)

    def test_tenant_scope_fails_closed(self) -> None:
        tenant_user = OpsPrincipal(
            id="user",
            email="user@example.com",
            role="tenant_user",
            tenant_ids=("tenant_a", "tenant_b"),
            must_change_password=False,
            session_token_hash="session",
            csrf_hash="csrf",
        )
        admin = OpsPrincipal(
            id="admin",
            email="admin@example.com",
            role="platform_admin",
            tenant_ids=(),
            must_change_password=False,
            session_token_hash="session",
            csrf_hash="csrf",
        )

        self.assertEqual(
            "tenant_b",
            authorize_tenant_scope(tenant_user, "tenant_b", self.settings),
        )
        with self.assertRaises(HTTPException):
            authorize_tenant_scope(tenant_user, "tenant_c", self.settings)
        with self.assertRaises(HTTPException):
            authorize_tenant_scope(tenant_user, None, self.settings)
        with self.assertRaises(HTTPException):
            authorize_tenant_scope(admin, None, self.settings)
        self.assertIsNone(
            authorize_tenant_scope(
                admin,
                None,
                Settings(_env_file=None, ops_allow_global_queries=True),
            )
        )

    def test_expired_session_is_rejected(self) -> None:
        with self.session_local() as session:
            user = self._user(session)
            response = Response()
            principal = create_ops_session(session, response, user, self.settings)
            row = session.get(OpsSession, principal.session_token_hash)
            row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.commit()
            session_cookie = next(
                value.split(";", 1)[0].split("=", 1)[1]
                for value in response.headers.getlist("set-cookie")
                if value.startswith(f"{OPS_SESSION_COOKIE_NAME}=")
            )
            with self.assertRaises(HTTPException) as expired:
                require_ops_principal(
                    request_with(cookies={OPS_SESSION_COOKIE_NAME: session_cookie}),
                    self.settings,
                    session,
                )
            self.assertEqual(401, expired.exception.status_code)


if __name__ == "__main__":
    unittest.main()
