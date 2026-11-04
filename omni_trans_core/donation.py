from dataclasses import dataclass


@dataclass(frozen=True)
class DonationTarget:
    name: str
    url: str
    message: str


@dataclass(frozen=True)
class DonationConfig:
    app: DonationTarget | None = None
    core: DonationTarget | None = None


CORE_DONATION = DonationTarget(
    name="Omni Trans Core",
    url="https://nerkun.donatik.ua/",
    message=(
        "Omni Trans Core is free and open source. "
        "If it helps you, you can support its development."
    ),
)


def resolve_donation_config(config: DonationConfig | None) -> DonationConfig:
    if config is None:
        return DonationConfig(core=CORE_DONATION)
    return DonationConfig(app=config.app, core=config.core or CORE_DONATION)
