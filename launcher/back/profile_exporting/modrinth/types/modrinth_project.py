from dataclasses import dataclass
from enum import StrEnum


class ClientServerSupport(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class Status(StrEnum):
    APPROVED = "approved"
    ARCHIVED = "archived"
    UNLISTED = "unlisted"
    PRIVATE = "private"
    DRAFT = "draft"
    REJECTED = "rejected"
    PROCESSING = "processing"
    WITHHELD = "withheld"
    SCHEDULED = "scheduled"
    UNKNOWN = "unknown"


class RequestedStatus(StrEnum):
    APPROVED = Status.APPROVED
    ARCHIVED = Status.ARCHIVED
    UNLISTED = Status.UNLISTED
    PRIVATE = Status.PRIVATE
    DRAFT = Status.DRAFT


class ProjectType(StrEnum):
    MOD = "mod"
    MODPACK = "modpack"
    RESOURCEPACK = "resourcepack"
    SHADER = "shader"

    SHADERPACK = SHADER
    """Alias for `SHADER`"""


class MonetizationStatus(StrEnum):
    MONETIZED = "monetized"
    DEMONETIZED = "demonetized"
    FORCE_DEMONETIZED = "force-demonetized"


@dataclass
class ModrinthProject:
    slug: str
    title: str
    description: str
    categories: list[str]
    client_side: ClientServerSupport
    server_side: ClientServerSupport
    body: str
    status: Status
    requested_status: RequestedStatus
    additional_categories: list[str]
    issues_url: str | None
    source_url: str | None
    wiki_url: str | None
    discord_url: str | None
    donation_urls: list[dict]
    project_type: ProjectType
    downloads: int
    icon_url: str | None
    color: int
    thread_id: str
    monetization_status: MonetizationStatus
    id: str
    team: str
    body_url: str | None
    moderator_message: dict[str, str | None]
    published: str
    """ISO-8601"""
    updated: str
    """ISO-8601"""
    approved: str
    """ISO-8601"""
    queued: str
    """ISO-8601"""
    followers: int
    license: dict[str, str | None]
    versions: list[str]
    game_versions: list[str]
    loaders: list[str]
    gallery: list[dict[str, str | bool | int | None]]
