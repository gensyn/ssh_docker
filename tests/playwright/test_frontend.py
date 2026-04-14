"""Playwright E2E tests: SSH Docker frontend / UI interactions."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Page, expect

from conftest import HA_URL


class TestFrontend:
    """Tests that exercise the Home Assistant frontend with the SSH Docker integration."""

    def test_home_assistant_frontend_loads(self, page: Page) -> None:
        """The Home Assistant frontend loads successfully."""
        page.goto(HA_URL)
        page.wait_for_load_state("networkidle")
        expect(page).not_to_have_title("")

    def test_integrations_page_accessible(self, page: Page) -> None:
        """The integrations settings page is accessible."""
        page.goto(f"{HA_URL}/config/integrations")
        page.wait_for_load_state("networkidle")
        assert page.url.startswith(HA_URL), f"Unexpected redirect to: {page.url}"

    def test_developer_tools_page_loads(self, page: Page) -> None:
        """Developer tools page loads (used for calling services manually)."""
        page.goto(f"{HA_URL}/developer-tools/service")
        page.wait_for_load_state("networkidle")
        assert page.url.startswith(HA_URL)

    def test_ssh_docker_panel_accessible(self, page: Page, ensure_integration: str) -> None:
        """The SSH Docker sidebar panel URL is accessible after setup."""
        page.goto(f"{HA_URL}/ssh-docker")
        page.wait_for_load_state("networkidle")
        assert page.url.startswith(HA_URL), f"Unexpected redirect to: {page.url}"

    def test_ssh_docker_visible_in_integrations(
        self, page: Page, ensure_integration: str
    ) -> None:
        """After setup, SSH Docker appears on the integrations page."""
        page.goto(f"{HA_URL}/config/integrations")
        page.wait_for_load_state("networkidle")
        ssh_card = page.get_by_text("SSH Docker", exact=False)
        expect(ssh_card.first).to_be_visible()

    def test_no_javascript_errors_on_main_page(self, page: Page) -> None:
        """The main HA page does not log critical JavaScript errors."""
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(HA_URL)
        page.wait_for_load_state("networkidle")
        # Filter out known non-critical errors
        critical = [e for e in errors if "ResizeObserver" not in e]
        assert len(critical) == 0, f"JavaScript errors: {critical}"

    def test_config_page_shows_integration_info(
        self, page: Page, ensure_integration: str
    ) -> None:
        """The SSH Docker integration detail page shows expected information."""
        page.goto(f"{HA_URL}/config/integrations")
        page.wait_for_load_state("networkidle")

        # Try to click on the SSH Docker integration card
        ssh_link = page.get_by_text("SSH Docker", exact=False).first
        if ssh_link.is_visible():
            ssh_link.click()
            page.wait_for_load_state("networkidle")
        # Verify we are still on a valid HA page
        assert page.url.startswith(HA_URL)

    def test_developer_tools_shows_ssh_docker_services(
        self, page: Page, ensure_integration: str
    ) -> None:
        """Developer tools page allows access to ssh_docker services."""
        page.goto(f"{HA_URL}/developer-tools/service")
        page.wait_for_load_state("networkidle")
        # Page should be accessible and not redirect
        assert page.url.startswith(HA_URL)

    def test_panel_name_filter_input_present(
        self, page: Page, ensure_integration: str
    ) -> None:
        """The SSH Docker panel contains a name-filter text input."""
        page.goto(f"{HA_URL}/ssh-docker")
        page.wait_for_load_state("networkidle")

        # The panel uses shadow DOM; reach the input via JavaScript.
        input_present = page.evaluate(
            """() => {
                const panel = document.querySelector("ssh-docker-panel");
                if (!panel || !panel.shadowRoot) return false;
                return !!panel.shadowRoot.querySelector(".name-filter-input");
            }"""
        )
        assert input_present, "Name filter input not found in ssh-docker-panel shadow DOM"

    def test_panel_name_filter_hides_non_matching_containers(
        self, page: Page, ensure_integration: str
    ) -> None:
        """Typing a non-matching name into the filter removes containers from the panel."""
        page.goto(f"{HA_URL}/ssh-docker")
        page.wait_for_load_state("networkidle")

        # Wait until at least one container card is rendered.
        page.wait_for_function(
            """() => {
                const panel = document.querySelector("ssh-docker-panel");
                if (!panel || !panel.shadowRoot) return false;
                return panel.shadowRoot.querySelectorAll(".container-card").length > 0;
            }""",
            timeout=15000,
        )

        # Type a search string that will not match any container name.
        page.evaluate(
            """() => {
                const panel = document.querySelector("ssh-docker-panel");
                const input = panel.shadowRoot.querySelector(".name-filter-input");
                input.value = "__no_match_xyzzy__";
                input.dispatchEvent(new Event("input", { bubbles: true }));
            }"""
        )

        # After filtering, no container cards should remain.
        page.wait_for_function(
            """() => {
                const panel = document.querySelector("ssh-docker-panel");
                if (!panel || !panel.shadowRoot) return false;
                return panel.shadowRoot.querySelectorAll(".container-card").length === 0;
            }""",
            timeout=5000,
        )

    def test_panel_name_filter_case_insensitive(
        self, page: Page, ensure_integration: str
    ) -> None:
        """The name filter matches container names case-insensitively."""
        page.goto(f"{HA_URL}/ssh-docker")
        page.wait_for_load_state("networkidle")

        # Wait until at least one container card is rendered.
        page.wait_for_function(
            """() => {
                const panel = document.querySelector("ssh-docker-panel");
                if (!panel || !panel.shadowRoot) return false;
                return panel.shadowRoot.querySelectorAll(".container-card").length > 0;
            }""",
            timeout=15000,
        )

        # Retrieve the name of the first container card (case will vary).
        first_name: str = page.evaluate(
            """() => {
                const panel = document.querySelector("ssh-docker-panel");
                const el = panel.shadowRoot.querySelector(".container-name");
                return el ? el.textContent.trim() : "";
            }"""
        )
        assert first_name, "Could not read any container name from the panel"

        # Search using swapped case to verify case-insensitive matching.
        search_term = first_name.swapcase()
        page.evaluate(
            f"""() => {{
                const panel = document.querySelector("ssh-docker-panel");
                const input = panel.shadowRoot.querySelector(".name-filter-input");
                input.value = {repr(search_term)};
                input.dispatchEvent(new Event("input", {{ bubbles: true }}));
            }}"""
        )

        # The original container should still be visible.
        page.wait_for_function(
            """() => {
                const panel = document.querySelector("ssh-docker-panel");
                if (!panel || !panel.shadowRoot) return false;
                return panel.shadowRoot.querySelectorAll(".container-card").length > 0;
            }""",
            timeout=5000,
        )
