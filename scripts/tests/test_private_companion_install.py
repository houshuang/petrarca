"""Static safety checks for the root-only Companion nginx installer."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
INSTALLER = SCRIPTS_DIR / "install-private-companion.sh"
TEMPLATE = SCRIPTS_DIR / "nginx-petrarca-companion.conf.template"


class PrivateCompanionInstallerTests(unittest.TestCase):
    def test_shell_syntax(self):
        subprocess.run(["bash", "-n", str(INSTALLER)], check=True)

    def test_secret_and_rollback_invariants_are_present(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('require_private_root_file "$CAPABILITY_FILE"', source)
        self.assertIn('require_private_root_file "$COMPANION_ENV_FILE"', source)
        self.assertIn("SONIOX_API_KEY", source)
        self.assertIn("PETRARCA_RESURFACING_KEY", source)
        self.assertIn("must contain only its two required assignments", source)
        self.assertIn("20-companion-env.conf", source)
        self.assertIn("EnvironmentFile=", source)
        self.assertIn("restore_prior_service", source)
        self.assertIn("restore_prior_nginx", source)
        self.assertIn("rollback_transaction", source)
        self.assertIn('if ! nginx -t >"$ROLLBACK_DIR/nginx-test.log"', source)
        self.assertIn("if ! systemctl reload nginx", source)
        self.assertNotIn('sed "s/__CAPABILITY_PATH__/$CAPABILITY', source)

    def test_backend_is_restarted_and_verified_before_nginx_is_exposed(self):
        source = INSTALLER.read_text(encoding="utf-8")
        restart = source.index('systemctl restart "$SERVICE"')
        verify = source.index("if verify_companion_service", restart)
        expose = source.index('mv -f -- "$TMP_SNIPPET" "$SNIPPET"', verify)
        reload_nginx = source.index("systemctl reload nginx", expose)
        self.assertLess(restart, verify)
        self.assertLess(verify, expose)
        self.assertLess(expose, reload_nginx)

        verify_source = source[source.index("verify_companion_service()") : expose]
        self.assertIn('/proc/{sys.argv[1]}/environ', verify_source)
        self.assertIn('required = (b"SONIOX_API_KEY", b"PETRARCA_RESURFACING_KEY")', verify_source)
        self.assertNotIn("systemctl show-environment", verify_source)

    def test_failed_transaction_restores_both_config_layers(self):
        source = INSTALLER.read_text(encoding="utf-8")
        rollback_start = source.index("rollback_transaction()")
        rollback = source[rollback_start : source.index("\ncleanup()", rollback_start)]
        self.assertIn("restore_prior_nginx", rollback)
        self.assertIn("restore_prior_service", rollback)
        self.assertIn("TRANSACTION_ACTIVE", source)
        self.assertIn("trap cleanup EXIT", source)

    def test_template_has_only_explicit_private_routes_and_closed_fallback(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("__CAPABILITY_PATH__", template)
        self.assertIn("location ^~ /__CAPABILITY_PATH__/", template)
        self.assertIn("return 404;", template)
        for block in template.split("location ")[1:]:
            self.assertIn("access_log off;", block)
            self.assertIn("error_log /dev/null crit;", block)


if __name__ == "__main__":
    unittest.main()
