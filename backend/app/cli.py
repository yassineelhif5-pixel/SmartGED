"""Operational CLI.

    python -m app.cli bootstrap
    python -m app.cli create-tenant --name "Acme" --slug acme --admin-email a@acme.com --admin-password '...'
    python -m app.cli reprocess --tenant-slug acme --all-failed
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.database.session import session_scope
from app.models import Document, DocumentStatus, Tenant
from app.services import tenant_service
from app.services.bootstrap import bootstrap


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="documind")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("bootstrap", help="Sync permissions, plans, default settings and bootstrap Super Admin")

    ct = sub.add_parser("create-tenant", help="Provision a tenant")
    ct.add_argument("--name", required=True)
    ct.add_argument("--slug", required=True)
    ct.add_argument("--plan", default="business")
    ct.add_argument("--admin-email", required=True)
    ct.add_argument("--admin-name", default="Administrator")
    ct.add_argument("--admin-password")

    rp = sub.add_parser("reprocess", help="Re-queue documents in the pipeline")
    rp.add_argument("--tenant-slug", required=True)
    rp.add_argument("--all-failed", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "bootstrap":
        bootstrap()
        print("Bootstrap complete")
    elif args.cmd == "create-tenant":
        bootstrap()
        with session_scope(bypass_rls=True) as db:
            res = tenant_service.provision_tenant(
                db, name=args.name, slug=args.slug, plan_code=args.plan, admin_email=args.admin_email,
                admin_full_name=args.admin_name, admin_password=args.admin_password)
            print(f"Tenant {res.tenant.slug} ({res.tenant.id}) created, admin {res.admin.email}")
    elif args.cmd == "reprocess":
        from app.workers.celery_app import enqueue_processing

        with session_scope(bypass_rls=True) as db:
            tenant = db.scalar(select(Tenant).where(Tenant.slug == args.tenant_slug))
            if tenant is None:
                print("Unknown tenant", file=sys.stderr)
                return 1
            stmt = select(Document.id).where(Document.tenant_id == tenant.id, Document.deleted_at.is_(None))
            if args.all_failed:
                stmt = stmt.where(Document.status == DocumentStatus.failed)
            ids = list(db.scalars(stmt))
        for doc_id in ids:
            enqueue_processing(tenant.id, doc_id, force=True)
        print(f"{len(ids)} document(s) queued")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
