import asyncio
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.ops_admin import (
    create_ops_user,
    reset_ops_user_password,
    update_ops_user,
)
from app.core.security.ops import OpsPrincipal, hash_password
from app.db import Base
from app.models.ops_auth import OpsUser
from app.schemas.ops_auth import OpsUserCreate, OpsUserUpdate


class OpsAdminTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        self.session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def _admin(self, session):
        user = OpsUser(
            email="admin@example.com",
            password_hash=hash_password("admin-password-123"),
            role="platform_admin",
            is_active=True,
            must_change_password=False,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user, OpsPrincipal(
            id=user.id,
            email=user.email,
            role=user.role,
            tenant_ids=(),
            must_change_password=False,
            session_token_hash="session",
            csrf_hash="csrf",
        )

    def test_create_client_requires_membership_and_returns_one_time_password(self) -> None:
        with self.session_local() as session:
            _, principal = self._admin(session)
            result = asyncio.run(
                create_ops_user(
                    OpsUserCreate(
                        email="client@example.com",
                        role="tenant_user",
                        tenant_ids=["tenant_b", "tenant_a"],
                    ),
                    principal,
                    session,
                )
            )

        self.assertTrue(result["temporary_password"])
        self.assertEqual(
            ["tenant_a", "tenant_b"],
            result["user"]["tenant_ids"],
        )

    def test_last_admin_cannot_disable_or_demote_self(self) -> None:
        with self.session_local() as session:
            user, principal = self._admin(session)
            with self.assertRaises(HTTPException) as disabled:
                asyncio.run(
                    update_ops_user(
                        user.id,
                        OpsUserUpdate(is_active=False),
                        principal,
                        session,
                    )
                )
            with self.assertRaises(HTTPException) as demoted:
                asyncio.run(
                    update_ops_user(
                        user.id,
                        OpsUserUpdate(role="tenant_user", tenant_ids=["tenant_a"]),
                        principal,
                        session,
                    )
                )

        self.assertEqual(400, disabled.exception.status_code)
        self.assertEqual(400, demoted.exception.status_code)

    def test_reset_password_marks_change_required(self) -> None:
        with self.session_local() as session:
            _, principal = self._admin(session)
            created = asyncio.run(
                create_ops_user(
                    OpsUserCreate(
                        email="client@example.com",
                        role="tenant_user",
                        tenant_ids=["tenant_a"],
                    ),
                    principal,
                    session,
                )
            )
            user_id = created["user"]["id"]
            reset = asyncio.run(
                reset_ops_user_password(user_id, principal, session)
            )
            user = session.get(OpsUser, user_id)

        self.assertTrue(reset["temporary_password"])
        self.assertTrue(user.must_change_password)


if __name__ == "__main__":
    unittest.main()
