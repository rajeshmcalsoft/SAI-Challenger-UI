"""Where the UI finds things. Every path can be changed with an environment variable.

The UI reads the SAI-Challenger checkout (tests, profiles, reports). The only thing it adds there is what
run_poc.sh itself writes when the UI starts a run (the report files). UI-only facts live in the UI's own
config folder, and run records and console logs in its state folder.
"""
import os
import pwd
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_FACTS = Path(__file__).resolve().parent / "target_facts.toml"


@dataclass(frozen=True)
class Settings:
    sc_root: Path  # the SAI-Challenger checkout run_poc.sh lives in
    lock_dir: Path  # run_poc.sh's flock files (hardcoded there as /opt/sai-poc/locks)
    config_dir: Path  # the UI's own files
    mode: str = "local"
    facts: dict = field(default_factory=dict)
    state_dir: Path | None = None  # run records and console logs of UI runs (default <config_dir>/state)
    user: str = field(default_factory=lambda: pwd.getpwuid(os.getuid()).pw_name)  # as whoami: the poc_<user> mount

    def __post_init__(self):
        if self.state_dir is None:
            object.__setattr__(self, "state_dir", Path(self.config_dir) / "state")

    @property
    def poc_dir(self):
        return self.sc_root / "tests" / "poc"

    @property
    def targets_dir(self):
        return self.poc_dir / "targets"

    @property
    def reports_dir(self):
        return self.poc_dir / "reports"

    def forwards_traffic(self, profile):
        """The profile key wins once it exists; until then the UI's own target_facts.toml."""
        if profile.forwards_traffic is not None:
            return profile.forwards_traffic, "profile"
        value = self.facts.get(profile.name, {}).get("forwards_traffic")
        if isinstance(value, bool):
            return value, "ui"
        return None, "unknown"


def load():
    home = Path.home()
    config_dir = Path(os.environ.get("SAI_CHALLENGER_UI_CONFIG", home / ".config" / "sai-challenger-ui"))
    facts = {}
    for path in (_DEFAULT_FACTS, config_dir / "target_facts.toml"):  # the user's file overrides the default
        if path.is_file():
            with open(path, "rb") as f:
                for name, values in tomllib.load(f).items():
                    facts.setdefault(name, {}).update(values)
    return Settings(
        sc_root=Path(os.environ.get("SAI_CHALLENGER_UI_SC_ROOT", home / "SAI-Challenger")).expanduser(),
        lock_dir=Path(os.environ.get("SAI_CHALLENGER_UI_LOCK_DIR", "/opt/sai-poc/locks")),
        config_dir=config_dir,
        mode=os.environ.get("SAI_CHALLENGER_UI_MODE", "local"),
        facts=facts,
        state_dir=Path(os.environ.get("SAI_CHALLENGER_UI_STATE", home / ".local" / "state" / "sai-challenger-ui")),
    )
