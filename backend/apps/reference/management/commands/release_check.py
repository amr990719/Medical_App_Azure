"""One-off job before traffic shifts: one line per check, exit 1 when any of them fails."""

from django.core.management.base import BaseCommand

from apps.reference.release_checks import FAIL, run_checks


class Command(BaseCommand):
    help = (
        "Prove the deployed configuration works: migrations, shared cache, fiscal year, fee "
        "schedule, reference data, Blob access and Entra discovery. Output holds no secret."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fiscal-year",
            type=int,
            default=None,
            help="Check this year's fee schedule (default: CURRENT_FISCAL_YEAR).",
        )
        parser.add_argument("--skip-blob", action="store_true")
        parser.add_argument(
            "--require-admin", action="store_true", help="Also need one active administrator."
        )

    def handle(self, *args, fiscal_year=None, skip_blob=False, require_admin=False, **options):
        results = run_checks(
            fiscal_year=fiscal_year, skip_blob=skip_blob, require_admin=require_admin
        )
        for result in results:
            self.stdout.write(
                f"release_check name={result.name} status={result.status} detail={result.detail}"
            )
        failed = any(result.status == FAIL for result in results)
        self.stdout.write(f"release_check result={'fail' if failed else 'ok'}")
        if failed:
            raise SystemExit(1)
